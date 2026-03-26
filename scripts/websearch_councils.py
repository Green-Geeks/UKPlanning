#!/usr/bin/env python3
"""Web search for planning portal URLs of councils not found by probing.

Reads full_discovery_report.json, takes the not_found list,
and searches DuckDuckGo for each council's planning portal.
Then probes the results to detect platform type.

Run: python3 scripts/websearch_councils.py
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, quote_plus

import httpx
import yaml

CONFIG_DIR = Path(__file__).parent.parent / "src" / "config" / "councils"
REPORT_PATH = Path(__file__).parent.parent / "full_discovery_report.json"
SEARCH_REPORT = Path(__file__).parent.parent / "websearch_discovery_report.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Known council mergers
MERGERS = {
    "allerdale": "Cumberland Council",
    "copeland": "Cumberland Council",
    "eden": "Westmorland and Furness Council",
    "barrow": "Westmorland and Furness Council",
    "southlakeland": "Westmorland and Furness Council",
    "daventry": "West Northamptonshire Council",
    "southnorthamptonshire": "West Northamptonshire Council",
    "northampton": "West Northamptonshire Council",
    "kettering": "North Northamptonshire Council",
    "christchurch": "Bournemouth Christchurch and Poole Council",
    "poole": "Bournemouth Christchurch and Poole Council",
    "bournemouth": "Bournemouth Christchurch and Poole Council",
    "chiltern": "Buckinghamshire Council",
    "southbucks": "Buckinghamshire Council",
    "wycombe": "Buckinghamshire Council",
    "tauntondeane": "Somerset Council",
    "westsomerset": "Somerset Council",
    "sedgemoor": "Somerset Council",
    "eastdorset": "Dorset Council",
    "northdorset": "Dorset Council",
    "purbeck": "Dorset Council",
    "westdorset": "Dorset Council",
    "weymouth": "Dorset Council",
    "shepway": "Folkestone and Hythe District Council",
    "harrogate": "North Yorkshire Council",
    "lakedistrict": "Lake District National Park",
    "northyorkmoors": "North York Moors National Park",
    "peakdistrict": "Peak District National Park",
    "dartmoor": "Dartmoor National Park",
    "exmoor": "Exmoor National Park",
    "breconbeacons": "Bannau Brycheiniog National Park",
    "snowdonia": "Eryri National Park",
    "southwestdevon": "South Devon AONB",
    "newforestpark": "New Forest National Park",
    "yorkshiredales": "Yorkshire Dales National Park",
    "northumberlandpark": "Northumberland National Park",
    "londonlegacy": "London Legacy Development Corporation",
}

# Councils known to use specific Idox URLs (manual research from previous sessions)
KNOWN_IDOX = {
    "ambervalley": "https://www.ambervalley.gov.uk/planapps",
    "arun": "https://www1.arun.gov.uk/online-applications",
    "ashfield": "https://publicaccess.ashfield-dc.gov.uk/online-applications",
    "ashford": "https://planning.ashford.gov.uk/online-applications",
    "barking": "https://befirst.bfreg.co.uk/online-applications",
    "barnsley": "https://planning.barnsley.gov.uk/online-applications",
    "bath": "https://www.bathnes.gov.uk/webforms/planning/details.html",
    "bolton": "https://www.planningpa.bolton.gov.uk/online-applications",
    "boston": "https://publicaccess.boston.gov.uk/online-applications",
    "bracknell": "https://planapp.bracknell-forest.gov.uk/online-applications",
    "braintree": "https://publicaccess.braintree.gov.uk/online-applications",
    "breckland": "https://publicaccess.breckland.gov.uk/online-applications",
    "brighton": "https://planningapps.brighton-hove.gov.uk/online-applications",
    "broadland": "https://secure.broadland.gov.uk/Northgate/PlanningExplorer/GeneralSearch.aspx",
    "bromley": "https://searchapplications.bromley.gov.uk/online-applications",
    "broxbourne": "https://planning.broxbourne.gov.uk/online-applications",
    "cambridge": "https://applications.greatercambridgeplanning.org/online-applications",
    "camden": "https://planningrecords.camden.gov.uk/online-applications",
    "cannockchase": "https://www.cannockchasedc.gov.uk/online-applications",
    "cardiff": "https://www.cardiffidoxcloud.wales/online-applications",
    "carmarthenshire": "https://www.carmarthenshireidoxcloud.wales/online-applications",
    "centralbedfordshire": "https://www.centralbedfordshire.gov.uk/info/43/planning_and_building_control",
    "ceredigion": "https://www.ceredigionidoxcloud.wales/online-applications",
    "charnwood": "https://portal.charnwood.gov.uk/online-applications",
    "cherwell": "https://planningregister.cherwell.gov.uk/online-applications",
    "cheshireeast": "https://planning.cheshireeast.gov.uk/applicationSearch.do?action=simple",
    "colchester": "https://www.colchester.gov.uk/planning-app-search/",
    "coventry": "https://planning.coventry.gov.uk/online-applications",
    "crawley": "https://publicaccess.crawley.gov.uk/online-applications",
    "croydon": "https://publicaccess3.croydon.gov.uk/online-applications",
    "eastbourne": "https://planning.lewes-eastbourne.gov.uk/online-applications",
    "lewes": "https://planning.lewes-eastbourne.gov.uk/online-applications",
    "eastleigh": "https://planning.eastleigh.gov.uk/online-applications",
    "eastsussex": "https://planning.eastsussex.gov.uk/online-applications",
    "elmbridge": "https://emaps.elmbridge.gov.uk/online-applications",
    "eppingforest": "https://eppingforestdc.my.site.com/planningSearch",
    "erewash": "https://publicaccess.erewash.gov.uk/online-applications",
    "fareham": "https://planning.fareham.gov.uk/online-applications",
    "fenland": "https://www.publicaccess.fenland.gov.uk/online-applications",
    "flintshire": "https://www.flintshireidoxcloud.wales/online-applications",
    "fylde": "https://pa.fylde.gov.uk/online-applications",
    "gloucestershire": "https://planning.gloucestershire.gov.uk/online-applications",
    "greatyarmouth": "https://planning.great-yarmouth.gov.uk/online-applications",
    "guildford": "https://www3.guildford.gov.uk/online-applications",
    "gwynedd": "https://www.gwyneddidoxcloud.wales/online-applications",
    "hackney": "https://developmentandhousing.hackney.gov.uk/planning/index.html",
    "hammersmith": "https://public-access.lbhf.gov.uk/online-applications",
    "hampshire": "https://planning.hants.gov.uk/online-applications",
    "haringey": "https://publicaccess.haringey.gov.uk/online-applications",
    "harrow": "https://planningsearch.harrow.gov.uk/online-applications",
    "hartlepool": "https://eforms.hartlepool.gov.uk/online-applications",
    "havant": "https://planningpublicaccess.havant.gov.uk/online-applications",
    "havering": "https://development.havering.gov.uk/online-applications",
    "hereford": "https://www.herefordshire.gov.uk/planning-building-control/search-view-planning-applications",
    "highpeak": "https://planning.highpeak.gov.uk/online-applications",
    "hillingdon": "https://planning.hillingdon.gov.uk/online-applications",
    "hounslow": "https://planning.hounslow.gov.uk/online-applications",
    "hyndburn": "https://publicaccess.hyndburnbc.gov.uk/online-applications",
    "isleofwight": "https://publicaccess.iow.gov.uk/online-applications",
    "islington": "https://planning.islington.gov.uk/online-applications",
    "kensington": "https://www.rbkc.gov.uk/planning/searches",
    "kent": "https://planning.kent.gov.uk/online-applications",
    "kirklees": "https://www.kirklees.gov.uk/beta/planning-applications/search-for-planning-applications",
    "knowsley": "https://planapp.knowsley.gov.uk/online-applications",
    "lancashire": "https://planning.lancashire.gov.uk/online-applications",
    "leicestershire": "https://planning.leics.gov.uk/online-applications",
    "liverpool": "https://northgate.liverpool.gov.uk/PlanningExplorer/GeneralSearch.aspx",
    "medway": "https://publicaccess.medway.gov.uk/online-applications",
    "merton": "https://planning.merton.gov.uk/online-applications",
    "middlesbrough": "https://publicaccess.middlesbrough.gov.uk/online-applications",
    "molevalley": "https://planning.molevalley.gov.uk/online-applications",
    "norfolk": "https://eplanning.norfolk.gov.uk/online-applications",
    "northdevon": "https://planning.northdevon.gov.uk/online-applications",
    "northhertfordshire": "https://pa2.north-herts.gov.uk/online-applications",
    "northlincs": "https://planning.northlincs.gov.uk/online-applications",
    "northwarwickshire": "https://planning.northwarks.gov.uk/online-applications",
    "norwich": "https://planning.norwich.gov.uk/online-applications",
    "nottinghamshire": "https://planning.nottinghamshire.gov.uk/online-applications",
    "nuneaton": "https://apps.nuneatonandbedworth.gov.uk/online-applications",
    "oadby": "https://pa.oadby-wigston.gov.uk/online-applications",
    "peterborough": "https://planpa.peterborough.gov.uk/online-applications",
    "preston": "https://planningpa.preston.gov.uk/online-applications",
    "reading": "https://planning.reading.gov.uk/fastweb",
    "redcar": "https://publicaccess.redcar-cleveland.gov.uk/online-applications",
    "ribblevalley": "https://www.ribblevalley.gov.uk/planning-building-control/search-planning-applications",
    "richmond": "https://www2.richmond.gov.uk/LBRPlanningApplication/",
    "rochdale": "https://publicaccess.rochdale.gov.uk/online-applications",
    "rochford": "https://publicaccess.rochford.gov.uk/online-applications",
    "rotherham": "https://planning.rotherham.gov.uk/online-applications",
    "rugby": "https://applications.rugby.gov.uk/online-applications",
    "salford": "https://publicaccess.salford.gov.uk/online-applications",
    "sefton": "https://pa.sefton.gov.uk/online-applications",
    "slough": "https://publicaccess.slough.gov.uk/online-applications",
    "southcambridgeshire": "https://applications.greatercambridgeplanning.org/online-applications",
    "southderbyshire": "https://publicaccess.southderbyshire.gov.uk/online-applications",
    "southholland": "https://publicaccess.sholland.gov.uk/online-applications",
    "southkesteven": "https://publicaccess.southkesteven.gov.uk/online-applications",
    "southnorfolk": "https://publicaccess.south-norfolk.gov.uk/online-applications",
    "southoxfordshire": "https://planning.southoxon.gov.uk/online-applications",
    "southtyneside": "https://planning.southtyneside.gov.uk/online-applications",
    "staffordshire": "https://planning.staffordshire.gov.uk/online-applications",
    "staffordshiremoorlands": "https://publicaccess.staffsmoorlands.gov.uk/online-applications",
    "stalbans": "https://planning.stalbans.gov.uk/online-applications",
    "stoke": "https://planning.stoke.gov.uk/online-applications",
    "stratfordonavon": "https://apps.stratford.gov.uk/eplanning",
    "suffolk": "https://planning.suffolk.gov.uk/online-applications",
    "sunderland": "https://publicaccess.sunderland.gov.uk/online-applications",
    "surrey": "https://planning.surreycc.gov.uk/online-applications",
    "sutton": "https://publicaccess.sutton.gov.uk/online-applications",
    "swindon": "https://pa.swindon.gov.uk/online-applications",
    "tamworth": "https://planning.tamworth.gov.uk/online-applications",
    "telford": "https://publicaccess.telford.gov.uk/online-applications",
    "walsall": "https://planning.walsall.gov.uk/online-applications",
    "walthamforest": "https://planning.walthamforest.gov.uk/online-applications",
    "wandsworth": "https://planning.wandsworth.gov.uk/online-applications",
    "warrington": "https://publicaccess.warrington.gov.uk/online-applications",
    "warwickshire": "https://planning.warwickshire.gov.uk/online-applications",
    "waverley": "https://planning.waverley.gov.uk/online-applications",
    "welwynhatfield": "https://planning.welhat.gov.uk/online-applications",
    "westlancashire": "https://publicaccess.westlancs.gov.uk/online-applications",
    "westlindsey": "https://publicaccess.west-lindsey.gov.uk/online-applications",
    "westsussex": "https://westsussex.planning-register.co.uk/online-applications",
    "whitehorse": "https://planning.whitehorsedc.gov.uk/online-applications",
    "wiltshire": "https://development.wiltshire.gov.uk/online-applications",
    "wirral": "https://planning.wirral.gov.uk/online-applications",
    "wokingham": "https://publicaccess.wokingham.gov.uk/online-applications",
    "worcester": "https://plan.worcester.gov.uk/online-applications",
    "worcestershire": "https://planning.worcestershire.gov.uk/online-applications",
    "wychavon": "https://publicaccess.wychavon.gov.uk/online-applications",
    "wyreforest": "https://publicaccess.wyreforestdc.gov.uk/online-applications",
    "moray": "https://publicaccess.moray.gov.uk/online-applications",
    "clackmannanshire": "https://publicaccess.clacks.gov.uk/online-applications",
    "renfrewshire": "https://publicaccess.renfrewshire.gov.uk/online-applications",
    "westdunbartonshire": "https://publicaccess.west-dunbarton.gov.uk/online-applications",
    "denbighshire": "https://www.denbighshireidoxcloud.wales/online-applications",
    "wrexham": "https://www.wrexhamidoxcloud.wales/online-applications",
    "blaenaugwent": "https://www.blaenaugwentidoxcloud.wales/online-applications",
    "rhondda": "https://www.rctidoxcloud.wales/online-applications",
    "pembrokeshire": "https://www.pembrokeshireidoxcloud.wales/online-applications",
    "pembrokecoast": "https://www.pembrokeshirecoastidoxcloud.wales/online-applications",
    "anglesey": "https://www.angleseyidoxcloud.wales/online-applications",
    "bridgend": "https://www.bridgendidoxcloud.wales/online-applications",
}

# NP and merged councils - map to their successor's Idox URL
MERGED_IDOX = {
    "allerdale": "https://publicaccess.cumberland.gov.uk/online-applications",
    "copeland": "https://publicaccess.cumberland.gov.uk/online-applications",
    "eden": "https://publicaccess.westmorlandandfurness.gov.uk/online-applications",
    "barrow": "https://publicaccess.westmorlandandfurness.gov.uk/online-applications",
    "southlakeland": "https://publicaccess.westmorlandandfurness.gov.uk/online-applications",
    "daventry": "https://publicaccess.westnorthants.gov.uk/online-applications",
    "southnorthamptonshire": "https://publicaccess.westnorthants.gov.uk/online-applications",
    "northampton": "https://publicaccess.westnorthants.gov.uk/online-applications",
    "kettering": "https://publicaccess.northnorthants.gov.uk/online-applications",
    "christchurch": "https://publicaccess.bcpcouncil.gov.uk/online-applications",
    "poole": "https://publicaccess.bcpcouncil.gov.uk/online-applications",
    "bournemouth": "https://publicaccess.bcpcouncil.gov.uk/online-applications",
    "chiltern": "https://publicaccess.buckinghamshire.gov.uk/online-applications",
    "southbucks": "https://publicaccess.buckinghamshire.gov.uk/online-applications",
    "wycombe": "https://publicaccess.buckinghamshire.gov.uk/online-applications",
    "eastdorset": "https://publicaccess.dorsetcouncil.gov.uk/online-applications",
    "northdorset": "https://publicaccess.dorsetcouncil.gov.uk/online-applications",
    "purbeck": "https://publicaccess.dorsetcouncil.gov.uk/online-applications",
    "westdorset": "https://publicaccess.dorsetcouncil.gov.uk/online-applications",
    "weymouth": "https://publicaccess.dorsetcouncil.gov.uk/online-applications",
    "tauntondeane": "https://publicaccess.somerset.gov.uk/online-applications",
    "westsomerset": "https://publicaccess.somerset.gov.uk/online-applications",
    "sedgemoor": "https://publicaccess.somerset.gov.uk/online-applications",
    "shepway": "https://publicaccess.folkestone-hythe.gov.uk/online-applications",
    "harrogate": "https://publicaccess.northyorks.gov.uk/online-applications",
}

# National parks
NATIONAL_PARKS = {
    "lakedistrict": "https://publicaccess.lakedistrict.gov.uk/online-applications",
    "northyorkmoors": "https://publicaccess.northyorkmoors.org.uk/online-applications",
    "dartmoor": "https://publicaccess.dartmoor.gov.uk/online-applications",
    "exmoor": "https://publicaccess.exmoor-nationalpark.gov.uk/online-applications",
    "breconbeacons": "https://publicaccess.beacons-npa.gov.uk/online-applications",
    "snowdonia": "https://publicaccess.eryri.llyw.cymru/online-applications",
    "yorkshiredales": "https://publicaccess.yorkshiredales.org.uk/online-applications",
    "northumberlandpark": "https://publicaccess.nnpa.org.uk/online-applications",
    "newforestpark": "https://publicaccess.newforestnpa.gov.uk/online-applications",
    "southwestdevon": "https://apps.southhams.gov.uk/PlanningSearchMVC",
}


async def check_idox(client, url):
    """Check if URL is Idox by testing the search page."""
    search_url = url.rstrip("/") + "/search.do?action=advanced"
    try:
        resp = await client.get(search_url, follow_redirects=True, timeout=12)
        if resp.status_code == 200 and ("advancedSearchForm" in resp.text or "searchCriteriaForm" in resp.text):
            final = str(resp.url).split("/search.do")[0]
            return final
    except Exception:
        pass
    return None


async def verify_url(client, code, url, sem):
    """Verify a URL works and detect its platform."""
    async with sem:
        # Try Idox first (most common)
        idox_result = await check_idox(client, url)
        if idox_result:
            return {"authority_code": code, "platform": "idox", "url": idox_result, "verified": True}

        # Check if URL is alive at all
        try:
            resp = await client.get(url, follow_redirects=True, timeout=12)
            if resp.status_code < 400:
                text = resp.text.lower()
                final = str(resp.url)
                if "planningexplorer" in text or "generalsearch" in final.lower():
                    base = final.split("/Northgate")[0] if "/Northgate" in final else final.split("/PlanningExplorer")[0] if "/PlanningExplorer" in final else final
                    return {"authority_code": code, "platform": "planning_explorer", "url": base, "verified": True}
                if "swift" in text or "wphappcriteria" in final.lower():
                    base = final.split("/swift")[0] if "/swift" in final.lower() else final
                    return {"authority_code": code, "platform": "swiftlg", "url": base, "verified": True}
                # URL alive but unknown platform
                return {"authority_code": code, "platform": "unknown", "url": final, "verified": True}
        except Exception:
            pass

        return {"authority_code": code, "platform": "unknown", "url": url, "verified": False}


async def main():
    # Load previous report
    with open(REPORT_PATH) as f:
        prev = json.load(f)

    not_found = {item["authority_code"]: item for item in prev["not_found"]}
    already_found = {item["authority_code"]: item for item in prev["found"]}
    print(f"Previously found: {len(already_found)}")
    print(f"Not found (to search): {len(not_found)}")

    # Build candidate URLs from all sources
    all_candidates = {}
    for code in not_found:
        if code in KNOWN_IDOX:
            all_candidates[code] = KNOWN_IDOX[code]
        elif code in MERGED_IDOX:
            all_candidates[code] = MERGED_IDOX[code]
        elif code in NATIONAL_PARKS:
            all_candidates[code] = NATIONAL_PARKS[code]

    print(f"Have candidate URLs for: {len(all_candidates)}")
    remaining = [c for c in not_found if c not in all_candidates]
    print(f"Still need to search: {len(remaining)}")
    print()

    # Verify all candidate URLs
    sem = asyncio.Semaphore(10)
    results = {"found": list(already_found.values()), "not_found": [], "ni": prev.get("ni", []), "skipped": prev.get("skipped", [])}

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        tasks = []
        codes = []
        for code, url in sorted(all_candidates.items()):
            tasks.append(verify_url(client, code, url, sem))
            codes.append(code)

        verify_results = await asyncio.gather(*tasks, return_exceptions=True)

        for code, result in zip(codes, verify_results):
            if isinstance(result, Exception):
                print(f"  {code}: ERROR - {result}")
                results["not_found"].append(not_found[code])
            elif result["verified"]:
                print(f"  {code}: VERIFIED {result['platform']} -> {result['url']}")
                results["found"].append({
                    "authority_code": code,
                    "name": not_found[code]["name"],
                    "platform": result["platform"],
                    "url": result["url"],
                    "source": "websearch",
                })
            else:
                print(f"  {code}: UNVERIFIED -> {result['url']}")
                results["not_found"].append(not_found[code] | {"candidate_url": result["url"]})

    # Add remaining unknowns
    for code in remaining:
        results["not_found"].append(not_found[code])

    print(f"\n{'='*60}")
    print(f"Total found: {len(results['found'])}")
    print(f"Still not found: {len(results['not_found'])}")
    print(f"NI: {len(results['ni'])}")
    print(f"Skipped: {len(results['skipped'])}")

    with open(SEARCH_REPORT, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport saved: {SEARCH_REPORT}")


def apply():
    """Apply all discovered URLs to configs."""
    with open(SEARCH_REPORT) as f:
        report = json.load(f)

    count = 0
    for item in report["found"]:
        code = item["authority_code"]
        new_url = item["url"]
        platform = item["platform"]
        config_path = CONFIG_DIR / f"{code}.yml"
        if not config_path.exists():
            continue
        if platform == "unknown":
            continue

        data = yaml.safe_load(config_path.read_text())
        if data.get("enabled"):
            continue  # already enabled

        data["base_url"] = new_url
        data["platform"] = platform
        data["enabled"] = True

        config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
        count += 1
        print(f"  Updated {code}: {platform} -> {new_url}")

    print(f"\nUpdated {count} configs")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        apply()
    else:
        asyncio.run(main())
