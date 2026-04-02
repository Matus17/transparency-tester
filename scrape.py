import json
import time
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser #https://docs.python.org/3/library/urllib.robotparser.html
from playwright.async_api import async_playwright
import asyncio
import re
from ai_prompts import PROMPTS, agent
import keywords as k
#aszncio crawler
#https://gist.github.com/justynroberts/996118684a5de2cf9d305e217c3bd1e4

#to fix:
#viacnasobne prehladavanie pristupnost page
#nekoyistentny pocet stranok -> too many requesst error
# pred regexom filtorvat iba viditelny text
# stale to najde viac slov z rovnakeho zoznamu, asi kvoli async
# zjednodusit citanie z Axe-core vystupu



other_kw = ["primátor"]

async def transp_test_start(start_url):
    s2 = Scraper(start_url)
    await s2.start()


class Scraper:
    MAX_DEPTH = 2   # maximalna hlbka hladania linkov, domovska
                    # stranka je (depth 0), linky na nej (depth 1)

    def __init__(self, start_url):
        self.robots_txt = RobotFileParser()
        self.queue_lock = asyncio.Lock()
        self.counter_lock = asyncio.Lock()
        self.accessibility_lock = asyncio.Lock()
        self.start_url = start_url #main page, !!! pridat urlparse
        self.visitedpages = set() # navstivene stranky 
        self.page_report_final = {} #vysledny zoznam pre zapis do jsonu
        self.found_text_elements = [] #najdene textove obsahy, podla kriterii !!! string potom zmenit 
        self.admitted_rule_breaks = [] #najdene WCAG paravidla vo Vyhlásení o prístupnosti
        self.page_counter = 0 #helper page counter
        self.max_sempaphore = 5 # pocet podstranok spracovavanzch naraz
        self.gdpr_keywords = {word: False for word in k.gdpr_kw}
        self.contact_spravca_keywords = {word: False for word in k.contact_spravca_kw}
        self.tabule_keywords = {word: False for word in k.tabule_kw}
        self.pristupnost_keywords = {word: False for word in k.pristupnost_kw}

        self.type_of_text_element = [self.gdpr_keywords, self.contact_spravca_keywords, self.tabule_keywords, self.pristupnost_keywords]
        
        self.semaphore = None
        
        
        self.search_state = {
            "accessibility": {"found": False, "searching": False},
            "gdpr": {"found": False, "searching": False}, 
            "spravca": {"found": False, "searching": False}, 
        }
        self.search_lock = asyncio.Lock()
    async def start(self):
        # ulozenie ../robots.txt suboru zo stranky
        #robots_link_parts= urlparse(self.start_url)
        #robots_url = f"{robots_link_parts.scheme}://{robots_link_parts.netloc}/robots.txt"
        #self.robots_txt.set_url(robots_url)
        #self.robots_txt.read()
        # ---------------------
        time_start = time.time()
        
        self.semaphore = asyncio.Semaphore(self.max_sempaphore)
        async with async_playwright() as p: #https://playwright.dev/python/docs/library
            browser = await p.chromium.launch(headless=True)
            queue = [(self.start_url, 0)]
            #self.visitedpages.add(self.start_url)
            
            while queue:
                tasks_list = []
                while queue and len(tasks_list) < self.max_sempaphore:
                    url, curr_depth = queue.pop(0)
                    scrape_res = self.scrape_curr_page(url, curr_depth, queue, browser)
                    tasks_list.append(scrape_res)
                await asyncio.gather(*tasks_list)
            await browser.close()
            

        data = {
            "wcag_type_count": len(self.page_report_final),
            "rules": self.page_report_final,
            "links": self.found_text_elements,
            "admitted_rule_breaks": self.admitted_rule_breaks,
        }

        with open("accesibilty_report.json", "w", encoding="utf-8") as subor:
            json.dump(data, subor)

        print(f"Searched {self.start_url} for {int(time.time() - time_start)} seconds")

   
    async def scrape_curr_page(self, url, curr_depth, queue, browser):
        # prehladanie text. emementov aktualnej stranky, 
        # viac stranok naraz podla parametru max_semaphore
        async with self.semaphore:
            if url in self.visitedpages:
                return
            self.visitedpages.add(url)

            #delay = self.robots_txt.crawl_delay("*")
            #if delay:
            #    print(delay)
            #    await asyncio.sleep(delay)
            if self.page_counter >= 10:
                self.page_counter += 1
                do_check = False
            else:
                self.page_counter += 1
                do_check = True

            print(f"ON PAGE: {url} (depth {curr_depth}) {self.page_counter}")

            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded")
            except Exception as e:
                print(f"Failed to open 1 {url}: {e}")
                await page.close()
                return

            
            for text_element_dict in self.type_of_text_element:
                async with self.counter_lock:
                    if all(value == False for value in text_element_dict.values()):
                        await self.which_text_to_find(browser,text_element_dict, url, page)
                    
            if do_check:
                await self.check_wcag(page, url)
            
            # pridanie linkov z current page
            if curr_depth < self.MAX_DEPTH:
                links = await page.locator("a[href]").evaluate_all("x => x.map(y => y.href)")
                #print(f"Added {len(links)} links")
                async with self.queue_lock:
                    for link in links:
                        link_parts = urlparse(link)
                        if link_parts.netloc == urlparse(self.start_url).netloc:
                            if link not in self.visitedpages:
                                #if self.robots_txt.can_fetch("*", link):
                                if not self.check_if_skip_url(link):

                                    queue.append((link, curr_depth + 1))
          
            await page.close()

    
    async def which_text_to_find(self, browser, word_dict, current_url, current_page):
        # hladanie viditelneho textu na current page
        if word_dict is self.pristupnost_keywords:
            await self.accessibility_find(browser, word_dict, current_url, current_page)
        elif word_dict == self.gdpr_keywords:
            await self.gdpr_find(browser, word_dict, current_url, current_page)
        elif word_dict == self.contact_spravca_keywords:
            await self.contact_spravca_find(browser, word_dict, current_url, current_page)

    async def contact_spravca_find(self, browser, word_dict, current_url, current_page):
        #print("HLADAM SPRAVCA KEYWORDS")
        search_type = "spravca"
        result = await self.general_find(search_type, browser, word_dict, current_url, current_page)
        if not result:
            return
        text, found_href = result
        #print(f"Found accessibility on {found_href}")
        
    async def gdpr_find(self, browser, word_dict, current_url, current_page):
        #print("HLADAM GDPR KEYWORDS")
        search_type = "gdpr"
        result = await self.general_find(search_type, browser, word_dict, current_url, current_page)
        if not result:
            return
        text, found_href = result
        await self.check_content(text, found_href, search_type)

    async def accessibility_find(self, browser, word_dict, current_url, current_page):
        # hladanie "Vyhlásenia o prístupnosti" a WCAG pravidiel v nom

        #print("HLADAM ACCESSIBILITY KEYWORDS")
        
        search_type = "accessibility"
        result = await self.general_find(search_type, browser, word_dict, current_url, current_page)
        if not result:
            return
        text, found_href = result
        # hladanie regexom Wcag pravidlá v texte
        regex = r"\b\d{1,2}\.\d{1,2}\.\d{1,2}\.?\b"
        matches = re.findall(regex, text)
        print(matches)
        self.admitted_rule_breaks.append(matches)

                    
        
    async def general_find(self, search_type, browser, word_dict, current_url, current_page):
        async with self.search_lock:
            state = self.search_state[search_type]
            if state["found"] or state["searching"]:
                return
            state["searching"] = True
            print(f"SEARCHING {search_type} on {current_url}")

        result = await self.word_link_find(word_dict,current_page)
        
        if not result:
            async with self.search_lock:
                state["searching"] = False
            return
        word, found_href = result
        full_link = urljoin(current_url, found_href)

        # otvori novu izolovanu page a hlada 
        accessibility_page = await browser.new_page()
        try:
            await accessibility_page.goto(full_link, wait_until="domcontentloaded")
            #inner_text vrati iba viditelny text
            text = await accessibility_page.locator("body").inner_text()
            async with self.search_lock:
                state["found"] = True
            print(f"Found {search_type}: {word} on {found_href}")
            return ([text, found_href])
        except Exception as e:
            print(f"Nepodarilo sa otvorit pristupnost link {found_href}: {e}")
            
        finally:
            await accessibility_page.close()
            async with self.search_lock:
                state["searching"] = False

    async def word_link_find(self, word_dict,current_page):
        for word, found in word_dict.items():
            if found:
                continue

            locator = current_page.get_by_text(word, exact=False)
            count = await locator.count()

            if  count == 0:
                continue
            
            for i in range(count):
                element = locator.nth(i)
                if not await element.is_visible(): # iba viditelny text, po prvom matchi skoci
                    continue
                tag_name = (await element.evaluate("el => el.tagName")).lower()
                href = await element.get_attribute("href") if tag_name == "a" else None
                # musi ist o konkretny link na napr. "Vyhásenie o prístupnosti"
                if href:
                    return ([word, href])

        return None
    
    async def check_content(self, text, found_href, search_type):

        # vlozit do promptu text
        prompt = PROMPTS[search_type].replace("{text}", text[:2000])
        
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
        
        print(f"hodnotenie ({search_type}) pre {found_href}:")
        for key, value in result.items():
            print(f" --- {key}: {value}/10")
        
        return result
    async def check_wcag(self,page, url):
        # pustenie Axe-Core scriptu na najdenie WCAG 
        # pravidiel a ich zapisanie do zoznamu 
        # !! STIAHNUT axe.min.js podľa README !!
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
    

    
    def check_if_skip_url(self, url):
        # nepridavat do queue obrazky, subory !!! neskor upravit
        pic_extension = (".pdf", ".jpg", ".jpeg", ".png", ".gif",".svg", ".zip", ".docx", ".xlsx")
        path = urlparse(url).path.lower()
        return any(path.endswith(f) for f in pic_extension) or "cookies" in path
    

s = Scraper("ISVS url")
asyncio.run(s.start())
