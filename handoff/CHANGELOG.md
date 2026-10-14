# Handoff revision 1.1 — approved cartoon UI and chat workspace

14 October 2026. This revises the implementation specification; it does not claim the application has been built.

- Replaced the obsolete white three-column UI reference with the user-approved cartoon dark/light mockups.
- Added the expanded-sidebar reference while preserving the approved characters, colors, card treatment and content hierarchy.
- Made dark and light complete themes with a persistent switch; dark is the initial default.
- Made all eight personalities visible in the roster; three are selected by default. A panel can request all eight.
- Defined collapsed/expanded/mobile sidebar states, chat history, folder navigation, search, pinning, archive/restore, moving, renaming, deletion and exports.
- Defined per-chat draft recovery, active-run navigation, copy/reply, edit-and-branch and regeneration without overwriting published history.
- Added folder and chat-organization API/data contracts, search projections, fixtures and acceptance cases.
- Added UI tokens, persona presentation mappings, static portrait reuse guidance and implementation priorities.
- Preserved the existing Jev/OpenAI architecture, personality prompts, provider configuration, evaluation design and budget decisions.

Read `START_HERE.md`, document 03 for design, document 14 for workspace behavior, and the updated execution prompt. The new specification takes precedence over prior copies of the handoff.
