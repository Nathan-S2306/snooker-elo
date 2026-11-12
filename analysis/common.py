"""Shared helpers for the analysis scripts."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from elo import FrameElo, load_matches  # noqa: E402

CHARTS = ROOT / "charts"
CHARTS.mkdir(exist_ok=True)

# Chart styling (light background for Substack/LinkedIn images)
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e1"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]   # validated: first three categorical slots
REFERENCE = "#a3a29c"                         # muted grey for context lines

# snooker.org gives Chinese names in Western order; show them the usual snooker way
CHINESE_SURNAMES = {
    "Zhao", "Wu", "Chang", "Zhang", "Si", "Ding", "Zhou", "Fan", "Yan", "Xiao", "Lei", "Pang",
    "Liang", "Li", "Yuan", "Lyu", "Tian", "He", "Xu", "Guo", "Jiang", "Gao", "Long", "Huang",
    "Cao", "Bai", "Wang", "Chen", "Liu", "Lu", "Ma", "Sun", "Yang", "Zhu", "Luo", "Peng",
}


def display_name(name: str, nationality: str = "") -> str:
    parts = name.split()
    if nationality.lower() == "china" and len(parts) == 2 and parts[1] in CHINESE_SURNAMES:
        return f"{parts[1]} {parts[0]}"
    return name


def players():
    with open(ROOT / "data" / "players.csv", newline="") as f:
        return {r["player_id"]: display_name(r["name"], r.get("nationality", "")) for r in csv.DictReader(f)}


def matches():
    return load_matches(ROOT / "data" / "matches.csv")


def style_axes(ax):
    import matplotlib.pyplot as plt  # noqa: F401
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=10, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
