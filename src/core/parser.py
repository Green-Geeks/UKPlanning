from bs4 import BeautifulSoup, Tag
from typing import Callable, Optional


class PageParser:
    """CSS-selector-driven HTML field extraction."""

    def __init__(self, parser: str = "lxml"):
        self._parser = parser

    def _soup(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, self._parser)

    def select_one(self, html: str, selector: str) -> Optional[Tag]:
        """Select a single element from HTML."""
        return self._soup(html).select_one(selector)

    def extract(
        self,
        html: str,
        selectors: dict[str, str],
        transforms: Optional[dict[str, Callable[[str], str]]] = None,
    ) -> dict[str, Optional[str]]:
        """Extract named fields from HTML using CSS selectors.
        Returns a dict with field names as keys. Missing fields are None.
        """
        soup = self._soup(html)
        result: dict[str, Optional[str]] = {}
        for field_name, selector in selectors.items():
            element = soup.select_one(selector)
            if element:
                value = element.get_text(strip=True)
                if transforms and field_name in transforms:
                    value = transforms[field_name](value)
                result[field_name] = value
            else:
                result[field_name] = None
        return result

    def extract_list(
        self,
        html: str,
        selector: str,
        attr: Optional[str] = None,
    ) -> list[str]:
        """Extract a list of values from HTML using a CSS selector.
        If attr is provided, extracts that attribute from each element.
        Otherwise extracts text content.
        """
        soup = self._soup(html)
        elements = soup.select(selector)
        if attr:
            return [el[attr] for el in elements if el.has_attr(attr)]
        return [el.get_text(strip=True) for el in elements]
