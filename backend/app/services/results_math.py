"""Experiment Lab analysis (doc 09 §Analysis and reporting). Pure functions: paired differences by
case (replicates averaged), a case-level bootstrap interval only with enough matched cases, and
intent-to-treat vs labeled sensitivity views. Nothing here invents a missing value."""

import random
from collections import defaultdict
from dataclasses import dataclass
from statistics import fmean
from typing import Any

METRICS = ("useful_breadth", "usefulness", "consistency", "redundancy")
MIN_CI_CASES = 5
RESAMPLES = 2000


@dataclass(frozen=True)
class TrialPoint:
    case_id: str
    replicate: int
    mode: str
    trial_id: str
    degraded: bool


def trial_scores(ratings: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    """Per trial: each rater's LATEST rating counts; raters are averaged; null stays null."""
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for r in sorted(ratings, key=lambda r: r["created_at"]):
        latest[(str(r["trial_id"]), r["rater_alias"])] = r
    by_trial: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (trial, _), r in latest.items():
        by_trial[trial].append(r)
    out: dict[str, dict[str, float | None]] = {}
    for trial, rs in by_trial.items():
        out[trial] = {}
        for m in METRICS:
            vals = [r[m] for r in rs if r.get(m) is not None]
            out[trial][m] = fmean(vals) if vals else None
    return out


def bootstrap_ci(diffs: list[float], *, seed: int, n: int = RESAMPLES) -> tuple[float, float]:
    """95% percentile interval, resampling CASES (doc 09: not individual messages)."""
    rng = random.Random(seed)
    means = sorted(fmean(rng.choices(diffs, k=len(diffs))) for _ in range(n))
    return means[int(0.025 * (n - 1))], means[int(0.975 * (n - 1))]


def _case_means(
    points: list[TrialPoint],
    scores: dict[str, dict[str, float | None]],
    mode: str,
    metric: str,
    exclude_degraded: bool,
) -> dict[str, float]:
    per_case: dict[str, list[float]] = defaultdict(list)
    for p in points:
        if p.mode != mode or (exclude_degraded and p.degraded):
            continue
        value = scores.get(p.trial_id, {}).get(metric)
        if value is not None:
            per_case[p.case_id].append(value)
    return {case: fmean(vals) for case, vals in per_case.items()}


def paired_comparison(
    points: list[TrialPoint],
    scores: dict[str, dict[str, float | None]],
    left: str,
    right: str,
    metric: str,
    *,
    seed: int,
    exclude_degraded: bool = False,
) -> dict[str, Any]:
    a = _case_means(points, scores, left, metric, exclude_degraded)
    b = _case_means(points, scores, right, metric, exclude_degraded)
    cases = sorted(set(a) & set(b))
    diffs = [a[c] - b[c] for c in cases]
    view = "sensitivity (degraded trials excluded)" if exclude_degraded else "intent-to-treat"
    low = high = None
    if len(diffs) >= MIN_CI_CASES:
        low, high = bootstrap_ci(diffs, seed=seed)
        note = f"{view}: 95% bootstrap interval by case ({RESAMPLES} resamples)"
    elif diffs:
        note = f"{view}: exploratory — fewer than {MIN_CI_CASES} matched cases, no interval"
    else:
        note = f"{view}: no matched rated cases"
    return {
        "left": left,
        "right": right,
        "metric": metric,
        "matched_cases": len(cases),
        "mean_difference": fmean(diffs) if diffs else None,
        "ci95_low": low,
        "ci95_high": high,
        "case_differences": [
            {"case_id": c, "difference": d} for c, d in zip(cases, diffs, strict=True)
        ],
        "interpretation": note,
    }
