"""Idox platform scraper for UK planning authorities.

Idox is the dominant planning portal platform, used by ~250 UK councils.
This module defines the default selectors and the scraper class.
"""

IDOX_SEARCH_SELECTORS = {
    "result_links": "ul#searchresults li.searchresult > a",
    "result_uids": "ul#searchresults li.searchresult p.metainfo > span:first-child",
    "next_page": "a.next",
    "dates_tab": "a#subtab_dates",
    "info_tab": "a#subtab_details",
}

IDOX_SELECTORS = {
    "reference": "th:-soup-contains('Reference') + td",
    "address": "th:-soup-contains('Address') + td",
    "description": "th:-soup-contains('Proposal') + td",
    "status": "th:-soup-contains('Status') + td",
    "alt_reference": "th:-soup-contains('Alternative Reference') + td",
}

IDOX_DATES_SELECTORS = {
    "date_received": "th:-soup-contains('Application Received') + td",
    "date_validated": "th:-soup-contains('Validated') + td",
    "expiry_date": "th:-soup-contains('Expiry Date') + td",
    "target_date": "th:-soup-contains('Target Date') + td",
    "decision_date": "th:-soup-contains('Decision Made Date') + td",
    "consultation_expiry": "th:-soup-contains('Standard Consultation Expiry') + td",
}

IDOX_INFO_SELECTORS = {
    "application_type": "th:-soup-contains('Application Type') + td",
    "case_officer": "th:-soup-contains('Case Officer') + td",
    "parish": "th:-soup-contains('Parish') + td",
    "ward": "th:-soup-contains('Ward') + td",
    "applicant_name": "th:-soup-contains('Applicant Name') + td",
    "agent_name": "th:-soup-contains('Agent Name') + td",
    "decision_level": "th:-soup-contains('Decision Level') + td",
}
