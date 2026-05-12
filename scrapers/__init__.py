"""FC2 scraper package. Each site gets its own module."""

from scrapers.base import BaseScraper
from scrapers.fc2ppvdb_scraper import Fc2ppvdbScraper

SCRAPERS = {
    "fc2ppvdb": Fc2ppvdbScraper,
}
