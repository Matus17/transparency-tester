import asyncio
from scrape import Scraper
import json
s = Scraper("https://www.unsk.sk/")
asyncio.run(s.start())

import score_accessibility as a
import score_inf as i
import score_usability as u

results = {
    "pristupnost": a.calculate(),
    "pouzitelnost": u.calculate(),
    "informativnost": i.calculate()
}

with open("final_score.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)