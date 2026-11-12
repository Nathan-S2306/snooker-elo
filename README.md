# Snooker Elo

**Live dashboard: https://nathan-s2306.github.io/snooker-elo/**

A frame-based rating system for professional snooker, used to rank players on current form and predict tournaments.

## Why frame-based?

Standard Elo only looks at who won. Snooker gives more information than that, because a 10–9 win and a 10–1 win are very different results. So each player gets a rating for their chance of winning a single **frame**, and ratings are updated from the share of frames won.

A per-frame chance then converts into a match-win chance for any match length:

```
P(win first-to-N) = Σ_k  C(N−1+k, k) · pᴺ · (1−p)ᵏ     for k = 0 … N−1
```

That matters in snooker. A player who wins 45% of frames against a stronger opponent wins about 39% of best-of-7 matches, but only about 28% of best-of-35s.

## What's here

| File | What it does |
|---|---|
| `src/fetch_data.py` | Downloads results from the [snooker.org](https://snooker.org) API: cached, resumable, and within their 2-requests-per-minute limit |
| `src/elo.py` | Builds ratings, evaluates predictions, tunes K |
| `analysis/` | Article analyses and charts, plus `build_site.py`, which exports the dashboard data |
| `docs/` | The dashboard (GitHub Pages), refreshed daily |
| `src/simulate.py` | Monte Carlo tournament simulator: plays a draw thousands of times |
| `tests/` | Checks the model recovers known skill on simulated data |
| `.github/workflows/update-data.yml` | Daily automatic data and ratings refresh |

## Running it

```bash
SNOOKER_ORG_HEADER=... python src/fetch_data.py --from-season 2010   # get data
python src/elo.py --tune                                             # pick K on held-out matches
python src/elo.py --k 8                                              # write data/ratings.csv
python src/simulate.py --draw data/draw.txt --rounds 6,6,6,6,6,9,10  # tournament odds
python -m pytest tests                                               # sanity checks
```

## How it's evaluated

Every prediction is made **before** the match, using only earlier results. Ratings are scored on log-loss and accuracy over the most recent 20% of matches, and K is chosen to minimise held-out log-loss.

## Data

Results come from [snooker.org](https://snooker.org), used with permission. Thanks to the snooker.org team for maintaining it.
