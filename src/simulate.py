"""
Monte Carlo tournament simulator.

Give it a draw (players in bracket order) and the frames-to-win for each round,
and it plays the tournament thousands of times using the Elo match probabilities.

Draw file: a text/CSV file with one player_id per line, in bracket order
(line 1 plays line 2, line 3 plays line 4, ...). Length must be a power of two.

Example:
    python src/simulate.py --draw data/uk_2026_draw.txt --rounds 6,6,6,6,6,9,10 --sims 20000
"""

from __future__ import annotations

import csv
import random
from collections import Counter
from pathlib import Path

from elo import FrameElo, load_matches


def simulate(draw, frames_to_win, model: FrameElo, sims=10000, seed=1):
    rng = random.Random(seed)
    reached = [Counter() for _ in range(len(frames_to_win) + 1)]   # reached[r][player]
    cache = {}

    def p(a, b, n):
        key = (a, b, n)
        if key not in cache:
            cache[key] = model.p_match(a, b, n)
        return cache[key]

    for _ in range(sims):
        alive = list(draw)
        for r, n in enumerate(frames_to_win):
            for pl in alive:
                reached[r][pl] += 1
            alive = [a if rng.random() < p(a, b, n) else b for a, b in zip(alive[::2], alive[1::2])]
        reached[-1][alive[0]] += 1
    return reached


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--draw", required=True)
    ap.add_argument("--rounds", required=True, help="frames to win per round, e.g. 6,6,6,6,6,9,10")
    ap.add_argument("--matches", default="data/matches.csv")
    ap.add_argument("--players", default="data/players.csv")
    ap.add_argument("--k", type=float, default=FrameElo.k)
    ap.add_argument("--sims", type=int, default=20000)
    ap.add_argument("--out", default="data/simulation.csv")
    args = ap.parse_args()

    draw = [l.split(",")[0].strip() for l in Path(args.draw).read_text().splitlines() if l.strip()]
    rounds = [int(x) for x in args.rounds.split(",")]
    if len(draw) != 2 ** len(rounds):
        raise SystemExit(f"Draw has {len(draw)} players but {len(rounds)} rounds need {2 ** len(rounds)}")

    names = {}
    if Path(args.players).exists():
        with open(args.players, newline="") as f:
            names = {r["player_id"]: r["name"] for r in csv.DictReader(f)}

    model = FrameElo(k=args.k).fit(load_matches(Path(args.matches)))
    reached = simulate(draw, rounds, model, args.sims)

    labels = [f"reach_r{i + 1}" for i in range(1, len(rounds))] + ["final_win"]
    rows = []
    for pl in draw:
        probs = [reached[r][pl] / args.sims for r in range(1, len(rounds) + 1)]
        rows.append([pl, names.get(pl, pl), round(model.rating(pl), 1)] + [round(x, 4) for x in probs])
    rows.sort(key=lambda r: -r[-1])
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["player_id", "name", "rating"] + labels)
        w.writerows(rows)
    print(f"Wrote {args.out}. Title chances:")
    for r in rows[:16]:
        print(f"  {r[1]:<25} {r[-1] * 100:5.1f}%")


if __name__ == "__main__":
    main()
