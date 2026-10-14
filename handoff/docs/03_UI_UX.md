# UI and interaction specification — approved cartoon design

Version 1.1. This replaces the previous light-only interface specification.

## Visual source of truth

Follow the user-approved [dark design](../ui/approved-room-dark.png) and [light design](../ui/approved-room-light.png). Use the expanded-sidebar companions in [dark](../ui/sidebar-expanded-dark.png) and [light](../ui/sidebar-expanded-light.png) for the requested navigation extension. Keep the same characters, calm palette, concise cards, small speech-bubble artwork, and recognizable personality selection. These are generated design references, not running-app screenshots. Written behavior, semantic tokens, contrast and responsive rules below govern details an image cannot define.

Use the images to build real, responsive React components. Never make the whole mockup a background with invisible click targets. The original white three-column interface is retired. Do not reintroduce a permanently open brief/sources rail, oversized 3D heads, or dense dashboard widgets.

## Theme, type and illustration

`config/design-tokens.json` is the exact semantic-token specification. Dark is the default on a new browser. The header has explicit Light and Dark controls; the selected option has text, shape and an accessible pressed state. A switch updates the full app, including menus, dialogs, charts, code blocks, search and empty states. Persist the choice locally and apply it before first paint. Do not infer an OS mode unless a future System option is explicitly added.

Dark uses warm midnight canvas, slightly raised graphite cards, ivory text and soft yellow action controls. Light uses warm off-white canvas, white cards, charcoal text and the same yellow actions. Colorful accents belong to small cartoon portraits and role cues; primary content remains quiet. Normal text must meet 4.5:1 contrast, large text 3:1, and focus/interactive boundaries 3:1. Decorative separators may be subtler. Never put pale yellow text on white or use a faint border as the only control affordance.

Use a local system sans-serif stack, 16px body, 13px secondary labels, approximately 30px desktop room title, 1.55 line height. Titles can wrap instead of shrinking. Use the supplied 4/8px spacing scale. Minimum interactive target is 40px desktop and 44px touch. The app is a working creative tool: generous space, restrained borders, little motion, no giant headings or glossy effects.

Portraits are static editorial cartoon artwork. All eight profiles have a distinct consistent portrait; repeat the same character in the roster and contribution headers. See `config/persona-ui.json` and [asset guidance](../ui/README.md). Portraits are roughly 64px in the roster and 32px in a message header. Do not encode gender, age or ethnicity as behavioral rules. Selection rings/checks are DOM elements outside the artwork. Abstract speech-bubble doodles are decorative, `aria-hidden`, low contrast, and disappear on small screens. No runtime avatar-generation service is required.

## App shell and navigation

| Route | Screen | Essential elements |
| --- | --- | --- |
| `/` | New chat | Idea composer, all-eight selector with default trio, optional three concise starters |
| `/chats` | All / pinned / archived chats | Searchable paginated list; filter state in query string |
| `/folders/:folderId` | Folder contents | Folder title, chats, new-chat-in-folder, folder menu |
| `/rooms/:id` | Chat room | Turn-based transcript, roster, composer, details drawer |
| `/personalities` | Catalog | Eight compact profiles, examples, priorities and accessible selection |
| `/lab` | Experiment Lab | Cases, run progress, blind comparisons, ratings, measured results |
| `/settings` | Local settings | Provider availability, demo/live state, connection check, limits, appearance, local data controls |

Use “chat” for history/navigation labels; retain “room” for the brainstorming concept and existing `/rooms` route. API “session” means the same persistent conversation. These are not separate objects.

Desktop navigation has two states: 64px collapsed rail and 272px expanded sidebar. Initial state is collapsed to match the approved mockup; remember the user's explicit choice. Expand/collapse is a labeled button near the brand, keyboard accessible. Expanding changes main-content width without resetting its transcript, draft, scroll position or selected personalities. The reference companion is illustrative; use these widths and responsive rules, not literal pixel measurements from the image.

