from src.core.parser import PageParser


SAMPLE_IDOX_DETAIL = """
<html><body>
<table>
  <tr><th>Reference</th><td>24/01234/FUL</td></tr>
  <tr><th>Address</th><td>123 High Street, London</td></tr>
  <tr><th>Proposal</th><td>Erection of new dwelling</td></tr>
  <tr><th>Status</th><td>Pending Consideration</td></tr>
</table>
</body></html>
"""

SAMPLE_IDOX_RESULTS = """
<html><body>
<ul id="searchresults">
  <li>
    <a href="/application/123">View</a>
    <p class="metainfo">No: APP/001 <span>received</span></p>
  </li>
  <li>
    <a href="/application/456">View</a>
    <p class="metainfo">No: APP/002 <span>received</span></p>
  </li>
</ul>
</body></html>
"""

SAMPLE_EMPTY = "<html><body><p>No results found</p></body></html>"


class TestPageParser:
    def test_extract_single_fields(self):
        parser = PageParser()
        selectors = {
            "reference": "th:-soup-contains('Reference') + td",
            "address": "th:-soup-contains('Address') + td",
            "description": "th:-soup-contains('Proposal') + td",
        }
        result = parser.extract(SAMPLE_IDOX_DETAIL, selectors)
        assert result["reference"] == "24/01234/FUL"
        assert result["address"] == "123 High Street, London"
        assert result["description"] == "Erection of new dwelling"

    def test_extract_missing_field_returns_none(self):
        parser = PageParser()
        selectors = {
            "reference": "th:-soup-contains('Reference') + td",
            "parish": "th:-soup-contains('Parish') + td",
        }
        result = parser.extract(SAMPLE_IDOX_DETAIL, selectors)
        assert result["reference"] == "24/01234/FUL"
        assert result["parish"] is None

    def test_extract_list(self):
        parser = PageParser()
        selector = "ul#searchresults li a"
        result = parser.extract_list(SAMPLE_IDOX_RESULTS, selector, attr="href")
        assert result == ["/application/123", "/application/456"]

    def test_extract_list_text(self):
        parser = PageParser()
        selector = "ul#searchresults li p.metainfo"
        result = parser.extract_list(SAMPLE_IDOX_RESULTS, selector)
        assert len(result) == 2
        assert "APP/001" in result[0]

    def test_extract_list_empty(self):
        parser = PageParser()
        selector = "ul#searchresults li a"
        result = parser.extract_list(SAMPLE_EMPTY, selector)
        assert result == []

    def test_extract_with_custom_transform(self):
        parser = PageParser()
        selectors = {
            "status": "th:-soup-contains('Status') + td",
        }
        transforms = {
            "status": lambda v: v.lower().replace(" ", "_"),
        }
        result = parser.extract(SAMPLE_IDOX_DETAIL, selectors, transforms=transforms)
        assert result["status"] == "pending_consideration"

    def test_select_one_element(self):
        parser = PageParser()
        element = parser.select_one(SAMPLE_IDOX_DETAIL, "th:-soup-contains('Reference') + td")
        assert element is not None
        assert element.get_text(strip=True) == "24/01234/FUL"

    def test_select_one_missing_returns_none(self):
        parser = PageParser()
        element = parser.select_one(SAMPLE_IDOX_DETAIL, "th:-soup-contains('Parish') + td")
        assert element is None
