# To-do / notes

- **Your Party → add Jeremy Corbyn's page.** Currently tracked only via Zarah
  Sultana's page (`104380177666241`). Find Jeremy Corbyn's official Facebook ad
  page ID (run `python3 scripts/find_pages.py`, look for a clean "Jeremy Corbyn"
  page — note his "Peace and Justice Project" page `100214261915768` may be the
  closest) and add it to the "Your Party" entry in `scripts/advertisers.py`. Also
  add the official Your Party page once one exists.

- **Spend window is 30 days for now.** `WINDOW_DAYS` in `scripts/build.py` is set
  to 30. Because each run merges new ads into `data/ads.json`, history builds up
  over time — bump `WINDOW_DAYS` to 90 once we've been collecting for a while.

- **AI-written daily summary (optional).** The summary is currently auto-generated
  from the numbers. Could add a Claude-written paragraph later, wired to use
  Becky's Max plan via the Claude Code GitHub Action (so no extra API cost).
