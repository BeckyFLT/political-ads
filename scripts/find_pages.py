#!/usr/bin/env python3
"""Discover the Facebook page IDs for each party and leader.

The Meta Ad Library lets you pull every ad a *page* has run, but you have to
know that page's numeric ID. This helper searches the Ad Library for each name
we care about and prints the candidate pages, ranked by how many of their ads
match, so a human can pick the real official page and paste its ID into
``advertisers.py``.

Run:  python3 scripts/find_pages.py
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_VERSION = "v21.0"

# What to search for. We search both the party and its leader so we can grab
# both pages in one pass.
SEARCHES = [
    "The Labour Party", "Keir Starmer",
    "Conservatives", "Kemi Badenoch",
    "Reform UK", "Nigel Farage",
    "Liberal Democrats", "Ed Davey",
    "Green Party", "Zack Polanski",
    "Scottish National Party", "John Swinney",
    "Plaid Cymru", "Rhun ap Iorwerth",
    "Restore Britain", "Rupert Lowe",
    "Reclaim Party", "Laurence Fox",
    "Your Party", "Jeremy Corbyn", "Zarah Sultana",
]


def get_token():
    tok = os.environ.get("FB_TOKEN")
    if tok:
        return tok.strip()
    path = os.path.join(HERE, "fb_token.txt")
    if os.path.exists(path):
        return open(path).read().strip()
    sys.exit("No token found: set FB_TOKEN or create fb_token.txt")


def search(token, term, limit_pages=3):
    """Return {page_id: (page_name, count)} for one search term."""
    params = {
        "search_terms": term,
        "ad_reached_countries": "GB",
        "ad_active_status": "ALL",
        "ad_type": "POLITICAL_AND_ISSUE_ADS",
        "fields": "id,page_id,page_name",
        "limit": "100",
        "access_token": token,
    }
    url = "https://graph.facebook.com/%s/ads_archive?%s" % (
        API_VERSION, urllib.parse.urlencode(params))
    counts = defaultdict(int)
    names = {}
    pages_fetched = 0
    while url and pages_fetched < limit_pages:
        with urllib.request.urlopen(url) as resp:
            payload = json.load(resp)
        if "error" in payload:
            print("  API error: %s" % payload["error"].get("message"))
            break
        for a in payload.get("data", []):
            pid = a.get("page_id")
            if not pid:
                continue
            counts[pid] += 1
            names[pid] = a.get("page_name", "")
        url = payload.get("paging", {}).get("next")
        pages_fetched += 1
    return {pid: (names[pid], counts[pid]) for pid in counts}


def main():
    token = get_token()
    for term in SEARCHES:
        print("\n=== %s ===" % term)
        results = search(token, term)
        ranked = sorted(results.items(), key=lambda kv: -kv[1][1])
        for pid, (name, count) in ranked[:6]:
            print("  %-20s  %3d ads  %s" % (pid, count, name))


if __name__ == "__main__":
    main()
