#!/usr/bin/env python3
"""Political Ads Monitor — build the site.

Pulls every ad run by the parties and leaders listed in ``advertisers.py`` from
Meta's (Facebook/Instagram) public Ad Library, groups them by party, totals the
spend over the last 90 days, writes a short daily summary, and renders a single
static page (``index.html``) plus a downloadable spreadsheet (``data/ads.csv``).

Run twice a day by the GitHub Action in ``.github/workflows/update.yml``. Run by
hand with:  python3 scripts/build.py

If the Facebook token is missing or the fetch fails, it falls back to the last
saved data in ``data/ads.json`` so the page can still be rebuilt offline.
"""
import csv
import datetime
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import advertisers as adv

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(HERE, "data")
API_VERSION = "v21.0"
COUNTRY = "GB"

# Spend window shown on the site. Start at 30; because every run merges new ads
# into data/ads.json (see merge_history), the stored dataset grows over time, so
# this can be bumped toward 90 once we've been collecting for a few weeks.
WINDOW_DAYS = 30
FETCH_DAYS = 30          # how far back we ask Meta for each run
HISTORY_KEEP_DAYS = 120  # how long a stored ad is kept before being pruned

# Pacing, to stay inside Meta's ~200 calls/hour and avoid the cost-based
# throttle (error 613). All sleeps are inside this script, not the shell.
PAGE_BATCH = 10          # page IDs per request (Meta allows up to 10)
SLEEP_BETWEEN_PAGES = 2  # seconds between paginated requests
SLEEP_BETWEEN_BATCHES = 5
THROTTLE_BACKOFF = 60    # seconds to wait after an error 613
MAX_RETRIES = 4

SITE_TITLE = "UK Political Ads Monitor"

PAGE_TO_PARTY = adv.page_to_party()
PARTY_COLOUR = adv.party_colour()
PARTY_ORDER = adv.PARTY_ORDER


# --- Facebook token ----------------------------------------------------

def get_token():
    tok = os.environ.get("FB_TOKEN")
    if tok:
        return tok.strip()
    path = os.path.join(HERE, "fb_token.txt")
    if os.path.exists(path):
        return open(path).read().strip()
    return None


# --- Fetch from the Ad Library -----------------------------------------

def _get_json(url):
    """Fetch one page, retrying with a back-off when Meta throttles (613)."""
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(url) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            if e.code == 400 and ("613" in body or "request limit" in body.lower()):
                print("  throttled (613); waiting %ds..." % THROTTLE_BACKOFF, flush=True)
                time.sleep(THROTTLE_BACKOFF)
                continue
            raise
        err = payload.get("error")
        if err:
            code = err.get("code")
            if code in (613, 4, 17, 32, 80004):  # rate/throttle codes
                print("  throttled (code %s); waiting %ds..." % (code, THROTTLE_BACKOFF), flush=True)
                time.sleep(THROTTLE_BACKOFF)
                continue
            raise RuntimeError("API error: %s" % err.get("message"))
        return payload
    raise RuntimeError("Gave up after %d throttled retries" % MAX_RETRIES)


def fetch_for_pages(token, page_ids, date_min):
    """Pull ads run by the given page IDs since date_min, batched and paced."""
    fields = ",".join([
        "id", "page_id", "page_name", "ad_creative_bodies",
        "ad_delivery_start_time", "ad_delivery_stop_time",
        "spend", "impressions", "publisher_platforms",
    ])
    ads = []
    batches = [page_ids[i:i + PAGE_BATCH] for i in range(0, len(page_ids), PAGE_BATCH)]
    for bi, batch in enumerate(batches):
        params = {
            "search_page_ids": ",".join(batch),
            "ad_reached_countries": COUNTRY,
            "ad_active_status": "ALL",
            "ad_type": "POLITICAL_AND_ISSUE_ADS",
            "ad_delivery_date_min": date_min,
            "fields": fields,
            "limit": "100",
            "access_token": token,
        }
        url = "https://graph.facebook.com/%s/ads_archive?%s" % (
            API_VERSION, urllib.parse.urlencode(params))
        print("  batch %d/%d (%d pages)..." % (bi + 1, len(batches), len(batch)), flush=True)
        page_n = 0
        while url:
            payload = _get_json(url)
            ads.extend(payload.get("data", []))
            url = payload.get("paging", {}).get("next")
            page_n += 1
            if url:
                time.sleep(SLEEP_BETWEEN_PAGES)
        if bi + 1 < len(batches):
            time.sleep(SLEEP_BETWEEN_BATCHES)
    return ads


