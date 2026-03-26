import json
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright



pristupnost_kw = [
    "vyhlásenie o prístupnosti", "Vyhlásenie o prístupnosti",
    "vyhlasenie o prístupnosti", "vyhlásenie o pristupnosti",
    "vyhlasenie o pristupnosti", "Vyhlasenie o prístupnosti",
    "Vyhlásenie o pristupnosti", "Vyhlasenie o pristupnosti",
]


def transp_test_start(start_url):
    scraper = Scraper(start_url)
    scraper.start()


class Scraper:
    MAX_DEPTH = 2

    def __init__(self, start_url):
        self.start_url = start_url
        self.visitedpages = set()
        self.page_report_final = {}
        self.found_text_elements = []
        self.admitted_rule_breaks = []
        self.page_counter = 0
       
        self.pristupnost_keywords = {wrd: False for wrd in pristupnost_kw}

        self.type_of_text_element = [ self.pristupnost_keywords]


    def start(self):
        time_start = time.time()

        with sync_playwright() as p: #https://playwright.dev/python/docs/library
            browser = p.chromium.launch(headless=True)
            queue = [(self.start_url, 0)]

            while queue:
                url, depth = queue.pop(0)
                self.process_page(url, depth, queue, browser)

            browser.close()

        data = {
            "wcag_type_count": len(self.page_report_final),
            "rules": self.page_report_final,
            "links": self.found_text_elements,
            "admitted_rule_breaks": self.admitted_rule_breaks,
        }

        with open("accesibilty_report.json", "w", encoding="utf-8") as subor:
            json.dump(data, subor)

        print(f"Searched {self.start_url} for {int(time.time() - time_start)} seconds")

   
    def process_page(self, url, depth, queue, browser):
        if url in self.visitedpages:
            return
        self.visitedpages.add(url)

        if self.page_counter >= 10:
            do_check = False
        else:
            self.page_counter += 1
            do_check = True

        #print(f"ON PAGE: {url} (depth {depth})")

        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Failed to open 1 {url}: {e}")
            page.close()
            return


        if do_check:
            #print(f"CHECKING WCAG ON {url}")
            try:
                page.add_script_tag(path="axe.min.js") #https://docs.loadforge.com/examples/qa-testing/axe-accessibility-testing#axe-core-accessibility-testing  to to je cez cdnjs
                results = page.evaluate("""
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

        if depth < self.MAX_DEPTH:
            links = page.locator("a[href]").evaluate_all("x => x.map(y => y.href)")
            
            for link in links:
                link_parts = urlparse(link)
                if link_parts.netloc == urlparse(self.start_url).netloc:
                    if link not in self.visitedpages:
                        if not self.check_if_skip_url(link):
                            new_depth = depth +1
                            queue.append((link, new_depth))

        page.close()


    def which_text_to_find(self, browser, word_dict, current_url, current_page):
        if word_dict is self.pristupnost_keywords:
            self.accessibility_find(browser, word_dict, current_url, current_page)
        else:
            pass

   


    def check_if_skip_url(self, url):
        pic_extension = (".pdf", ".jpg", ".jpeg", ".png", ".gif",".svg", ".zip", ".docx", ".xlsx")
        path = urlparse(url).path.lower()
        return any(path.endswith(f) for f in pic_extension)
    
s = Scraper("ISVS url")
s.start()
