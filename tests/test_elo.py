"""Sanity checks for the rating model, using simulated players with known skill."""

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from elo import FrameElo, evaluate, frame_win_prob, match_win_prob  # noqa: E402
from simulate import simulate  # noqa: E402


def test_match_prob_basics():
    assert abs(match_win_prob(0.5, 6) - 0.5) < 1e-12
    assert abs(match_win_prob(0.6, 1) - 0.6) < 1e-12
    # a 55% frame edge becomes a bigger match edge as matches get longer
    short, long_ = match_win_prob(0.55, 4), match_win_prob(0.55, 18)
    assert 0.55 < short < long_ < 1
    # symmetry
    assert abs(match_win_prob(0.3, 10) + match_win_prob(0.7, 10) - 1) < 1e-12


def test_match_prob_matches_simulation():
    rng = random.Random(0)
    p, n, trials = 0.58, 6, 100_000
    wins = 0
    for _ in range(trials):
        a = b = 0
        while a < n and b < n:
            if rng.random() < p:
                a += 1
            else:
                b += 1
        wins += a == n
    assert abs(wins / trials - match_win_prob(p, n)) < 0.01


def _synthetic_matches(num_players=60, num_matches=6000, seed=1):
    rng = random.Random(seed)
    skill = {f"P{i}": rng.gauss(1500, 120) for i in range(num_players)}
    matches = []
    for i in range(num_matches):
        a, b = rng.sample(sorted(skill), 2)
        n = rng.choice([4, 5, 6, 9, 10])
        p = frame_win_prob(skill[a], skill[b])
        fa = fb = 0
        while fa < n and fb < n:
            if rng.random() < p:
                fa += 1
            else:
                fb += 1
        matches.append({"p1": a, "p2": b, "s1": fa, "s2": fb, "date": f"{i:06d}"})
    return skill, matches


def test_ratings_recover_true_skill():
    skill, matches = _synthetic_matches()
    model = FrameElo().fit(matches)
    players = sorted(skill)
    xs = [skill[p] for p in players]
    ys = [model.rating(p) for p in players]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    corr = cov / math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    assert corr > 0.9, corr


def test_predictions_beat_coin_flip():
    _, matches = _synthetic_matches()
    ll, acc, n = evaluate(matches, FrameElo(), start_index=3000)
    assert n > 2500
    assert ll < math.log(2)   # better than 50/50 guessing
    assert acc > 0.6


def test_simulation_probabilities_sum_to_one():
    skill, matches = _synthetic_matches()
    model = FrameElo().fit(matches)
    draw = sorted(skill)[:16]
    reached = simulate(draw, [4, 5, 6, 9], model, sims=2000)
    assert sum(reached[-1].values()) == 2000
    best = max(draw, key=model.rating)
    assert reached[-1][best] == max(reached[-1].values())
