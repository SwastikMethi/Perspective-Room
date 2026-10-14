# Evaluation and experiment plan

## Hypothesis and conditions

The project tests whether a Jev-supervised personality discussion improves useful breadth while maintaining relevance and consistency. It does not test whether personas are genuine people or licensed experts, and it does not assume Jev will win.

| Condition | Generation behavior | Coordination and assessment |
| --- | --- | --- |
| A — Standard | One neutral assistant, no persona profiles | Same intake/memory utilities and deterministic validation; no Jev |
| B — Fixed panel | Same selected profiles as C | Deterministic round-robin speakers, fixed explore/challenge/expand move cycle; no Jev |
| C — Jev-guided | Same base model and profile definitions as B | Jev chooses speakers/moves and provides the semantic assessment described in document 05 |

C versus B measures the added Jev coordination-and-assessment package. It does not isolate routing from repair. C versus A measures the complete multi-perspective experience. A better score in C cannot be attributed to an underlying model upgrade because the configured generation model is held constant.

## Matched comparison requirements

Keep the exact starting idea, user constraints, scripted follow-ups, base generation model, supported inference settings, persona versions, context policy, and output ceilings fixed. B and C share the same selected-personality order. Use one independent session per case/condition/repetition, with no content leakage between conditions.

The authored seed set contains 30 cases across products, community, work, creative projects, education, and well-being. Each has three predetermined user turns. It is a pilot set, not a validated benchmark. Scripted follow-ups are comparable but less natural than adaptive human discussion; report that limitation.

For primary comparison, use research off or the same immutable evidence pack across conditions. Null pack IDs in the seed set mean no evidence is supplied, even if batch policy is fixture. The supplied synthetic pack is for plumbing tests only and must retain its fixture label. Do not describe synthetic evidence as real research. A separate live-research comparison can measure the whole experience, including different queries and evidence.

Apply the same turn-level visible-output allowance: Standard targets up to approximately 450 words in one contribution, while B/C target up to three 150-word contributions. The default hard generation-output budget is 12,288 tokens per turn, divided across persona contributions for B/C. These ceilings include provider reasoning where relevant and do not equalize actual computation. Record actual tokens, context volume, calls, repairs, and elapsed time; do not claim an improvement independent of compute without a separately matched-cost study.

The intake and memory calls are shared utilities with matching settings. Jev calls and triggered repairs are part of C's treatment cost. Log them all. In ordinary use the UI can request a whole eight-person panel; the primary benchmark uses the case-defined three-person selection.

## Human rating rubric

| Metric | 1 | 3 | 5 |
| --- | --- | --- | --- |
| Useful breadth — primary | Repeats one view or irrelevant alternatives | Several relevant angles with some overlap | Distinct, useful possibilities that change what the user could consider |
| Usefulness | Generic or hard to act on | Some concrete suggestions | Clear, relevant next steps or experiments tailored to constraints |
| Personality consistency | Mostly indistinguishable or contradictory behavior | Recognizable profiles with drift | Stable priorities with appropriate updates after new evidence |
| Redundancy — lower is better | Little unnecessary repetition | Several overlapping contributions | Mostly repetition without development |

Personality consistency is not applicable to Standard; store null, not zero. Additional manual labels: unsupported factual claim, missed explicit constraint, false credential claim, and mishandled disagreement. Count distinct useful directions by meaning, not sentence count or length. A useful development of an existing idea can count as progress without being an entirely new topic.

The product user's own rating is valuable, but it is not an independent blinded study. A small user study can have multiple volunteers rate exported anonymized trials without adding an account system. Record a non-identifying rater alias. At least a subset should receive two ratings to inspect disagreement. Do not use Jev as the sole judge of whether Jev improved the results.

## Blind presentation and reveal

Shuffle A/B/C labels within each matched case/repetition and persist the mapping. Hide mode badges, provider names, metrics, and fallback diagnostics while rating. Keep persona labels so fidelity can be assessed. This masks the intervention label, not the obvious number of speakers. The local owner can inspect stored data; blinding is a study presentation aid, not an access-control boundary.

When a trial is revealed, record that fact. Ratings saved afterward are marked unblinded by the server regardless of the client flag. Never silently overwrite a prior rating. A new rating can supersede one for analysis while preserving history.

## Analysis and reporting

Report sample counts, completion rates, fallbacks, repairs, and evidence policy before comparisons. Pair results by case and repetition. For C−B and C−A, show the paired difference distribution, mean/median, and a 95% bootstrap interval sampled by case (not by individual message). With very small samples, show raw points and describe results as exploratory. Repetitions from one case are not independent new ideas.

Include degraded C runs in an intent-to-treat view; also provide a labeled sensitivity view excluding degraded runs. Report incomplete trials rather than deleting failures from the denominator. Cost is unknown when rate cards or usage are missing. Demo-provider output never enters a live-model effectiveness report.

Possible outcomes are improvement, no clear difference, or worse performance. A functional release requires working measurement, not a favorable result. To claim useful improvement, predeclare a practically meaningful threshold before inspecting results, check that uncertainty and user relevance support it, and report the chosen threshold. Do not invent a universal success percentage.

## Lab execution

Default to one repetition and a small selected subset; support the full 30-case set. Each trial means one complete case/condition/repetition conversation, including its three user turns. Validate `case_count × mode_count × repetitions <= max_trials`, maximum 90 per batch. Reject an oversized request with a clear 422, never truncate silently. Higher repetitions can be run on smaller subsets.

The evaluation service reuses the normal orchestrator, persistence, and provider adapters. It schedules bounded child work without occupying all worker slots while awaiting queued children. Cancel prevents new turns and cancels active child work. Persist progress so a restart marks interrupted trials honestly. The user can select unfinished cases for a new batch; this runs the selected conditions again and shows the new planned trial count. There is no automatic continuation of uncertain paid calls. Re-running creates a separate batch, not overwritten results or silently pooled measurements.

Export case inputs, condition/version identifiers, evidence hashes, ratings, output lengths, provider usage, latency, failures, and quality flags. Preserve live provider request IDs locally for diagnosis without exposing credentials.
