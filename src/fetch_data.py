"""
Download professional snooker results from the snooker.org API.

snooker.org asks anyone collecting data automatically to agree an
X-Requested-By header value with them first. Put the agreed value in the
SNOOKER_ORG_HEADER environment variable (a GitHub Actions secret).

Writes:
  data/raw/*.json      cached API responses (finished events are never re-downloaded)
  data/matches.csv     one row per completed match
  data/players.csv     player id -> name
  data/events.csv      event metadata

Usage:
  SNOOKER_ORG_HEADER=... python src/fetch_data.py --from-season 2010
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import time as _time
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.snooker.org/"
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DATA = ROOT / "data"
PAUSE_SECONDS = 32.0  # snooker.org allows 2 requests per minute; stay just under it
DEADLINE = None       # set from --max-minutes; stop starting new requests after this


class TimeUp(Exception):
    """Raised when this run's time budget is used up; the next run carries on from the cache."""


def get(params: dict, cache_name: str | None = None, refresh: bool = False):
    """GET from the API, caching the JSON to data/raw/<cache_name>.json."""
    path = RAW / f"{cache_name}.json" if cache_name else None
    if path and path.exists() and not refresh:
        return json.loads(path.read_text())
    if DEADLINE and _time.monotonic() > DEADLINE:
        raise TimeUp()
    header = os.environ.get("SNOOKER_ORG_HEADER")
    if not header:
        sys.exit("Set SNOOKER_ORG_HEADER to the value agreed with snooker.org.")
    url = BASE + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"X-Requested-By": header})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            break
        except Exception as exc:
            wait = 60 * (attempt + 1)   # back off a full minute or more
            print(f"  retrying {params} after error: {exc} (waiting {wait:.0f}s)", file=sys.stderr)
            time.sleep(wait)
    else:
        raise RuntimeError(f"Giving up on {params}")
    time.sleep(PAUSE_SECONDS)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    return data


def current_season(today=None) -> int:
    """Snooker seasons start in the summer; the 2026/27 season is '2026'."""
    today = today or dt.date.today()
    return today.year if today.month >= 6 else today.year - 1


def is_main_tour_snooker(ev: dict) -> bool:
    return (str(ev.get("Tour", "")).lower() == "main"
            and str(ev.get("Discipline", "snooker")).lower() == "snooker"
            and str(ev.get("Sex", "Both")).lower() in ("both", "men", ""))


def event_finished(ev: dict, today: dt.date) -> bool:
    try:
        return dt.date.fromisoformat(str(ev.get("EndDate"))[:10]) < today - dt.timedelta(days=2)
    except ValueError:
        return False


def match_date(m: dict, ev: dict) -> str:
    for key in ("EndDate", "StartDate", "ScheduledDate"):
        v = str(m.get(key) or "")
        if len(v) >= 10 and not v.startswith("0000"):
            return v[:10]
    return str(ev.get("StartDate", ""))[:10]


def main():
    import argparse
    global DEADLINE
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-season", type=int, default=2010)
    ap.add_argument("--max-minutes", type=float, default=0,
                    help="stop after this long and save progress (0 = no limit)")
    args = ap.parse_args()
    if args.max_minutes:
        DEADLINE = _time.monotonic() + args.max_minutes * 60
    try:
        complete = collect(args.from_season)
    except TimeUp:
        complete = False
    (DATA / "download_complete").write_text("yes\n" if complete else "no\n")
    print("Download complete." if complete else "Time budget used up - the next run will carry on from the cache.")


def collect(from_season):
    today = dt.date.today()
    season_now = current_season(today)
    events, matches, players = [], [], {}
    try:
        _collect(from_season, today, season_now, events, matches, players)
    finally:
        write_csvs(events, matches, players)
    return True


def _collect(from_season, today, season_now, events, matches, players):

    for season in range(from_season, season_now + 1):
        evs = get({"t": 5, "s": season}, f"events_{season}", refresh=(season == season_now))
        evs = [e for e in evs if is_main_tour_snooker(e)]
        print(f"Season {season}: {len(evs)} main-tour events")
        for ev in evs:
            events.append(ev)
            if str(ev.get("StartDate", ""))[:10] > today.isoformat():
                continue                                          # not started: no results yet
            done = event_finished(ev, today)
            ms = get({"t": 6, "e": ev["ID"]}, f"matches_{ev['ID']}", refresh=not done)
            for m in ms or []:
                s1, s2 = int(m.get("Score1") or 0), int(m.get("Score2") or 0)
                p1, p2 = m.get("Player1ID"), m.get("Player2ID")
                status = m.get("Status")
                if status is not None and int(status) != 3:      # 3 = finished
                    continue
                if int(m.get("Type") or 1) != 1:                  # 1 = standard one-on-one
                    continue
                if not p1 or not p2 or (s1 == 0 and s2 == 0) or int(m.get("WinnerID") or 0) == 0:
                    continue
                walkover = bool(m.get("Walkover1") or m.get("Walkover2"))
                matches.append({
                    "match_id": m["ID"], "event_id": ev["ID"], "event_name": ev.get("Name", ""),
                    "event_type": ev.get("Type", ""), "season": season,
                    "date": match_date(m, ev), "round": m.get("Round", ""),
                    "p1": p1, "p2": p2, "s1": s1, "s2": s2,
                    "frames_to_win": max(s1, s2), "walkover": int(walkover),
                })

        for pl in get({"t": 10, "st": "p", "s": season}, f"players_{season}",
                      refresh=(season == season_now)) or []:
            name = " ".join(x for x in (pl.get("FirstName"), pl.get("MiddleName"), pl.get("LastName")) if x)
            players[str(pl["ID"])] = {"player_id": pl["ID"], "name": name,
                                      "nationality": pl.get("Nationality", "")}



def write_csvs(events, matches, players):
    DATA.mkdir(exist_ok=True)
    matches.sort(key=lambda m: (m["date"], m["event_id"], m["match_id"]))
    with open(DATA / "matches.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(matches[0].keys()) if matches else ["match_id"])
        w.writeheader()
        w.writerows(matches)
    with open(DATA / "players.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["player_id", "name", "nationality"])
        w.writeheader()
        w.writerows(players.values())
    with open(DATA / "events.csv", "w", newline="") as f:
        cols = ["ID", "Name", "Season", "Type", "StartDate", "EndDate", "Venue", "City", "Country"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(events)
    print(f"Saved {len(matches)} matches, {len(players)} players, {len(events)} events")


if __name__ == "__main__":
    main()
