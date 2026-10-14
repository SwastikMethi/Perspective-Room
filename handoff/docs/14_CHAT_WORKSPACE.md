# Chat workspace, sidebar and folders

Version 1.1. These are complete first-release requirements, alongside the existing brainstorming and evaluation features. A “chat” is the existing session entity. A folder organizes chats inside the app; it is not an operating-system directory picker or a retrieval corpus. Use one folder level, with no nested folder tree in this release.

## Navigation and history

The sidebar expands from a 64px icon rail to 272px. Persist expanded/collapsed state and open folder IDs locally; desktop and mobile states are separate. The history region scrolls without hiding New chat, Search or bottom navigation. Routes, selection, draft and active runs survive sidebar toggles.

All chats lists active, non-archived user-created chats across folders. Pinned filters that set. Recent shows non-pinned active chats in descending `last_activity_at`, then ID order. Folder child lists contain the folder's non-archived chats. A chat may appear in both its folder and a global filtered view; it remains one record. Evaluation-generated sessions are excluded from user history and folder controls, but remain available through Lab. Use paginated lists, show Load more, and do not download every transcript to build navigation. Deduplicate by session ID, preserve scroll when activity reorders rows, and reconcile the first page after a mutation or completion.

New chat opens an unsent draft. From a folder's New chat action, set the destination folder; the global New chat defaults to unfiled. The first Send persists the session and opening turn using distinct stable idempotency keys. A refreshed partial creation resumes the same created chat/turn submission instead of creating another. Do not fill the sidebar with blank chats on button presses.

An active row shows a small non-color-only working indicator. Switching chats does not cancel work. Fetch lightweight history every five seconds only while an observed run is active and when the window regains focus; per-chat SSE stays attached only to the current view. On returning to a running chat, load the current snapshot, replay from the last cursor and deduplicate. Other chats can run within the global concurrency ceiling. No provider call is tied to route mounting.

## Folders

| Action | Behavior |
| --- | --- |
| Create | Inline input or dialog; trim name, 1–80 characters; reject a case-insensitive duplicate folder name. Idempotent create. |
| Open/close | Chevron toggles children and persists that browser's state; does not select a chat or trigger generation. |
| Open folder | Clicking the name opens `/folders/:folderId`; breadcrumb and folder list appear. |
| Rename | Optimistic `expected_version`; preserve ID and chat membership. |
| New chat here | Opens the new-chat draft with folder destination visible. |
| Move chat | Accessible “Move to folder” menu supports any folder or “No folder”; single membership only. |
| Delete folder | Confirmation explicitly says chats will be kept. Transactionally set their `folder_id=null`, increment their organization versions, then delete folder. No chat/content/provider record is deleted. |

Deleting a folder is permitted while a member chat is running because membership is not model context. An in-flight move into a deleted folder fails with 404/409; refresh the folder list and retain the old membership. New chat creation targeting a folder that disappeared fails visibly; offer No folder, never silently choose another. Revalidate membership and versions in a transaction. A folder can contain active and archived chats; its visible child count excludes archived ones.

## Chat row menu and ordinary actions

| Action | Behavior |
| --- | --- |
| Open | Load the persisted transcript, draft, settings and active run. Active chat is marked in all visible lists. |
| Rename | 1–120 trimmed characters; user title wins over a later generated title. Update organization metadata, not model context. |
| Pin / Unpin | Persist a boolean. Pinned view and membership remain consistent after refresh. |
| Move to folder | Update single folder ID or unfile; available by menu and keyboard. Drag/drop is optional and cannot be the only mechanism. |
| Archive | Only idle user chats; remove from ordinary history, retain all messages/sources/ideas. Active run returns 409 and offers explicit Stop. |
| Restore | Available in Archived; retain original folder if it still exists, otherwise unfiled. Restore does not generate. |
| Duplicate chat | Use existing fork with all committed history, new IDs and “Copy of …” title. Default to same folder, unpinned and unarchived. |
| Fork here | Copy only the chosen committed prefix and provenance. Show an origin link. Never mutate the source. |
| Export | Markdown/JSON download of this chat using existing provenance-preserving export. |
| Delete chat | Confirmation names the chat and states permanent local removal. Active/evaluation-linked rules remain. Move to another chat or Start and clear only this chat's local draft on success. |

Archived chats are readable and exportable; controls permit copy, restore or delete. Sending, participant/context changes, pinning, moving, duplicating and branching require restoration first. Rename remains allowed. Archive/unarchive is not deletion, and deleting a folder never deletes archived contents. There is no promise of Undo after permanent deletion; do not display a fake Undo action.

## Search

