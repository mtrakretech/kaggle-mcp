# Kaggle MCP Server

**Full Kaggle API as a Model Context Protocol (MCP) server — 25 tools.**

Works with:

- Claude Desktop
- Claude Code
- OpenAI Codex CLI
- Cursor
- Hermes Agent
- Windsurf
- OpenCode
- VS Code Copilot / MCP
- Continue.dev
- Any MCP client that supports **stdio** (preferred) or HTTP SSE

Use it to run notebooks on free Kaggle GPU/TPU, search/download datasets, manage competitions, and browse models — from your AI coding agent.

---

## Features

| Area | What you can do |
|------|-----------------|
| **Kernels / notebooks** | Search, list yours, pull/push, run on free GPU/TPU, status, logs, outputs, private/public toggle, delete |
| **Datasets** | Search, details, download, upload, version, delete |
| **Competitions** | List, leaderboard, download data, submit predictions |
| **Models** | Browse + details |
| **Account** | Username + quick kernel summary |

**Transports**

- `--stdio` — standard for Claude Desktop / Claude Code / Codex / Cursor / Hermes / most agents
- `--port N` — lightweight HTTP SSE + `/rpc` for custom/web clients

**Security**

- No hardcoded credentials
- Uses `KAGGLE_USERNAME` + `KAGGLE_KEY` env vars
- Falls back to `~/.kaggle/kaggle.json`
- API key never leaves your machine except to Kaggle

---

## Requirements