# --- Clean ads into rows -----------------------------------------------

def midpoint(rng):
    """Midpoint of a Meta {lower_bound, upper_bound} range, as a number."""
    if not rng:
        return 0.0
    lo = float(rng.get("lower_bound") or 0)
    hi = rng.get("upper_bound")
    hi = float(hi) if hi not in (None, "") else lo
    return (lo + hi) / 2.0


def build_rows(ads, window_start):
    """Keep ads that started within the window (or are still running) and tag
    each with its party. Most recent first."""
    rows = []
    seen = set()
    for a in ads:
        ad_id = a.get("id", "")
        if ad_id in seen:
            continue
        seen.add(ad_id)
        start = a.get("ad_delivery_start_time", "")
        stop = a.get("ad_delivery_stop_time", "")
        running = not stop
        if start < window_start and not running:
            continue
        pid = str(a.get("page_id", ""))
        party = PAGE_TO_PARTY.get(pid)
        if not party:
            continue  # not one of our tracked pages
        spend = a.get("spend") or {}
        impr = a.get("impressions") or {}
        bodies = a.get("ad_creative_bodies") or []
        text = " ".join(b.strip() for b in bodies if b).strip()
        rows.append({
            "id": ad_id,
            "page_id": pid,
            "page_name": a.get("page_name", ""),
            "party": party,
            "start": start,
            "stop": stop or "still running",
            "running": running,
            "spend_estimate": round(midpoint(spend)),
            "impressions_estimate": round(midpoint(impr)),
            "platforms": ", ".join(a.get("publisher_platforms") or []),
            "text": text,
            "link": "https://www.facebook.com/ads/library/?id=%s" % ad_id,
        })
    rows.sort(key=lambda r: r["start"], reverse=True)
    return rows


