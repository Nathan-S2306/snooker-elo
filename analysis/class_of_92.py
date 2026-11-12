"""
Is the Class of 92 finished?

Plots O'Sullivan, Higgins and Williams's frame-Elo rating at the end of every
month since 2010, against the rating of the world's 16th-best active player
(roughly the line for being a 'top 16' player).

Writes charts/class_of_92.png and charts/class_of_92.csv
"""

import csv
import datetime as dt
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from common import (CHARTS, REFERENCE, SERIES, TEXT_PRIMARY, TEXT_SECONDARY,  # noqa: E402
                    FrameElo, matches, players, style_axes)

CLASS_OF_92 = ["Ronnie O'Sullivan", "John Higgins", "Mark J Williams"]
LABELS = {"Mark J Williams": "Mark Williams"}
ACTIVE_DAYS = 365


def month_end(d: str) -> str:
    return d[:7]


def main():
    names = players()
    ids = {v: k for k, v in names.items()}
    who = [ids[n] for n in CLASS_OF_92]

    model = FrameElo()
    last_seen = {}
    monthly = defaultdict(dict)      # month -> {series: rating}
    rows = matches()
    current_month = None

    def snapshot(month):
        cutoff = (dt.date.fromisoformat(month + "-28") - dt.timedelta(days=ACTIVE_DAYS)).isoformat()
        active = sorted((r for p, r in model.ratings.items() if last_seen.get(p, "") >= cutoff), reverse=True)
        if len(active) >= 16:
            monthly[month]["Top-16 line"] = active[15]
            monthly[month]["World No. 1"] = active[0]
        for pid, n in zip(who, CLASS_OF_92):
            if pid in model.ratings:
                monthly[month][n] = model.ratings[pid]

    for m in rows:
        mo = month_end(m["date"])
        if current_month and mo != current_month:
            snapshot(current_month)
        current_month = mo
        model.update(m["p1"], m["p2"], int(m["s1"]), int(m["s2"]), m["date"])
        last_seen[m["p1"]] = last_seen[m["p2"]] = m["date"]
    snapshot(current_month)

    months = sorted(monthly)
    # first year is the model warming up from scratch - start the chart in 2011
    months = [mo for mo in months if mo >= "2011-07"]
    xs = [dt.date.fromisoformat(mo + "-15") for mo in months]

    with open(CHARTS / "class_of_92.csv", "w", newline="") as f:
        cols = CLASS_OF_92 + ["Top-16 line", "World No. 1"]
        w = csv.writer(f)
        w.writerow(["month"] + cols)
        for mo in months:
            w.writerow([mo] + [round(monthly[mo].get(c, float("nan")), 1) for c in cols])

    # Plot each player's gap above the 16th-best active player. This removes the slow
    # upward drift in everyone's numbers (all players started at 1500 in 2010).
    months = [mo for mo in months if mo >= "2012-07"]          # skip the model's warm-up years
    xs = [dt.date.fromisoformat(mo + "-15") for mo in months]

    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
    style_axes(ax)
    ax.plot([xs[0], xs[-1] + dt.timedelta(days=60)], [0, 0], color=REFERENCE, linewidth=1.5, linestyle=(0, (4, 3)))
    ax.annotate("16th-best active player", (xs[-1] + dt.timedelta(days=75), 0), xytext=(7, 0),
                textcoords="offset points", va="center", fontsize=9.5, color=TEXT_SECONDARY)

    end_labels = []
    for n, colour in zip(CLASS_OF_92, SERIES):
        ys = [monthly[mo][n] - monthly[mo]["Top-16 line"] for mo in months]
        ax.plot(xs, ys, color=colour, linewidth=2, solid_capstyle="round")
        end_labels.append([ys[-1], ys[-1], LABELS.get(n, n).split()[-1], colour])

    # direct labels at the right edge with a colour key, nudged apart so they never collide
    end_labels.sort()
    gap = 9
    for i in range(1, len(end_labels)):
        if end_labels[i][0] - end_labels[i - 1][0] < gap:
            end_labels[i][0] = end_labels[i - 1][0] + gap
    x_end = xs[-1]
    x_lab = x_end + dt.timedelta(days=75)
    for y_lab, y_line, label, colour in end_labels:
        ax.plot([x_end, x_lab], [y_line, y_lab], color=colour, linewidth=1, alpha=0.8)
        ax.plot([x_lab], [y_lab], marker="o", markersize=6, color=colour, markeredgecolor="white",
                markeredgewidth=1.5)
        ax.annotate(f"{label}  +{y_line:.0f}", (x_lab, y_lab), xytext=(7, 0), textcoords="offset points",
                    va="center", fontsize=10.5, color=TEXT_PRIMARY, fontweight="bold")

    ax.set_title("Still top-16 players, but O'Sullivan is back near his lowest point since 2012", loc="left",
                 fontsize=15, color=TEXT_PRIMARY, fontweight="bold", pad=24)
    ax.text(0, 1.02, "Rating points above the 16th-best active player, end of each month, 2012–2026",
            transform=ax.transAxes, fontsize=10.5, color=TEXT_SECONDARY)
    ax.set_ylabel("Points above the top-16 line", color=TEXT_SECONDARY, fontsize=10)
    ax.set_xlim(xs[0], xs[-1] + dt.timedelta(days=560))
    ax.set_xticks([dt.date(y, 1, 1) for y in range(2013, 2027)])
    ax.set_xticklabels([str(y) if y % 2 == 0 else "" for y in range(2013, 2027)])
    fig.text(0.01, 0.01, "Data: snooker.org  ·  Model: frame-based Elo", fontsize=8.5, color=TEXT_SECONDARY)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(CHARTS / "class_of_92.png", facecolor=fig.get_facecolor())

    last = months[-1]
    print(f"Ratings at {last}:")
    for n in CLASS_OF_92 + ["Top-16 line", "World No. 1"]:
        print(f"  {n:<20} {monthly[last].get(n, float('nan')):7.1f}")
    print("Gap above the top-16 line - now, peak, and lowest since 2012-07:")
    for n in CLASS_OF_92:
        g = {mo: monthly[mo][n] - monthly[mo]["Top-16 line"] for mo in months}
        hi, lo = max(g, key=g.get), min(g, key=g.get)
        below = sum(v < 0 for v in g.values())
        print(f"  {n:<20} now {g[last]:+6.1f}  peak {g[hi]:+6.1f} ({hi})  low {g[lo]:+6.1f} ({lo})"
              f"  months below line: {below}/{len(g)}")


if __name__ == "__main__":
    main()
