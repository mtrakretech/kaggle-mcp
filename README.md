# 🏆 Kaggle MCP Server

**Full Kaggle API via the Model Context Protocol (MCP).**

Use any MCP-compatible AI client (Claude Code, Codex CLI, Cursor, Windsurf, OpenCode, etc.) to:

- 🤖 **Run notebooks** on Kaggle's free GPU/TPU (30+ hrs/week of NVIDIA T4/P100)
- 📊 **Search & download** any public/private dataset
- 🏅 **Compete** — submit to competitions, view leaderboards
- 🧠 **Browse models** — find and inspect ML models
- 📋 **Monitor** kernel status, logs, outputs, files
- 🔄 **Manage** — push, pull, delete, update, toggle private/public

## Quick Start

```bash
# 1. Install
git clone https://github.com/YOUR_USERNAME/kaggle-mcp
cd kaggle-mcp
pip install requests

# 2. Set your Kaggle credentials
export KAGGLE_USERNAME=your_username
export KAGGLE_KEY=your_api_key  # From https://www.kaggle.com/settings/api

# 3. Run the server
python kaggle_mcp.py --stdio        # For Claude Code / Codex CLI
python kaggle_mcp.py --port 8234    # For HTTP/SSE clients
```

## Usage with AI Clients

### Claude Code
```json
// Add to ~/.claude/settings.json or claude_desktop_config.json
{
  "mcpServers": {
    "kaggle": {
      "command": "python",
      "args": ["/path/to/kaggle_mcp.py", "--stdio"],
      "env": {
        "KAGGLE_USERNAME": "your_username",
        "KAGGLE_KEY": "your_api_key"
      }
    }
  }
}
```

### Codex CLI
```bash
# Codex will pick up the MCP server automatically
export KAGGLE_USERNAME=your_username
export KAGGLE_KEY=your_api_key
python kaggle_mcp.py --stdio
```

### Cursor
```json
// Settings → Features → MCP Servers → Add New
{
  "name": "kaggle",
  "type": "command",
  "command": "python /path/to/kaggle_mcp.py --stdio",
  "env": {
    "KAGGLE_USERNAME": "your_username",
    "KAGGLE_KEY": "your_api_key"
  }
}
```

### Windsurf / OpenCode
```json
// ~/.windsurf/mcp_config.json or similar
{
  "mcpServers": {
    "kaggle": {
      "command": "python",
      "args": ["/path/to/kaggle_mcp.py", "--stdio"]
    }
  }
}
```

## 🛠 Available Tools (25)

### Kernels / Notebooks
| Tool | Description | Key Params |
|------|-------------|------------|
| `search_kernels` | Search public notebooks | `query`, `limit`, `sort_by` |
| `list_my_kernels` | List your notebooks | `limit`, `page` |
| `kernel_status` | Check execution status | `ref` (username/kernel-name) |
| `kernel_output` | Download output files | `ref` |
| `kernel_logs` | Get execution logs | `ref` |
| `kernel_list_files` | List output files | `ref` |
| `pull_notebook` | Download notebook .ipynb | `ref` |
| `push_notebook` | Upload & run on free GPU | `path`, `gpu`, `tpu`, `dataset_sources` |
| `update_kernel` | Change metadata (visibility, GPU) | `ref`, `is_private`, `enable_gpu` |
| `delete_kernel` | Permanently delete | `ref` |
| `preview_notebook` | Preview notebook cells | `ref`, `max_cells` |
| `toggle_kernel_visibility` | Quick private/public toggle | `ref`, `make_public` |

### Datasets
| Tool | Description | Key Params |
|------|-------------|------------|
| `search_datasets` | Search datasets | `query`, `sort_by`, `file_type` |
| `dataset_details` | Get metadata, files, size | `ref` |
| `download_dataset` | Download files | `ref`, `unzip` |
| `upload_dataset` | Create new dataset | `dir_path`, `private`, `description` |
| `update_dataset` | New version | `ref`, `dir_path`, `version_notes` |
| `delete_dataset` | Delete permanently | `ref` |

### Competitions
| Tool | Description | Key Params |
|------|-------------|------------|
| `list_competitions` | List active competitions | `category`, `search`, `limit` |
| `competition_leaderboard` | View leaderboard | `comp`, `limit` |
| `download_competition_data` | Download competition files | `comp` |
| `submit_competition` | Submit predictions | `comp`, `file`, `message` |

### Models
| Tool | Description | Key Params |
|------|-------------|------------|
| `list_models` | Browse ML models | `search`, `owner`, `limit` |
| `model_details` | Get model info | `model_ref` |

### Account
| Tool | Description | Key Params |
|------|-------------|------------|
| `get_account_info` | Your account info | _(none)_ |

## 🔧 Architecture

```
┌─────────────┐     MCP Protocol      ┌──────────────────┐
│  AI Client   │ ◄──── stdio/SSE ────► │  kaggle_mcp.py   │
│  (Claude,    │                       │                  │
│   Codex,     │                       │  ┌────────────┐  │
│   Cursor)    │                       │  │ Kaggle CLI │  │
└─────────────┘                       │  │ (kaggle)   │  │
                                       │  └────────────┘  │
                                       │  ┌────────────┐  │
                                       │  │ REST API   │  │
                                       │  │(requests)  │  │
                                       │  └────────────┘  │
                                       └──────────────────┘
                                              │
                                       ┌──────▼──────┐
                                       │   Kaggle    │
                                       │   Servers   │
                                       └─────────────┘
```

## 🔐 Security

- **No hardcoded credentials** — uses `KAGGLE_USERNAME` and `KAGGLE_KEY` env vars
- Falls back to `~/.kaggle/kaggle.json` if env vars are not set
- Your API key never leaves your machine

## 📄 License

MIT — free for all use, commercial included.
