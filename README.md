# Kaggle MCP Server

**Independent Kaggle CLI MCP server with 74 tools (v3.1), including a local experiment ledger.**

Track notebook fingerprints, declared dataset versions, parameters, and reported metrics across experiments. Compare runs sharing the same declared evaluation protocol.

Kaggle also offers an [official remote MCP server](https://www.kaggle.com/docs/mcp).
This community project is independent and is not endorsed by Kaggle or Anthropic.
Its distinct addition is a local experiment provenance workflow.

See [experiment tools and tutorial](docs/EXPERIMENTS.md) and the [development roadmap](docs/ROADMAP.md).

```bash
python examples/experiment_demo.py  # offline demo; synthetic metrics, no account needed
python -m unittest discover -s tests -v
```

Works with Claude Desktop, Claude Code, OpenAI Codex CLI, Cursor, Hermes Agent, Windsurf, OpenCode, VS Code MCP, Continue.dev, and any stdio MCP client.

## What you can do

| Area | Tools |
|------|-------|
| **Kernels** | search, list mine, status, logs, files, output download, pull/push, init, update, delete, preview, visibility, topics |
| **Datasets** | search, list mine, details, files, download, init, upload, version, metadata, status, delete, topics |
| **Competitions** | list, files, download, submit, submissions, leaderboard, team-submissions, episodes, replay, logs, pages, topics |
| **Models** | list/get/create/update/delete, instances, versions, version files/download, topics |
| **Forums** | list forums, list/show topics |
| **Benchmarks** | list tasks, list models, task status |
| **Account** | quota (GPU/TPU), account info, CLI config |

**Transports**
- `--stdio` preferred for agents
- `--port N` legacy local HTTP SSE + `/rpc`; not validated as standard remote MCP. Do not expose it as a hosted service.

## Install

```bash
git clone https://github.com/mtrakretech/kaggle-mcp.git
cd kaggle-mcp
pip install -r requirements.txt
```

### Credentials (recommended: terminal setup)

```bash
python kaggle_mcp.py --setup
```

What it does:
1. Tells you where to get a token: https://www.kaggle.com/settings → **API** → **Create New Token**
2. Asks for **username** + **API key** (key input hidden)
3. Optionally reuses a downloaded `kaggle.json` (cwd / Downloads / `~/.kaggle`)
4. Saves:
   - `~/.kaggle/kaggle.json` (chmod 600 when possible)
   - project `.env` (`KAGGLE_USERNAME`, `KAGGLE_KEY`, `KAGGLE_API_TOKEN`)
5. Validates with `kaggle quota`

Non-interactive:

```bash
python kaggle_mcp.py --setup --username YOUR_USER --key YOUR_KEY
python kaggle_mcp.py --setup --from-json ~/Downloads/kaggle.json
python kaggle_mcp.py --setup --no-env          # only ~/.kaggle/kaggle.json
python kaggle_mcp.py --setup --no-validate    # skip API check
```

Manual alternatives:

```bash
export KAGGLE_USERNAME=your_username
export KAGGLE_KEY=your_api_key
export KAGGLE_API_TOKEN=$KAGGLE_KEY
```

Or hand-write `~/.kaggle/kaggle.json`:

```json
{"username":"your_username","key":"your_api_key"}
```

## Quick test

```bash
python kaggle_mcp.py --setup          # first time
python kaggle_mcp.py --list-tools
python kaggle_mcp.py --stdio
```

## Client setup

Replace `/ABSOLUTE/PATH/TO/kaggle-mcp/kaggle_mcp.py` with your real path.  
Copy-paste examples: [`examples/`](examples/).

### Claude Desktop
`%APPDATA%\Claude\claude_desktop_config.json` (Windows) / `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "kaggle": {
      "command": "python",
      "args": ["/ABSOLUTE/PATH/TO/kaggle-mcp/kaggle_mcp.py", "--stdio"],
      "env": {
        "KAGGLE_USERNAME": "your_kaggle_username",
        "KAGGLE_KEY": "your_kaggle_api_key",
        "KAGGLE_API_TOKEN": "your_kaggle_api_key"
      }
    }
  }
}
```

### Claude Code / Cursor / Windsurf
Same `mcpServers.kaggle` JSON shape as above.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.kaggle]
command = "python"
args = ["/ABSOLUTE/PATH/TO/kaggle-mcp/kaggle_mcp.py", "--stdio"]

