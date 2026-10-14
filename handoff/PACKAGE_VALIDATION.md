# Documentation package validation — revision 1.1

Checked on 14 October 2026. These checks validate the handoff, not a running application.

- All 31 JSON files and the OpenAPI YAML parse successfully.
- The API contains 30 paths and 39 operations with unique operation IDs and matching path parameters.
- Internal API references resolve; the standalone domain mirror matches OpenAPI components.
- The five model-output schemas still match their public components. Original and new examples pass the included checker for the schema keywords used in this package.
- New folder, organization, search-list and fork-result fixtures validate. Workspace folder membership/counts, draft keys, search deep links and branch lineage/version references agree.
- There are exactly eight behavioral profiles, eight corresponding presentation mappings, and thirty benchmark cases with three turns each.
- Jev request/response probabilities, confidence and options remain internally consistent.
- All local Markdown links resolve. Core theme text pairs meet at least 4.5:1 contrast and focus/canvas pairs at least 3:1; the rendered app still needs accessibility checks.
- Four UI PNG references are included: user-approved dark/light collapsed views and matching expanded-sidebar companions. They were visually inspected. PNG dimensions, sprite rectangle bounds and asset/config paths agree.
- Both themes and 64px/272px sidebar tokens agree with application defaults. The superseded white UI PNG/SVG is absent.
- API credential placeholders are empty and the default dollar cap remains unset.
- The original personality definitions, LLM-output schemas, Jev orchestration, prompt/context rules, research protocol and evaluation specification are unchanged.

Reproduce the package checks with `python validation/validate_handoff.py` (requires PyYAML). The current run passed 630 assertions/reference checks. The checker covers syntax, internal relationships and the schema subset used here; it is not a full JSON Schema/OpenAPI standards validator. The ZIP includes a refreshed SHA-256 manifest, excluding the manifest itself, for transfer integrity.

This revision edits requirements, configuration, contracts, examples and visual references. No app implementation, browser behavior, live provider call or product-effectiveness experiment has been executed. The implementation acceptance checklist remains intentionally unmarked.
