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
from collections import deque



logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    level="DEBUG",
    format="<green>{time:HH:mm:ss}</green> - <level>{level:<8}</level> - {message}",
    colorize=True, )
logger.add("scrape.log", level="DEBUG", format="{time:HH:mm:ss} - {level:<8} - {message}", mode="w")


###################################################################
# BASE SCRAPE #####################################################
###################################################################
class BaseScraper:
    def __init__(self, start_url):
        p = urlparse(start_url)
        netloc = p.netloc.removeprefix("www.")
        self.start_url = f"{p.scheme}://{netloc}/"

        self.search_lock = asyncio.Lock()
        self.robots_lock = asyncio.Lock()
        self.search_state = {}
        self.type_of_keyword = {}
        self.found_text_keywords = {}
        self.content_scores = {}

        self.robots_cache = {}

    def add_www(self, url):
        parts = urlparse(url)
        main_netloc = urlparse(self.start_url).netloc
        if parts.netloc == main_netloc:
            return parts._replace(netloc="www." + parts.netloc).geturl()
        return url

    def netloc_no_www(self,url):
        return urlparse(url).netloc.removeprefix("www.")
    
    async def get_domain_robots(self, url):
        # Stiahne a sparsuje robots.txt domény, pri chybe povolí 
        # všetko.
        #

        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            async with httpx.AsyncClient(headers={"user-agent": "Mozilla/5.0"}, follow_redirects=True, timeout=5, verify=False) as c:
                response = await c.get(robots_url)
                if response.status_code == 200:
                    rp = RobotFileParser()
                    rp.set_url(robots_url)
                    rp.parse(response.text.splitlines())
                    return rp
        except Exception as e:
            logger.debug(f"robots.txt exception: {e}")
        
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.parse(["User-agent: *", "Allow: /"])
        return rp

    async def is_robots_allowed(self, url):
        # Skontroluje či je URL povolená podľa robots.txt domény 
        # a výsledky cachuje.
        #

        netloc = urlparse(url).netloc
        async with self.robots_lock:
            if netloc not in self.robots_cache:
                self.robots_cache[netloc] = await self.get_domain_robots(url)
            r = self.robots_cache[netloc]
        if not r.can_fetch("*", url):
            logger.warning(f"FORBIDDEN BY robots.txt: {url}")
            return False
        return True
    
    async def general_find(self, search_type, browser, current_url, current_page, depth):
        # Nájde odkazy na stránke podľa kľúčových slov a otvorí ich.
        # Vráti zoznam [text, url] pre každú úspešne otvorenú stránku.
        #
        
        async with self.search_lock:
            state = self.search_state[search_type]
            word_set = self.type_of_keyword[search_type]
            if state["found"]:
                return
            logger.debug(f"SEARCHING {search_type} on {current_url}")

        # 1. hladaj link na stranke
        target_url_list = await self.find_target_url(word_set, current_page, current_url)

        # 2. otvor cielovu stranku
        results = []
        for target_url in target_url_list:
            async with self.search_lock:
                if state["found"]:
                    return None
            result = await self.open_target_page(search_type, target_url, depth, browser)
            if result:
                results.append(result)

        return results if results else None

    async def is_href_visited(self, search_type, target_url):
        if not await self.is_robots_allowed(target_url):
            return True
        async with self.search_lock:
            if target_url in self.found_text_keywords[search_type]:
                return True
            self.found_text_keywords[search_type].append(target_url)
        return False

    async def extract_page_text(self, page):
        for selector in ["header", "footer", "nav"]:
            await page.eval_on_selector_all(selector,"elements => elements.forEach(el => el.remove())")
        body_text = await page.locator("body").inner_text()
        for frame in page.frames[1:]:
            try:
                frame_text = await frame.locator("body").inner_text()
                body_text += "\n" + frame_text
            except Exception:
                pass
        return body_text

    async def open_target_page(self, search_type, target_url, depth, browser):
        # Otvorí cieľovú stránku, extrahuje jej text a vráti ho 
        # spolu s URL.
        #

        if await self.is_href_visited(search_type, target_url):
            return None

        helper_page = await browser.new_page()
        try:
            goto_url = self.add_www(target_url)
            rs = await helper_page.goto(goto_url, wait_until="networkidle")
            if rs and rs.status >= 400:
                logger.warning(f"open_target_page LOAD ERROR {rs.status} {target_url}")
                await asyncio.sleep(5)
                return None

            text = await self.extract_page_text(helper_page)
            logger.success(f"OPENED {search_type} ON {target_url} depth {depth}")
            return [text, target_url]
        except Exception as e:
            logger.warning(f"open_target_page ERROR {target_url}: {e}")
            await asyncio.sleep(1)
            return None
        finally:
            await helper_page.close()

    async def find_target_url(self, word_set, current_page, current_url):
        # Hľadá klúčové slová na stránke a vracia zoznam URL odkazov 
        # ktoré sa nachádzajú v okolí nájdeného textu (rodičovský 
        # element alebo predchádzajúci súrodenec).

        found_hrefs = set()
        for word in word_set:
            regex = re.compile(word, re.IGNORECASE)
            locator = current_page.get_by_text(regex)
            count = await locator.count()
            if count > 0:
                logger.debug(f"  '{word}' -> {count} on {current_url}")
            if count == 0:
                continue
            
            for i in range(count):
                element = locator.nth(i)
                visible = await element.is_visible()
                if not visible:
                    continue
                href = await element.evaluate("""
                    el => {
                        let curr_el = el;
                        let level = 0;
                        let max_level = 2;
                        while (curr_el && curr_el !== document.body && level < max_level) {
                            if (curr_el.tagName === 'A' && curr_el.href) {
                                return curr_el.href; }
                            
                            let sibling_el = curr_el.previousElementSibling;
                            while (sibling_el) {
                                if (sibling_el.tagName === 'A' && sibling_el.href) {
                                    return sibling_el.href; }
                                sibling_el = sibling_el.previousElementSibling;
                            }
                            curr_el = curr_el.parentElement;
                            level++;
                        }
                        return null;
                    }
                """)
                logger.debug(f"  href={href} for word {word} on {current_url}")
                if not href:
                    continue
                
                if not await self.is_robots_allowed(href):
                    continue
                found_hrefs.add(href)
        
        return list(found_hrefs)
    

    async def check_content(self, text, found_href, search_type, depth):
        # Pošle nájdený text do OpenAI API na vyhodnotenie obsahu,
        # uloží najlepšie skóre a označí hľadanie za ukončené ak 
        # priemer >= 7.5.

        prompt = PROMPTS[search_type].replace("{text}", text[:10000])
        response = await agent.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature= 0,
            response_format={"type": "json_object"}
        )

        out = response.choices[0].message.content.strip()
        result = json.loads(out)
        
        logger.debug(f"rating ({search_type}) for {found_href}:")
        for key, value in result.items():
            logger.debug(f" --- {key}: {value}")
            
        async with self.search_lock:
            self.update_best_ai_score(search_type, found_href, result,depth)
            if result.get("priemer", 0) >= 7.5: #potom uz nehladame lepsie
                self.search_state[search_type]["found"] = True

        return result

    def update_best_ai_score(self, search_type, found_href, result, depth):
        # Aktualizuje najlepšie skóre pre daný typ hľadania ak je 
        # priemer >= 5 a lepší ako predchádzajúci výsledok.
        #

        priemer = result.get("priemer", 0)
        if priemer < 5:
            return
        
        prev_score = self.content_scores.get(search_type)
        if not prev_score or priemer > prev_score.get("score", {}).get("priemer", 0):
            self.content_scores[search_type] = {
                    "url": found_href,
                    "score": result,
                    "depth": depth
                }

