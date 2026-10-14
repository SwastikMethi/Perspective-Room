# Approved UI and asset guidance

The user selected the final cartoon interface. These files are design references for a real responsive app, not an implemented UI.

| File | Authority |
| --- | --- |
| [approved-room-dark.png](approved-room-dark.png) | User-approved dark appearance, all eight characters, selected trio, compact response cards |
| [approved-room-light.png](approved-room-light.png) | Matching user-approved light appearance; same layout and characters |
| [sidebar-expanded-dark.png](sidebar-expanded-dark.png) | Dark companion for the requested expandable sidebar, folders and chat history |
| [sidebar-expanded-light.png](sidebar-expanded-light.png) | Matching light expanded-sidebar companion |

The original `room-reference.svg/png` has been removed so the implementation agent cannot follow the superseded white three-column layout. The collapsed references establish the art direction. The expanded companion extends it; document 03 and tokens define exact widths, accessible contrast and responsiveness. Do not copy typography or proportions literally if that makes real content cramped. Use a maximum of three response columns and preserve readable content when the sidebar opens.

## Static portraits

The reference PNGs include all eight original fictional cartoon portraits. `config/persona-ui.json` maps stable persona IDs to short labels, colors and portrait source rectangles. Its labels do not change the full behavioral profiles. Preserve `customer` for Advocate, `civic` for Civic thinker, and `health` for Health thinker.

For a self-contained implementation, the approved PNGs can be reused as static sprite sources. Render only the indicated square inside a circular `overflow: hidden` avatar. Given a source rectangle `(x,y,w,h)`, source image `(W,H)` and displayed avatar width `d`, use scale `s=d/w`, background-size `W*s H*s`, and background-position `-x*s -y*s`. Use the matching theme image. This preserves the exact accepted portraits without a runtime external image service. Keep an accessible role label beside the decorative portrait; do not rely on the portrait alone. Build selection rings/checks and menus as DOM controls, not pixels from the screenshot. Fine-tune source rectangles visually if a hair edge needs adjustment; dedicated optimized portrait assets may replace the sprite while keeping identity and style.

Copy these static assets into the application's served asset directory using hashed build imports. Do not load them from a chat attachment URL or sandbox path at runtime. The app shell, text, response cards, borders and controls must be normal components; using the whole screenshot as a clickable app is unacceptable. Doodles can be tiny local SVG paths; they are decoration and are hidden on narrow screens.

## State examples the implementer must capture

Capture actual-app screenshots, not these mockups: dark/light with collapsed rail; dark/light with expanded sidebar and an open folder; search with results; eight selected/eight replies; a long reply with citations; a long multi-turn chat; and mobile navigation/composer. The supplied images cover one concise turn, so written specifications govern those additional states.
