import json
import time
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser #https://docs.python.org/3/library/urllib.robotparser.html
from playwright.async_api import async_playwright
import asyncio
import re
from ai_prompts import PROMPTS, agent
import keywords as k
from loguru import logger
import httpx
import feedparser
#aszncio crawler
#https://gist.github.com/justynroberts/996118684a5de2cf9d305e217c3bd1e4

#to fix:
#nekozistentny pocet stranok -> too many requesst error
# pred regexom filtorvat iba viditelny text
# zjednodusit citanie z Axe-core vystupu
# header a footer sa checkene az ke sa najde odkaz
# kucove slova mozu odkazovat na dropdown menu
#https://loguru.readthedocs.io/en/stable/api/logger.html
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    level="DEBUG",
    format="<green>{time:HH:mm:ss}</green> - <level>{level:<8}</level> - {message}",
    colorize=True, )




class Scraper:
    MAX_DEPTH = 2
    MAX_PAGES_AT_ONCE = 10
    def __init__(self, start_url):
        self.robots_txt = RobotFileParser()
        self.queue_lock = asyncio.Lock()
        self.counter_lock = asyncio.Lock()
        self.search_lock = asyncio.Lock()

        self.page_counter = 0
        self.fail_counter = 0
        
        # normalizacia main stranky domeny
        parsed = urlparse(start_url)
        netloc = parsed.netloc
        if not netloc.startswith("www."):
            netloc = "www." + netloc
        self.start_url = f"{parsed.scheme}://{netloc}/"

        self.type_of_keyword = {
            "gdpr": k.gdpr_kw, "spravca": k.spravca_kw,
            "tabula": k.tabule_kw, "vyhlaseniePristupnost": k.pristupnost_kw,
            "rss": k.rss_kw, "prevadzkovatel": k.prevadzkovatel_kw, 
            "kontakt": k.kontakt_kw, "mapa_stranky": k.mapa_stranky_kw,
            "obstaravanie": k.obstaravanie_kw
        }
        
        self.search_state = {key: {"found": False, "searching": False} for key in self.type_of_keyword}
        self.depth_of_found_element ={key: None for key in self.type_of_keyword}
        self.found_text_keywords = {key: [] for key in self.type_of_keyword}
        self.content_scores = {key: None for key in self.type_of_keyword}

        self.visitedpages = set()
        self.page_report_final = {}
        self.admitted_rule_breaks = set()
        self.found_spravca= ""
        

        self.semaphore = None


        self.subdomain_counter = {}
        self.seen_subdomain_links = set()
        self.max_pages_per_subdomain = 20

    async def start(self):
    
        time_start = time.time()
        self.semaphore = asyncio.Semaphore(self.MAX_PAGES_AT_ONCE)
        self.load_robots_txt()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            queue = [(self.start_url, 0)]

            while queue:
                tasks_list = []
                while queue and len(tasks_list) < self.MAX_PAGES_AT_ONCE:
                    url, curr_depth = queue.pop(0)
                    scrape_result = self.scrape_curr_page(url, curr_depth, queue, browser)
                    tasks_list.append(scrape_result)
                await asyncio.gather(*tasks_list)
            await browser.close()

        self.save_json()
        logger.success(f"SUBDOMAIN COUNTER: {self.subdomain_counter}")
        logger.success(f"Searched {self.start_url} for {int(time.time() - time_start)} seconds")
        logger.success(f"VISITED {len(self.visitedpages)}, FAILED {self.fail_counter}")

    def load_robots_txt(self):
        robots_url= f"{self.start_url}robots.txt"
        headers ={"user-agent":"Mozilla/5.0"}
        #https://www.python-httpx.org/advanced/clients/
        with httpx.Client(headers=headers, follow_redirects=True) as usrClient:
            response = usrClient.get(robots_url)
            self.robots_txt.set_url(robots_url)
            self.robots_txt.parse(response.text.splitlines())

    async def scrape_curr_page(self, url, curr_depth, queue, browser):
        # otvori stranku -> zavola hladanie klucovych slov
        # -> zavola kontrolu WCAG -> pozbiera linky na stranke
        async with self.semaphore:
            async with self.queue_lock:
                if url in self.visitedpages:
                    return
                self.visitedpages.add(url)

            if not self.is_robots_allowed(url):
                return
            
            async with self.counter_lock:
                self.page_counter += 1
                
                if self.page_counter >= 100:
                    do_wcag_check = False
                else:
                    do_wcag_check = True
                logger.debug(f"page_counter={self.page_counter} do_wcag_check={do_wcag_check}")
            logger.info(f"ON PAGE: {url} (depth {curr_depth}) {self.page_counter}")

            # otovrenie stranky
            page = await browser.new_page()
            try:
                if self.is_robots_allowed(url):
                    await page.goto(url, wait_until="domcontentloaded")
            except Exception as e:
                logger.warning(f"Failed to open {url}: {e}")
                async with self.counter_lock:
                    self.fail_counter +=1
                await page.close()
                return

            await self.keyword_search(browser, url, page, curr_depth)

            if do_wcag_check and urlparse(url).netloc.removeprefix("www.") == urlparse(self.start_url).netloc.removeprefix("www."):
                await self.check_wcag(page, url)

            if curr_depth < self.MAX_DEPTH:
                await self.get_all_links( page, url, curr_depth, queue)

            await page.close()

    async def keyword_search(self, browser, url, page, curr_depth):
        for word_type in self.type_of_keyword.keys():
            if word_type in ["spravca", "prevadzkovatel"]:

                if  urlparse(url).netloc.removeprefix("www.") == urlparse(self.start_url).netloc.removeprefix("www.") and curr_depth == 0:
                    await self.main_page_content_search(browser, word_type, url, page, curr_depth)
            else:
                await self.page_content_search(browser, word_type, url, page, curr_depth)

    async def get_all_links(self, page, url, curr_depth, queue):
        #hlada vsetky linky na aktualnej stranke, kontroluje ci patria dodomeny
        # alebo subdomeny a prida ich do queue
        # a[href] 
        links = await page.locator("a").evaluate_all("x => x.map(y => y.href)")
        main_domain_netloc = urlparse(self.start_url).netloc.removeprefix("www.")
        added = 0
        async with self.queue_lock:
            for link in links:
                link_parts = urlparse(link)
                current_netloc = link_parts.netloc.removeprefix("www.")

                # pridavaju sa linky len z hlavnej domeny a subdomeny (az do self.max_pages_per_subdomain)
                if self.check_if_skip_link(link, main_domain_netloc, current_netloc):
                    continue
                if current_netloc !=main_domain_netloc:
                    if link in self.seen_subdomain_links:
                        continue
                    subdomain_count = self.subdomain_counter.get(current_netloc, 0)
                    if subdomain_count >= self.max_pages_per_subdomain:
                        continue
                    self.subdomain_counter[current_netloc] = subdomain_count + 1
                    self.seen_subdomain_links.add(link)
                added += 1
                queue.append((link, curr_depth + 1))
            #logger.debug(f"ADDED {added} links to queue from {url}")

    def save_json(self):
        # ulozi vysledky testu do json suboru
        data = {
            "wcag_type_count": len(self.page_report_final),
            "rules": self.page_report_final,
            "links": self.found_text_keywords,
            "admitted_rule_breaks": list(self.admitted_rule_breaks),
            "spravca": self.found_spravca,
        }
        with open("end_report.json", "w", encoding="utf-8") as subor:
            json.dump(data, subor, indent= 2)
        logger.info("Saved end_report.json")


    async def main_page_content_search(self, browser, search_type, current_url, current_page, depth):
        # sprostredkuje hladanie klucovych slov (keywords) na 
        # hlavnej stranke, hladame spravcu a prevadzkovatela
        text = ""
        result = await self.general_find(search_type, browser, current_url, current_page, depth)
        
        if not result:
            found_url= current_url
        else:
            text, found_url = result

        text += await self.get_page_header_footer_text(browser)
        check_result = await self.check_content(text,found_url,search_type)
        #self.found_spravca = check_result

    async def page_content_search(self, browser, search_type, current_url, current_page, depth):
        # sprostredkuje hladanie klucovych slov (keywords) na stranke
        text = ""
        result = await self.general_find(search_type, browser, current_url, current_page, depth)
        
        if not result:
            return
        else:
            text, found_url = result

       
        if search_type == "gdpr":
            await self.check_content(text,found_url, search_type)

        if search_type == "tabula":
            await self.check_content(text,found_url, search_type)
        
        if search_type == "vyhlaseniePristupnost":
            # treba to zlepit ako predtym
            regex1= r"\b[1-4]\.[1-9]\.[1-9]\.?(?!\s*\d{4})\b|\b[1-4]\.[1-9]\.?(?!\.\s*\d{4}|\s*\d{4})\b"
            
            matches = re.findall(regex1, text)
            #matches2 = re.findall(regex2, text)
            #matches = set(matches1 + matches2)
            self.admitted_rule_breaks.update(matches)
            self.accessibility_url = current_url
            logger.debug(f"AMDITTED RULE BREAKS { self.admitted_rule_breaks}")

        if search_type == "rss":
            #kontroluje validitu rss kanalu
            headers ={"user-agent":"Mozilla/5.0"}
            with httpx.Client(headers=headers, follow_redirects=True) as usrClient:
                response = usrClient.get(found_url)
                content_type = response.headers.get("content-type", "")
                
                if "xml" in content_type or "rss" in content_type:
                    feed = feedparser.parse(response.text)
                    if not feed.bozo and len(feed.entries) > 0:
                        logger.success(f"VALID RSS: {found_url}")
                else:
                    if self.is_robots_allowed(found_url):
                        rss_page = await browser.new_page()
                        try:
                            await rss_page.goto(found_url, wait_until="networkidle")
                            links = await rss_page.locator("a[href*='rss'], a[href*='feed'], a[href*='atom']").evaluate_all("x => x.map(y => y.href)")
                            rss_links = [url for url in links if not url.endswith(".html")]
                            #logger.debug(f"ALL RSS links: {rss_links}")
                            for rss_url in rss_links:
                                
                                response = usrClient.get(rss_url)
                                content_type = response.headers.get("content-type", "")
                                if "xml" not in content_type and "rss" not in content_type:
                                    continue
                                feed = feedparser.parse(response.text)
                                if not feed.bozo and len(feed.entries) >0:
                                    logger.success(f"VALID RSS: {rss_url}")
                                else:
                                    logger.warning(f"NON-VALID RSS: {rss_url}")
                        finally:
                            await rss_page.close()
                    else:
                        logger.warning(f"NON-VALID RSS: {found_url}")

        if search_type == "mapa_stranky":
            pass
        if search_type == "obstaravanie":
            pass

    async def get_page_header_footer_text(self, browser):
        # vrati 1. text  (header a footer)

        helper_page = await browser.new_page()
        header =""
        footer = ""
        try:
            await helper_page.goto(self.start_url, wait_until="domcontentloaded")
            try:
                header= await helper_page.locator("header").inner_text(timeout=3000)
            except Exception:
                pass
            try:
                footer= await helper_page.locator("footer").inner_text(timeout=3000)
            except Exception:
                pass
            return header + "\n" + footer
        except Exception as e:
            logger.warning(f"START PAGE OPEN FAILED (deader, footer): {e}")
            return ""
        finally:
            await helper_page.close()

    async def general_find(self, search_type, browser, current_url, current_page, depth):
        async with self.search_lock:
            state = self.search_state[search_type]
            word_set = self.type_of_keyword[search_type]
            if state["found"] or state["searching"]:
                return
            state["searching"] = True
            logger.debug(f"SEARCHING {search_type} on {current_url}")

        try:
            # 1. hladaj link na stranke
            target_url = await self.find_target_url(word_set, current_page, current_url, browser)
            
            # 2. ak nenajde link, skontroluj ci sme uz na spravnej stranke
            if not target_url:
                word = await self.fallback_page_title_find(word_set, current_page)
                if not word:
                    return None
                target_url = current_url

            # 3. otvor cielovu stranku
            return await self.open_target_page(search_type, target_url, depth, browser)

        finally:
            async with self.search_lock:
                state["searching"] = False




    async def open_target_page(self, search_type, target_url, depth, browser):
        if not self.is_robots_allowed(target_url):
            return None
        helper_page = await browser.new_page()
        try:
            await helper_page.goto(target_url, wait_until="networkidle")
            await helper_page.wait_for_timeout(2000)
            text = await helper_page.locator("body").inner_text()
            async with self.search_lock:
                self.search_state[search_type]["found"] = True
                self.found_text_keywords[search_type].append(target_url)
            logger.success(f"FOUND {search_type} ON {target_url} depth {depth}")
            return [text, target_url]
        except Exception as e:
            logger.warning(f"open_target_page ERROR {target_url}: {e}")
            return None
        finally:
            await helper_page.close()

    async def find_target_url(self, word_set, current_page, current_url, browser):
        for word in word_set:
            locator = current_page.get_by_text(word, exact=False)
            count = await locator.count()
            if count == 0:
                continue
            
            for i in range(count):
                element = locator.nth(i)
                if not await element.is_visible():
                    continue
                
                # hladanie href
                tag_name = (await element.evaluate("el => el.tagName")).lower()
                href = await element.get_attribute("href") if tag_name == "a" else None
                
                # 2. AI fallback
                if not href:
                    href = await self.ai_find_href(element, word)
                
                if not href:
                    continue
                
                full_url = urljoin(current_url, href)
                if not full_url.startswith("http"):
                    continue
                if not self.is_robots_allowed(full_url):
                    continue
                return full_url
        
        return None
    async def ai_find_href(self, element, word):
        try:
            surrounding_html = await element.locator("xpath=../../../../../..").inner_html()
            
            response = await agent.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", 
                           "content": f"V tomto HTML nájdi href odkaz ktorý najviac súvisí s textom '{word}'. Vráť iba samotný href string, nič iné. Ak nenájdeš, vráť NULL.\n\n{surrounding_html[:3000]}"}],
                temperature=0
            )
            
            href = response.choices[0].message.content.strip()
            logger.debug(f"AI found href: {href} for word: {word}")
            return None if href == "NULL" else href
        except Exception as e:
            logger.warning(f"ai_find_href error: {e}")
            return None
    async def fallback_page_title_find(self, word_set, current_page):
        # fallback ak sa nic nenajde, skonroluje nadpis aktualnej 
        # stranky. Edge case: ak nie je viditelny text priamo asociovany
        # s elementom href
        # vrati 1. word
        #       2. None
        for word in word_set:
           
            locator = current_page.locator("h1").get_by_text(word, exact=False)
            if await locator.count() == 0:
                continue
            if await locator.first.is_visible():
                return word
        return None

    async def check_content(self, text, found_href, search_type):
        # vklada najdeny text do promptu a zavola opeani API
        # na vyhodnotenie obsahu
        # vrati 1. hodnotenie definovane v ai_prompts.py
        prompt = PROMPTS[search_type].replace("{text}", text[:10000])
        
        #logger.debug(f"TEXT PREVIEW ({search_type}): {text[:3000]}")
        #https://milvus.io/ai-quick-reference/how-do-i-call-openais-api-asynchronously-in-python
        response = await agent.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature= 0 
        )
        #print(f"prompt: {prompt}")
        # konzistentnosto odpovedi temperature = 0
        out = response.choices[0].message.content.strip()
        #prompt vracia vystup v zlom formate
        out = out.replace("```json", "").replace("```", "").strip()
        result = json.loads(out)
        
        logger.debug(f"hodnotenie ({search_type}) pre {found_href}:")
        #vymysliet zapisovanie??
        for key, value in result.items():
            print(f" --- {key}: {value}")
            
        valid = self.update_best_ai_score(search_type, found_href, result)
        if not valid:
            async with self.search_lock:
                self.search_state[search_type]["found"] = False
                self.search_state[search_type]["searching"] = False

        return result

    def update_best_ai_score(self, search_type, found_href, result):
        priemer = result.get("priemer", 0)
        if priemer == 0:
            return False
        
        prev_score = self.content_scores.get(search_type)
        if not prev_score or priemer > prev_score.get("score", {}).get("priemer", 0):
            self.content_scores[search_type] = {
                "url": found_href,
                "score": result
            }
        return True
    async def check_wcag(self,page, url):
        logger.debug(f"=====CHECKING WCAG ON {url}")
        # pustenie Axe-Core scriptu na najdenie WCAG 
        # pravidiel a ich zapisanie do zoznamu 
        # !! STIAHNUT axe.min.js podľa README !!
        try:
            await page.add_script_tag(path="axe.min.js") #https://docs.loadforge.com/examples/qa-testing/axe-accessibility-testing#axe-core-accessibility-testing  to to je cez cdnjs
            results = await page.evaluate("""
                () => {
                    return axe.run({
                        runOnly: {
                            type: 'tag',
                            values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']
                        }
                                            });}""")
            #print(results["violations"]) 
            for res in results["violations"]: #jeden prvok -> jedno pravidlo
                current_tags = res.get("tags",[])
                #print(f"{current_tags} {url}")
                found_wcag_tags = []
                for t in current_tags:

                    if t.startswith("wcag"):
                        #print(found_wcag_tags)
                        found_wcag_tags.append(t)
                        if len(found_wcag_tags) >= 2:
                            break
                final_rule = None #finalny string v tvare "WCAGx.x.x LEVEL YY"
                if len(found_wcag_tags) >= 2:
                    #print(found_wcag_tags)
                    for t in found_wcag_tags:
                        if t[5] == "a":
                            wcag_level = t[5:].upper()
                        else:
                            wcag_number = t[:4].upper() + t[4] + "." +t[5] + "." +t[6] + "."
                    final_rule = wcag_number + " LEVEL: " + wcag_level
                count = len(res.get("nodes", []))
                
                if final_rule != None and final_rule not in self.page_report_final:
                    self.page_report_final[final_rule] = {
                        "count": 1,
                        "description of curr rule": res.get("description", ""),
                        "url": [url]
                    }
                elif final_rule != None and final_rule in self.page_report_final:
                    self.page_report_final[final_rule]["count"] += count
                    if url not in self.page_report_final[final_rule]["url"]:
                        self.page_report_final[final_rule]["url"].append(url)
        
        #niekedy nemusi prejst axe-core kvoli TrustedScript
        except Exception as e:
            logger.warning(f"Failed Axe-Core {url}: {e}")  

    def check_if_skip_link(self, link, main_domain_netloc, current_netloc):
        # nepridavat do queue obrazky, subory, visited/zakazane/ mimo domain url, 
        extension = (".pdf", ".jpg", ".jpeg", ".png", ".gif",".svg", ".zip", ".docx", ".xlsx")
        
        path = urlparse(link).path.lower()
        if any(path.endswith(f) for f in extension) or any(w in path for w in ["cookies", "download"]):
            #logger.debug(f"SKIP (extension/path): {link}")
            return True
        if not (current_netloc == main_domain_netloc or current_netloc.endswith("." + main_domain_netloc)):
            #logger.debug(f"SKIP (domain mismatch): {link} | current: {current_netloc} | main: {main_domain_netloc}")
            return True
        if link in self.visitedpages: #!
            #logger.debug(f"SKIP (visited): {link}")
            return True
        if not self.is_robots_allowed(link):
            return True
        return False
    
    def is_robots_allowed(self, url):
        if not self.robots_txt.can_fetch("*", url):
            logger.warning(f"FORBIDDEN BY robots.txt: {url}")
            return False
        return True


s = Scraper("https://levice.sk/")
asyncio.run(s.start())
