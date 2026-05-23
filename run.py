import asyncio
import sys
from scrape import Scraper
import score_final as score

if __name__ == "__main__":
    if len(sys.argv) > 1:
        url = sys.argv[1]
        asyncio.run(Scraper(url).start())
        score.calc()