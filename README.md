# UK Political Ads Monitor

A small static website that watches the Facebook & Instagram political ads run
by the main UK parties and their leaders, and shows them all in one place —
grouped by party, with a running spend total ("spendometer") and a short daily
summary.

## What it does

Twice a day a script (`scripts/build.py`):

1. Asks **Meta's public Ad Library** for the ads run by each page listed in
   `scripts/advertisers.py` (each party + its leader), over the last 30 days.
2. Groups them by party, adds up the estimated spend, and writes a one-paragraph
   **daily summary** from the numbers.
3. Rebuilds **`index.html`** (the page you see) and **`data/ads.csv`** (the full
   data to download).

It **accumulates history**: every run merges new ads into `data/ads.json`, so the
dataset grows over time even though each fetch only looks back 30 days.

## Who is tracked

See `scripts/advertisers.py`. To add or change a party/leader, find their page ID
with `python3 scripts/find_pages.py`, paste it in, and rebuild. Outstanding
tweaks are in `TODO.md`.

## Running it yourself

```
python3 scripts/build.py
```

Needs a Meta Ad Library access token in `fb_token.txt` (kept out of git) or the
`FB_TOKEN` environment variable. Without one it rebuilds from the last saved data.

## How it's published

The GitHub Action in `.github/workflows/update.yml` runs the build twice a day
and commits the refreshed page. The site is served as static files (see
`wrangler.jsonc` for Cloudflare Pages).

## A note on the numbers

Meta publishes spend and impressions as **ranges**, not exact figures — every £
amount here is the midpoint of a range, so treat it as an estimate. Meta also
only reliably reports the most recent ~90 days.
