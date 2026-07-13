#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════╗
║  Kaggle MCP Server v2.1                                     ║
║  Full Kaggle API via Model Context Protocol                  ║
║                                                              ║
║  Compatible with: Claude Code, Codex CLI, Cursor,           ║
║                   Windsurf, OpenCode, and more               ║
║                                                              ║
║  Transport modes:                                            ║
║    --stdio      Stdio mode (default for Claude Code/Codex)   ║
║    --port N     HTTP SSE mode (for web clients)              ║
║    --help       This message                                 ║
╚═══════════════════════════════════════════════════════════════╝

Environment variables (recommended over CLI):
  KAGGLE_USERNAME       Your Kaggle username
  KAGGLE_KEY            Your Kaggle API key (from kaggle.json, or token from settings)
  KAGGLE_API_TOKEN      Optional; defaults to KAGGLE_KEY (kaggle CLI v2.2.3+)
"""

import json, os, sys, subprocess, tempfile, shutil, uuid, threading, time
import urllib.parse, io, zipfile, textwrap, re
from pathlib import Path
from typing import Any

# ============================================================================
# CONFIGURATION — always from env vars, NEVER hardcoded
# ============================================================================
KAGGLE_USER = os.environ.get("KAGGLE_USERNAME") or ""
KAGGLE_KEY  = os.environ.get("KAGGLE_KEY") or ""
API_BASE    = "https://www.kaggle.com/api/v1"

if not KAGGLE_USER or not KAGGLE_KEY:
    # Fallback: try reading ~/.kaggle/kaggle.json
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if kaggle_json.exists():
        try:
            creds = json.loads(kaggle_json.read_text())
            KAGGLE_USER = creds.get("username", KAGGLE_USER)
            KAGGLE_KEY  = creds.get("key", KAGGLE_KEY)
        except Exception:
            pass

if not KAGGLE_USER or not KAGGLE_KEY:
    print("ERROR: Set KAGGLE_USERNAME and KAGGLE_KEY env vars, or configure ~/.kaggle/kaggle.json", file=sys.stderr)
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {KAGGLE_KEY}", "Content-Type": "application/json"}

# ============================================================================
# TOOL REGISTRY
# ============================================================================
TOOLS: dict[str, dict] = {}
_log_buf: list[str] = []

def log(msg: str):
    """Write to stderr (visible in server logs, NOT on stdout which is MCP protocol)."""
    _log_buf.append(msg)
    print(f"[kaggle-mcp] {msg}", file=sys.stderr, flush=True)

def tool(name: str, desc: str, params: dict = None) -> callable:
    """Decorator: register an MCP tool function."""
    def dec(fn):
        TOOLS[name] = {"fn": fn, "desc": desc, "params": params or {}}
        return fn
    return dec

# ============================================================================
# HELPERS
# ============================================================================

def _kaggle(*args: str, timeout: int = 120) -> dict:
    """Run kaggle CLI command and return structured result."""
    env = os.environ.copy()
    env["KAGGLE_USERNAME"] = KAGGLE_USER
    env["KAGGLE_KEY"] = KAGGLE_KEY
    env["KAGGLE_API_TOKEN"] = os.environ.get("KAGGLE_API_TOKEN") or KAGGLE_KEY  # v2.2.3+
    # Disable progress bars for JSON-friendly output
    env["KAGGLE_NO_PROGRESS"] = "1"
    try:
        r = subprocess.run(
            ["kaggle", *args],
            capture_output=True, text=True, timeout=timeout, env=env
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            return {"error": err[:500]}
        return {"output": r.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except FileNotFoundError:
        return {"error": "kaggle CLI not found — install with: pip install kaggle"}
    except Exception as e:
        return {"error": str(e)[:500]}


def _api(method: str, path: str, data: dict = None, params: dict = None,
         timeout: int = 30) -> Any:
    """Call Kaggle REST API directly."""
    import requests
    try:
        r = requests.request(
            method,
            f"{API_BASE}/{path.lstrip('/')}",
            headers=HEADERS, json=data, params=params,
            timeout=timeout
        )
        if r.status_code in (200, 201):
            if r.headers.get("content-type", "").startswith("application/json"):
                return r.json()
            return {"raw": r.text[:2000]}
        return {"error": f"API {r.status_code}: {r.text[:300]}"}
    except Exception as e:
        return {"error": str(e)[:300]}


def _parse_ref(ref: str) -> tuple[str, str]:
    """Parse 'username/kernel-name' into (owner, slug)."""
    parts = ref.replace(" ", "").split("/")
    if len(parts) == 2:
        return parts[0], parts[1]
    return KAGGLE_USER, parts[0]


# ============================================================================
# TOOL IMPLEMENTATIONS
# ============================================================================

# ── Kernels / Notebooks ──────────────────────────────────────────

@tool("search_kernels",
      "Search public Kaggle notebooks/kernels by keyword",
      {"query": {"type": "string", "description": "Search term"},
       "sort_by": {"type": "string",
                    "enum": ["hotness", "commentCount", "dateCreated",
                             "dateModified", "score"],
                    "description": "Sort order (default: hotness)"},
       "limit": {"type": "number", "description": "Max results (1-100)", "default": 10}})
def search_kernels(query: str = "", sort_by: str = "hotness", limit: int = 10):
    if not query:
        return {"error": "query is required"}
    limit = max(1, min(100, int(limit)))
    return _kaggle("kernels", "list", "--search", query,
                   "--sort-by", sort_by, "--page-size", str(limit), "-v")


@tool("list_my_kernels",
      "List your own Kaggle notebooks",
      {"limit": {"type": "number", "description": "Max results", "default": 20},
       "page": {"type": "number", "description": "Page number (1-based)", "default": 1}})
def list_my_kernels(limit: int = 20, page: int = 1):
    limit = max(1, min(100, int(limit)))
    page = max(1, int(page))
    return _kaggle("kernels", "list", "--mine",
                   "--page-size", str(limit), "--page", str(page), "-v")


@tool("kernel_status",
      "Check notebook/kernel execution status (running, complete, error)",
      {"ref": {"type": "string",
               "description": "Kernel reference: 'username/kernel-name'"}})
def kernel_status(ref: str = ""):
    if not ref:
        return {"error": "ref is required (e.g. 'username/kernel-name')"}
    return _kaggle("kernels", "status", ref)


@tool("kernel_output",
      "Download kernel output files as ZIP. Returns file path or content listing.",
      {"ref": {"type": "string", "description": "Kernel reference"}})
def kernel_output(ref: str = ""):
    if not ref:
        return {"error": "ref is required"}
    # Save to temp dir
    out_dir = tempfile.mkdtemp(prefix="kg_output_")
    try:
        result = _kaggle("kernels", "output", ref, "-p", out_dir, timeout=60)
        if "error" in result:
            shutil.rmtree(out_dir, ignore_errors=True)
            return result
        # List downloaded files
        files = []
        for f in Path(out_dir).rglob("*"):
            if f.is_file():
                files.append(str(f.relative_to(out_dir)))
        if not files:
            shutil.rmtree(out_dir, ignore_errors=True)
            return {"message": "Kernel has no output files", "ref": ref}
        # Read first text file for preview if available
        preview = ""
        for f in sorted(files):
            fp = Path(out_dir) / f
            if fp.suffix in (".txt", ".csv", ".log", ".json", ".out", ".html"):
                preview = fp.read_text(errors="replace")[:2000]
                break
        return {
            "ref": ref,
            "download_path": out_dir,
            "files": files,
            "file_count": len(files),
            "preview": preview[:2000] if preview else "(binary files only)"
        }
    except Exception as e:
        shutil.rmtree(out_dir, ignore_errors=True)
        return {"error": str(e)[:300]}


@tool("kernel_logs",
      "Get kernel execution logs (stdout/stderr from run)",
      {"ref": {"type": "string", "description": "Kernel reference"}})
def kernel_logs(ref: str = ""):
    if not ref:
        return {"error": "ref is required"}
    return _kaggle("kernels", "logs", ref)


@tool("kernel_list_files",
      "List output files generated by a completed kernel run",
      {"ref": {"type": "string", "description": "Kernel reference"}})
def kernel_list_files(ref: str = ""):
    if not ref:
        return {"error": "ref is required"}
    out_dir = tempfile.mkdtemp(prefix="kg_ls_")
    try:
        result = _kaggle("kernels", "output", ref, "-p", out_dir, timeout=60)
        if "error" in result:
            shutil.rmtree(out_dir, ignore_errors=True)
            return result
        files = []
        total_size = 0
        for f in Path(out_dir).rglob("*"):
            if f.is_file():
                size = f.stat().st_size
                total_size += size
                files.append({
                    "path": str(f.relative_to(out_dir)),
                    "size_bytes": size,
                    "size_hr": _hr_size(size)
                })
        shutil.rmtree(out_dir, ignore_errors=True)
        return {"ref": ref, "files": files, "total_files": len(files),
                "total_size_bytes": total_size}
    except Exception as e:
        return {"error": str(e)[:300]}


def _hr_size(b: int) -> str:
    if b < 1024: return f"{b}B"
    if b < 1048576: return f"{b/1024:.1f}KB"
    return f"{b/1048576:.1f}MB"


@tool("pull_notebook",
      "Download notebook source (.ipynb file). Returns file path.",
      {"ref": {"type": "string", "description": "Kernel reference"},
       "output_dir": {"type": "string",
                       "description": "Output directory (default: current dir)"}})
def pull_notebook(ref: str = "", output_dir: str = "."):
    if not ref:
        return {"error": "ref is required"}
    out = os.path.abspath(output_dir)
    os.makedirs(out, exist_ok=True)
    result = _kaggle("kernels", "pull", ref, "-p", out, timeout=60)
    if "error" in result:
        return result
    # List downloaded files
    files = [str(f) for f in Path(out).iterdir()
             if f.is_file() and f.stat().st_ctime > time.time() - 30]
    return {"ref": ref, "output_directory": out,
            "files_downloaded": files}


@tool("push_notebook",
      "Upload a Jupyter notebook to Kaggle and run it on free GPU/TPU",
      {"path": {"type": "string",
                 "description": "Path to .ipynb file"},
       "name": {"type": "string",
                 "description": "Short name/slug for the kernel (default: filename)"},
       "gpu": {"type": "boolean", "description": "Enable free GPU (T4/P100)", "default": True},
       "tpu": {"type": "boolean", "description": "Enable TPU", "default": False},
       "internet": {"type": "boolean", "description": "Enable internet access", "default": True},
       "private": {"type": "boolean", "description": "Private until published", "default": True},
       "dataset_sources": {"type": "string",
                            "description": "Comma-separated dataset refs to attach, e.g. 'owner1/ds1,owner2/ds2'"},
       "auto_push": {"type": "boolean",
                      "description": "Auto-push after metadata creation (default: True)", "default": True}})
def push_notebook(path: str = "", name: str = "", gpu: bool = True,
                  tpu: bool = False, internet: bool = True, private: bool = True,
                  dataset_sources: str = "", auto_push: bool = True):
    if not path or not os.path.exists(path):
        return {"error": f"File not found: {path}"}
    if not path.endswith(".ipynb"):
        return {"error": "Only .ipynb files are supported"}

    tmpdir = tempfile.mkdtemp(prefix="kg_push_")
    try:
        shutil.copy2(path, os.path.join(tmpdir, "__notebook__.ipynb"))

        # Read original notebook for title fallback
        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)
        original_title = ""
        if "metadata" in nb and isinstance(nb["metadata"], dict):
            original_title = nb["metadata"].get("title", "") or nb["metadata"].get("kaggle", {}).get("title", "")

        title = name or original_title or os.path.splitext(os.path.basename(path))[0]
        slug = re.sub(r"[^a-zA-Z0-9-]", "-", title.lower()).strip("-")[:50]

        # Parse dataset sources
        ds_sources = []
        if dataset_sources:
            ds_sources = [s.strip() for s in dataset_sources.split(",") if s.strip()]

        meta = {
            "id": f"{KAGGLE_USER}/{slug}",
            "title": title,
            "code_file": "__notebook__.ipynb",
            "language": "python",
            "kernel_type": "notebook",
            "is_private": bool(private),
            "enable_gpu": bool(gpu),
            "enable_tpu": bool(tpu),
            "enable_internet": bool(internet),
        }
        if ds_sources:
            meta["dataset_sources"] = ds_sources

        with open(os.path.join(tmpdir, "kernel-metadata.json"), "w") as f:
            json.dump(meta, f, indent=2)

        log(f"Pushing kernel '{title}' (GPU={gpu}, TPU={tpu}, private={private})")
        if not auto_push:
            return {"message": "Metadata prepared (auto_push=False)",
                    "metadata_path": os.path.join(tmpdir, "kernel-metadata.json"),
                    "kernel_ref": f"{KAGGLE_USER}/{slug}"}

        result = _kaggle("kernels", "push", "--kernel-path", tmpdir, timeout=180)
        if "error" in result:
            return result
        return {
            "status": "pushed",
            "kernel_ref": f"{KAGGLE_USER}/{slug}",
            "title": title,
            "metadata": {
                "gpu": bool(gpu), "tpu": bool(tpu),
                "internet": bool(internet), "private": bool(private)
            },
            "check_status_with": f"kernel_status ref='{KAGGLE_USER}/{slug}'"
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@tool("update_kernel",
      "Update kernel metadata (visibility, GPU, etc.) without re-uploading code",
      {"ref": {"type": "string", "description": "Kernel reference"},
       "is_private": {"type": "boolean",
                       "description": "Set private (True) or public (False)"},
       "enable_gpu": {"type": "boolean", "description": "Enable/disable GPU"},
       "enable_tpu": {"type": "boolean", "description": "Enable/disable TPU"},
       "enable_internet": {"type": "boolean", "description": "Enable/disable internet"}})
def update_kernel(ref: str = "", is_private: bool = None,
                  enable_gpu: bool = None, enable_tpu: bool = None,
                  enable_internet: bool = None):
    if not ref:
        return {"error": "ref is required"}
    # Pull existing kernel metadata, modify, push back
    out_dir = tempfile.mkdtemp(prefix="kg_upd_")
    try:
        pull = _kaggle("kernels", "pull", ref, "-p", out_dir, timeout=60)
        if "error" in pull:
            return pull
        # Find downloaded files
        files = list(Path(out_dir).iterdir())
        meta_file = out_dir / "kernel-metadata.json"
        nb_file = None
        for f in files:
            if f.name == "kernel-metadata.json":
                meta_file = f
            elif f.suffix == ".ipynb":
                nb_file = f

        if meta_file.exists():
            with open(meta_file) as f:
                meta = json.load(f)
        else:
            # Create minimal metadata
            meta = {"id": ref, "title": ref.split("/")[-1] if "/" in ref else ref}

        if is_private is not None:
            meta["is_private"] = bool(is_private)
        if enable_gpu is not None:
            meta["enable_gpu"] = bool(enable_gpu)
        if enable_tpu is not None:
            meta["enable_tpu"] = bool(enable_tpu)
        if enable_internet is not None:
            meta["enable_internet"] = bool(enable_internet)

        meta["code_file"] = nb_file.name if nb_file else "__notebook__.ipynb"
        meta["kernel_type"] = "notebook"
        meta["language"] = "python"

        with open(meta_file, "w") as f:
            json.dump(meta, f, indent=2)

        result = _kaggle("kernels", "push", "--kernel-path", str(out_dir), timeout=120)
        if "error" in result:
            return result
        return {"status": "updated", "ref": ref,
                "new_metadata": {k: v for k, v in meta.items()
                                 if k in ("is_private", "enable_gpu", "enable_tpu", "enable_internet")}}
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


@tool("delete_kernel",
      "Delete a notebook/kernel permanently",
      {"ref": {"type": "string", "description": "Kernel reference"}})
def delete_kernel(ref: str = ""):
    if not ref:
        return {"error": "ref is required"}
    return _kaggle("kernels", "delete", ref)


# ── Datasets ────────────────────────────────────────────────────

@tool("search_datasets",
      "Search Kaggle datasets (public and accessible private)",
      {"query": {"type": "string", "description": "Search term"},
       "sort_by": {"type": "string",
                    "enum": ["hottest", "votes", "updated", "active"],
                    "description": "Sort order (default: hottest)"},
       "file_type": {"type": "string",
                      "enum": ["csv", "json", "sqlite", "bigquery", "parquet"],
                      "description": "Filter by file type"},
       "limit": {"type": "number", "description": "Max results (1-100)", "default": 10}})
def search_datasets(query: str = "", sort_by: str = "hottest",
                    file_type: str = "", limit: int = 10):
    if not query:
        return {"error": "query is required"}
    limit = max(1, min(100, int(limit)))
    args = ["datasets", "list", "--search", query,
            "--sort-by", sort_by, "-v"]
    if file_type:
        args.extend(["--file-type", file_type])
    # datasets list uses fixed page size of 20; get page 1 and truncate
    result = _kaggle(*args)
    if "output" in result:
        lines = result["output"].split("\n")
        header = lines[:1]  # CSV header
        data_lines = lines[1:1+limit] if len(lines) > 1 else []
        result["output"] = "\n".join(header + data_lines) if header else "\n".join(data_lines)
        result["total_matches"] = max(len(lines) - 1, 0)
        result["shown"] = min(limit, len(data_lines))
    return result


@tool("dataset_details",
      "Get detailed metadata about a dataset (size, files, description)",
      {"ref": {"type": "string",
               "description": "Dataset reference: 'owner/dataset-name'"}})
def dataset_details(ref: str = ""):
    if not ref:
        return {"error": "ref is required"}
    result = _api("GET", f"datasets/view/{ref}")
    if isinstance(result, dict) and "error" not in result:
        # Format nicely
        return {
            "ref": ref,
            "title": result.get("title", ""),
            "subtitle": result.get("subtitle", ""),
            "description": result.get("description", "")[:500],
            "size": result.get("size", ""),
            "total_bytes": result.get("totalBytes", 0),
            "dataset_files": [
                {"name": f.get("name", ""),
                 "size_bytes": f.get("size", 0),
                 "type": f.get("fileType", "")}
                for f in (result.get("datasetFiles", []) or [])
            ],
            "file_count": len(result.get("datasetFiles", []) or []),
            "is_private": result.get("isPrivate", False),
            "owner": result.get("ownerName", ""),
            "current_version": result.get("currentVersionNumber", ""),
            "downloads": result.get("downloadCount", 0),
            "views": result.get("viewCount", 0),
            "upvotes": result.get("totalVotes", 0),
        }
    return result


@tool("download_dataset",
      "Download dataset files. Returns directory path with files.",
      {"ref": {"type": "string", "description": "Dataset reference"},
       "unzip": {"type": "boolean",
                  "description": "Automatically unzip (default: False)", "default": False},
       "output_dir": {"type": "string",
                       "description": "Download to this directory (default: temp dir)"}})
def download_dataset(ref: str = "", unzip: bool = False, output_dir: str = ""):
    if not ref:
        return {"error": "ref is required"}
    out_dir = output_dir or tempfile.mkdtemp(prefix="kg_ds_")
    os.makedirs(out_dir, exist_ok=True)
    result = _kaggle("datasets", "download", ref, "-p", out_dir,
                     "--unzip" if unzip else "", timeout=120)
    if "error" in result:
        return result
    files = []
    total_size = 0
    for f in Path(out_dir).rglob("*"):
        if f.is_file():
            size = f.stat().st_size
            total_size += size
            files.append({
                "path": str(f.relative_to(out_dir)),
                "size_bytes": size,
                "size_hr": _hr_size(size)
            })
    return {
        "ref": ref,
        "download_path": out_dir,
        "files": files,
        "total_files": len(files),
        "total_size_bytes": total_size,
        "total_size_hr": _hr_size(total_size)
    }


@tool("upload_dataset",
      "Create a new dataset on Kaggle",
      {"dir_path": {"type": "string",
                     "description": "Directory containing dataset files"},
       "name": {"type": "string",
                 "description": "Dataset slug name (default: dir basename)"},
       "private": {"type": "boolean",
                    "description": "Private dataset (default: True)", "default": True},
       "description": {"type": "string",
                        "description": "Short description (optional)"},
       "subtitle": {"type": "string", "description": "One-line subtitle (optional)"}})
def upload_dataset(dir_path: str = "", name: str = "", private: bool = True,
                   description: str = "", subtitle: str = ""):
    if not dir_path or not os.path.isdir(dir_path):
        return {"error": f"Directory not found: {dir_path}"}
    n = name or os.path.basename(os.path.normpath(dir_path))

    # Write dataset-metadata.json
    meta = {
        "title": n,
        "id": f"{KAGGLE_USER}/{n}",
        "licenses": [{"name": "CC0-1.0"}]
    }
    if description:
        meta["description"] = description
    if subtitle:
        meta["subtitle"] = subtitle

    meta_path = os.path.join(dir_path, "dataset-metadata.json")
    have_meta = os.path.exists(meta_path)
    try:
        if not have_meta:
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
        args = ["datasets", "create", "-p", dir_path]
        if private:
            args.append("--private")
        result = _kaggle(*args, timeout=120)
        if "error" in result:
            return result
        return {
            "status": "created",
            "dataset_ref": f"{KAGGLE_USER}/{n}",
            "private": bool(private),
            "directory": dir_path
        }
    finally:
        if not have_meta and os.path.exists(meta_path):
            os.remove(meta_path)


@tool("update_dataset",
      "Create a new version of an existing dataset",
      {"ref": {"type": "string", "description": "Dataset reference"},
       "dir_path": {"type": "string",
                     "description": "Directory with updated files"},
       "version_notes": {"type": "string",
                          "description": "What changed in this version (default: 'Updated')",
                          "default": "Updated"}})
def update_dataset(ref: str = "", dir_path: str = "", version_notes: str = "Updated"):
    if not ref:
        return {"error": "ref is required"}
    if not dir_path or not os.path.isdir(dir_path):
        return {"error": f"Directory not found: {dir_path}"}
    return _kaggle("datasets", "version", "-p", dir_path, "-m", version_notes, timeout=120)


@tool("delete_dataset",
      "Delete a dataset permanently",
      {"ref": {"type": "string", "description": "Dataset reference"}})
def delete_dataset(ref: str = ""):
    if not ref:
        return {"error": "ref is required"}
    return _kaggle("datasets", "delete", ref)


# ── Competitions ───────────────────────────────────────────────

@tool("list_competitions",
      "List active Kaggle competitions",
      {"category": {"type": "string",
                     "enum": ["", "featured", "research", "recruitment",
                              "gettingStarted", "masters", "playground"],
                     "description": "Filter by category"},
       "sort_by": {"type": "string",
                    "enum": ["latestDeadline", "earliestDeadline",
                             "mostEntries", "recentlyCreated"],
                    "description": "Sort order"},
       "search": {"type": "string", "description": "Search in title"},
       "limit": {"type": "number", "description": "Max results (1-100)", "default": 10}})
def list_competitions(category: str = "", sort_by: str = "latestDeadline",
                      search: str = "", limit: int = 10):
    limit = max(1, min(100, int(limit)))
    args = ["competitions", "list", "--page-size", str(limit),
            "--sort-by", sort_by, "-v"]
    if category:
        args.extend(["--category", category])
    if search:
        args.extend(["--search", search])
    return _kaggle(*args)


@tool("competition_leaderboard",
      "View competition leaderboard",
      {"comp": {"type": "string", "description": "Competition name/slug"},
       "limit": {"type": "number", "description": "Max entries (default: 10)"}})
def competition_leaderboard(comp: str = "", limit: int = 10):
    if not comp:
        return {"error": "comp (competition slug) is required"}
    limit = max(1, min(100, int(limit)))
    return _kaggle("competitions", "leaderboard", comp,
                   "--page-size", str(limit))


@tool("download_competition_data",
      "Download competition dataset files",
      {"comp": {"type": "string", "description": "Competition slug"},
       "file_name": {"type": "string",
                      "description": "Specific file to download (optional)"},
       "output_dir": {"type": "string",
                       "description": "Output directory (default: temp dir)"}})
def download_competition_data(comp: str = "", file_name: str = "",
                              output_dir: str = ""):
    if not comp:
        return {"error": "comp is required"}
    out_dir = output_dir or tempfile.mkdtemp(prefix="kg_comp_")
    os.makedirs(out_dir, exist_ok=True)
    args = ["competitions", "download", comp, "-p", out_dir]
    if file_name:
        args.extend(["-f", file_name])
    result = _kaggle(*args, timeout=180)
    if "error" in result:
        return result
    files = list(Path(out_dir).iterdir())
    return {
        "competition": comp,
        "download_path": out_dir,
        "files": [str(f.name) for f in files if f.is_file()],
        "file_count": len([f for f in files if f.is_file()])
    }


@tool("submit_competition",
      "Submit predictions to a competition",
      {"comp": {"type": "string", "description": "Competition slug"},
       "file": {"type": "string", "description": "Path to submission CSV file"},
       "message": {"type": "string",
                    "description": "Submission description (optional)"}})
def submit_competition(comp: str = "", file: str = "", message: str = ""):
    if not comp:
        return {"error": "comp is required"}
    if not file or not os.path.exists(file):
        return {"error": f"Submission file not found: {file}"}
    msg = message or f"Submission from Kaggle MCP"
    return _kaggle("competitions", "submit", comp, "-f", file, "-m", msg, timeout=120)


# ── Models ──────────────────────────────────────────────────────

@tool("list_models",
      "List Kaggle models",
      {"search": {"type": "string", "description": "Search term (optional)"},
       "owner": {"type": "string",
                  "description": "Filter by owner username (optional)"},
       "sort_by": {"type": "string",
                    "enum": ["hotness", "downloadCount", "voteCount",
                             "recentlyUpdated", "recentlyCreated"],
                    "description": "Sort order"},
       "limit": {"type": "number", "description": "Max results (1-100)", "default": 10}})
def list_models(search: str = "", owner: str = "", sort_by: str = "hotness",
                limit: int = 10):
    limit = max(1, min(100, int(limit)))
    args = ["models", "list", "--page-size", str(limit),
            "--sort-by", sort_by]
    if search:
        args.extend(["--search", search])
    if owner:
        args.extend(["--owner", owner])
    return _kaggle(*args)


@tool("model_details",
      "Get details about a specific model",
      {"model_ref": {"type": "string",
                      "description": "Model reference: 'owner/model-slug'"}})
def model_details(model_ref: str = ""):
    if not model_ref:
        return {"error": "model_ref is required"}
    return _kaggle("models", "get", model_ref)


# ── Account / Status ───────────────────────────────────────────

@tool("get_account_info",
      "Get your Kaggle account info and usage stats",
      {})
def get_account_info():
    """Get user info via the API."""
    result = _api("GET", f"kernels/list?user={KAGGLE_USER}&page-size=1")
    if isinstance(result, dict) and "error" in result:
        # Fallback: check via CLI
        mine = _kaggle("kernels", "list", "--mine", "--page-size", "1")
        return {
            "username": KAGGLE_USER,
            "kernels_list": mine,
            "note": "Full account details require Kaggle website login"
        }
    return {
        "username": KAGGLE_USER,
        "api_status": "connected",
        "note": "GPU quota info is available on Kaggle Settings page"
    }


@tool("preview_notebook",
      "Preview the first N cells of a notebook from Kaggle",
      {"ref": {"type": "string", "description": "Kernel reference"},
       "max_cells": {"type": "number",
                      "description": "Number of cells to preview (default: 5)", "default": 5}})
def preview_notebook(ref: str = "", max_cells: int = 5):
    if not ref:
        return {"error": "ref is required"}
    max_cells = max(1, min(50, int(max_cells)))
    out_dir = tempfile.mkdtemp(prefix="kg_preview_")
    try:
        result = _kaggle("kernels", "pull", ref, "-p", out_dir, timeout=60)
        if "error" in result:
            return result
        # Find .ipynb
        nb_files = list(Path(out_dir).glob("*.ipynb"))
        if not nb_files:
            return {"error": "No notebook file found"}
        nb_path = nb_files[0]
        with open(nb_path, "r", encoding="utf-8") as f:
            nb = json.load(f)
        cells = nb.get("cells", [])
        preview = []
        for i, cell in enumerate(cells[:max_cells]):
            src = "".join(cell.get("source", []))
            preview.append({
                "cell_index": i,
                "cell_type": cell.get("cell_type", "unknown"),
                "source_preview": src[:500] if src else "(empty)",
                "source_length": len(src)
            })
        return {
            "ref": ref,
            "total_cells": len(cells),
            "previewed": len(preview),
            "cells": preview,
            "kaggle_metadata": nb.get("metadata", {}).get("kaggle", {})
        }
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


@tool("toggle_kernel_visibility",
      "Quick toggle a kernel between private and public",
      {"ref": {"type": "string", "description": "Kernel reference"},
       "make_public": {"type": "boolean",
                        "description": "True = make public, False = make private",
                        "default": True}})
def toggle_kernel_visibility(ref: str = "", make_public: bool = True):
    if not ref:
        return {"error": "ref is required"}
    return update_kernel(ref=ref, is_private=not make_public)


# ============================================================================
# MCP TRANSPORT LAYER
# ============================================================================

def _tool_list() -> list:
    """Build MCP tool list from registry."""
    result = []
    for name, t in TOOLS.items():
        props = {}
        required = []
        for pname, pinfo in t["params"].items():
            ptype = pinfo.get("type", "string")
            # Map to JSON Schema types
            schema_type = "string"
            if ptype in ("number", "integer", "int"):
                schema_type = "number"
            elif ptype in ("boolean", "bool"):
                schema_type = "boolean"
            elif ptype == "object":
                schema_type = "object"

            prop_def = {"type": schema_type,
                         "description": pinfo.get("description", "")}

            if "enum" in pinfo:
                prop_def["enum"] = pinfo["enum"]
            if "default" in pinfo:
                prop_def["default"] = pinfo["default"]
            else:
                required.append(pname)

            props[pname] = prop_def

        result.append({
            "name": name,
            "description": t["desc"],
            "inputSchema": {
                "type": "object",
                "properties": props,
                "required": required
            }
        })
    return result


def _handle_mcp_request(data: dict) -> dict:
    """Process one MCP JSON-RPC request and return response."""
    msg_id = data.get("id", 0)
    method = data.get("method", "")
    params = data.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "kaggle-mcp",
                    "version": "2.1.0"
                }
            }
        }

    elif method == "notifications/initialized":
        log("Client initialized")
        return None  # no response for notifications

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "result": {"tools": _tool_list()}
        }

    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        if name not in TOOLS:
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"}
            }
        try:
            log(f"Calling tool '{name}' with args={json.dumps(args)[:200]}")
            fn = TOOLS[name]["fn"]
            result = fn(**args)
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "content": [{
                        "type": "text",
                        "text": json.dumps(result, indent=2, ensure_ascii=False)
                    }]
                }
            }
        except Exception as e:
            log(f"Error in '{name}': {e}")
            return {
                "jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32603, "message": str(e)[:500]}
            }

    elif method == "resources/list":
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "result": {"resources": []}
        }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    else:
        return {
            "jsonrpc": "2.0", "id": msg_id,
            "result": {}  # noop for unknown methods
        }


# ── Transport: STDIO (for Claude Code, Codex CLI, Cursor, Windsurf, OpenCode) ──

def _run_stdio():
    """Run MCP server over stdin/stdout (standard for Claude Code / Codex)."""
    log("Starting in STDIO mode — waiting for MCP messages on stdin...")
    # Signal readiness by writing a startup message to stderr
    print(json.dumps({"tools_loaded": len(TOOLS), "mode": "stdio"}), file=sys.stderr, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            resp = _handle_mcp_request(data)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            # Ignore malformed lines
            log(f"Invalid JSON on stdin: {line[:100]}")
            continue
        except EOFError:
            break
        except KeyboardInterrupt:
            break


# ── Transport: HTTP SSE (for web-based / custom clients) ──

def _run_http(port: int):
    """Run MCP server over HTTP SSE transport."""
    from http.server import HTTPServer, BaseHTTPRequestHandler

    sessions: dict[str, dict] = {}

    class MCPHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/sse":
                self._handle_sse()
            elif parsed.path == "/health":
                self._json({"status": "ok", "tools": len(TOOLS), "mode": "http-sse"})
            elif parsed.path == "/tools":
                self._json({"tools": _tool_list()})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/messages":
                self._handle_message()
            elif parsed.path == "/rpc":
                self._handle_rpc()
            else:
                self._json({"error": "not found"}, 404)

        def do_OPTIONS(self):
            self.send_response(200)
            self._cors_headers()
            self.end_headers()

        def _cors_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

        def _handle_sse(self):
            sess_id = str(uuid.uuid4())
            sessions[sess_id] = {"lock": threading.Lock(), "queue": []}
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self._cors_headers()
            self.end_headers()

            # Send endpoint event
            ep = json.dumps({"endpoint": f"/messages?sessionId={sess_id}"})
            self.wfile.write(f"event: endpoint\ndata: {ep}\n\n".encode())
            self.wfile.flush()

            # Send initialized
            init = json.dumps({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            })
            self.wfile.write(f"event: message\ndata: {init}\n\n".encode())
            self.wfile.flush()

            log(f"SSE session {sess_id} started")
            try:
                while sess_id in sessions:
                    time.sleep(1)
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                sessions.pop(sess_id, None)
                log(f"SSE session {sess_id} closed")

        def _handle_message(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode() if length else "{}"
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json({"error": "invalid JSON"}, 400)
                return

            resp = _handle_mcp_request(data)
            self._json(resp or {})

        def _handle_rpc(self):
            """Simple JSON-RPC over HTTP POST (alternative to SSE)."""
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode() if length else "{}"
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json({"error": "invalid JSON"}, 400)
                return
            resp = _handle_mcp_request(data)
            self._json(resp or {})

        def _json(self, data, code=200):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

        def log_message(self, fmt, *args):
            try:
                log(f"HTTP: {fmt % args}")
            except Exception:
                log(f"HTTP: {fmt} {args}")

    server = HTTPServer(("127.0.0.1", port), MCPHandler)
    log(f"Kaggle MCP Server running on http://127.0.0.1:{port}")
    log(f"{len(TOOLS)} tools loaded — User: {KAGGLE_USER}")
    print(f"http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down...")
        server.server_close()


# ============================================================================
# ENTRY POINT
# ============================================================================

def print_usage():
    print(__doc__)
    print(f"\nAvailable tools ({len(TOOLS)}):")
    for name in sorted(TOOLS.keys()):
        params = TOOLS[name]["params"]
        param_str = ", ".join(f"{k}: {v.get('type','str')}" for k, v in params.items())
        print(f"  {name:35s} {param_str}")
    sys.exit(0)


def main(argv=None):
    """Entry point for console script and direct execution."""
    import sys as _sys
    if argv is not None:
        _sys.argv = [_sys.argv[0], *argv]

    if "--help" in _sys.argv or "-h" in _sys.argv:
        print_usage()

    if "--stdio" in _sys.argv:
        _run_stdio()
    elif any(a.startswith("--port") for a in _sys.argv):
        try:
            idx = [a for a in _sys.argv if a.startswith("--port")][0]
            port = int(idx.split("=")[-1] if "=" in idx else _sys.argv[_sys.argv.index(idx) + 1])
        except (ValueError, IndexError):
            port = 8234
        _run_http(port)
    elif "--list-tools" in _sys.argv:
        print(json.dumps(_tool_list(), indent=2))
    else:
        if _sys.stdin.isatty():
            print("No mode specified. Use --stdio (Claude/Codex/Cursor) or --port N (HTTP).", file=_sys.stderr)
            print("Starting HTTP mode on default port 8234...", file=_sys.stderr)
            _run_http(8234)
        else:
            _run_stdio()


if __name__ == "__main__":
    main()