Expanded sidebar, top to bottom: brand/collapse; New chat; Search chats; All chats and Pinned; Folders with New folder; openable folder rows and indented chat children; Recent; Archived; Personalities; Experiment Lab; Settings. Footer navigation remains reachable while the history section scrolls independently. Chats have an active state, truncated title with accessible full label, progress indicator when running, and an overflow menu on hover/focus. Touch always has a reachable menu control. A count or dot must not rely on color alone.

Collapsed rail keeps New chat, Search, Chats, Folders, Personalities, Lab and Settings reachable through labeled icons and tooltips. Chats/Folders opens the expanded navigation to that section. Search opens the search dialog directly. Do not require a hover action to reach history. Detailed semantics and complete actions are in [document 14](14_CHAT_WORKSPACE.md).

## Responsive behavior

Main workspace is fluid with a maximum width of 1280px and 24–48px desktop padding. Choose response columns from available CONTENT width, not merely viewport width: three columns at 960px or more, two at 640–959px, one below 640px. A long expanded response spans the entire group width. Never shrink text to keep three cards beside the expanded sidebar.

At viewport widths below 900px, replace the fixed sidebar with a menu button and an overlay drawer up to 320px wide. Opening traps focus; Escape, backdrop or Close dismisses it and restores focus. Selecting a chat closes it. The desktop preference survives mobile use. Below 640px use a single-column transcript, 16px padding, a compact header, and a touch-scrollable roster with visible overflow affordance and an accessible count. All eight remain reachable; no unlabeled truncation or hidden selected persona. The composer respects keyboard/safe-area insets and cannot cover the newest reply. Respect reduced motion.

Test at 1440×900 and 1920×1080 with both sidebar states, 1024×768, and 390×844. At 200% zoom reflow rather than clip. Doodles are removed before content space is sacrificed.

## New chat and eight-personality roster

New chat shows “What would you like to think through?”, an input and the roster. No database record or provider work exists until the first valid Send. If launched from a folder, keep that folder as a visible destination chip. Canceling an empty draft leaves no empty chat in history. Create and first-turn requests use separate stable idempotency keys.

Roster order and short labels are fixed:

| ID | Visible label | Full profile name |
| --- | --- | --- |
| `mentor` | Mentor | Empathetic mentor |
| `skeptic` | Skeptic | Skeptical realist |
| `explorer` | Explorer | Creative explorer |
| `strategist` | Strategist | Business strategist |
| `engineer` | Engineer | Practical engineer |
| `customer` | Advocate | Customer advocate |
| `civic` | Civic thinker | Public-service thinker |
| `health` | Health thinker | Healthcare thinker |

Desktop shows all eight in one compact row when space permits. Below 960px of available roster width, keep the same row horizontally scrollable with visible edge affordances rather than compressing labels or dropping personalities. “Choose perspectives”, “3 selected · 8 available” and “Select all” establish that the initial trio is only a selection. Each selection is a labeled checkbox/button with portrait, name and checkmark. Selecting all updates to “8 selected · 8 available”; the control then offers “Use default trio”. Prevent deselecting the last participant and explain why. A separate profile-details action exposes priorities and an Ask directly action; selecting must not unexpectedly navigate.

Selection changes are saved after successful API mutation, with rollback on failure. During a run, selection and context changes are disabled with a concise reason; browsing profiles remains possible. Standard mode displays a clear single-assistant state and disables persona targeting without pretending eight speakers participated. The panel preference can remain available for a later fork.

## Header, transcript and response cards

Header includes the room title, discreet mode/degraded/demo status, Saved ideas, Light/Dark switch, and overflow for brief, sources, summary, fork and export. Do not surface model IDs or coordinator confidence alongside normal messages. Provider information lives in run details/Settings. Title renaming is also available from the sidebar.

The approved screenshot is ONE visible turn, not a fixed dashboard. A real transcript renders chronological turn groups: user text followed by replies belonging to that run. Earlier turns remain scrollable and searchable. Show full user messages with ordinary expand/collapse for unusually long text. Code, lists and citations must remain usable.

