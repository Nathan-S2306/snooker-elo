"""
Frame-based Elo ratings for professional snooker.

Ordinary Elo only looks at who won a match. Snooker gives us more than that:
a 10-9 win and a 10-1 win are very different results. So each player gets a
rating that predicts their chance of winning a single *frame*, and ratings are
updated from the share of frames won.

A per-frame win chance then converts into a match-win chance for any match
length, which matters a lot in snooker: an underdog has a far better chance in a
best-of-7 than in a best-of-35.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


def frame_win_prob(rating_a: float, rating_b: float, scale: float = 400.0) -> float:
    """Chance that A wins a single frame against B."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / scale))


def match_win_prob(p_frame: float, frames_to_win: int) -> float:
    """Chance of winning a first-to-N match, given a per-frame win chance.

    Sums the ways A can reach N frames while B has k < N:
    P = sum_k C(N-1+k, k) * p^N * (1-p)^k
    """
    n, p, q = frames_to_win, p_frame, 1.0 - p_frame
    return sum(math.comb(n - 1 + k, k) * p**n * q**k for k in range(n))


@dataclass
class FrameElo:
    k: float = 8.0                 # how fast ratings move
    scale: float = 400.0           # rating gap that gives 10:1 frame odds
    initial: float = 1500.0        # starting rating for an unknown player
    provisional_matches: int = 20  # new players move faster for their first N matches
    provisional_boost: float = 2.0

    ratings: dict = field(default_factory=dict)
    played: dict = field(default_factory=lambda: defaultdict(int))
    history: list = field(default_factory=list)

    def rating(self, player) -> float:
        return self.ratings.get(player, self.initial)

    def p_frame(self, a, b) -> float:
        return frame_win_prob(self.rating(a), self.rating(b), self.scale)

    def p_match(self, a, b, frames_to_win: int) -> float:
        return match_win_prob(self.p_frame(a, b), frames_to_win)

    def _k(self, player) -> float:
        boost = self.provisional_boost if self.played[player] < self.provisional_matches else 1.0
        return self.k * boost

    def update(self, a, b, frames_a: int, frames_b: int, date=None, match_id=None):
        """Update both players from one match result."""
        n = frames_a + frames_b
        if n == 0:
            return
        expected = self.p_frame(a, b)
        actual = frames_a / n
        # sqrt(n): longer matches tell us more, but not linearly more
        surprise = (actual - expected) * math.sqrt(n)
        ra, rb = self.rating(a), self.rating(b)
        self.ratings[a] = ra + self._k(a) * surprise
        self.ratings[b] = rb - self._k(b) * surprise
        self.played[a] += 1
        self.played[b] += 1
        self.history.append((date, match_id, a, b, frames_a, frames_b, ra, rb, expected))

    def fit(self, matches):
        """matches: iterable of dicts with p1, p2, s1, s2 (and optionally date, match_id), in date order."""
        for m in matches:
            self.update(m["p1"], m["p2"], int(m["s1"]), int(m["s2"]), m.get("date"), m.get("match_id"))
        return self


def evaluate(matches, model: FrameElo, start_index: int = 0):
    """Score match-winner predictions made *before* each match (no peeking).

    Returns (log_loss, accuracy, n) over matches from start_index onwards.
    """
    eps = 1e-9
    ll, correct, n = 0.0, 0, 0
    for i, m in enumerate(matches):
        s1, s2 = int(m["s1"]), int(m["s2"])
        ftw = max(s1, s2)
        if i >= start_index and ftw > 0 and s1 != s2:
            p = model.p_match(m["p1"], m["p2"], ftw)
            won = s1 > s2
            ll += -math.log(max(eps, p if won else 1 - p))
            correct += (p >= 0.5) == won
            n += 1
        model.update(m["p1"], m["p2"], s1, s2, m.get("date"), m.get("match_id"))
    return (ll / n if n else float("nan"), correct / n if n else float("nan"), n)


# snooker.org round codes, in the order they're played (see api.snooker.org/help.html)
ROUND_ORDER = {c: i for i, c in enumerate([1, 2, 3, 4, 5, 6, 20, 21, 19, 16, 7, 8, 9, 10, 11, 12, 13, 14, 18, 15])}


def _round_rank(r) -> int:
    try:
        return ROUND_ORDER.get(int(r), 50)
    except (TypeError, ValueError):
        return 50


def load_matches(path: Path):
    with open(path, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("walkover", "0") in ("0", "", "False")]
    # date first, then round, so a final is never rated before its semi-finals
    rows.sort(key=lambda r: (r["date"], _round_rank(r.get("round")), r.get("event_id", "")))
    return rows


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Build frame-Elo ratings from data/matches.csv")
    ap.add_argument("--matches", default="data/matches.csv")
    ap.add_argument("--players", default="data/players.csv")
    ap.add_argument("--out", default="data/ratings.csv")
    ap.add_argument("--k", type=float, default=FrameElo.k)
    ap.add_argument("--tune", action="store_true", help="grid-search K on the last 20%% of matches")
    args = ap.parse_args()

    matches = load_matches(Path(args.matches))
    if args.tune:
        split = int(len(matches) * 0.8)
        print(f"Tuning on {len(matches) - split} held-out matches")
        for k in (2, 4, 6, 8, 10, 12, 16, 20):
            ll, acc, n = evaluate(matches, FrameElo(k=k), split)
            print(f"  K={k:<3} log-loss={ll:.4f}  accuracy={acc:.3f}")
        return

    names = {}
    if Path(args.players).exists():
        with open(args.players, newline="") as f:
            names = {r["player_id"]: r["name"] for r in csv.DictReader(f)}

    model = FrameElo(k=args.k).fit(matches)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "player_id", "name", "rating", "matches"])
        ranked = sorted(model.ratings.items(), key=lambda kv: -kv[1])
        for i, (pid, r) in enumerate(ranked, 1):
            w.writerow([i, pid, names.get(pid, pid), round(r, 1), model.played[pid]])
    print(f"Wrote {args.out}. Top 10:")
    for i, (pid, r) in enumerate(ranked[:10], 1):
        print(f"  {i:>2}. {names.get(pid, pid):<25} {r:7.1f}")


if __name__ == "__main__":
    main()
