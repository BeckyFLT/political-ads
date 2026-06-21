"""Who we monitor.

Each party we track, its brand colour, and the Facebook page IDs we pull ads
from — one for the party itself and one for its leader (where the leader runs
their own ads). Page IDs were found and verified with ``scripts/find_pages.py``;
to add or change an advertiser, run that helper, copy the right numeric ID here,
then rebuild.

``party`` is the label everything is grouped under on the site. Any ad whose
page ID is listed here is attributed to that party.
"""

PARTIES = [
    {
        "party": "Labour",
        "colour": "#E4003B",
        "pages": {
            "25749647410": "The Labour Party",
            "1586251881644270": "Keir Starmer",
        },
    },
    {
        "party": "Conservative",
        "colour": "#0087DC",
        "pages": {
            "8807334278": "Conservatives",
            "1386296491436207": "Kemi Badenoch",
        },
    },
    {
        "party": "Reform UK",
        "colour": "#12B6CF",
        "pages": {
            "230416667843105": "Reform UK",
            "133737666673845": "Nigel Farage",
        },
    },
    {
        "party": "Liberal Democrats",
        "colour": "#FAA61A",
        "pages": {
            "5883973269": "Liberal Democrats",
            "278256552212142": "Ed Davey",
        },
    },
    {
        "party": "Green",
        "colour": "#6AB023",
        "pages": {
            "20995300784": "Green Party of England and Wales",
            # Zack Polanski has no separate ad-running page yet.
        },
    },
    {
        "party": "SNP",
        "colour": "#FDF38E",
        "pages": {
            "77249349077": "Scottish National Party (SNP)",
            "141848389215355": "John Swinney",
        },
    },
    {
        "party": "Plaid Cymru",
        "colour": "#005B54",
        "pages": {
            "26416930992": "Plaid Cymru",
            "567732343266273": "Rhun ap Iorwerth",
        },
    },
    {
        "party": "Restore Britain",
        "colour": "#0a1640",
        "pages": {
            "610052892200709": "Restore Britain",
            "379417526259248": "Rupert Lowe",
        },
    },
    {
        "party": "Reclaim",
        "colour": "#7B2BB0",
        "pages": {
            "1721275931466984": "The Reclaim Party",
            # Laurence Fox runs ads through the Reclaim Party page.
        },
    },
    {
        "party": "Your Party",
        "colour": "#D40000",
        "pages": {
            # No verified party ad page yet (founded 2025). Tracked for now via
            # co-founder Zarah Sultana's page; add the party page ID here when
            # one appears.
            "104380177666241": "Zarah Sultana MP",
        },
    },
]


def page_to_party():
    """Flat lookup: page_id -> party label."""
    out = {}
    for entry in PARTIES:
        for pid in entry["pages"]:
            out[pid] = entry["party"]
    return out


def all_page_ids():
    ids = []
    for entry in PARTIES:
        ids.extend(entry["pages"].keys())
    return ids


def party_colour():
    return {entry["party"]: entry["colour"] for entry in PARTIES}


# Display order = the order parties are listed above.
PARTY_ORDER = [entry["party"] for entry in PARTIES]
