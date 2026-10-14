# Jev orchestration and policy

## Division of responsibility

The LLM understands the user's message and writes contributions. Jev evaluates explicit questions against a compact state. Backend code owns eligibility, source checks, state transitions, cancellation, limits, and publication. User-specified recipients and actions override automatic choices.

Use HTTP `POST https://api.typesafe.ai/v1/systemone`, bearer authentication, and the versioned model in configuration. Provider envelope: `state`, `model`, and `questions`; results are under `answers`. Choice questions use `type=choice`, `instructions`, and an option-to-description `criteria` map. Score questions use an ordered criteria array. Details and sources are in document 13; the bundled request/response fixtures show original application-specific examples.

## State prepared for each coordination step

Include the current user request, scoped focus, confirmed brief and constraints, explicit controls, selected profile summaries, relevant public messages, a concise idea ledger, open questions, evidence availability, already-heard participants, and remaining contribution/research capacity. Use stable IDs throughout. Untrusted message/evidence contents are data and never change policy or allowed options.

The intake LLM supplies one `focus` string and an optional research question. Jev does not invent those strings. New topic exploration happens through an `explore` contribution and the next turn's context; do not ask Jev for unbounded text.

## One independent question batch per routing step

1. `next_speaker`: choose from the code-generated eligible participants plus `return_user`. Ask only which available perspective would most usefully address the supplied focus, considering prior contributions. `return_user` means another automatic contribution is unlikely to help or essential user context is missing.
2. `move_<persona_id>`: for each eligible persona, ask which contribution type that specific persona should make on the current focus. Options: `explore`, `challenge`, `expand`, `combine`, `clarify`. Include persona name/profile in the question instructions; question IDs are not visible to Jev.
3. `research_needed`: choose `needed`, `not_needed`, or `uncertain` for whether the supplied research question requires current external evidence and is useful to this turn.

These questions do not depend on one another's outputs. Each move question is explicitly conditional on its named persona speaking. After the batch, code reads the selected speaker's already-computed move. Never write a question that asks Jev to inspect another answer from the same call.

When the user names a participant, skip automatic speaker selection and use the corresponding move result. When the user chooses a move, keep that move. Panel mode fixes all speakers; evaluate their moves and research needs against the same initial snapshot, then generate independent drafts. Summary uses the moderator without speaker routing.

For a panel round, assess each initial draft against that same pre-round snapshot. Cross-persona duplication within the current panel can be logged for the next turn, but must not feed sibling drafts into an initial-view repair. This preserves independence while still allowing cross-persona development on subsequent turns.

## Deterministic policy

Apply rules in this order:

1. Stop/cancellation, invalid state, input limits, and provider availability.
2. Explicit user target, audience, move, and research override.
3. Eligible selected participants; exclude those already heard in this auto round.
4. Remaining contribution, provider-attempt, and time limits.
5. Valid Jev result and configured confidence threshold.
6. Fixed fallback when a result is uncertain, malformed, or unavailable.

Validate every selected option against the exact request options; validate probabilities, finite values, confidence bounds, and expected answer types. Never execute an arbitrary returned string as a tool or persona ID. For a single eligible option, choose it in code.

Initial experimental thresholds: routing confidence 0.35; audit failure confidence 0.70. These are provisional settings, not calibrated guarantees. Below the routing threshold, use the least recently heard eligible selected participant, breaking ties by selection order. Default move is `explore` on the first contribution and `expand` afterward. Do not force a second perspective when no participants remain.

If Jev selects `return_user`, end the round after published replies. If no contribution has been published, produce one short moderator clarification when the intake supplied a material missing question; otherwise use the deterministic speaker fallback so the user does not receive an unexplained empty result.

## Research decision

Research is allowed only if session policy permits it and this turn has capacity. Explicit `force` performs a research step. Auto requires `needed` above the routing threshold and a nonempty intake research question. `uncertain` continues with labeled assumptions unless the requested answer depends on the missing fact; in that case ask the user or offer Research this. Maximum one research job per turn. Its output becomes shared evidence for the rest of the turn; code overrides later research choices once capacity is consumed.

## Draft assessment and publication

First validate the LLM schema, referenced IDs, URLs, citation IDs, and output limits in code. Then, in Jev-guided mode, assess three independent dimensions against the candidate and context:

- `profile_fit`: 0 = contradicts profile priorities or invents credentials; 1 = generic/unclear; 2 = clearly reflects the profile.
- `distinct_value`: 0 = restates a prior point without development; 1 = modest elaboration; 2 = a useful new question, implication, alternative, or concrete development.
- `constraint_fidelity`: 0 = contradicts an explicit user constraint; 1 = ambiguous or incomplete; 2 = respects the constraints or explicitly explains a trade-off.

Use the ordered three-level Score primitive. Its score can be fractional. Trigger one repair when a dimension has score below 0.5 and confidence at least 0.70, or a deterministic validation fails. At most one repair is allowed across the whole turn, including schema and semantic repairs. Persist all attempts and the repair reason. Give the LLM the failed dimension and relevant evidence; never claim Jev supplied a free-form rationale it did not return.

If repair capacity is exhausted: deterministically invalid content is not published; a schema-valid but semantically weak contribution can be published with `quality_warning` in run details. Return control rather than loop. Audit unavailability allows schema-valid output with `audit_unavailable`. Low-confidence audit results are observations, not automatic rejection. Do not display numerical Jev scores as scientific measures of idea quality.

The Standard and Fixed panel baselines use the same deterministic validation and repair ceiling, with no Jev calls. Therefore the main experiment estimates the full Jev coordination-and-assessment package, not routing alone. The evaluation document requires that distinction in reporting.

## Model selection

Use the same configured OpenAI model for every personality in the initial product and benchmark. Jev selects a perspective and contribution, not a different generation model. Keep provider interfaces replaceable. Any later model-switching experiment must be a separate condition so model quality does not confound this experiment.

## Traceability

Record request ID, run ID, profile/prompt versions, eligible options, selected outcome, confidence, scores, timing, fallback reason, and provider-reported usage. Store input hashes plus the bounded decision state locally for reproducibility; exclude secrets and hidden reasoning. Ordinary UI explanations can be deterministic, such as "You asked Engineer" or "Fixed order used because coordination was unavailable." Do not manufacture a detailed internal explanation of Jev's choice.
