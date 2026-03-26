#!/usr/bin/env python3
"""Find real planning portal URLs via gov.uk register pages.

For each disabled council:
1. Fetch https://www.gov.uk/search-register-planning-decisions/{slug}
2. Extract the council planning URL
3. Follow that URL to find the actual Idox/PE/SwiftLG portal
4. Update configs with verified URLs

This finds the REAL URLs that actually resolve, not guessed patterns.
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml
from bs4 import BeautifulSoup

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"
REPORT_PATH = Path(__file__).parent.parent / "govuk_discovery_report.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

# Map authority_code to gov.uk slug (when different)
SLUG_MAP = {
    "allerdale": "cumberland",
    "copeland": "cumberland",
    "barrow": "westmorland-and-furness",
    "eden": "westmorland-and-furness",
    "southlakeland": "westmorland-and-furness",
    "daventry": "west-northamptonshire",
    "northampton": "west-northamptonshire",
    "southnorthamptonshire": "west-northamptonshire",
    "kettering": "north-northamptonshire",
    "christchurch": "bournemouth-christchurch-and-poole",
    "poole": "bournemouth-christchurch-and-poole",
    "bournemouth": "bournemouth-christchurch-and-poole",
    "chiltern": "buckinghamshire",
    "southbucks": "buckinghamshire",
    "wycombe": "buckinghamshire",
    "eastdorset": "dorset",
    "northdorset": "dorset",
    "purbeck": "dorset",
    "westdorset": "dorset",
    "weymouth": "dorset",
    "tauntondeane": "somerset",
    "westsomerset": "somerset",
    "sedgemoor": "somerset",
    "shepway": "folkestone-and-hythe",
    "harrogate": "north-yorkshire",
    "isleofwight": "isle-of-wight",
    "hammersmith": "hammersmith-and-fulham",
    "kensington": "kensington-and-chelsea",
    "barking": "barking-and-dagenham",
    "eaststaffordshire": "east-staffordshire",
    "northhertfordshire": "north-hertfordshire",
    "southtyneside": "south-tyneside",
    "southoxfordshire": "south-oxfordshire",
    "southkesteven": "south-kesteven",
    "southholland": "south-holland",
    "southderbyshire": "south-derbyshire",
    "southnorfolk": "south-norfolk",
    "northlincs": "north-lincolnshire",
    "westlindsey": "west-lindsey",
    "westlancashire": "west-lancashire",
    "eastbourne": "lewes-and-eastbourne",  # merged
    "lewes": "lewes-and-eastbourne",
    "stalbans": "st-albans",
    "stoke": "stoke-on-trent",
    "staffordshiremoorlands": "staffordshire-moorlands",
    "nuneaton": "nuneaton-and-bedworth",
    "welwynhatfield": "welwyn-hatfield",
    "greatyarmouth": "great-yarmouth",
    "highpeak": "high-peak",
    "cannockchase": "cannock-chase",
    "whitehorse": "vale-of-white-horse",
    "wyreforest": "wyre-forest",
    "redcar": "redcar-and-cleveland",
    "lakedistrict": "lake-district",
    "northyorkmoors": "north-york-moors",
    "peakdistrict": "peak-district",
    "dartmoor": "dartmoor",
    "exmoor": "exmoor",
    "yorkshiredales": "yorkshire-dales",
    "northumberlandpark": "northumberland",  # national park uses county slug
    "newforestpark": "new-forest",  # national park
    "breconbeacons": "brecon-beacons",
    "snowdonia": "snowdonia",
    "pembrokecoast": "pembrokeshire-coast",
    "blaenaugwent": "blaenau-gwent",
    "rhondda": "rhondda-cynon-taf",
    "flintshire": "flintshire",
    "denbighshire": "denbighshire",
    "carmarthenshire": "carmarthenshire",
    "ceredigion": "ceredigion",
    "anglesey": "isle-of-anglesey",
    "gwynedd": "gwynedd",
    "pembrokeshire": "pembrokeshire",
    "westdunbartonshire": "west-dunbartonshire",
    "clackmannanshire": "clackmannanshire",
    "renfrewshire": "renfrewshire",
    "moray": "moray",
    "molevalley": "mole-valley",
    "blackburn": "blackburn-with-darwen",
    "rochford": "rochford",
    "breckland": "breckland",
    "bracknell": "bracknell-forest",
    "ashfield": "ashfield",
    "bolton": "bolton",
    "boston": "boston",
    "charnwood": "charnwood",
    "crawley": "crawley",
    "erewash": "erewash",
    "fareham": "fareham",
    "guildford": "guildford",
    "haringey": "haringey",
    "hounslow": "hounslow",
    "hyndburn": "hyndburn",
    "islington": "islington",
    "kent": "kent",
    "lancashire": "lancashire",
    "leicestershire": "leicestershire",
    "merton": "merton",
    "middlesbrough": "middlesbrough",
    "norfolk": "norfolk",
    "northdevon": "north-devon",
    "northwarwickshire": "north-warwickshire",
    "nottinghamshire": "nottinghamshire",
    "peterborough": "peterborough",
    "preston": "preston",
    "rugby": "rugby",
    "slough": "slough",
    "suffolk": "suffolk",
    "sunderland": "sunderland",
    "sutton": "sutton",
    "telford": "telford-and-wrekin",
    "warrington": "warrington",
    "waverley": "waverley",
    "worcestershire": "worcestershire",
    "wychavon": "wychavon",
    "barnsley": "barnsley",
    "bromley": "bromley",
    "camden": "camden",
    "dorset": "dorset",
    "eastsussex": "east-sussex",
    "eastleigh": "eastleigh",
    "fenland": "fenland",
    "gloucestershire": "gloucestershire",
    "hampshire": "hampshire",
    "harrow": "harrow",
    "hartlepool": "hartlepool",
    "havant": "havant",
    "havering": "havering",
    "hillingdon": "hillingdon",
    "medway": "medway",
    "norwich": "norwich",
    "rochdale": "rochdale",
    "rotherham": "rotherham",
    "salford": "salford",
    "staffordshire": "staffordshire",
    "swindon": "swindon",
    "walsall": "walsall",
    "walthamforest": "waltham-forest",
    "warwickshire": "warwickshire",
    "wirral": "wirral",
    "wokingham": "wokingham",
    "worcester": "worcester",
    "wrexham": "wrexham",
}


def get_disabled_idox():
    """Get disabled councils that we think should be Idox."""
    disabled = {}
    for f in sorted(CONFIG_DIR.glob("*.yml")):
        data = yaml.safe_load(f.read_text())
        if data.get("enabled") is False and data.get("platform") in ("idox", "swiftlg", "planning_explorer"):
            disabled[data["authority_code"]] = data
    return disabled


async def fetch_govuk_url(client, slug):
    """Fetch the planning portal URL from gov.uk."""
    url = f"https://www.gov.uk/search-register-planning-decisions/{slug}"
    try:
        resp = await client.get(url, follow_redirects=True, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Find the link to the council's planning page
            link = soup.find("a", class_="gem-c-button")
            if link and link.get("href"):
                return link["href"]
            # Try other link patterns
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http") and "gov.uk/search-register" not in href:
                    return href
    except Exception:
        pass
    return None


async def check_for_idox(client, base_url):
    """Given a council URL, try to find the Idox portal."""
    parsed = urlparse(base_url)
    domain = parsed.hostname or ""

    # Common Idox subdomain patterns
    candidates = []
    parts = domain.split(".")
    if len(parts) >= 2:
        base_domain = ".".join(parts[-2:])
        if base_domain == "gov.uk" and len(parts) >= 3:
            base_domain = ".".join(parts[-3:])
        for prefix in ["publicaccess", "planning", "pa", "idoxpa", "eplanning",
                        "planningonline", "plan", "planningpa", "planapp",
                        "eforms", "apps", "development", "planningrecords",
                        "searchapplications", "emaps", "portal"]:
            candidates.append(f"https://{prefix}.{base_domain}/online-applications")
        # Also try www subdomain path
        candidates.append(f"https://www.{base_domain}/online-applications")
        candidates.append(f"https://{base_domain}/online-applications")

    # And the direct URL path
    candidates.append(f"{base_url.rstrip('/')}/online-applications")

    for candidate in candidates[:20]:
        search_url = candidate.rstrip("/") + "/search.do?action=advanced"
        try:
            resp = await client.get(search_url, follow_redirects=True, timeout=12)
            if resp.status_code == 200 and ("advancedSearchForm" in resp.text or "searchCriteriaForm" in resp.text):
                return str(resp.url).split("/search.do")[0]
        except Exception:
            continue

    return None


async def main():
    disabled = get_disabled_idox()
    print(f"Disabled councils to check: {len(disabled)}")

    results = {"found": [], "not_found": []}
    sem = asyncio.Semaphore(5)

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        for i, (code, data) in enumerate(sorted(disabled.items())):
            async with sem:
                slug = SLUG_MAP.get(code, code)
                label = f"[{i+1}/{len(disabled)}]"

                # Step 1: Get council URL from gov.uk
                govuk_url = await fetch_govuk_url(client, slug)
                if not govuk_url:
                    print(f"{label} {code}: no gov.uk page for slug '{slug}'")
                    results["not_found"].append({"authority_code": code, "name": data["name"], "reason": "no gov.uk page"})
                    continue

                # Step 2: Try to find Idox portal from that domain
                idox_url = await check_for_idox(client, govuk_url)
                if idox_url:
                    print(f"{label} {code}: FOUND idox -> {idox_url}")
                    results["found"].append({
                        "authority_code": code,
                        "name": data["name"],
                        "platform": "idox",
                        "url": idox_url,
                        "govuk_url": govuk_url,
                    })
                else:
                    print(f"{label} {code}: gov.uk -> {govuk_url} (no Idox found)")
                    results["not_found"].append({
                        "authority_code": code,
                        "name": data["name"],
                        "govuk_url": govuk_url,
                    })

                await asyncio.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"Found: {len(results['found'])}")
    print(f"Not found: {len(results['not_found'])}")

    with open(REPORT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Report: {REPORT_PATH}")


def apply():
    """Apply found URLs to configs."""
    with open(REPORT_PATH) as f:
        report = json.load(f)

    count = 0
    for item in report["found"]:
        code = item["authority_code"]
        config_path = CONFIG_DIR / f"{code}.yml"
        if not config_path.exists():
            continue
        data = yaml.safe_load(config_path.read_text())
        data["base_url"] = item["url"]
        data["platform"] = item["platform"]
        data["enabled"] = True
        config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        count += 1
        print(f"  {code}: {item['url']}")

    print(f"\nUpdated {count} configs")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        apply()
    else:
        asyncio.run(main())