def write_csv(rows, path):
    cols = ["page_name", "party", "start", "stop", "spend_estimate",
            "impressions_estimate", "platforms", "text", "link"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# --- Small helpers -----------------------------------------------------

def pounds(n):
    return "£{:,.0f}".format(n)


def esc(s):
    return html.escape(str(s if s is not None else ""))


def _round_up(n, step):
    if n <= 0:
        return step
    return ((int(n) // step) + (1 if n % step else 0)) * step


# --- The spendometer (cumulative-spend line chart) ---------------------

def build_spend_chart_svg(rows, window_start):
    start = datetime.date.fromisoformat(window_start)
    end = datetime.date.today()
    if end < start:
        return ""
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += datetime.timedelta(days=1)

    # Parties that actually spent, biggest first; only they get a line.
    totals = {}
    for r in rows:
        totals[r["party"]] = totals.get(r["party"], 0) + r["spend_estimate"]
    keys = [p for p in sorted(totals, key=lambda p: -totals[p]) if totals[p] > 0]
    if not keys:
        return ""

    series = {}
    for k in keys:
        cum = 0
        vals = []
        # spend booked on the day each ad started; ads that started before the
        # window are counted on day 0 so the running total is complete.
        per_day = {}
        for r in rows:
            if r["party"] != k:
                continue
            day = r["start"] if r["start"] >= window_start else window_start
            per_day[day] = per_day.get(day, 0) + r["spend_estimate"]
        for day in days:
            cum += per_day.get(day.isoformat(), 0)
            vals.append(cum)
        series[k] = vals

    W, H = 760, 300
    PAD_L, PAD_R, PAD_T, PAD_B = 64, 16, 18, 36
    max_y = max((max(v) for v in series.values()), default=0)
    max_y = _round_up(max_y, 1000) or 1000

    def x(i):
        if len(days) == 1:
            return PAD_L
        return PAD_L + i * (W - PAD_L - PAD_R) / (len(days) - 1)

    def y(v):
        return H - PAD_B - v * (H - PAD_T - PAD_B) / max_y

    parts = ['<svg viewBox="0 0 %d %d" width="100%%" style="max-width:%dpx" '
             'role="img" aria-label="Cumulative ad spend by party">' % (W, H, W)]
    for tick in range(5):
        gv = max_y * tick / 4
        gy = y(gv)
        parts.append('<line x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f" stroke="#eee"/>'
                     % (PAD_L, W - PAD_R, gy, gy))
        parts.append('<text x="%.1f" y="%.1f" text-anchor="end" font-size="11" fill="#888">£%s</text>'
                     % (PAD_L - 6, gy + 4, "{:,.0f}".format(gv)))
    if len(days) > 1:
        step = max(1, len(days) // 6)
        for i in range(0, len(days), step):
            parts.append('<text x="%.1f" y="%d" text-anchor="middle" font-size="11" fill="#888">%s</text>'
                         % (x(i), H - 12, days[i].strftime("%d %b")))
    for p in keys:
        colour = PARTY_COLOUR.get(p, "#888")
        pts = " ".join("%.1f,%.1f" % (x(i), y(v)) for i, v in enumerate(series[p]))
        parts.append('<polyline fill="none" stroke="%s" stroke-width="2.5" '
                     'stroke-linejoin="round" stroke-linecap="round" points="%s"/>'
                     % (colour, pts))
    parts.append('</svg>')

    legend_items = []
    for p in keys:
        colour = PARTY_COLOUR.get(p, "#888")
        legend_items.append(
            '<span class="legend-item"><span class="dot" style="background:%s"></span>%s</span>'
            % (colour, esc(p)))
    legend = '<div class="legend">' + " ".join(legend_items) + '</div>'
    return "".join(parts) + legend


# --- Daily auto-summary ------------------------------------------------

def daily_summary(rows, by_party, total_spend, today):
    """A short factual paragraph built from the numbers."""
    if not rows:
        return "No ads found for the tracked parties in the last %d days." % WINDOW_DAYS
    yesterday = (today - datetime.timedelta(days=1)).isoformat()
    today_s = today.isoformat()
    new_ads = [r for r in rows if r["start"] in (today_s, yesterday)]
    running = [r for r in rows if r["running"]]
    ranked = sorted(by_party.items(), key=lambda kv: -kv[1]["spend"])
    top_party, top = ranked[0]

    bits = []
    bits.append(
        "Across the %d tracked parties, <strong>%s</strong> has been spent on "
        "<strong>%d</strong> Facebook &amp; Instagram ads in the last %d days, "
        "with <strong>%d</strong> still running today."
        % (len(by_party), pounds(total_spend), len(rows), WINDOW_DAYS, len(running)))
    bits.append(
        "The biggest spender is <strong>%s</strong> (%s across %d ads)."
        % (esc(top_party), pounds(top["spend"]), top["ads"]))
    if new_ads:
        new_by_party = {}
        for r in new_ads:
            new_by_party[r["party"]] = new_by_party.get(r["party"], 0) + 1
        lead = max(new_by_party, key=new_by_party.get)
        bits.append(
            "In the last 24 hours <strong>%d new ad(s)</strong> launched, led by "
            "<strong>%s</strong> (%d)." % (len(new_ads), esc(lead), new_by_party[lead]))
    else:
        bits.append("No new ads launched in the last 24 hours.")
    return " ".join(bits)


# --- Page rendering ----------------------------------------------------

STYLE = """
:root { --ink:#1a1a1a; --muted:#666; --line:#e5e5e5; --bg:#fafafa; }
* { box-sizing:border-box; }
body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
  Helvetica,Arial,sans-serif; color:var(--ink); background:var(--bg);
  line-height:1.5; }
.wrap { max-width:1000px; margin:0 auto; padding:24px 18px 80px; }
h1 { font-size:1.9rem; margin:0 0 4px; }
h2 { font-size:1.35rem; margin:40px 0 10px; }
h3 { font-size:1.1rem; margin:0; }
.sub { color:var(--muted); margin:0 0 6px; }
.stamp { font-size:.85rem; color:var(--muted); margin-bottom:20px; }
.summary { background:#fff; border:1px solid var(--line); border-left:4px solid #444;
  border-radius:8px; padding:16px 18px; margin:16px 0 8px; }
.cards { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:18px 0; }
.card { background:#fff; border:1px solid var(--line); border-radius:8px;
  padding:14px; text-align:center; }
.card .big { font-size:1.6rem; font-weight:700; }
.card .lbl { font-size:.78rem; color:var(--muted); text-transform:uppercase;
  letter-spacing:.03em; }
.chart { background:#fff; border:1px solid var(--line); border-radius:8px;
  padding:16px; overflow-x:auto; }
.legend { display:flex; flex-wrap:wrap; gap:12px; margin-top:12px; font-size:.85rem; }
.legend-item { display:flex; align-items:center; gap:5px; }
.dot { display:inline-block; width:11px; height:11px; border-radius:50%;
  vertical-align:middle; }
table { width:100%; border-collapse:collapse; background:#fff; font-size:.9rem; }
th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line);
  vertical-align:top; }
th { font-size:.78rem; text-transform:uppercase; letter-spacing:.03em; color:var(--muted); }
td.num { white-space:nowrap; }
.party-block { background:#fff; border:1px solid var(--line); border-radius:8px;
  margin:14px 0; overflow:hidden; }
.party-head { display:flex; align-items:center; gap:10px; padding:14px 16px;
  border-bottom:1px solid var(--line); }
.party-head .swatch { width:14px; height:14px; border-radius:3px; }
.party-head .meta { margin-left:auto; color:var(--muted); font-size:.9rem; text-align:right; }
.party-body { padding:0; }
.party-body table { border:0; }
details summary { cursor:pointer; padding:12px 16px; color:var(--muted);
  font-size:.9rem; user-select:none; }
.text { color:#333; }
.muted { color:var(--muted); }
a { color:#0b66c3; }
.foot { margin-top:48px; padding-top:16px; border-top:1px solid var(--line);
  color:var(--muted); font-size:.82rem; }
@media (max-width:640px) {
  .cards { grid-template-columns:repeat(2,1fr); }
  h1 { font-size:1.5rem; }
  td.hide-sm, th.hide-sm { display:none; }
}
"""


def render_party_block(entry_party, d, rows):
    colour = PARTY_COLOUR.get(entry_party, "#888")
    party_rows = [r for r in rows if r["party"] == entry_party]
    ad_rows = ""
    for r in party_rows[:60]:
        ad_rows += (
            '<tr><td class="num">%s</td><td>%s</td><td class="num">%s</td>'
            '<td class="text hide-sm">%s</td>'
            '<td><a href="%s" target="_blank" rel="noopener">view</a></td></tr>'
            % (esc(r["start"]), esc(r["page_name"]), pounds(r["spend_estimate"]),
               esc(r["text"][:200]), esc(r["link"])))
    more = ""
    if len(party_rows) > 60:
        more = '<p class="muted" style="padding:10px 16px">+ %d more — see the spreadsheet.</p>' % (len(party_rows) - 60)
    table = (
        '<table><tr><th>Started</th><th>Advertiser</th><th>Est. spend</th>'
        '<th class="hide-sm">Ad text</th><th>Link</th></tr>%s</table>%s'
        % (ad_rows, more)) if party_rows else '<p class="muted" style="padding:14px 16px">No ads in the last %d days.</p>' % WINDOW_DAYS
    return (
        '<div class="party-block">'
        '<div class="party-head"><span class="swatch" style="background:%s"></span>'
        '<h3>%s</h3>'
        '<span class="meta">%s &middot; %d ad(s)</span></div>'
        '<details %s><summary>Show ads</summary><div class="party-body">%s</div></details>'
        '</div>'
        % (colour, esc(entry_party), pounds(d["spend"]), d["ads"],
           "open" if d["spend"] >= 1 and len(party_rows) <= 12 else "", table))


def write_index(rows, path):
    today = datetime.date.today()
    window_start = (today - datetime.timedelta(days=WINDOW_DAYS)).isoformat()
    updated = datetime.datetime.now().strftime("%d %B %Y, %H:%M")
    total_spend = sum(r["spend_estimate"] for r in rows)

    by_party = {}
    for r in rows:
        d = by_party.setdefault(r["party"], {"ads": 0, "spend": 0, "impr": 0})
        d["ads"] += 1
        d["spend"] += r["spend_estimate"]
        d["impr"] += r["impressions_estimate"]
    # Ensure every tracked party appears, even with zero ads.
    for p in PARTY_ORDER:
        by_party.setdefault(p, {"ads": 0, "spend": 0, "impr": 0})

    summary = daily_summary(rows, by_party, total_spend, today)
    chart = build_spend_chart_svg(rows, window_start)

    # Party blocks in spend order, then any tracked party with no spend.
    ordered = sorted(by_party.items(), key=lambda kv: (-kv[1]["spend"], PARTY_ORDER.index(kv[0])))
    party_blocks = "".join(render_party_block(p, d, rows) for p, d in ordered)

    page = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="A daily monitor of Facebook &amp; Instagram political ads run by the main UK parties and their leaders.">
<style>{style}</style>
</head>
<body>
<div class="wrap">
  <h1>{title}</h1>
  <p class="sub">Every Facebook &amp; Instagram ad run by the main UK parties and
    their leaders, refreshed twice a day, grouped by party.</p>
  <div class="stamp">Last updated {updated} &middot; spend totals cover the last {window} days</div>

  <div class="summary"><strong>Today&rsquo;s summary.</strong> {summary}</div>

  <div class="cards">
    <div class="card"><div class="big">{n_ads}</div><div class="lbl">ads tracked</div></div>
    <div class="card"><div class="big">{total_spend}</div><div class="lbl">est. spend ({window}d)</div></div>
    <div class="card"><div class="big">{n_running}</div><div class="lbl">running now</div></div>
    <div class="card"><div class="big">{n_parties}</div><div class="lbl">parties watched</div></div>
  </div>

  <h2>Spendometer &mdash; cumulative spend, last {window} days</h2>
  <p class="sub">Running total of estimated spend by each party (party + leader
    pages combined), by the day each ad started.</p>
  <div class="chart">{chart}</div>

  <h2>By party</h2>
  {party_blocks}

  <div class="foot">
    Source: Meta Ad Library (Facebook &amp; Instagram political &amp; issue ads,
    UK). Spend and impression figures are midpoints of the ranges Meta publishes
    &mdash; estimates, not exact amounts. &ldquo;Your Party&rdquo; is tracked via
    co-founder Zarah Sultana&rsquo;s page until the party has its own ad page.
    <br>Download the full data: <a href="data/ads.csv">ads.csv</a>.
  </div>
</div>
</body>
</html>""".format(
        title=SITE_TITLE,
        style=STYLE,
        updated=updated,
        window=WINDOW_DAYS,
        summary=summary,
        n_ads=len(rows),
        total_spend=pounds(total_spend),
        n_running=sum(1 for r in rows if r["running"]),
        n_parties=len(PARTY_ORDER),
        chart=chart or "<p class='muted'>No spend data yet.</p>",
        party_blocks=party_blocks,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


# --- Main --------------------------------------------------------------

def merge_history(fresh_rows, cache_path, today):
    """Combine freshly-fetched ads with what we stored last time, so the dataset
    grows over time. Fresh data wins for ads seen this run; older ads are kept
    until they fall outside the keep window."""
    stored = {}
    if os.path.exists(cache_path):
        try:
            for r in json.load(open(cache_path)):
                stored[r["id"]] = r
        except Exception as e:
            print("  WARN: could not read cache: %s" % e)
    for r in fresh_rows:
        stored[r["id"]] = r  # fresh figures replace any older copy
    cutoff = (today - datetime.timedelta(days=HISTORY_KEEP_DAYS)).isoformat()
    kept = [r for r in stored.values() if r.get("running") or r.get("start", "") >= cutoff]
    kept.sort(key=lambda r: r["start"], reverse=True)
    return kept


def main():
    today = datetime.date.today()
    fetch_start = (today - datetime.timedelta(days=FETCH_DAYS)).isoformat()
    cache_path = os.path.join(DATA_DIR, "ads.json")
    os.makedirs(DATA_DIR, exist_ok=True)

    token = get_token()
    all_rows = None
    if token:
        try:
            print("Fetching ads for %d pages since %s..."
                  % (len(adv.all_page_ids()), fetch_start), flush=True)
            ads = fetch_for_pages(token, adv.all_page_ids(), fetch_start)
            print("  got %d raw ads" % len(ads), flush=True)
            fresh = build_rows(ads, fetch_start)
            all_rows = merge_history(fresh, cache_path, today)
            json.dump(all_rows, open(cache_path, "w"), indent=2, ensure_ascii=False)
            print("  stored %d ads total (history)" % len(all_rows), flush=True)
        except Exception as e:
            print("  fetch failed: %s" % e, flush=True)

    if all_rows is None:
        if os.path.exists(cache_path):
            print("Falling back to cached data/ads.json", flush=True)
            all_rows = json.load(open(cache_path))
        else:
            sys.exit("No data and no cache — cannot build.")

    # The page and spreadsheet show the display window only.
    window_start = (today - datetime.timedelta(days=WINDOW_DAYS)).isoformat()
    rows = [r for r in all_rows if r.get("running") or r.get("start", "") >= window_start]

    write_csv(rows, os.path.join(DATA_DIR, "ads.csv"))
    write_index(rows, os.path.join(HERE, "index.html"))
    print("Built index.html with %d ads in window (%s est. spend)."
          % (len(rows), pounds(sum(r["spend_estimate"] for r in rows))), flush=True)


if __name__ == "__main__":
    main()