Search chats opens an accessible dialog or sidebar search view; `Ctrl/Cmd+K` is a shortcut and the button always remains available. Search chat titles and persisted public message text case-insensitively using literal substring matching. Index normalized plain text for user, persona, moderator and summary messages; include contribution block text, not private reasoning, API keys, provider traces or external web pages. Search is local database work and never calls an LLM.

Use a 250ms debounce and cancel stale client requests. Queries are trimmed and 1–200 characters; empty means normal listing. Default excludes archived and evaluation-generated chats. “Include archived” changes the query scope explicitly. Filter by folder, pinned or unfiled; never send conflicting folder/unfiled filters. Escape SQL LIKE wildcard characters for literal search and bind parameters. Search results return one hit per chat, a bounded plain-text snippet, matching message ID/sequence when applicable, and folder/archived context. Render highlights safely, never raw HTML.

Results sort by `last_activity_at DESC, id DESC`. A title match takes precedence; otherwise return the earliest matching message. Clicking a content hit opens `/rooms/:id?message=:messageId`, loads a message window around it, and scrolls/highlights without rerunning anything. Clicking an archived result opens read-only with Restore. Deleted or stale results show a clear missing-result state. Paginate with cursors bound to query/filter state; discard cursors when filters change. Search result empty/error/loading states are distinct.

## Composer, copy, edit and regenerate

Basic actions include Copy message, Copy code, Reply, Pin idea, target via picker/`@`, Enter/Shift+Enter, Stop, Retry missing replies, and jump to latest. The existing five structured moves remain accessible through context controls. Attachment ingestion, voice and filesystem browsing are not part of this text-first build; plus opens text-context actions instead.

Published messages remain immutable. “Edit message” on a user message opens an editable draft and clearly says “Send as new branch”. On confirmation, fork immediately BEFORE that user message, then submit the changed text in the new chat. Preserve the old chat, citations and descendants. On the first user message this produces an empty transcript prefix with the applicable pre-turn seed/brief; it does not copy later memory or replies. Creating a fork alone makes no provider calls. A canceled edit or failed fork keeps the original draft available. The client persists the fork ID and stable operation keys until the follow-up submission succeeds.

“Regenerate round” acts on a completed round, explicitly creates a new branch before its opening user message, and resubmits that original turn's text and structured controls from the original immutable snapshot. It regenerates the whole round, not a single silently replaced card. Display that label and a one-line explanation before the action. Reject active, evaluation-managed or nonterminal source rounds. Copy only pre-turn context/profile/settings and remap references; no later brief/memory is allowed. An interrupted or partial latest round instead uses existing Retry missing replies, preserving successful work in the same chat. A successful prior round is never routed to the partial-failure retry endpoint.

Store enough original turn controls internally to execute these actions; public client code must not reconstruct them from rendered text. A regeneration request is an explicit user action with normal limits, idempotency and error handling. The branch API returns the exact resolved turn template when branching before a user message; send it only after the user's explicit action, not on ordinary fork navigation.

## State, versions and data ownership

Database state: folders; chat title/folder/pin/archive fields; transcript; sources; saved ideas; runs; organization versions and activity timestamps. Browser-only state: theme, expanded sidebar, open folders, last visited chat, per-chat draft/target/references, unsent new-chat draft/destination. Local storage keys are namespaced by app and schema version. No credentials. Clear only deleted-chat drafts; failed submissions, rename or search must not erase them. If a saved target/ref was removed, retain text and ask the user to reselect it.

Chat content uses the existing `version`; chat organization uses separate `organization_version`. Title, pin and folder changes are permitted during a run, are atomic, and never bump context `version` or mutate a run snapshot. Context-changing edits remain blocked during runs. Archive requires no active run; restoring changes organization only. Folder writes use folder `version`. Stale mutations return 409 with the latest applicable version, keep entered text, and offer refresh/reapply. Deleting a folder unfiles chats and increments each organization version in the same transaction.

`last_activity_at` advances when a user message or contribution is committed, not on viewing, pinning, moving, renaming, theme switching or SSE replay. Use it for history ordering. `updated_at` may reflect other metadata writes. Automatically generated title is a one-time best effort; use internal `title_is_custom`/compare-and-set so a late generation cannot overwrite a manual rename. None of this organization metadata is sent to Jev/LLM unless the user explicitly writes it into the conversation.

## Required verification

Test folder create/rename/open/delete, moving to/from a folder, duplicates and stale versions; deletion must keep every member chat. Test history pagination and literal search against both title and message, archived scope, safe snippets and message deep links. Switch rapidly among two chats with different drafts while one run completes; restore exactly the correct text and results. Check archive/restore, active-run protection, delete confirmation, pin persistence, full-copy and early-prefix branches. Edit a first user message and regenerate a later round without leaking later context. Verify all controls with keyboard and in both themes, expanded/collapsed/mobile states. Test a full eight-speaker panel and long content; neither may break layout or hide source access.