###################################################################
# MAIN PAGE #######################################################
###################################################################
class MainPageScraper(BaseScraper):
    def __init__(self, start_url):
        super().__init__(start_url)
        self.type_of_keyword = {
            "spravca": k.spravca_kw,
            "prevadzkovatel": k.prevadzkovatel_kw,
            "mapa_stranky": k.mapa_stranky_kw,
        }
        self.search_state = {key: {"found": False} for key in self.type_of_keyword}
        self.found_text_keywords = {key: [] for key in self.type_of_keyword}
        self.result = {
            "https": False,
            "search_element": False,
            "spravca": None,
            "prevadzkovatel": None,
            "mapa_stranky":False
        }

    async def load_main_page(self, browser):
        # Načíta hlavnú stránku, skontroluje HTTPS a vyhľadávanie,
        # a spustí hľadanie správcu, prevádzkovateľa a mapy stránky.
        #

        goto_url = self.add_www(self.start_url)
        await self.check_https(goto_url)
        page = await browser.new_page()
        try:
            await page.goto(goto_url, wait_until="domcontentloaded")
            await self.check_search_element(page)
            for search_type in self.type_of_keyword.keys():
                await self.main_page_content_search(browser, search_type, self.start_url, page, 0)
        except Exception as e:
            logger.error(f"MainPageScraper PAGE LOAD FAIL: {e}")
        finally:
            await page.close()
        self.save_json()

    async def check_https(self, url):
        # Overí či stránka beží na HTTPS protokole odoslaním 
        # GET požiadavky.
        #

        if not url.startswith("https://"):
            return
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.get(url)
            self.result["https"] = True
        except Exception:
            return



    async def check_search_element(self, page):
        # Skontroluje či stránka obsahuje vyhľadávacie pole
        # podľa atribútov input a button elementov.
        #

        inputs = await page.locator("input, button").all()
        for i in inputs:
            for attr in ["id", "type","class", "name"]:
                value = await i.get_attribute(attr) or ""
                if "search" in value.lower():
                    self.result["search_element"] = True
                    return


    def save_json(self):
        # Uloženie výstupného súboru, týkajúceho sa použiteľnosti 
        # hlavnej stránky.
        #

        with open("main_page_report.json", "w", encoding="utf-8") as f:
            json.dump(self.result, f, indent=2, ensure_ascii=False)
        logger.info("Saved main_page_report.json")

    async def main_page_content_search(self, browser, search_type, current_url, current_page, depth):
        # Sprostredkuje hľadanie kľúčových slov (keywords) na 
        # hlavnej stránke, hľdáme správcu a prevádzkovateľa
        #

        text = ""
        result = await self.general_find(search_type, browser, current_url, current_page, depth)
        
        if result:
            text, found_url= result[0]
        else:
            found_url = current_url

        if search_type in ["spravca", "prevadzkovatel"]:
            text += await self.get_page_header_footer_text(browser)
            check_result = await self.check_content(text, found_url, search_type, depth)
            self.result[search_type] = check_result.get(search_type)
        else:
            self.result[search_type] = True
        
    async def get_page_header_footer_text(self, browser):
        # Získanie obsahu header a footer zo stránky.
        # Používa sa na doplnenie kontextu pri hľadaní správcu a 
        # prevádzkovateľa.

        helper_page = await browser.new_page()
        header =""
        footer = ""
        try:
            goto_url = self.add_www(self.start_url)
            await helper_page.goto(goto_url, wait_until="domcontentloaded")
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
            logger.warning(f"START PAGE OPEN FAILED (header, footer): {e}")
            return ""
        finally:
            await helper_page.close()



