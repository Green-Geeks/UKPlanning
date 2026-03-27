# Prompt: Reverse-Engineer Remaining Planning Council Scrapers

Use this prompt to continue enabling the remaining 55 disabled UK planning councils one at a time.

---

## Prompt to paste:

```
Pick up from memory. We have 378/433 UK planning councils enabled (87%) with 14 platform scrapers. 55 councils remain disabled — each uses a unique bespoke system.

Your task: pick the next disabled council, reverse-engineer its planning search, and build a scraper. Work through them one at a time.

For each council:

1. Read its config from `src/config/councils/{code}.yml` to get the base_url
2. Use httpx to GET the URL and analyze the HTML — look for:
   - Forms with date fields (POST with ViewState for ASP.NET)
   - JSON APIs (check Network tab patterns, look for `/api/`, `Handler.ashx`, fetch() calls)
   - Weekly list pages (often at /Planning/WeeklyList or /weekly)
   - RSS feeds
   - The /Search/Standard endpoint (planning-register.co.uk pattern)
3. If httpx doesn't reveal the search mechanism, use Playwright to:
   - Load the page and intercept all network requests
   - Fill search fields and click submit
   - Capture any JSON API calls
4. Build the scraper in `src/platforms/{code}.py` following the pattern of existing scrapers
5. Register it in `src/scheduler/registry.py`
6. Update the council YAML to `enabled: true` with the correct platform
7. Test it, run `python3 -m pytest tests/`, commit

Key patterns that worked this session:
- **Planning Register bypass**: /Search/Standard?SearchType=Planning&AcknowledgeLetterDateFrom=... bypasses reCAPTCHA
- **ASP.NET ViewState**: GET page → extract hidden fields → POST with dates (Fareham pattern)
- **Aura replay**: Extract fwuid from bootstrap URL, POST to /s/sfsites/aura (Salesforce pattern)
- **Weekly list scraping**: Parse HTML tables from weekly list pages when detail pages are blocked (Tascomi/Barnsley pattern)
- **JSON API discovery**: Use Playwright to intercept network requests, then replay with httpx
- **Accept: application/json header**: Some endpoints return HTML by default but JSON with this header (Civica)

Skip these councils (10) — they don't have scrapeable portals:
- alderney, sark, guernsey, jersey, isleofman, scillyisles (crown dependencies)
- londonlegacy, northamptonshire (defunct/merged)
- nip (national infrastructure inspectorate)
- midulster (not on NI portal yet)

Start with whichever council you think is most likely to crack quickly based on the notes in memory/project_status.md.
```

---

## Tips for efficiency:

- **Batch similar platforms**: If you crack one Civica council (stalbans/ashfield), the same approach works for both
- **Check Agile first**: The 4 remaining Agile councils (exmoor, islington, pembrokecoast, yorkshiredales) might be on a different API host — try intercepting with Playwright
- **Salesforce 3**: anglesey, carmarthenshire, southderbyshire need the fwuid extraction but may have different page paths or register names
- **Don't spend more than 15 mins per council** — if it's not cracking, mark it as investigated and move on
- **Commit after each council** to preserve progress
