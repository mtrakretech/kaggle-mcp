# Roadmap: agent-assisted, reproducible Kaggle research

The goal is a useful companion to Kaggle's official server: explainable experiments
with source fingerprints, evaluation discipline, bounded execution, and reviewable
results. More tools alone do not establish usefulness or adoption.

## Implemented in 3.1

- Six local experiment provenance tools with a SQLite ledger.
- Notebook and code fingerprints, dataset version warnings and evaluation declarations.
- Append-only reported results, pagination and guarded comparisons.
- MCP argument type/enum checks, error flags, notification handling and safer logging.
- Offline tests, synthetic demonstration and cross-platform CI configuration.

## Next: execution with provenance

- Launch a fingerprinted snapshot with explicit approval, private visibility and bounded resources.
- Persist run state before launch; reconcile ambiguous timeouts without duplicate submissions.
- Attach dataset versions through supported Kaggle APIs and verify actual attachments.
- Nonblocking status refresh, cancellation where supported, logs and output manifests.
- Import metrics from a documented artifact schema; label imported versus independently verified evidence.
- Artifact hashes, dependency lockfiles and environment manifests.
- Acceptance: simulated failures at each launch/poll/download boundary plus an opt-in live test.

## Then: trustworthy evaluation

- Dataset profiling with row/byte limits and privacy-conscious previews.
- Train/validation overlap, duplicate and target-leakage diagnostics with documented limits.
- Seed sweeps, repeated measurements, confidence intervals and Pareto comparisons.
- Reproducible split manifests; group/time-aware evaluation templates.
- Submission CSV schema checks and explicit confirmation before competition submissions.
- Acceptance: small public fixtures with known leakage and invalid submissions.

## Integration and reliability

- Official remote MCP adapter with runtime capability discovery; no invented endpoints.
- Per-tool compatibility matrix for supported Kaggle CLI versions.
- Distinguish modern bearer tokens from legacy username/key authentication.
- Replace legacy HTTP/SSE with an SDK-backed, authenticated Streamable HTTP transport.
- Tool allowlists/read-only profiles, workspace boundaries and output limits.
- Retry only safe operations with bounded backoff; never blindly retry writes.
- Signed release artifacts, package installation smoke tests and migration policy.

## Community and evidence

- Publish a real end-to-end demonstration with reproducible inputs and measured results.
- Ask users to report actual workflow failures and prioritize those issues.
- Accessible English documentation, followed by community-reviewed Kurdish/Arabic guides.
- Maintain a dated evidence page containing verified usage/contribution metrics, with sources.
- Use actual evidence in grant/program applications. Do not claim planned features as shipped,
  fabricated downloads, independent verification, partnership, or guaranteed acceptance.

These are planned milestones, not current capabilities or delivery promises.