###################################################################
# MAIN SCRAPE #####################################################
###################################################################
class Scraper(BaseScraper):
    MAX_DEPTH = 3
    MAX_PAGES_AT_ONCE = 8
    MAX_PAGE_COUNT = 1500
    MAX_PAGES_PER_SUBDOMAIN = 20
    def __init__(self, start_url):
        super().__init__(start_url)
        self.type_of_keyword = {
            "gdpr": k.gdpr_kw, 
            "tabula": k.tabule_kw, "vyhlaseniePristupnost": k.pristupnost_kw,
            "rss": k.rss_kw, 
            "kompetencie": k.kompetencie,
            "objednavky": k.objednavky_kw, "faktury": k.faktury_kw, 
        }
        
        self.search_state = {key: {"found": False} for key in self.type_of_keyword}
        self.found_text_keywords = {key: [] for key in self.type_of_keyword}
        self.content_scores = {key: None for key in self.type_of_keyword}

        self.visitedpages = set()
        self.page_report_final = {}
        self.found_rule_breaks = set()

        self.queue_lock = asyncio.Lock()
        self.counter_lock = asyncio.Lock()

        self.page_counter = 0
        self.fail_counter = 0
        self.wcag_check_counter = 0
        self.subdomain_counter = {}
        self.seen_subdomain_links = set()


    async def start(self):
        # Spustenie scrapovania. Načíta hlavnú stránku, prehľadáva 
        # BFS do MAX_DEPTH, otvara MAX_PAGES_AT_ONCE stranok(async task).
        #

        time_start = time.time()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            main_page_scraper = MainPageScraper(self.start_url)
            await main_page_scraper.load_main_page(browser)

            queue = deque([(self.start_url, 0)])
            self.visitedpages.add(self.start_url)
            tasks_set = set()
            while queue or tasks_set:
                while len(tasks_set) < self.MAX_PAGES_AT_ONCE:
                    async with self.queue_lock:
                        if not queue:
                            break
                        if self.page_counter >= self.MAX_PAGE_COUNT:
                            break
                        url, curr_depth = queue.popleft()
                    task = asyncio.create_task(
                        self.scrape_curr_page(url, curr_depth, queue, browser)
                    )
                    tasks_set.add(task)
                if not tasks_set:
                    break
                x, tasks_set = await asyncio.wait(tasks_set, return_when=asyncio.FIRST_COMPLETED)
            
            if tasks_set:
                await asyncio.wait(tasks_set)
            await browser.close()

            time_end = time.time()
        self.save_json()
        logger.success(f"SUBDOMAINS: {self.subdomain_counter}")
        logger.success(f"SEARCHED {self.start_url} FOR {int(time_end - time_start)} SECONDS")
        logger.success(f"BFS SEARCHED TO DEPTH: {self.MAX_DEPTH}")
        logger.success(f"ASYNC TASKS: {self.MAX_PAGES_AT_ONCE}")
        logger.success(f"SEARCH LIMIT OF {self.MAX_PAGE_COUNT} REACHED: {self.page_counter>=self.MAX_PAGE_COUNT}")
        logger.success(f"FOUND {len(self.visitedpages)} PAGES, OPENED {self.page_counter-self.fail_counter}, FAILED {self.fail_counter}")

    async def scrape_curr_page(self, url, curr_depth, queue, browser):
        # Otvori stránku a zavolá hladanie kľúčových slov,
        # kontrolu WCAG, zber nových odkazov.
        #

        await asyncio.sleep(0.3)
        async with self.counter_lock:
            self.page_counter += 1


        if not await self.is_robots_allowed(url):
            async with self.counter_lock:
                self.fail_counter += 1
            return

        page = await browser.new_page()
        try:
            goto_url = self.add_www(url)
            rs = await page.goto(goto_url, wait_until="domcontentloaded")
            if rs and rs.status >= 400:
                logger.warning(f"FAILED TO OPEN {url}: status {rs.status}")
                async with self.counter_lock:
                    self.fail_counter += 1
                return
            logger.info(f"ON PAGE {self.page_counter}: {url} (depth {curr_depth})")

            await self.keyword_search(browser, url, page, curr_depth)

            if self.wcag_check_counter < 100 and self.netloc_no_www(url) == self.netloc_no_www(self.start_url):
                content_type = rs.headers.get("content-type", "")
                if "text/html" in content_type:
                    await self.check_wcag(page, url)

            if curr_depth < self.MAX_DEPTH:
                await self.get_all_links( page, url, curr_depth, queue)

        except Exception as e:
            logger.warning(f"FAILED TO OPEN {url}: {e}")
            async with self.counter_lock:
                self.fail_counter +=1
            return

        finally:
            await page.close()

    async def keyword_search(self, browser, url, page, curr_depth):
        # Spúšťa hľahanie odkazov, ktoré sa ešte nenašli, v 
        # dostatočnom ohodnotení.
        #

        for word_type in self.type_of_keyword.keys():
            async with self.search_lock:
                is_found = self.search_state[word_type]["found"]
            if is_found:
                continue
            await self.page_content_search(browser, word_type, url, page, curr_depth)

    async def get_all_links(self, page, url, curr_depth, queue):
        # Hľadanie nových odkazov na aktuálnej stránke, ktoré sú v 
        # doméne alebo subdoméne a ich pridávanie do queue. Počet 
        # subdomén je obmedzený.

        links = await page.locator("a").evaluate_all("x => x.map(y => y.href)")
        main_domain_netloc = self.netloc_no_www(self.start_url)
        added = 0
        async with self.queue_lock:
            for link in links:
                link = urlparse(link)._replace(fragment="").geturl()
                link_parts = urlparse(link)
                if link_parts.netloc.startswith("www."):
                    link = link_parts._replace(netloc=link_parts.netloc.removeprefix("www.")).geturl()
                current_netloc = self.netloc_no_www(link)

                if self.check_if_skip_link(link, main_domain_netloc, current_netloc):
                    continue
                if current_netloc !=main_domain_netloc:

                    if link in self.seen_subdomain_links:
                        continue
                    subdomain_count = self.subdomain_counter.get(current_netloc, 0)
                    if subdomain_count >= self.MAX_PAGES_PER_SUBDOMAIN:
                        continue
                    self.subdomain_counter[current_netloc] = subdomain_count + 1
                    self.seen_subdomain_links.add(link)
                
                if link in self.visitedpages:
                    continue

                self.visitedpages.add(link)
                queue.append((link, curr_depth + 1))
                added += 1
                
            logger.debug(f"ADDED {added} links to queue from {url}")

    def save_json(self):
        # Uloženie výstupných súborov na hodnotenie.
        #
        #

        keywords_data = {
            "keywords": {
                k: {
                    "priemer": v["score"].get("priemer") if v else None,
                    "found_on":v["url"] if v else None,
                    "depth": v["depth"] if v else None,
                }
                for k, v in self.content_scores.items()
            },
        }
        
        accessibility_data = {
            "wcag": {
                "count": len(self.page_report_final),
                "found_rules": list(self.found_rule_breaks),
                "rules": self.page_report_final
            },

            "pages_visited": self.page_counter-self.fail_counter,
            "pages_failed": self.fail_counter
        }

        with open("keywords_report.json", "w", encoding="utf-8") as f:
            json.dump(keywords_data, f, indent=2, ensure_ascii=False)
        
        with open("accessibility_report.json", "w", encoding="utf-8") as f:
            json.dump(accessibility_data, f, indent=2, ensure_ascii=False)
        
        logger.info("Saved keywords_report.json and accessibility_report.json")


    async def page_content_search(self, browser, search_type, current_url, current_page, depth):
        # volanie príslušných funkcii na prehľadávanie stránky
        #
        #
        results = await self.general_find(search_type, browser, current_url, current_page, depth)
        if not results:
            return

        for text, found_url in results:
            async with self.search_lock:
                if self.search_state[search_type]["found"]:
                    return

            if search_type == "vyhlaseniePristupnost":
                main_netloc = self.netloc_no_www(self.start_url)
                found_netloc = self.netloc_no_www(found_url)
                if found_netloc != main_netloc:
                    continue

            if search_type in ("vyhlaseniePristupnost", "objednavky", "faktury", "kompetencie", "tabula", "gdpr"):
                await self.check_content(text, found_url, search_type, depth)

            elif search_type == "rss":
                async with httpx.AsyncClient(headers={"user-agent": "Mozilla/5.0"},timeout=10, follow_redirects=True,verify=False) as c:
                    is_valid_rss= await self.check_rss_url(found_url, c)
                    rss_url = found_url
                    if not is_valid_rss and await self.is_robots_allowed(found_url):
                        rss_page = await browser.new_page()
                        try:
                            goto_url = self.add_www(found_url)
                            await rss_page.goto(goto_url, wait_until="domcontentloaded")
                            links = await rss_page.locator("a[href*='rss'], a[href*='feed'], a[href*='atom']").evaluate_all("x => x.map(y => y.href)")
                            for l in links:
                                is_valid_rss = await self.check_rss_url(l, c)
                                if is_valid_rss:
                                    rss_url = l
                                    break
                        finally:
                            await rss_page.close()

                async with self.search_lock:
                    if is_valid_rss and not self.search_state["rss"]["found"]:
                        self.search_state["rss"]["found"] = True
                        self.content_scores["rss"] = {"url": rss_url, "score": {"priemer":10}, "depth":depth}



    async def check_rss_url(self, url, client):
        # Kontrola, či ide o RSS stránku, ktorá je 
        # typu XML a obsahuje záznam.
        #

        try:
            if not await self.is_robots_allowed(url):
                return False
            response = await client.get(url)
            content_type = response.headers.get("content-type", "")
            logger.debug(f"RSS check {url} ->type: {content_type}")
            if "xml" not in content_type:
                logger.warning(f"NON-VALID RSS(no XML): {url}")
                return False
            feed = feedparser.parse(response.text)
            if feed.bozo:
                logger.warning(f"NON-VALID RSS: {url}")
                return False
            if len(feed.entries) == 0:
                logger.warning(f"NON-VALID RSS: {url}")
                return False
            logger.success(f"VALID RSS: {url}")
            return True
        except Exception:
            return False
        

    async def check_wcag(self,page, url):
        # Spustenie Axe-Core scriptu na kontrolu WCAG 2.2 pravidiel.
        # Ukladanie chyby, URL a počtu.
        #

        logger.debug(f"=====CHECKING WCAG ON {url}")
        try:
            await page.add_script_tag(path="axe.min.js")
            results = await page.evaluate("""
                () => {
                    return axe.run({
                        runOnly: {
                            type: 'tag',
                            values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22a', 'wcag22aa']
                        }
                                            });}""")

            for res in results["violations"]: #jeden prvok -> jedno pravidlo
                current_tags = res.get("tags",[])
                found_wcag_tags = []
                for t in current_tags:

                    if t.startswith("wcag"):
                        found_wcag_tags.append(t)
                        
                if len(found_wcag_tags) != 0:
                    for tag in found_wcag_tags:
                        if tag[4:].isdigit():
                            
                            count = len(res.get("nodes", []))
                            self.found_rule_breaks.add(tag)
                            if tag not in self.page_report_final:
                                self.page_report_final[tag] = {
                                    
                                    "rule description": [res.get("description", "")],
                                    "url": {url: count}
                                }
                            else:
                                desc = res.get("description","")
                                if desc not in self.page_report_final[tag]["rule description"]:
                                    self.page_report_final[tag]["rule description"].append(desc)
                                if url not in self.page_report_final[tag]["url"]:
                                    self.page_report_final[tag]["url"][url] = count
                                else:
                                    self.page_report_final[tag]["url"][url] += count
            self.wcag_check_counter += 1

        except Exception as e:
            logger.warning(f"Failed Axe-Core {url}: {e}")

    def check_if_skip_link(self, link, main_domain_netloc, current_netloc):
        # Vráti True ak sa má link preskočiť. Súbory, mimo domény, 
        # alebo už navštívené stránky
        #

        extension = (".pdf", ".jpg", ".jpeg", ".png", ".gif",".svg", ".zip", ".docx", ".xlsx")
        
        path = urlparse(link).path.lower()
        if any(path.endswith(f) for f in extension) or any(w in path for w in ["cookies", "download"]):
            return True
        main_netloc_no_www = main_domain_netloc.removeprefix("www.")
        if not (current_netloc == main_domain_netloc or current_netloc.endswith("." + main_netloc_no_www)):
            return True
        if link in self.visitedpages:
            return True

        return False
