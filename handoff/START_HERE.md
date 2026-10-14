# Perspective Room — implementation handoff

Version 1.1 · 14 October 2026 · Owner: Swastik Methi

Build a local, polished brainstorming application in which eight simulated personalities help a person explore an idea. OpenAI generates conversation; TypeSafe Jev selects useful contributions and assesses their fit. The central experiment is whether this combination produces more useful perspectives than an ordinary LLM conversation or a fixed personality panel.

This folder is a specification and seed-data package, not a running application. The scope is settled; the implementation agent should build the complete application in one coding session with internal verification checkpoints.

## Confirmed decisions

- Personal/local use without login. Bind the published application to loopback.
- Research when useful, with visible, clickable sources and clear unknowns.
- Eight built-in personalities. All eight are available; select between one and eight for a session. Default selection: mentor, skeptic, explorer.
- OpenAI API for generation and research; Jev remains the coordinator. API credentials are supplied through backend environment variables.
- The earlier $200 constraint is removed. There is no default dollar spending cap; operational limits prevent runaway work.
- React + TypeScript + Vite frontend, FastAPI backend, PostgreSQL persistence, Docker Compose. The production build is served by FastAPI on one origin.
- One configured generation model across personalities and experiment arms initially. The provider configuration is replaceable; distinct personalities do not depend on distinct models.
- Text conversation, saved ideas, summaries, session forks, source inspection, and the three-arm Experiment Lab are all part of this implementation.
- Follow the user-approved cartoon interface in both dark and light themes; dark is the default. All eight personalities are visible in the selector.
- Include an expandable chat sidebar with history, search, folders, pinning, archive/restore, rename, move, delete, export, and per-chat drafts. Folders organize chats inside this app.

## How to use this package

1. Put this directory in a new repository as `handoff/`.
2. Give the coding agent the entire folder, not only the PRD.
3. Paste [OPUS_EXECUTION_PROMPT.md](OPUS_EXECUTION_PROMPT.md) into Opus 5.5.
4. Supply API keys locally in the resulting application's `.env`; never paste them into committed documentation.
5. Require the agent to complete the acceptance checklist and report which checks used mocks versus live providers.

## Reading order

| File | Purpose |
| --- | --- |
| [01_PRD.md](docs/01_PRD.md) | Product behavior, user stories, scope, success criteria |
| [02_TRD.md](docs/02_TRD.md) | Architecture, jobs, state, concurrency, reliability |
| [03_UI_UX.md](docs/03_UI_UX.md) | Screens, interactions, layout, tokens, accessibility |
| [04_PERSONALITIES.md](docs/04_PERSONALITIES.md) | Eight distinct personalities and consistency rules |
| [05_JEV_ORCHESTRATION.md](docs/05_JEV_ORCHESTRATION.md) | Typed decisions, deterministic policy, uncertainty and fallback |
| [06_PROMPTS_AND_CONTEXT.md](docs/06_PROMPTS_AND_CONTEXT.md) | Prompt templates, context selection, memory contracts |
| [07_RESEARCH_AND_SOURCES.md](docs/07_RESEARCH_AND_SOURCES.md) | Research execution and source provenance |
| [08_API_AND_DATA.md](docs/08_API_AND_DATA.md) | API semantics, persistence, SSE, schema ownership |
| [09_EVALUATION.md](docs/09_EVALUATION.md) | Fair comparisons, human ratings, interpretation |
| [10_TEST_PLAN.md](docs/10_TEST_PLAN.md) | Meaningful automated and live checks |
| [11_IMPLEMENTATION_PLAN.md](docs/11_IMPLEMENTATION_PLAN.md) | Complete build order and deliverables |
| [12_SETUP_OPERATIONS.md](docs/12_SETUP_OPERATIONS.md) | Setup, configuration, recovery, troubleshooting |
| [13_DECISIONS_AND_SOURCES.md](docs/13_DECISIONS_AND_SOURCES.md) | Design decisions and verified provider references |
| [14_CHAT_WORKSPACE.md](docs/14_CHAT_WORKSPACE.md) | Sidebar, folders, search, drafts, chat actions, and state rules |
| [ACCEPTANCE_CHECKLIST.md](ACCEPTANCE_CHECKLIST.md) | Final implementation gate |

`config/` contains application defaults, personality definitions, design tokens, and an environment template. `contracts/` contains machine-readable public and model-output contracts. `fixtures/` contains examples and a 30-case evaluation seed set. Fixtures are illustrative, never measured product results.

The user-approved [dark mockup](ui/approved-room-dark.png) and [light mockup](ui/approved-room-light.png) are the visual source of truth. The expanded sidebar companions in [dark](ui/sidebar-expanded-dark.png) and [light](ui/sidebar-expanded-light.png) add chat navigation in the same design. Read [ui/README.md](ui/README.md) for reference precedence and asset usage. These are design images, not screenshots of an implemented app. The earlier white three-column design has been removed.

See [CHANGELOG.md](CHANGELOG.md) for the complete 1.1 revision.

## Precedence and reconciliation

User decisions above take priority. For product scope use the PRD; for orchestration use document 05; for public fields use `contracts/openapi.yaml`; for LLM output shapes use the individual JSON schemas; for personality content and limits use `config/`. For appearance use the approved dark/light references together with document 03 and design tokens; document 14 owns sidebar/chat behavior. Use written specifications for responsive states and behaviors not visible in the mockups. Supporting documents explain those contracts. If a genuine contradiction is found, resolve it according to this order, update the affected docs, and record the decision. Do not silently omit a required feature.

No application has been built or provider calls executed as part of authoring this package. Provider interfaces were checked against official documentation on the date above; account access still requires a live check during implementation.

See [PACKAGE_VALIDATION.md](PACKAGE_VALIDATION.md) for checks performed on this handoff itself. The archive includes a manifest of file sizes and SHA-256 hashes for transfer integrity.
