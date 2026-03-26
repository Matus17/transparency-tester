import json
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser #https://docs.python.org/3/library/urllib.robotparser.html
from playwright.async_api import async_playwright
import asyncio

#aszncio crawler
#https://gist.github.com/justynroberts/996118684a5de2cf9d305e217c3bd1e4

pristupnost_kw = [
    "vyhlásenie o prístupnosti", "Vyhlásenie o prístupnosti",
    "vyhlasenie o prístupnosti", "vyhlásenie o pristupnosti",
    "vyhlasenie o pristupnosti", "Vyhlasenie o prístupnosti",
    "Vyhlásenie o pristupnosti", "Vyhlasenie o pristupnosti",
]


async def transp_test_start(start_url):
    s2 = Scraper(start_url)
    await s2.start()


class Scraper:
    MAX_DEPTH = 2

    def __init__(self, start_url):
        self.robots_txt = RobotFileParser()
        self.queue_lock = asyncio.Lock()
        self.start_url = start_url
        self.visitedpages = set()
        self.page_report_final = {}
        self.found_text_elements = []
        self.admitted_rule_breaks = []
        self.page_counter = 0
        self.max_pages_at_once = 5
        self.pristupnost_keywords = {wrd: False for wrd in pristupnost_kw}
        self.semaphore = None
        self.type_of_text_element = [ self.pristupnost_keywords]
        self.take_end_url = False

    async def start(self):
        robots_link_parts= urlparse(self.start_url)
        robots_url = f"{robots_link_parts.scheme}://{robots_link_parts.netloc}/robots.txt"
        self.robots_txt.set_url(robots_url)
        self.robots_txt.read()
        time_start = time.time()
        zero_count = 0;        
        self.semaphore = asyncio.Semaphore(self.max_pages_at_once)
        async with async_playwright() as p: #https://playwright.dev/python/docs/library
            browser = await p.chromium.launch(headless=True)
            queue = [(self.start_url, 0)]
            #self.visitedpages.add(self.start_url)
            
            while queue:
                tasks_list = []
                while queue and len(tasks_list) < self.max_pages_at_once:
                    if len(queue) == 1:
                        zero_count += 1
                        if zero_count == 2: 
                            self.take_end_url = True
                    url, curr_depth = queue.pop(0)
                    if self.take_end_url:
                        end_url = url
                    tasks_list.append(self.process_page(url, curr_depth, queue, browser))
                await asyncio.gather(*tasks_list)
            await browser.close()
            print(f"Finished at {end_url}")

        data = {
            "wcag_type_count": len(self.page_report_final),
            "rules": self.page_report_final,
            "links": self.found_text_elements,
            "admitted_rule_breaks": self.admitted_rule_breaks,
        }

        with open("accesibilty_report.json", "w", encoding="utf-8") as subor:
            json.dump(data, subor)

        print(f"Searched {self.start_url} for {int(time.time() - time_start)} seconds")

   
    async def process_page(self, url, curr_depth, queue, browser):
        
        async with self.semaphore:
          
            if url in self.visitedpages:
                return
            self.visitedpages.add(url)
            delay = self.robots_txt.crawl_delay("*")
            if delay:
                print(delay)
                await asyncio.sleep(delay)
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


            if do_check:
                #print(f"CHECKING WCAG ON {url}")
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

                    for res in results["violations"]:
                        current_tags = res.get("tags",[])
                        found_wcag_tags = []
                        for t in current_tags:
                            if t.startswith("wcag"):
                                #print(found_wcag_tags)
                                found_wcag_tags.append(t)
                                if len(found_wcag_tags) >= 2:
                                    break
                        final_rule = None
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
                
                except Exception as e:
                    print(f"Axe-core fail {url}: {e}")
            
            if self.take_end_url:
                print(f"Finish depth ({curr_depth})")
            if curr_depth < self.MAX_DEPTH:
                links = await page.locator("a[href]").evaluate_all("x => x.map(y => y.href)")
                #print(f"Added {len(links)} links")
                async with self.queue_lock:
                    for link in links:
                        link_parts = urlparse(link)
                        if link_parts.netloc == urlparse(self.start_url).netloc:
                            if link not in self.visitedpages:
                                if self.robots_txt.can_fetch("*", link):
                                    if not self.check_if_skip_url(link):
                                        
                                        #self.visitedpages.add(link)
                                        
                                        queue.append((link, curr_depth + 1))
          
            await page.close()


    async def which_text_to_find(self, browser, word_dict, current_url, current_page):
        if word_dict is self.pristupnost_keywords:
            await self.accessibility_find(browser, word_dict, current_url, current_page)
        else:
            pass

   


    def check_if_skip_url(self, url):
        pic_extension = (".pdf", ".jpg", ".jpeg", ".png", ".gif",".svg", ".zip", ".docx", ".xlsx")
        path = urlparse(url).path.lower()
        return any(path.endswith(f) for f in pic_extension)
    
s = Scraper("ISVS link")
asyncio.run(s.start())