- Python **3.10+**
- Kaggle account + API token: [kaggle.com/settings](https://www.kaggle.com/settings) → **API** → **Create New Token**
- Packages: `requests`, `kaggle` (installed via `pip install -r requirements.txt`)

---

## Install

```bash
git clone https://github.com/mtrakretech/kaggle-mcp.git
cd kaggle-mcp
pip install -r requirements.txt
# optional editable install (adds `kaggle-mcp` console script):
# pip install -e .
```

### Credentials

**Option A — env vars (recommended for MCP configs)**

```bash
export KAGGLE_USERNAME=your_username
export KAGGLE_KEY=your_api_key          # from kaggle.json "key"
export KAGGLE_API_TOKEN=$KAGGLE_KEY     # required by kaggle CLI v2.2.3+
```

Windows (PowerShell):

```powershell
$env:KAGGLE_USERNAME="your_username"
$env:KAGGLE_KEY="your_api_key"
$env:KAGGLE_API_TOKEN=$env:KAGGLE_KEY
```

**Option B — `~/.kaggle/kaggle.json`**

```json
{"username":"your_username","key":"your_api_key"}
```

chmod on Linux/macOS:

```bash
mkdir -p ~/.kaggle
cp /path/to/kaggle.json ~/.kaggle/kaggle.json
chmod 600 ~/.kaggle/kaggle.json
```

**Option C — project `.env`**

```bash
cp .env.example .env
# edit .env, then use ./kaggle-mcp.sh or kaggle-mcp.cmd
```

---

## Quick test

```bash
# list tools (needs credentials)
python kaggle_mcp.py --list-tools

# stdio mode (what agents use)
python kaggle_mcp.py --stdio

# HTTP mode
python kaggle_mcp.py --port 8234
curl http://127.0.0.1:8234/health
```

Unix launcher:

```bash
./kaggle-mcp.sh --list-tools
```

Windows launcher:

```bat
kaggle-mcp.cmd --list-tools
```

---

## Client setup (copy-paste)

Replace `/ABSOLUTE/PATH/TO/kaggle-mcp/kaggle_mcp.py` with the real path  
(Windows example: `C:\\Users\\YOU\\kaggle-mcp\\kaggle_mcp.py`).

Ready-made files live in [`examples/`](examples/).

### 1) Claude Desktop

Config file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\\Claude\\claude_desktop_config.json`

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

Restart Claude Desktop. Confirm tools under the hammer / MCP icon.

### 2) Claude Code

Add the same `mcpServers` block to Claude Code settings (`~/.claude/settings.json` or project `.claude/settings.json`), or use Claude Code’s MCP add flow with command:

```bash
python /ABSOLUTE/PATH/TO/kaggle-mcp/kaggle_mcp.py --stdio
```

Set env vars as above.

### 3) OpenAI Codex CLI

`~/.codex/config.toml`:

```toml
[mcp_servers.kaggle]
command = "python"
args = ["/ABSOLUTE/PATH/TO/kaggle-mcp/kaggle_mcp.py", "--stdio"]

[mcp_servers.kaggle.env]
KAGGLE_USERNAME = "your_kaggle_username"
KAGGLE_KEY = "your_kaggle_api_key"
KAGGLE_API_TOKEN = "your_kaggle_api_key"
```

### 4) Cursor

**Settings → MCP → Add new MCP server** (or edit MCP JSON):

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

### 5) Hermes Agent

In Hermes `config.yaml` under `mcp_servers:`:

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
    connect_timeout: 60
```

Then:

```bash
hermes mcp test kaggle
# or reload MCP in the running agent
```

> Prefer **stdio**. Hermes streamable-HTTP expects a different wire shape than this server’s simple SSE helper.

### 6) Windsurf

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

### 7) OpenCode

```json
{
  "mcp": {
    "kaggle": {
      "type": "local",
      "command": ["python", "/ABSOLUTE/PATH/TO/kaggle-mcp/kaggle_mcp.py", "--stdio"],
      "enabled": true,
      "environment": {
        "KAGGLE_USERNAME": "your_kaggle_username",
        "KAGGLE_KEY": "your_kaggle_api_key",
        "KAGGLE_API_TOKEN": "your_kaggle_api_key"
      }
    }
  }
}
```

### 8) VS Code (MCP)

```json
{
  "servers": {
    "kaggle": {
      "type": "stdio",
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

### 9) Continue.dev

```yaml
mcpServers:
  - name: kaggle
    command: python
    args:
      - /ABSOLUTE/PATH/TO/kaggle-mcp/kaggle_mcp.py
      - --stdio
    env:
      KAGGLE_USERNAME: your_kaggle_username
      KAGGLE_KEY: your_kaggle_api_key
      KAGGLE_API_TOKEN: your_kaggle_api_key
```

### 10) Generic stdio client

Any MCP host:

```text
command: python
args:    [<repo>/kaggle_mcp.py, --stdio]
env:     KAGGLE_USERNAME, KAGGLE_KEY, KAGGLE_API_TOKEN
```

---

## Tools (25)

### Kernels / notebooks (12)

| Tool | Description |
|------|-------------|
| `search_kernels` | Search public notebooks |
| `list_my_kernels` | List your notebooks |
| `kernel_status` | running / complete / error |
| `kernel_output` | Download outputs |
| `kernel_logs` | Execution logs |
| `kernel_list_files` | List output files |
| `pull_notebook` | Download `.ipynb` |
| `push_notebook` | Upload + run (optional free GPU/TPU) |
| `update_kernel` | Visibility / GPU flags |
| `delete_kernel` | Permanent delete |
| `preview_notebook` | First N cells |
| `toggle_kernel_visibility` | Private ↔ public |

### Datasets (6)

| Tool | Description |
|------|-------------|
| `search_datasets` | Search |
| `dataset_details` | Metadata + files |
| `download_dataset` | Download (+ unzip) |
| `upload_dataset` | Create |
| `update_dataset` | New version |
| `delete_dataset` | Permanent delete |

### Competitions (4)

| Tool | Description |
|------|-------------|
| `list_competitions` | Active comps |
| `competition_leaderboard` | Leaderboard |
| `download_competition_data` | Comp files |
| `submit_competition` | Submit predictions |

### Models (2)

| Tool | Description |
|------|-------------|
| `list_models` | Browse |
| `model_details` | One model |

### Account (1)

| Tool | Description |
|------|-------------|
| `get_account_info` | Account + kernel snapshot |

---

## Architecture

```
┌──────────────────┐     MCP (stdio / SSE)     ┌─────────────────┐
│  AI client       │ ◄──────────────────────► │  kaggle_mcp.py  │
│  Claude / Codex  │                          │  25 tools       │
│  Cursor / Hermes │                          │  ┌───────────┐  │
└──────────────────┘                          │  │ kaggle CLI│  │
                                              │  └───────────┘  │
                                              │  ┌───────────┐  │
                                              │  │ REST API  │  │
                                              │  └───────────┘  │
                                              └────────┬────────┘
                                                       │
                                              ┌────────▼────────┐
                                              │ Kaggle servers  │
                                              └─────────────────┘
```

---

## Common agent prompts

- “List my Kaggle notebooks and their last run status.”
- “Search datasets for Titanic CSV and download the top hit.”
- “Push `train.ipynb` to Kaggle with GPU enabled and poll until complete.”
- “Show featured competitions ending soon.”
- “Submit `submission.csv` to competition X with message ‘baseline v1’.”

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ERROR: Set KAGGLE_USERNAME and KAGGLE_KEY` | Export env vars or place `~/.kaggle/kaggle.json` |
| Auth fails on kernels/competitions | Set **both** `KAGGLE_KEY` and `KAGGLE_API_TOKEN` to the same value |
| `kaggle CLI not found` | `pip install kaggle` and ensure it is on `PATH` |
| Client shows 0 tools | Use **stdio** (`--stdio`), restart client, check absolute path + Python |
| Hermes HTTP connect fails | Switch config to stdio (recommended); simple SSE is not streamable-HTTP |
| Windows `python` not found | Use full path to `python.exe` in the MCP `command` field |
| Permission denied on `kaggle.json` | `chmod 600 ~/.kaggle/kaggle.json` |

---

## Development

```bash
python -m py_compile kaggle_mcp.py
python kaggle_mcp.py --list-tools
```

Project layout: see [CONTENTS.md](CONTENTS.md).  
Version history: [CHANGELOG.md](CHANGELOG.md).

---

## License

MIT — free for personal and commercial use. See [LICENSE](LICENSE).

---

## Links

- Repo: https://github.com/mtrakretech/kaggle-mcp
- Kaggle API token: https://www.kaggle.com/settings
- MCP spec: https://modelcontextprotocol.io/
