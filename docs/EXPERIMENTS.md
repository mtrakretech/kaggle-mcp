# Reproducible experiment ledger

Kaggle provides an official remote MCP server at <https://www.kaggle.com/mcp>.
This independent community project adds a local workflow layer for tracking what
an agent intended to run and what a user reports happened. It is not affiliated
with or endorsed by Kaggle or Anthropic.

## Six working tools

| Tool | Purpose |
| --- | --- |
| `plan_experiment` | Inspect a local version 4 notebook and save its experiment plan |
| `verify_experiment` | Detect changes in notebook bytes or code since planning |
| `get_experiment` | Retrieve a plan and its full observation history |
| `record_experiment_result` | Append finite numeric metrics, notes, and an optional kernel reference |
| `list_experiments` | Browse plans with pagination |
| `compare_experiments` | Rank latest observations by a named metric, minimizing or maximizing |

Start with `python kaggle_mcp.py --stdio`. Local tools need no credentials.
Kaggle operations still require your normal Kaggle credentials.

Example `tools/call` arguments for `plan_experiment`:

```json
{
  "path": "/absolute/path/train.ipynb",
  "name": "gradient-boosting-baseline",
  "datasets_json": "[\"owner/dataset/3\"]",
  "parameters_json": "{\"learning_rate\":0.05}",
  "seed": 42,
  "accelerator": "cpu",
  "internet": false,
  "evaluation_protocol": "Holdout manifest sha256:YOUR_HASH; RMSE; seed 42"
}
```

1. Plan the experiment and review warnings.
2. Execute using your chosen Kaggle client after reviewing code and permissions.
   The planning tool does not upload or execute anything.
3. Verify the notebook against the plan before and after execution.
4. Record metrics with `record_experiment_result`, using the returned experiment ID.
5. Plan another run with the same dataset references and evaluation protocol.
6. Compare using `experiment_ids_json`, a JSON array of IDs, `metric`, and `mode`.

A comparison uses the **latest observation**, not the best cherry-picked observation.
It rejects differing dataset references and differing or empty evaluation protocols.
Missing metrics are reported separately. Ties retain the supplied experiment order.

Run the offline demonstration:

```bash
python examples/experiment_demo.py
python -m unittest discover -s tests -v
```

The demo uses explicitly synthetic scores and a temporary database. It demonstrates
bookkeeping, not model quality or real Kaggle execution.

## Storage and privacy

Plans and observations live in `~/.kaggle-mcp/experiments.sqlite3`. Override with
`KAGGLE_MCP_EXPERIMENT_DB`. Back up this file while the server is stopped.
The file is created with owner-only permissions where the platform supports them;
Windows access control follows the containing directory's ACLs.
No credentials or notebook source are stored by these tools. Notebook hashes,
parameters, dataset references, notes, and metrics are stored. Do not put secrets
in parameters or notes. The ledger has no upload, sync, telemetry, or delete tool.
Returned records are visible to the connected MCP client and its model provider.

## What the ledger can and cannot establish

- Full-byte SHA-256 detects any notebook change, including saved outputs.
- Code SHA-256 ignores output and markdown changes while preserving code-cell order.
- Plans preserve declared seed, accelerator, internet setting, parameters and dataset versions.
- These settings are **not injected** into code, and dataset versions are **not automatically enforced** during execution.
- User-reported metrics are labeled accordingly. A kernel reference is an annotation,
  not proof that Kaggle produced the metrics or executed the fingerprinted source.
- Identical declarations cannot establish clean execution, absence of data leakage,
  deterministic hardware, dependency reproducibility, or statistical significance.
- The ledger is append-only through its API, but its SQLite file is not tamper-proof.

Use stdio for MCP clients. The existing HTTP/SSE implementation is legacy, has not
been validated as a standards-compliant remote MCP transport, and should not be
exposed to a network or used as a hosted service.
