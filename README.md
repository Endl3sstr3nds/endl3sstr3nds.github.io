# Endl3ss Tr3nds

Source for [endl3sstr3nds.com](https://endl3sstr3nds.com): one trader's real account, posted every day. Each trade, what it cost, and why it went wrong.

- `index.html` is the whole site (homepage and Logbook).
- `img/` holds the images.
- `CNAME` tells GitHub Pages which domain serves the site.

Nothing here is financial advice.

## How the Logbook posts itself

- `data/days.json` holds one record per trading day.
- `tools/post_day.py` scores a day from the broker's fills, with the method fixed in code, and adds it.
- `tools/build.py` renders the records into `index.html`. `tools/check.py` must pass before anything is pushed.
- A scheduled task runs this every weekday at 8:12 PM ET. No fills data or account numbers are stored here.
