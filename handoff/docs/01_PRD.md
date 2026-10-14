# Product requirements — Perspective Room

## Product question

Can Jev coordinate an LLM into distinct, consistent personalities that help a user discover useful possibilities they would miss in an ordinary conversation? The product supports exploration, constructive disagreement, idea development, and revisiting assumptions. A consensus or a winning personality is not required.

## Target user and primary journey

Initial user: a person exploring a product, work process, community initiative, creative project, or everyday decision on their own computer. Example: "I want to build an interview-practice app for college students." They choose perspectives, share constraints, question individual participants, save useful ideas, and leave with alternatives and a concrete experiment.

The default room has Mentor, Skeptic, and Explorer selected. All eight profiles are visible together in the desktop selector; on small screens the same roster scrolls with clear overflow affordance. The default trio is checked and the other five remain visible and selectable. The user's first message starts the session; title generation and extraction of a working brief happen in the background. Optional constraints are conversational, not a required intake form.

## P0 requirements

| ID | Requirement | Acceptance behavior |
| --- | --- | --- |
| PR-01 | Eight personalities | Catalog includes all eight profiles in `config/personalities.json`; select 1–8; profile descriptions explain their distinct contributions. |
| PR-02 | Natural conversation | User can send ordinary text, address a personality through the target picker or mention autocomplete, and respond to a specific message. |
| PR-03 | User control | Commands and structured UI selections override automatic speaker selection. Stop immediately prevents new provider calls and new contributions. |
| PR-04 | Guided turns | Auto mode produces up to three contributions per submitted turn, usually from different selected participants, then returns control. The user can continue indefinitely through new turns. |
| PR-05 | Ask the panel | Explicit panel mode requests exactly one contribution from each selected participant, up to eight. Partial failure is visible and does not discard successful replies. |
| PR-06 | Distinct perspectives | Contributions reflect profile priorities and habits, contain a specific useful angle, and avoid copying previous responses. Disagreement is grounded in assumptions or priorities. |
| PR-07 | Targeted exploration | Expand, Challenge, Combine, and Summarize actions are available. Combine can reference two or more saved ideas or messages. |
| PR-08 | Idea evolution | A working brief records the idea, explicit user constraints, assumptions, and open questions. User edits create an immutable idea revision. Model suggestions never silently become user-confirmed facts. |
| PR-09 | Saved ideas | Users can pin a useful contribution, rename the saved idea, add their own note, and mark it exploring, selected, or parked. |
| PR-10 | Research | Research automatically runs when materially useful and not already answered by evidence. User can explicitly request it or turn it off for a session. Citations are visible beside supported text. |
| PR-11 | Summaries | Summary states useful directions, disagreements, assumptions, open questions, and suggested experiments. It links to supporting messages and sources. |
| PR-12 | Persistence | Refresh preserves conversation, profiles, ideas, sources, and job state. A session can be renamed, deleted, forked, and exported as Markdown or JSON. |
| PR-13 | Comparison modes | Standard, Fixed panel, and Jev-guided modes work in the same app. Session mode is fixed at creation; use a fork or Lab comparison to change it. |
| PR-14 | Experiment Lab | Run matched cases, inspect progress, rate anonymized outputs, reveal conditions, view measured results, and export data. |
| PR-15 | Honest operation | Demo, degraded coordination, missing keys, failures, cancellations, and unverified claims are clearly represented. No fabricated provider activity or benchmark results. |
| PR-16 | Accessible UI | Keyboard access, readable contrast, meaningful loading states, reduced-motion support, usable desktop and mobile layouts. |
| PR-17 | Approved design and themes | Match the approved cartoon portraits, compact perspective cards and quiet artwork; working persistent dark/light switch, dark default. |
| PR-18 | Chat workspace | Expand/collapse sidebar; list, reopen, search, rename, pin, archive/restore, move, delete and export chats. Maintain drafts and running jobs while switching chats. |
| PR-19 | Chat folders | Create, rename, open/close, and delete single-level folders; add/move chats; deleting a folder retains chats. |
| PR-20 | Everyday chat actions | Copy, reply, keyboard send, stop, retry missing replies, duplicate/fork, edit-and-branch a sent user message, and regenerate a round in a new branch without overwriting history. |

## Interaction semantics

- `auto`: Jev selects useful speakers and moves, subject to limits and explicit user intent.
- `person`: one named, selected personality responds. If it is not selected, offer to add it before submitting; never silently add it.
- `panel`: each selected personality responds once. On the opening turn, use the same input snapshot for independent first views. On later turns, each sees the prior public conversation but not sibling drafts from the current panel round.
- `summary`: the neutral moderator summarizes, outside the eight personalities. It is a utility role, not a ninth persona.
- The optional move override is `explore`, `challenge`, `expand`, or `combine`. A message-specific Reply sets `reply_to_message_id`; Combine carries referenced saved-idea IDs. Otherwise the router chooses a move.
- Free-text names become structured mentions only after selecting an autocomplete result. An ambiguous plain-text name is ordinary text; the intake step may ask a short clarifying question.

The user can type the next draft while a run is active; sending another turn or changing the active room’s participants/settings/brief waits for completion or Stop. Navigating to a different chat is always allowed; its draft and generation state remain independent. Pinning and feedback remain available. Summaries are explicit actions or suggested buttons; the system does not repeatedly force summaries.

## Personality behavior

Traits are operational instructions, not demographic stereotypes or diagnostic labels. An empathetic persona can disagree; a skeptic can acknowledge progress; a practical persona can suggest an experiment instead of dismissing an idea. Opinions can change with new evidence while priorities remain recognizable. Participants do not claim human experience, personal credentials, or actual professional responsibility.

## Complete first-release scope

P0 includes all requirements above, one local user, English-first text interaction, the eight curated profiles, live research, and evaluation. Voice, runtime avatar generation/customization, image/video generation, file-upload ingestion, arbitrary local filesystem browsing, nested folders, public accounts, billing, organizations, custom-persona authoring, and provider marketplace features are outside this release. Bundled static cartoon portraits, both themes, and single-level chat folders are required. The composer plus opens useful text/context actions, not an unimplemented attachment uploader. The configuration format allows later extension without making those features partial stubs in the UI.

## Success and release criteria

Functional release is determined by the acceptance checklist and meaningful tests. Research success is measured separately; a working application may find Jev offers no improvement. Primary research outcome: blind human-rated useful breadth of perspectives. Supporting outcomes: concrete new directions, persona consistency, usefulness, redundancy, unsupported claims, elapsed time, tokens, and cost when rates are configured. Details and limits are in document 09.

No fixed $200 cap remains. Track use and allow an optional user-configured cap. Per-turn and provider-call limits remain as reliability controls.

## Example experience

The user proposes interview practice for students. Explorer suggests peer practice groups. Mentor asks how anxious students can start comfortably. Skeptic asks what would make students return. The user selects Engineer and asks for a small implementation. Engineer proposes text practice with specific feedback. Research verifies a current platform capability only if needed. The user pins the feedback idea and asks for a summary: a text prototype, a small user study, and unresolved questions about repeat use and demand. This illustrates desired behavior, not a promised model output.
