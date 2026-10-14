# Implementation acceptance checklist

This checklist is intentionally unmarked. It is for the implementation agent to complete with actual evidence. Documentation validation does not establish application correctness.

## Product

- [ ] All eight configured personalities are selectable and behaviorally distinct in inspected examples.
- [ ] Auto, direct-person, panel, reply, explore, challenge, combine, and summary flows work.
- [ ] Explicit user choices override automatic routing.
- [ ] First panel views are generated from an identical input snapshot.
- [ ] Brief edits are versioned; user corrections override derived memory.
- [ ] Saved ideas, notes/status, forks, persistence, deletion, and exports work.
- [ ] Chat history, title/body search, pinning, archive/restore, rename, move and export work after refresh.
- [ ] Folder create/rename/open/close/delete works; folder deletion retains every member chat.
- [ ] Copy/reply, edit-and-branch and regenerate-round actions preserve published source history.
- [ ] Per-chat drafts and ongoing generation survive switching among chats without duplicate work.
- [ ] Sources are visible, clickable, and attached to the relevant factual blocks.
- [ ] Research failure and uncertainty are represented honestly.

## Integration and reliability

- [ ] Real OpenAI and Jev adapters are implemented, with documented configuration.
- [ ] Demo mode is explicit and never substitutes for a live failure.
- [ ] Jev request/response contracts, independent questions, and fallback behavior are tested.
- [ ] Duplicate submissions and concurrent turns cannot duplicate logical work.
- [ ] Stop prevents new work and late publication; published messages survive.
- [ ] SSE replay does not rerun generation or duplicate displayed messages.
- [ ] Restart recovery preserves committed output and marks uncertain work interrupted.
- [ ] Provider refusal, truncation, malformed output, timeout, and partial failure are handled.
- [ ] Context, contribution, retry, research, deadline, and concurrency limits are enforced.
- [ ] Credentials are absent from browser bundles, logs, exports, and git.
- [ ] The application is published on loopback only; database port is private.

## UI

- [ ] Start, Chats, Folder, Room, Personalities, Lab, and Settings screens are complete.
- [ ] Visual implementation follows the approved cartoon references, including all eight recognizable portraits.
- [ ] Dark is default; dark/light switch persists and themes every screen/menu/dialog.
- [ ] Sidebar expands/collapses; mobile drawer, search, chat menus and open folder children are keyboard accessible.
- [ ] All-eight panel replies, long responses with sources and multi-turn history reflow without clipping; details stay closed by default.
- [ ] Desktop and mobile walkthroughs pass without overflow or unreachable controls.
- [ ] Loading, empty, partial, error, cancellation, reconnect, and missing-key states are usable.
- [ ] Keyboard navigation, focus, reduced motion, readable contrast, and zoom are checked.
- [ ] No fake benchmark metrics, decorative reasoning traces, or unfinished required controls appear.

## Experiment

- [ ] Standard, Fixed panel, and Jev-guided are implemented with recorded configuration.
- [ ] Matched comparisons hold model/profile/evidence settings appropriately constant.
- [ ] Blind labels and reveal tracking work; persona consistency is null for Standard.
- [ ] Incomplete/degraded trials remain in denominators and exports.
- [ ] Synthetic/demo data is labeled and excluded from live effectiveness claims.
- [ ] Ratings, paired comparisons, uncertainty display, and CSV/JSON export work.
- [ ] No large live benchmark runs without an explicit Run action.

## Delivery

- [ ] A fresh checkout starts using the documented Docker Compose command.
- [ ] Migrations, seed loading, dependency lockfiles, and environment template are supplied.
- [ ] Required automated tests and actual browser checks were run; results are recorded.
- [ ] Actual-app screenshots include both themes, both sidebar states, a folder, search, all eight replies, long content and mobile navigation.
- [ ] Any live smoke tests are identified separately from mocks; missing access is disclosed.
- [ ] Implementation notes, report, screenshots, and exact launch commands are delivered.

The experimental conclusion may be positive, negative, or inconclusive. Marking the application complete must never require inventing evidence that Jev improves it.