[mcp_servers.kaggle.env]
KAGGLE_USERNAME = "your_kaggle_username"
KAGGLE_KEY = "your_kaggle_api_key"
KAGGLE_API_TOKEN = "your_kaggle_api_key"
```

### Hermes Agent (`config.yaml`)

```yaml
mcp_servers:
  kaggle:
    command: python
    args:
      - /ABSOLUTE/PATH/TO/kaggle-mcp/kaggle_mcp.py
      - --stdio
    env:
      KAGGLE_USERNAME: your_kaggle_username
      KAGGLE_KEY: your_kaggle_api_key
      KAGGLE_API_TOKEN: your_kaggle_api_key
    timeout: 180
```

Use **stdio** (not HTTP SSE) with Hermes.

### OpenCode / VS Code / Continue
See `examples/opencode_config.json`, `examples/vscode_mcp.json`, `examples/continue_config.yaml`.

## Tools (74)

### Experiments (6)
`plan_experiment` `verify_experiment` `get_experiment` `record_experiment_result` `list_experiments` `compare_experiments`

These local tools work without Kaggle credentials when started with `--stdio`. See [limitations and storage](docs/EXPERIMENTS.md).

### Kernels (15)
`search_kernels` `list_my_kernels` `kernel_status` `kernel_logs` `kernel_files` `kernel_output` `pull_notebook` `push_notebook` `init_kernel` `update_kernel` `delete_kernel` `preview_notebook` `toggle_kernel_visibility` `list_kernel_topics` `show_kernel_topic`

### Datasets (13)
`search_datasets` `list_my_datasets` `dataset_details` `list_dataset_files` `download_dataset` `init_dataset` `upload_dataset` `update_dataset` `get_dataset_metadata` `dataset_status` `delete_dataset` `list_dataset_topics` `show_dataset_topic`

### Competitions (13)
`list_competitions` `list_competition_files` `download_competition_data` `submit_competition` `list_competition_submissions` `competition_leaderboard` `list_team_submissions` `list_competition_episodes` `download_competition_replay` `download_competition_episode_logs` `list_competition_pages` `list_competition_topics` `show_competition_topic`

### Models (18)
`list_models` `model_details` `init_model` `create_model` `update_model` `delete_model` `list_model_instances` `get_model_instance` `init_model_instance` `create_model_instance` `update_model_instance` `delete_model_instance` `list_model_instance_versions` `list_model_version_files` `download_model_version` `create_model_version` `delete_model_version` `list_model_topics`

### Forums / Benchmarks / Account (9)
`list_forums` `list_forum_topics` `show_forum_topic` `list_benchmark_tasks` `list_benchmark_models` `benchmark_task_status` `get_quota` `get_account_info` `get_config`

## Historical live test notes (v3.0)

The following are prior maintainer reports, not live verification of v3.1. New v3.1 checks run offline; no Kaggle account actions were performed.

Verified working against real API on this machine:
- kernels search/list/status/logs/files/pull/preview/output
- datasets search/list/details/files/metadata/download/topics
- competitions list/files/leaderboard/pages/topics/team-submissions
- models list/get/instances/versions
- forums list/topics, benchmarks list/models, quota, config, init skeletons

Known Kaggle-side soft fails (tool wiring OK; API returns error):
- `dataset_status` → 404 on some public datasets
- `list_competition_submissions` → 400 if you never entered the competition
- `list_model_version_files` / some instance paths → 404 if version ref wrong
- topic `show_*` → 429 under rate limit (retry later)

Destructive tools (`delete_*`, `submit_competition`, `push_notebook`, uploads) are implemented but not auto-run in CI-style tests.

## Security
- No hardcoded credentials
- Env vars or `~/.kaggle/kaggle.json` only
- The experiment ledger stores no credentials. Connected clients can see tool results; review content before sharing.
- Use stdio. Legacy HTTP is not intended for network exposure.
- Notebook outputs, uploaded folders, parameters and notes can contain sensitive data; review them before use.

## License
MIT — see [LICENSE](LICENSE)

## Links
- Repo: https://github.com/mtrakretech/kaggle-mcp
- Kaggle token: https://www.kaggle.com/settings
- MCP: https://modelcontextprotocol.io/
