import json
import time
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser #https://docs.python.org/3/library/urllib.robotparser.html
from playwright.async_api import async_playwright
import asyncio
import re
#aszncio crawler
#https://gist.github.com/justynroberts/996118684a5de2cf9d305e217c3bd1e4

#to fix:
#viacnasobne prehladavanie pristupnost page
#nekoyistentny pocet stranok -> too many requesst error
# pred regexom filtorvat iba viditelny text
# stale to najde viac slov z rovnakeho zoznamu, asi kvoli async
# zjednodusit citanie z Axe-core vystupu

pristupnost_kw = [
    "vyhlásenie o prístupnosti", "Vyhlásenie o prístupnosti",
    "vyhlasenie o prístupnosti", "vyhlásenie o pristupnosti",
    "vyhlasenie o pristupnosti", "Vyhlasenie o prístupnosti",
    "Vyhlásenie o pristupnosti", "Vyhlasenie o pristupnosti",
]

other_kw = ["primátor"]

async def transp_test_start(start_url):
    s2 = Scraper(start_url)
    await s2.start()


class Scraper:
    MAX_DEPTH = 2   # maximalna hlbka hladania linkov, domovska
                    # stranka je (depth 0), linky na nej (depth 1)

    def __init__(self, start_url):
        self.robots_txt = RobotFileParser() #
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
        self.pristupnost_keywords = {wrd: False for wrd in pristupnost_kw}
        self.other_keywords = {wrd: False for wrd in other_kw}
        
        self.semaphore = None
        self.type_of_text_element = [ self.pristupnost_keywords, self.other_keywords]


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
        else:
            await self.other_find(browser, word_dict, current_url, current_page)

    async def other_find(self, browser, word_dict, current_url, current_page):
        #print("HLADAM OTHER KEYWORDS")
        for word, found in word_dict.items():
            if found:
                continue
            #https://playwright.dev/python/docs/api/class-locator#locator-is-visible
            locator = current_page.get_by_text(word, exact=False)

            count = await locator.count()

            if  count == 0:
                word_dict[word] = False
                continue
            

            for i in range(count):
                element = locator.nth(i)

                # iba viditelny text, po prvom matchi skoci
                if await element.is_visible():
                    print(f"Found '{word}' on {current_url}")
                    self.found_text_elements.append(f"Found '{word}' on {current_url}")
                    word_dict[word] = True
                    break

    async def accessibility_find(self, browser, word_dict, current_url, current_page):
        # hladanie "Vyhlásenia o prístupnosti" a WCAG pravidiel v nom
        #print("HLADAM ACCESSIBILITY KEYWORDS")
        for word, found in word_dict.items():
            if found:
                continue

            
            async with self.accessibility_lock:
                if any(value == True for value in word_dict.values()):
                    break
                for k in word_dict:
                    word_dict[k] = True

            
            locator = current_page.get_by_text(word, exact=False)

            count = await locator.count()

            if  count == 0:
                word_dict[word] = False
                continue
            
            found_href = None
            for i in range(count):
                element = locator.nth(i)

                # iba viditelny text, po prvom matchi skoci
                if not await element.is_visible():
                    continue
                tag_name = (await element.evaluate("el => el.tagName")).lower()
                href = await element.get_attribute("href") if tag_name == "a" else None
                if href:
                    found_href = href
                    break
            # musi ist o konkretny link na "Vyhásenie o prístupnosti"
            if not found_href:
                for k in word_dict:
                    word_dict[k] = False
                continue

                
            full_link = urljoin(current_url, href)
            # otvori novu izolovanu accessibility_page a hlada 
            # regexom Wcag pravidlá v texte
            accessibility_page = await browser.new_page()
            try:
                await accessibility_page.goto(full_link, wait_until="domcontentloaded")
                text = await accessibility_page.locator("body").inner_text()
                regex = r"\b\d{1,2}\.\d{1,2}\.\d{1,2}\.?\b"
                matches = re.findall(regex, text)
                print(f"Hladam WCAG na stranke {href}")
                print(matches)
                self.admitted_rule_breaks.append(matches)
            except Exception as e:
                print(f"Nepodarilo sa otvorit pristupnost link {href}: {e}")
            finally:
                await accessibility_page.close()
    
    async def check_wcag(self,page, url):
        # pustenie Axe-Core scriptu na najdenie WCAG 
        # pravidiel a ich zapisanie do zoznamu 
        # !! STIAHNUT axe.min.js podľa README !!
        #print(f"CHECKING WCAG ON {url}")
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
        # nepridavat do queue oprazky, subory !!! neskor upravit
        pic_extension = (".pdf", ".jpg", ".jpeg", ".png", ".gif",".svg", ".zip", ".docx", ".xlsx")
        path = urlparse(url).path.lower()
        return any(path.endswith(f) for f in pic_extension) or "cookies" in path
    

s = Scraper("ISVS link")
asyncio.run(s.start())
