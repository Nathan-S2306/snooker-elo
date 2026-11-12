"""
Do players bounce back after a heavy defeat?

For every knockout exit, look at how the beaten player does at their NEXT event,
compared with what the ratings expected *before* each of those matches.

  performance = frames won - frames the model expected them to win
                (per frame played, so long and short matches count fairly)

A positive number means the player did better than their rating suggested.

Groups compared by how they went out last time:
  heavy defeat  - won 25% of frames or fewer (4-0, 4-1, 5-1, 6-2, 10-3 ...)
  close defeat  - lost by a single frame (4-3, 6-5, 10-9 ...)
  other defeat  - everything in between

Also repeats the test for elite players only (top 16 by rating at the time).

Writes charts/bounce_back.png and prints a summary table with 95% bootstrap CIs.
"""

import datetime as dt
import random
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from common import (CHARTS, GRID, SERIES, TEXT_PRIMARY, TEXT_SECONDARY,  # noqa: E402
                    FrameElo, matches, style_axes)

ROUND_ROBIN = "19"
MAX_GAP_DAYS = 120         # next event must start within this many days
MIN_FRAMES_TO_WIN = 4      # ignore very short formats for the "exit" match
GROUPS = ["Heavy defeat", "Other defeat", "Close defeat", "Won the event"]


def classify(won, lost):
    share = won / (won + lost)
    if lost - won == 1:
        return "Close defeat"
    if share <= 0.25:
        return "Heavy defeat"
    return "Other defeat"


def pooled(items):
    """Frames won above expectation, per 100 frames played (frame-weighted)."""
    return 100 * sum(d for d, _ in items) / sum(t for _, t in items)


def bootstrap_ci(items, n=2000, seed=7):
    rng = random.Random(seed)
    k = len(items)
    stats = sorted(pooled([items[rng.randrange(k)] for _ in range(k)]) for _ in range(n))
    return stats[int(0.025 * n)], stats[int(0.975 * n)]


def main():
    rows = matches()
    model = FrameElo()

    # per player, per event: list of (date, frames_won, frames_lost, expected_frames, elite)
    played = defaultdict(lambda: defaultdict(list))
    exits = []          # (player, event_id, date, group, elite)
    event_order = defaultdict(list)    # player -> [event_id in order]
    last_seen = {}

    for m in rows:
        a, b = m["p1"], m["p2"]
        s1, s2 = int(m["s1"]), int(m["s2"])
        n = s1 + s2
        # elite = top 16 among players active in the last year, before this match
        p = model.p_frame(a, b)
        for pl, won, lost, exp_share in ((a, s1, s2, p), (b, s2, s1, 1 - p)):
            ev = m["event_id"]
            if ev not in event_order[pl]:
                event_order[pl].append(ev)
            played[pl][ev].append((m["date"], won, lost, exp_share * n))
        if m["round"] != ROUND_ROBIN and "championship league" not in m["event_name"].lower() \
                and max(s1, s2) >= MIN_FRAMES_TO_WIN and s1 != s2:
            loser, won, lost = (b, s2, s1) if s1 > s2 else (a, s1, s2)
            cutoff = (dt.date.fromisoformat(m["date"]) - dt.timedelta(days=365)).isoformat()
            active = sorted((r for q, r in model.ratings.items() if last_seen.get(q, "") >= cutoff), reverse=True)
            elite = len(active) >= 16 and model.rating(loser) >= active[15]
            exits.append((loser, m["event_id"], m["date"], classify(won, lost), elite))
            if m["round"] == "15":                         # the final: the winner won the event
                winner = a if s1 > s2 else b
                w_elite = len(active) >= 16 and model.rating(winner) >= active[15]
                exits.append((winner, m["event_id"], m["date"], "Won the event", w_elite))
        model.update(a, b, s1, s2, m["date"])
        last_seen[a] = last_seen[b] = m["date"]

    results = defaultdict(list)          # (group, elite_only) -> [performance per frame]
    for pl, ev, date, group, elite in exits:
        order = event_order[pl]
        i = order.index(ev)
        if i + 1 >= len(order):
            continue
        nxt = played[pl][order[i + 1]]
        if (dt.date.fromisoformat(nxt[0][0]) - dt.date.fromisoformat(date)).days > MAX_GAP_DAYS:
            continue
        won = sum(x[1] for x in nxt)
        total = sum(x[1] + x[2] for x in nxt)
        expected = sum(x[3] for x in nxt)
        if total:
            item = (won - expected, total)
            results[(group, False)].append(item)
            if elite:
                results[(group, True)].append(item)

    print(f"{'Group':<14} {'Players':<8} {'n':>6} {'Frames vs expected':>20}  95% CI")
    summary = {}
    for elite in (False, True):
        for g in GROUPS:
            v = results[(g, elite)]
            mean = pooled(v)
            lo, hi = bootstrap_ci(v)
            summary[(g, elite)] = (mean, lo, hi, len(v))
            print(f"{g:<14} {'top 16' if elite else 'all':<8} {len(v):>6} {mean:>+19.2f}%  [{lo:+.2f}, {hi:+.2f}]")

    # chart: dot + CI per group, all players vs top 16
    fig, ax = plt.subplots(figsize=(10, 5), dpi=200)
    style_axes(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.axvline(0, color=TEXT_SECONDARY, linewidth=1)
    labels = {False: "All players", True: "Top-16 players"}
    ypos = {g: i for i, g in enumerate(reversed(GROUPS))}
    for k, elite in enumerate((False, True)):
        colour = SERIES[k]
        for g in GROUPS:
            mean, lo, hi, n = summary[(g, elite)]
            y = ypos[g] + (0.14 if not elite else -0.14)
            ax.plot([lo, hi], [y, y], color=colour, linewidth=2.5, solid_capstyle="round", zorder=2)
            ax.plot([mean], [y], marker="o", markersize=8, color=colour, markeredgecolor="#fcfcfb",
                    markeredgewidth=1.5, zorder=3)
            ax.annotate(f"{mean:+.1f}", (hi, y), xytext=(10, 0), textcoords="offset points",
                        va="center", fontsize=10, color=TEXT_PRIMARY,
                        bbox=dict(boxstyle="square,pad=0.15", fc="#fcfcfb", ec="none"))
    ax.set_yticks(list(ypos.values()))
    ax.set_yticklabels(list(ypos.keys()), fontsize=11, color=TEXT_PRIMARY)
    ax.set_xlabel("Frames won per 100 played, vs expected  (lines show 95% intervals)",
                  color=TEXT_SECONDARY, fontsize=10)
    for k, elite in enumerate((False, True)):
        ax.plot([], [], marker="o", color=SERIES[k], linewidth=2, label=labels[elite])
    ax.legend(loc="lower right", frameon=False, fontsize=10, labelcolor=TEXT_PRIMARY)
    ax.set_title("No bounce-back after a thrashing, but a clear champion's hangover", loc="left", fontsize=15,
                 color=TEXT_PRIMARY, fontweight="bold", pad=24)
    ax.text(0, 1.02, "Frames won at the next event above or below the model's expectation, by how the last event ended",
            transform=ax.transAxes, fontsize=10.5, color=TEXT_SECONDARY)
    ax.set_xlim(-5, 2.5)
    fig.text(0.01, 0.01, "Data: snooker.org 2010–2026  ·  Model: frame-based Elo", fontsize=8.5,
             color=TEXT_SECONDARY)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(CHARTS / "bounce_back.png", facecolor=fig.get_facecolor())


if __name__ == "__main__":
    main()