For concise sibling replies, use up to three columns of compact cards: small portrait/name, substantive headline, readable contribution and focus/hover actions. An explicit eight-person panel renders eight cards in stable roster order across rows, never eight narrow columns and never silently truncates to three. Show each requested slot's queued/complete/error state. Auto sequential contributions preserve actual publication order; independent panel siblings keep fixed roster order while results arrive. Keep the reader's position stable.

Real model content may be much longer than the illustrative sentence. A card's summary can use its supplied headline/first meaningful block; do not invent a new factual summary in client code. “Read full response” expands all blocks within the turn group. If collapsed content has citations, show an explicit source affordance and retain those citations when expanded. No ellipsis that hides the only way to reach evidence. Expanded prose uses a readable approximately 68-character measure. All full content persists and exports. Full-screen details should never be needed merely to read a reply.

Message actions: Copy, Reply, Ask more, Challenge, Pin, Feedback, and overflow for branch/regenerate where applicable. Show on hover/focus, keep them keyboard/touch accessible. Plain-text copy preserves attribution and citation URLs; copied code is code only. A source citation opens the Sources drawer to its exact record. External opening is a separate action. User-message editing and regeneration follow document 14's history-preserving branch rules.

## Composer, drafts and navigation

Composer defaults to Auto target and Research: Auto. The compact target control exposes Auto, Everyone selected, or one selected personality. `@` autocomplete inserts a structured target, never ambiguous plain text. Enter sends, Shift+Enter adds a newline; respect IME composition. Expose this hint in a tooltip/keyboard help. Plus opens Add context actions: reference saved ideas, add a textual constraint, or choose a move. File upload is not included; do not render a dead paperclip button.

Explore, Challenge, Combine and Summarize are contextual actions, not a permanent dense toolbar. Combine needs at least two chosen messages/ideas and previews the references. Controls change structured request data rather than secretly appending instructions to the visible user text. Summary is a moderator utility, not a ninth persona.

Drafts persist independently by chat. Switching to another chat is always possible while a run continues; it does not press Stop. The active chat's Send changes to Stop and prevents another simultaneous submission in that chat. Users may type a next draft, pin ideas and browse elsewhere. On return, fetch/replay existing output without starting paid work. Restore draft text/target/reference controls only for the correct chat; clear it only after an acknowledged submission.

## Details and secondary screens

Brief, Saved ideas, Sources, summary and run details open in a closed-by-default drawer or sheet. On desktop the drawer overlays the workspace up to 360px; on mobile it becomes a full-height sheet. Only one details drawer is open. Close returns focus. No permanently competing right rail in either theme.

Brief distinguishes confirmed user constraints from assumptions/open questions; explicit changes create revisions. Saved ideas support title, note, status and Combine. Sources show title/domain/retrieval date and supported text. Summary retains the five established sections and links. Keep these behaviors from the original product specification while using the new visual shell.

The catalog, Lab and Settings use the same semantic theme and navigation. Lab blinding, reveal tracking, measured denominators and no fabricated benchmark results remain unchanged. Cartoon portraits must not leak experiment condition labels. A demo banner is compact but persistent. Settings must not expose secrets.

## Honest states and accessibility

Use real progress stages, not simulated token typing or private reasoning. Empty folder: “No chats yet” and New chat. Empty history: composer, no fake records. Search with no matches: query, clear control and archive-scope option. Provider/research failure keeps existing replies. Missing keys offers explicitly labeled Demo mode. Fallback says “Fixed order used for this turn.” Reconnect never resubmits. Archive requires restore before sending. A stale edit keeps local input and offers refresh/reapply.

Support landmark navigation, visible focus, menu/dialog focus restoration, accessible checkbox groups, `aria-expanded` on folder/sidebar controls, and polite announcements only for meaningful status changes. Keep all eight names readable in both themes. Do not use low-opacity text to represent unselected personas. Preserve scroll while the user reads earlier messages; offer “New responses” instead of forcing scroll. Animation may enhance state transitions but conveys no information unavailable without motion.
