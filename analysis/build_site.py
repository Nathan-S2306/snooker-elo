"""
Export everything the dashboard (docs/index.html) needs as small JSON files.

  docs/data/ratings.json   current ratings for active players
  docs/data/history.json   month-end rating history per player
  docs/data/h2h.json       head-to-head records between current top-64 players
  docs/data/meta.json      when it was built, how many matches, model settings
"""

import csv
import datetime as dt
import json
from collections import defaultdict

from common import ROOT, FrameElo, display_name, matches

OUT = ROOT / "docs" / "data"
ACTIVE_DAYS = 365
HISTORY_FROM = "2012-07"          # skip the model's warm-up years
H2H_TOP = 64


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with open(ROOT / "data" / "players.csv", newline="") as f:
        info = {r["player_id"]: r for r in csv.DictReader(f)}

    def name(pid):
        r = info.get(pid)
        return display_name(r["name"], r.get("nationality", "")) if r else None

    rows = matches()
    model = FrameElo()
    last_seen, history = {}, defaultdict(dict)      # pid -> {month: rating}
    h2h = defaultdict(lambda: [0, 0, 0, 0])         # (a, b) a<b -> [a wins, b wins, a frames, b frames]
    month = None

    for m in rows:
        mo = m["date"][:7]
        if month and mo != month and month >= HISTORY_FROM:
            for pid in touched:
                history[pid][month] = round(model.ratings[pid], 1)
        if mo != month:
            touched = set()
        month = mo
        a, b, s1, s2 = m["p1"], m["p2"], int(m["s1"]), int(m["s2"])
        model.update(a, b, s1, s2, m["date"])
        last_seen[a] = last_seen[b] = m["date"]
        touched.update((a, b))
        key, flip = ((a, b), False) if a < b else ((b, a), True)
        rec = h2h[key]
        x, y = (s2, s1) if flip else (s1, s2)
        rec[0 if x > y else 1] += 1
        rec[2] += x
        rec[3] += y
    if month >= HISTORY_FROM:
        for pid in touched:
            history[pid][month] = round(model.ratings[pid], 1)

    today = dt.date.today()
    cutoff = (today - dt.timedelta(days=ACTIVE_DAYS)).isoformat()
    year_ago = (today - dt.timedelta(days=365)).isoformat()[:7]
    active = [pid for pid in model.ratings if last_seen.get(pid, "") >= cutoff and name(pid)]
    active.sort(key=lambda p: -model.ratings[p])

    def rating_at(pid, mo):
        months = [k for k in history[pid] if k <= mo]
        return history[pid][max(months)] if months else None

    ratings = []
    for rank, pid in enumerate(active, 1):
        then = rating_at(pid, year_ago)
        ratings.append({
            "id": pid, "rank": rank, "name": name(pid),
            "nationality": info[pid].get("nationality", ""),
            "rating": round(model.ratings[pid], 1),
            "change_12m": round(model.ratings[pid] - then, 1) if then is not None else None,
            "matches": model.played[pid], "last_played": last_seen[pid],
        })

    keep = set(active)
    hist_out = {pid: sorted(history[pid].items()) for pid in keep if history[pid]}

    top = set(active[:H2H_TOP])
    h2h_out = {f"{a}-{b}": v for (a, b), v in h2h.items() if a in top and b in top}

    (OUT / "ratings.json").write_text(json.dumps(ratings, separators=(",", ":")))
    (OUT / "history.json").write_text(json.dumps(hist_out, separators=(",", ":")))
    (OUT / "h2h.json").write_text(json.dumps(h2h_out, separators=(",", ":")))
    (OUT / "meta.json").write_text(json.dumps({
        "built": today.isoformat(), "matches": len(rows),
        "latest_match": rows[-1]["date"], "latest_event": rows[-1]["event_name"],
        "k": model.k, "scale": model.scale, "first_season": rows[0]["date"][:4],
    }, indent=1))
    sizes = {p.name: p.stat().st_size // 1024 for p in OUT.glob("*.json")}
    print(f"{len(ratings)} active players, {len(hist_out)} histories, {len(h2h_out)} head-to-heads. Sizes (KB): {sizes}")


if __name__ == "__main__":
    main()
