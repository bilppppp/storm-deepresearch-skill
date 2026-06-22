# Architecture Maintainability

Generated at: `2026-06-22`

## Summary

- decision: `pass`
- python files: `23`
- scripts: `12`
- tests: `11`
- internal modules: `2`
- CLI scripts: `10`
- Yao CLI command handlers: `0`
- entrypoint command handlers: `0`
- command modules: `0`
- largest file lines: `456`
- early watch threshold lines: `600`
- early watchlist: `0`
- watch threshold lines: `720`
- watchlist: `0`
- hotspots: `0`
- blockers: `0`

This report keeps maintainability risk visible before the Meta Skill grows more gates, renderers, and CLI commands.

## Hotspots

No file-size hotspots found.

## Watchlist

No near-threshold files found.

## Early Watchlist

No early watch files found.

## Largest Files

| File | Lines | Kind | Severity |
| --- | ---: | --- | --- |
| `scripts/validate_package.py` | `456` | `cli-script` | `pass` |
| `scripts/contract_io.py` | `374` | `internal-module` | `pass` |
| `tests/test_validate_package.py` | `248` | `test` | `pass` |
| `scripts/normalize_retrieval.py` | `241` | `cli-script` | `pass` |
| `scripts/export_report.py` | `239` | `cli-script` | `pass` |
| `tests/test_contracts.py` | `224` | `test` | `pass` |
| `scripts/init_research_package.py` | `191` | `cli-script` | `pass` |
| `tests/test_normalize_retrieval.py` | `137` | `test` | `pass` |
| `tests/test_init_research_package.py` | `132` | `test` | `pass` |
| `scripts/sanitize_release_archive.py` | `122` | `cli-script` | `pass` |
| `tests/test_library_contract.py` | `115` | `test` | `pass` |
| `tests/test_export_report.py` | `111` | `test` | `pass` |

## Release Rule

- `block` hotspots should be split before governed release.
- `warn` hotspots can ship only when Review Studio keeps them visible and a reviewer accepts the modularization plan.
- Do not split a file only for line count; split when a stable responsibility boundary is clear.
