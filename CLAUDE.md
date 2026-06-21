# How this repo works (read me first)

A static site that monitors UK political ads on Facebook/Instagram. No framework —
one Python script builds everything.

## The build model

`scripts/build.py` fetches ad data from Meta's Ad Library and **writes
`index.html` from scratch** every run. **Never hand-edit `index.html`** — your
changes are wiped on the next build. To change how the page looks, edit the
`STYLE` constant and the `write_index` / `render_party_block` functions in
`scripts/build.py`.

## Key files

- `scripts/advertisers.py` — the list of parties/leaders and their Facebook page
  IDs. This is the main thing you'll edit. Grouping and colours come from here.
- `scripts/find_pages.py` — helper to discover a page's numeric ID by name.
- `scripts/build.py` — fetch + render.
- `data/ads.json` — the accumulated ad history (deduped by ad ID). Grows over time.
- `data/ads.csv` — downloadable copy of the current window.
- `TODO.md` — outstanding tweaks.

## Meta Ad Library limits (important)

The API allows ~200 calls/token/hour and also throttles on request *cost*
(error 613). `build.py` already handles this: it asks for only the last
`FETCH_DAYS` (30) days, requests a lean set of fields, pulls page IDs in batches
with pauses, and backs off 60s and retries on a throttle. If you add many more
pages, keep an eye on the batching constants near the top of `build.py`.

## Token

The Meta token lives in `fb_token.txt` (git-ignored) or the `FB_TOKEN` secret in
GitHub Actions. Tokens expire roughly every 60 days — if the build starts failing
to fetch, refresh the token.
