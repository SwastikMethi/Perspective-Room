"""Experiment Lab analysis (doc 09 §Analysis): pure functions, no database."""

from app.services.results_math import (
    MIN_CI_CASES,
    TrialPoint,
    bootstrap_ci,
    paired_comparison,
    trial_scores,
)


def rating(trial, rater, at, breadth, consistency=None):
    return {
        "trial_id": trial,
        "rater_alias": rater,
        "created_at": at,
        "useful_breadth": breadth,
        "usefulness": 3,
        "consistency": consistency,
        "redundancy": 2,
    }


def test_latest_rating_per_rater_counts_and_raters_are_averaged():
    scores = trial_scores(
        [
            rating("t1", "ana", 1, 2),
            rating("t1", "ana", 2, 4),  # supersedes ana's first rating
            rating("t1", "ben", 1, 5),
        ]
    )
    assert scores["t1"]["useful_breadth"] == 4.5
    assert scores["t1"]["consistency"] is None  # null stays null, never zero


def points(n_cases, diff, *, degraded_case=None, reps=1):
    out = []
    for c in range(n_cases):
        for r in range(reps):
            out.append(TrialPoint(f"c{c}", r, "fixed_panel", f"b{c}{r}", False))
            out.append(TrialPoint(f"c{c}", r, "jev_guided", f"j{c}{r}", c == degraded_case))
    scores = {}
    for p in out:
        base = 3.0 + (diff if p.mode == "jev_guided" else 0.0) + 0.5 * p.replicate
        scores[p.trial_id] = {"useful_breadth": base}
    return out, scores


def test_ci_is_null_below_five_matched_cases_and_present_at_five():
    small, s1 = points(MIN_CI_CASES - 1, 1.0)
    row = paired_comparison(small, s1, "jev_guided", "fixed_panel", "useful_breadth", seed=7)
    assert row["matched_cases"] == 4 and row["mean_difference"] == 1.0
    assert row["ci95_low"] is None and row["ci95_high"] is None
    assert (
        row["interpretation"].startswith("intent-to-treat")
        and "exploratory" in row["interpretation"]
    )
    five, s2 = points(MIN_CI_CASES, 1.0)
    row = paired_comparison(five, s2, "jev_guided", "fixed_panel", "useful_breadth", seed=7)
    assert row["ci95_low"] == 1.0 and row["ci95_high"] == 1.0


def test_replicates_are_averaged_within_a_case_before_differencing():
    pts, scores = points(2, 1.0, reps=3)
    row = paired_comparison(pts, scores, "jev_guided", "fixed_panel", "useful_breadth", seed=1)
    assert row["matched_cases"] == 2  # cases, not trials
    assert [d["difference"] for d in row["case_differences"]] == [1.0, 1.0]


def test_sensitivity_view_excludes_degraded_trials_and_is_labeled():
    pts, scores = points(3, 1.0, degraded_case=0)
    itt = paired_comparison(pts, scores, "jev_guided", "fixed_panel", "useful_breadth", seed=1)
    sens = paired_comparison(
        pts, scores, "jev_guided", "fixed_panel", "useful_breadth", seed=1, exclude_degraded=True
    )
    assert itt["matched_cases"] == 3 and sens["matched_cases"] == 2
    assert sens["interpretation"].startswith("sensitivity")


def test_unmatched_or_unrated_cases_are_left_out_not_zeroed():
    pts, scores = points(3, 1.0)
    del scores["j10"]
    row = paired_comparison(pts, scores, "jev_guided", "fixed_panel", "useful_breadth", seed=1)
    assert row["matched_cases"] == 2
    none = paired_comparison(pts, {}, "jev_guided", "fixed_panel", "useful_breadth", seed=1)
    assert none["matched_cases"] == 0 and none["mean_difference"] is None


def test_bootstrap_is_deterministic_for_a_seed_and_brackets_the_mean():
    diffs = [0.0, 1.0, 2.0, 0.5, 1.5, 1.0]
    a, b = bootstrap_ci(diffs, seed=3), bootstrap_ci(diffs, seed=3)
    assert a == b and a[0] <= sum(diffs) / len(diffs) <= a[1]
