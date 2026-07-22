# Security Trust Report

- OK: `True`
- Scanned files: `68`
- Scripts: `20`
- Internal script modules: `7`
- Secret findings: `0`
- Network-capable scripts: `0`
- Network policy covered scripts: `0`
- Network policy missing scripts: `0`
- File-write scripts: `10`
- Permission approvals: `2 / 2`
- Permission approval gaps: `0`
- CLI help smoke checked: `13`
- CLI help smoke failures: `0`
- Interactive scripts: `0`
- Package hash scope: `source-contract-without-generated-reports`
- Package hash files: `68`
- Package SHA256: `82c8a0f79c687302c6cfb2592f4314a06e5809c148fc7d5ae8c361279dc4bd7b`

## Failures

- None

## Warnings

- None

## Dependency Evidence

- Files: `requirements-ci.txt`
- Pinned entries: `4`
- Unpinned entries: `0`

## Network Policy

- Policy file: `security/network_policy.json`
- Present: `False`
- Covered scripts: `0`
- Missing scripts: `none`
- Mismatches: `0`

## Permission Governance

- Policy file: `security/permission_policy.json`
- Present: `True`
- Required capabilities: `file_write, subprocess`
- Approved capabilities: `file_write, subprocess`
- Missing approvals: `none`
- Invalid approvals: `none`
- Expired approvals: `none`

## CLI Help Smoke

- Enabled: `True`
- Timeout seconds: `5.0`
- Checked scripts: `13`
- Passed scripts: `13`
- Failed scripts: `none`

## Script Surface

| Script | Interface | Declared | Argparse | Main Guard | Input | Network | File Write | Subprocess | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| scripts/agent_run_guard.py | cli | True | True | True | False | False | False | True | Host agents may generate orchestration runners; this guard fails fast on syntax corruption and kills long-running children instead of hiding output. |
| scripts/contract_io.py | internal-module | True | False | False | False | False | False | False | Shared contract loading and validation functions imported by package CLIs. |
| scripts/export_report.py | cli | False | True | True | False | False | True | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts/governed_release.py | internal-module | True | False | False | False | False | True | False | Imported by the single storm-research release command. |
| scripts/harness_io.py | internal-module | True | False | False | False | False | True | False | Provides deterministic identity and promotion primitives for stage receipts. |
| scripts/init_research_package.py | deprecated-cli | True | True | True | False | False | False | False | Compatibility surface forwarding initialization to the governed orchestrator. |
| scripts/local_output_eval_runner.py | cli | False | True | True | False | False | True | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts/merge_claim_ledger.py | internal-worker-cli | True | True | True | False | False | False | False | Returns a merged Claim set; only storm_research may commit stage receipts. |
| scripts/normalize_retrieval.py | internal-worker-cli | True | True | True | False | False | True | False | Produces validated staging records; only storm_research may commit receipts. |
| scripts/output_paths.py | internal-module | True | False | False | False | False | False | False | Shared output boundary checks imported by package CLIs. |
| scripts/render_audit_views.py | cli | False | True | True | False | False | True | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts/report_traceability.py | internal-module | True | False | False | False | False | False | False | Binds report paragraphs and public citations to governed Claims and sources. |
| scripts/run_checks.py | cli | False | True | True | False | False | False | True | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts/run_state.py | internal-module | True | False | False | False | False | True | False | Owns all governed run state transitions and receipt verification. |
| scripts/sanitize_release_archive.py | cli | False | True | True | False | False | True | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts/source_evidence.py | internal-module | True | False | False | False | False | False | False | Computes authoritative source hashes and provenance for the retrieval stage. |
| scripts/storm_research.py | cli | True | True | True | False | False | True | False | The only supported public command surface for governed research stages. |
| scripts/validate_contracts.py | cli | False | True | True | False | False | False | False | Default CLI classification; add SCRIPT_INTERFACE for internal modules. |
| scripts/validate_evidence.py | internal-worker-cli | True | True | True | False | False | False | False | Deterministic evidence closure used by the governed evidence stage. |
| scripts/validate_package.py | public-worker-cli | True | True | True | False | False | True | False | Offline governed validation and validation receipt commitment. |
