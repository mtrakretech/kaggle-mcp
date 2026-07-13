#!/usr/bin/env python3
"""
Kaggle MCP Server v3.0 — full Kaggle CLI surface via MCP.

Transports: --stdio | --port N | --list-tools
Clients: Claude Desktop/Code, Codex, Cursor, Hermes, Windsurf, OpenCode, VS Code, Continue
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.parse, uuid
from pathlib import Path
from typing import Any, Optional

KAGGLE_USER = os.environ.get("KAGGLE_USERNAME") or ""
KAGGLE_KEY = os.environ.get("KAGGLE_KEY") or ""
API_BASE = "https://www.kaggle.com/api/v1"

if not KAGGLE_USER or not KAGGLE_KEY:
    kj = Path.home() / ".kaggle" / "kaggle.json"
    if kj.exists():
        try:
            c = json.loads(kj.read_text(encoding="utf-8"))
            KAGGLE_USER = c.get("username") or KAGGLE_USER
            KAGGLE_KEY = c.get("key") or KAGGLE_KEY
        except Exception:
            pass
if not KAGGLE_USER or not KAGGLE_KEY:
    print("ERROR: Set KAGGLE_USERNAME and KAGGLE_KEY or ~/.kaggle/kaggle.json", file=sys.stderr)
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {KAGGLE_KEY}", "Content-Type": "application/json"}
TOOLS: dict[str, dict] = {}

def log(msg: str) -> None:
    print(f"[kaggle-mcp] {msg}", file=sys.stderr, flush=True)

def tool(name: str, desc: str, params: Optional[dict] = None):
    def dec(fn):
        TOOLS[name] = {"fn": fn, "desc": desc, "params": params or {}}
        return fn
    return dec

def _hr(b: int) -> str:
    if b < 1024: return f"{b}B"
    if b < 1048576: return f"{b/1024:.1f}KB"
    return f"{b/1048576:.1f}MB"

def _kaggle(*args: str, timeout: int = 120) -> dict:
    clean = [a for a in args if a is not None and a != ""]
    env = os.environ.copy()
    env["KAGGLE_USERNAME"] = KAGGLE_USER
    env["KAGGLE_KEY"] = KAGGLE_KEY
    env["KAGGLE_API_TOKEN"] = os.environ.get("KAGGLE_API_TOKEN") or KAGGLE_KEY
    env["KAGGLE_NO_PROGRESS"] = "1"
    try:
        r = subprocess.run(["kaggle", *clean], capture_output=True, text=True, timeout=timeout, env=env)
        if r.returncode != 0:
            return {"error": ((r.stderr or r.stdout or "").strip())[:800], "command": " ".join(["kaggle", *clean])}
        return {"output": (r.stdout or "").strip()}
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s"}
    except FileNotFoundError:
        return {"error": "kaggle CLI not found — pip install kaggle"}
    except Exception as e:
        return {"error": str(e)[:500]}

def _api(method: str, path: str, data=None, params=None, timeout: int = 30) -> Any:
    import requests
    try:
        r = requests.request(method, f"{API_BASE}/{path.lstrip('/')}", headers=HEADERS, json=data, params=params, timeout=timeout)
        if r.status_code in (200, 201):
            if r.headers.get("content-type", "").startswith("application/json"):
                return r.json()
            return {"raw": r.text[:3000]}
        return {"error": f"API {r.status_code}: {r.text[:400]}"}
    except Exception as e:
        return {"error": str(e)[:300]}

def _need(val, name: str):
    if val is None or str(val).strip() == "":
        return {"error": f"{name} is required"}
    return None

def _list_dir(out_dir: str) -> list:
    p = Path(out_dir)
    if not p.exists(): return []
    out = []
    for f in p.rglob("*"):
        if f.is_file():
            s = f.stat().st_size
            out.append({"path": str(f.relative_to(p)), "size_bytes": s, "size_hr": _hr(s)})
    return out

def _tmpdir(prefix: str) -> str:
    d = tempfile.mkdtemp(prefix=prefix)
    return d

# ========================= KERNELS =========================

@tool("search_kernels", "Search public Kaggle notebooks/kernels",
      {"query": {"type": "string"}, "sort_by": {"type": "string", "enum": ["hotness","commentCount","dateCreated","dateModified","score"], "default": "hotness"},
       "language": {"type": "string", "enum": ["all","python","r","sqlite","julia"], "default": "all"},
       "kernel_type": {"type": "string", "enum": ["all","script","notebook"], "default": "all"},
       "user": {"type": "string", "default": ""}, "competition": {"type": "string", "default": ""},
       "dataset": {"type": "string", "default": ""}, "limit": {"type": "number", "default": 10}})
def search_kernels(query: str = "", sort_by: str = "hotness", language: str = "all", kernel_type: str = "all",
                   user: str = "", competition: str = "", dataset: str = "", limit: int = 10):
    e = _need(query, "query")
    if e: return e
    limit = max(1, min(200, int(limit)))
    args = ["kernels","list","--search",query,"--sort-by",sort_by,"--page-size",str(limit),"-v"]
    if language and language != "all": args += ["--language", language]
    if kernel_type and kernel_type != "all": args += ["--kernel-type", kernel_type]
    if user: args += ["--user", user]
    if competition: args += ["--competition", competition]
    if dataset: args += ["--dataset", dataset]
    return _kaggle(*args)

@tool("list_my_kernels", "List your Kaggle notebooks",
      {"limit": {"type": "number", "default": 20}, "page": {"type": "number", "default": 1},
       "sort_by": {"type": "string", "enum": ["hotness","commentCount","dateCreated","dateRun","relevance","scoreAscending","scoreDescending","viewCount","voteCount"], "default": "dateRun"}})
def list_my_kernels(limit: int = 20, page: int = 1, sort_by: str = "dateRun"):
    return _kaggle("kernels","list","--mine","--page-size",str(max(1,min(200,int(limit)))),
                   "--page",str(max(1,int(page))),"--sort-by",sort_by,"-v")

@tool("kernel_status", "Check kernel run status", {"ref": {"type": "string"}})
def kernel_status(ref: str = ""):
    return _need(ref,"ref") or _kaggle("kernels","status",ref)

@tool("kernel_logs", "Get kernel execution logs", {"ref": {"type": "string"}})
def kernel_logs(ref: str = ""):
    return _need(ref,"ref") or _kaggle("kernels","logs",ref, timeout=90)

@tool("kernel_files", "List kernel output files (metadata)",
      {"ref": {"type": "string"}, "page_size": {"type": "number", "default": 50}})
def kernel_files(ref: str = "", page_size: int = 50):
    return _need(ref,"ref") or _kaggle("kernels","files",ref,"--page-size",str(max(1,min(200,int(page_size)))),"-v")

@tool("kernel_output", "Download kernel output files",
      {"ref": {"type": "string"}, "output_dir": {"type": "string", "default": ""}, "file_pattern": {"type": "string", "default": ""}})
def kernel_output(ref: str = "", output_dir: str = "", file_pattern: str = ""):
    e = _need(ref,"ref")
    if e: return e
    out = output_dir or _tmpdir("kg_output_")
    os.makedirs(out, exist_ok=True)
    args = ["kernels","output",ref,"-p",out,"-o","-q"]
    if file_pattern: args += ["--file-pattern", file_pattern]
    r = _kaggle(*args, timeout=180)
    if "error" in r: return r
    files = _list_dir(out)
    return {"ref": ref, "download_path": out, "files": files, "file_count": len(files)}

@tool("pull_notebook", "Download notebook source (.ipynb)",
      {"ref": {"type": "string"}, "output_dir": {"type": "string", "default": "."}, "with_metadata": {"type": "boolean", "default": True}})
def pull_notebook(ref: str = "", output_dir: str = ".", with_metadata: bool = True):
    e = _need(ref,"ref")
    if e: return e
    out = os.path.abspath(output_dir or ".")
    os.makedirs(out, exist_ok=True)
    args = ["kernels","pull",ref,"-p",out]
    if with_metadata: args.append("-m")
    r = _kaggle(*args, timeout=90)
    if "error" in r: return r
    return {"ref": ref, "output_directory": out, "files": [f.name for f in Path(out).iterdir() if f.is_file()]}

@tool("push_notebook", "Upload notebook and run on free GPU/TPU",
      {"path": {"type": "string"}, "name": {"type": "string", "default": ""},
       "gpu": {"type": "boolean", "default": True}, "tpu": {"type": "boolean", "default": False},
       "internet": {"type": "boolean", "default": True}, "private": {"type": "boolean", "default": True},
       "dataset_sources": {"type": "string", "default": ""}, "competition_sources": {"type": "string", "default": ""},
       "timeout_seconds": {"type": "number", "default": 0}})
def push_notebook(path: str = "", name: str = "", gpu: bool = True, tpu: bool = False, internet: bool = True,
                  private: bool = True, dataset_sources: str = "", competition_sources: str = "", timeout_seconds: int = 0):
    if not path or not os.path.exists(path): return {"error": f"File not found: {path}"}
    if not path.endswith(".ipynb"): return {"error": "Only .ipynb supported"}
    tmp = _tmpdir("kg_push_")
    try:
        shutil.copy2(path, os.path.join(tmp, "__notebook__.ipynb"))
        title = name or Path(path).stem
        slug = re.sub(r"[^a-zA-Z0-9-]", "-", title.lower()).strip("-")[:50] or "notebook"
        meta = {"id": f"{KAGGLE_USER}/{slug}", "title": title, "code_file": "__notebook__.ipynb",
                "language": "python", "kernel_type": "notebook", "is_private": bool(private),
                "enable_gpu": bool(gpu), "enable_tpu": bool(tpu), "enable_internet": bool(internet)}
        if dataset_sources:
            meta["dataset_sources"] = [s.strip() for s in dataset_sources.split(",") if s.strip()]
        if competition_sources:
            meta["competition_sources"] = [s.strip() for s in competition_sources.split(",") if s.strip()]
        Path(tmp, "kernel-metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        args = ["kernels","push","-p",tmp]
        if timeout_seconds and int(timeout_seconds) > 0: args += ["-t", str(int(timeout_seconds))]
        r = _kaggle(*args, timeout=240)
        if "error" in r: return r
        return {"status": "pushed", "kernel_ref": f"{KAGGLE_USER}/{slug}", "title": title,
                "gpu": bool(gpu), "tpu": bool(tpu), "private": bool(private), "cli": r.get("output","")}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

@tool("init_kernel", "Create kernel-metadata.json skeleton", {"folder": {"type": "string"}})
def init_kernel(folder: str = ""):
    e = _need(folder,"folder")
    if e: return e
    os.makedirs(folder, exist_ok=True)
    return _kaggle("kernels","init","-p",folder)

@tool("update_kernel", "Update kernel metadata via pull+push",
      {"ref": {"type": "string"}, "is_private": {"type": "boolean"}, "enable_gpu": {"type": "boolean"},
       "enable_tpu": {"type": "boolean"}, "enable_internet": {"type": "boolean"}})
def update_kernel(ref: str = "", is_private: bool = None, enable_gpu: bool = None,
                  enable_tpu: bool = None, enable_internet: bool = None):
    e = _need(ref,"ref")
    if e: return e
    out = _tmpdir("kg_upd_")
    try:
        pull = _kaggle("kernels","pull",ref,"-p",out,"-m", timeout=90)
        if "error" in pull: return pull
        meta_file = Path(out)/"kernel-metadata.json"
        nb = next((f for f in Path(out).iterdir() if f.suffix==".ipynb"), None)
        meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {"id": ref}
        if is_private is not None: meta["is_private"] = bool(is_private)
        if enable_gpu is not None: meta["enable_gpu"] = bool(enable_gpu)
        if enable_tpu is not None: meta["enable_tpu"] = bool(enable_tpu)
        if enable_internet is not None: meta["enable_internet"] = bool(enable_internet)
        meta["code_file"] = nb.name if nb else meta.get("code_file","__notebook__.ipynb")
        meta.setdefault("kernel_type","notebook"); meta.setdefault("language","python")
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        r = _kaggle("kernels","push","-p",out, timeout=180)
        if "error" in r: return r
        return {"status":"updated","ref":ref,"metadata":{k:meta.get(k) for k in ("is_private","enable_gpu","enable_tpu","enable_internet")}}
    finally:
        shutil.rmtree(out, ignore_errors=True)

@tool("delete_kernel", "Delete a kernel permanently", {"ref": {"type": "string"}})
def delete_kernel(ref: str = ""):
    return _need(ref,"ref") or _kaggle("kernels","delete",ref,"-y")

@tool("preview_notebook", "Preview first N cells of a notebook",
      {"ref": {"type": "string"}, "max_cells": {"type": "number", "default": 5}})
def preview_notebook(ref: str = "", max_cells: int = 5):
    e = _need(ref,"ref")
    if e: return e
    max_cells = max(1, min(50, int(max_cells)))
    out = _tmpdir("kg_preview_")
    try:
        r = _kaggle("kernels","pull",ref,"-p",out, timeout=90)
        if "error" in r: return r
        nbs = list(Path(out).glob("*.ipynb"))
        if not nbs: return {"error":"No notebook file found"}
        nb = json.loads(nbs[0].read_text(encoding="utf-8"))
        cells = nb.get("cells", [])
        preview = []
        for i, cell in enumerate(cells[:max_cells]):
            src = "".join(cell.get("source", []))
            preview.append({"cell_index":i,"cell_type":cell.get("cell_type","unknown"),
                            "source_preview":src[:500] if src else "(empty)","source_length":len(src)})
        return {"ref":ref,"total_cells":len(cells),"previewed":len(preview),"cells":preview}
    finally:
        shutil.rmtree(out, ignore_errors=True)

@tool("toggle_kernel_visibility", "Make kernel public or private",
      {"ref": {"type": "string"}, "make_public": {"type": "boolean", "default": True}})
def toggle_kernel_visibility(ref: str = "", make_public: bool = True):
    return update_kernel(ref=ref, is_private=not bool(make_public))

@tool("list_kernel_topics", "List discussion topics on a kernel",
      {"ref": {"type": "string"}, "sort_by": {"type": "string", "default": "hot"},
       "search": {"type": "string", "default": ""}, "page_size": {"type": "number", "default": 20}})
def list_kernel_topics(ref: str = "", sort_by: str = "hot", search: str = "", page_size: int = 20):
    e = _need(ref,"ref")
    if e: return e
    args = ["kernels","topics","list",ref,"--page-size",str(max(1,min(200,int(page_size)))), "--sort-by",sort_by,"-v"]
    if search: args += ["-s", search]
    return _kaggle(*args)

@tool("show_kernel_topic", "Show a kernel discussion topic", {"topic_ref": {"type": "string"}})
def show_kernel_topic(topic_ref: str = ""):
    return _need(topic_ref,"topic_ref") or _kaggle("kernels","topics","show",topic_ref,"-v")

# ========================= DATASETS =========================

@tool("search_datasets", "Search Kaggle datasets",
      {"query": {"type": "string", "default": ""}, "sort_by": {"type": "string", "enum": ["hottest","votes","updated","active"], "default": "hottest"},
       "file_type": {"type": "string", "enum": ["all","csv","json","sqlite","bigQuery"], "default": "all"},
       "user": {"type": "string", "default": ""}, "mine": {"type": "boolean", "default": False},
       "page": {"type": "number", "default": 1}, "limit": {"type": "number", "default": 10}})
def search_datasets(query: str = "", sort_by: str = "hottest", file_type: str = "all",
                    user: str = "", mine: bool = False, page: int = 1, limit: int = 10):
    if not query and not user and not mine: return {"error":"Provide query, user, or mine=true"}
    # datasets list page size fixed ~20; use -p for page, then truncate client-side
    args = ["datasets","list","--sort-by",sort_by,"-v","-p",str(max(1,int(page)))]
    if query: args += ["--search", query]
    if file_type and file_type != "all": args += ["--file-type", file_type]
    if user: args += ["--user", user]
    if mine: args.append("--mine")
    r = _kaggle(*args)
    if "error" in r or "output" not in r: return r
    limit = max(1, min(100, int(limit)))
    lines = [ln for ln in r["output"].splitlines() if ln.strip()]
    if not lines: return r
    header, body = lines[:1], lines[1:]
    body = body[:limit]
    return {"output": "\n".join(header + body), "shown": len(body), "page": max(1,int(page))}

@tool("list_my_datasets", "List your datasets",
      {"page": {"type": "number", "default": 1}, "limit": {"type": "number", "default": 20}})
def list_my_datasets(page: int = 1, limit: int = 20):
    r = _kaggle("datasets","list","--mine","-v","-p",str(max(1,int(page))))
    if "error" in r or "output" not in r: return r
    limit = max(1, min(100, int(limit)))
    lines = [ln for ln in r["output"].splitlines() if ln.strip()]
    if not lines: return r
    header, body = lines[:1], lines[1:]
    body = body[:limit]
    return {"output": "\n".join(header + body), "shown": len(body), "page": max(1,int(page))}

@tool("dataset_details", "Dataset metadata via REST API", {"ref": {"type": "string"}})
def dataset_details(ref: str = ""):
    e = _need(ref,"ref")
    if e: return e
    result = _api("GET", f"datasets/view/{ref}")
    if isinstance(result, dict) and "error" not in result:
        return {"ref":ref,"title":result.get("title",""),"subtitle":result.get("subtitle",""),
                "description":(result.get("description") or "")[:800],"total_bytes":result.get("totalBytes",0),
                "file_count":len(result.get("datasetFiles",[]) or []),
                "dataset_files":[{"name":f.get("name",""),"size_bytes":f.get("size",0),"type":f.get("fileType","")}
                                 for f in (result.get("datasetFiles",[]) or [])[:50]],
                "is_private":result.get("isPrivate",False),"owner":result.get("ownerName",""),
                "current_version":result.get("currentVersionNumber",""),"downloads":result.get("downloadCount",0),
                "votes":result.get("totalVotes",0)}
    return result

@tool("list_dataset_files", "List files in a dataset",
      {"ref": {"type": "string"}, "page_size": {"type": "number", "default": 50}})
def list_dataset_files(ref: str = "", page_size: int = 50):
    return _need(ref,"ref") or _kaggle("datasets","files",ref,"--page-size",str(max(1,min(200,int(page_size)))),"-v")

@tool("download_dataset", "Download dataset files",
      {"ref": {"type": "string"}, "file_name": {"type": "string", "default": ""},
       "unzip": {"type": "boolean", "default": False}, "output_dir": {"type": "string", "default": ""}})
def download_dataset(ref: str = "", file_name: str = "", unzip: bool = False, output_dir: str = ""):
    e = _need(ref,"ref")
    if e: return e
    out = output_dir or _tmpdir("kg_ds_")
    os.makedirs(out, exist_ok=True)
    args = ["datasets","download",ref,"-p",out,"-o","-q"]
    if file_name: args += ["-f", file_name]
    if unzip: args.append("--unzip")
    r = _kaggle(*args, timeout=300)
    if "error" in r: return r
    files = _list_dir(out)
    total = sum(f["size_bytes"] for f in files)
    return {"ref":ref,"download_path":out,"files":files,"total_files":len(files),"total_size_hr":_hr(total)}

@tool("init_dataset", "Create dataset-metadata.json skeleton", {"folder": {"type": "string"}})
def init_dataset(folder: str = ""):
    e = _need(folder,"folder")
    if e: return e
    os.makedirs(folder, exist_ok=True)
    return _kaggle("datasets","init","-p",folder)

@tool("upload_dataset", "Create a new dataset from a folder",
      {"dir_path": {"type": "string"}, "name": {"type": "string", "default": ""},
       "public": {"type": "boolean", "default": False}, "description": {"type": "string", "default": ""},
       "subtitle": {"type": "string", "default": ""}})
def upload_dataset(dir_path: str = "", name: str = "", public: bool = False, description: str = "", subtitle: str = ""):
    if not dir_path or not os.path.isdir(dir_path): return {"error": f"Directory not found: {dir_path}"}
    n = name or os.path.basename(os.path.normpath(dir_path))
    slug = re.sub(r"[^a-zA-Z0-9-]","-",n.lower()).strip("-")[:50]
    meta_path = os.path.join(dir_path, "dataset-metadata.json")
    have = os.path.exists(meta_path)
    if not have:
        meta = {"title": n, "id": f"{KAGGLE_USER}/{slug}", "licenses": [{"name": "CC0-1.0"}]}
        if description: meta["description"] = description
        if subtitle: meta["subtitle"] = subtitle
        Path(meta_path).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    try:
        args = ["datasets","create","-p",dir_path,"-q"]
        if public: args.append("-u")
        r = _kaggle(*args, timeout=300)
        if "error" in r: return r
        return {"status":"created","dataset_ref":f"{KAGGLE_USER}/{slug}","public":bool(public),"cli":r.get("output","")}
    finally:
        if not have and os.path.exists(meta_path):
            try: os.remove(meta_path)
            except OSError: pass

@tool("update_dataset", "Create new dataset version",
      {"dir_path": {"type": "string"}, "version_notes": {"type": "string", "default": "Updated"},
       "delete_old_versions": {"type": "boolean", "default": False}})
def update_dataset(dir_path: str = "", version_notes: str = "Updated", delete_old_versions: bool = False):
    if not dir_path or not os.path.isdir(dir_path): return {"error": f"Directory not found: {dir_path}"}
    args = ["datasets","version","-p",dir_path,"-m",version_notes or "Updated","-q"]
    if delete_old_versions: args.append("-d")
    return _kaggle(*args, timeout=300)

@tool("get_dataset_metadata", "Download dataset-metadata.json",
      {"ref": {"type": "string"}, "output_dir": {"type": "string", "default": ""}})
def get_dataset_metadata(ref: str = "", output_dir: str = ""):
    e = _need(ref,"ref")
    if e: return e
    out = output_dir or _tmpdir("kg_meta_")
    os.makedirs(out, exist_ok=True)
    r = _kaggle("datasets","metadata",ref,"-p",out)
    if "error" in r: return r
    mf = Path(out)/"dataset-metadata.json"
    content = None
    if mf.exists():
        try: content = json.loads(mf.read_text(encoding="utf-8"))
        except Exception: content = mf.read_text(encoding="utf-8")[:2000]
    return {"ref":ref,"path":str(mf),"metadata":content,"cli":r.get("output","")}

@tool("dataset_status", "Dataset creation/processing status", {"ref": {"type": "string"}})
def dataset_status(ref: str = ""):
    return _need(ref,"ref") or _kaggle("datasets","status",ref,"--format","json")

@tool("delete_dataset", "Delete dataset permanently", {"ref": {"type": "string"}})
def delete_dataset(ref: str = ""):
    return _need(ref,"ref") or _kaggle("datasets","delete",ref,"-y")

@tool("list_dataset_topics", "List dataset discussion topics",
      {"ref": {"type": "string"}, "sort_by": {"type": "string", "default": "hot"},
       "search": {"type": "string", "default": ""}, "page_size": {"type": "number", "default": 20}})
def list_dataset_topics(ref: str = "", sort_by: str = "hot", search: str = "", page_size: int = 20):
    e = _need(ref,"ref")
    if e: return e
    args = ["datasets","topics","list",ref,"--page-size",str(max(1,min(200,int(page_size)))), "--sort-by",sort_by,"-v"]
    if search: args += ["-s", search]
    return _kaggle(*args)

@tool("show_dataset_topic", "Show dataset topic thread", {"topic_ref": {"type": "string"}})
def show_dataset_topic(topic_ref: str = ""):
    return _need(topic_ref,"topic_ref") or _kaggle("datasets","topics","show",topic_ref,"-v")

# ========================= COMPETITIONS =========================

@tool("list_competitions", "List competitions",
      {"category": {"type": "string", "enum": ["all","featured","research","recruitment","gettingStarted","masters","playground"], "default": "all"},
       "group": {"type": "string", "enum": ["general","entered","inClass"], "default": "general"},
       "sort_by": {"type": "string", "enum": ["grouped","prize","earliestDeadline","latestDeadline","numberOfTeams","recentlyCreated"], "default": "latestDeadline"},
       "search": {"type": "string", "default": ""}, "limit": {"type": "number", "default": 20}})
def list_competitions(category: str = "all", group: str = "general", sort_by: str = "latestDeadline",
                      search: str = "", limit: int = 20):
    limit = max(1, min(200, int(limit)))
    args = ["competitions","list","--page-size",str(limit),"--sort-by",sort_by,"--group",group,"-v"]
    if category and category != "all": args += ["--category", category]
    if search: args += ["--search", search]
    return _kaggle(*args)

@tool("list_competition_files", "List competition data files",
      {"comp": {"type": "string"}, "page_size": {"type": "number", "default": 50}})
def list_competition_files(comp: str = "", page_size: int = 50):
    return _need(comp,"comp") or _kaggle("competitions","files",comp,"--page-size",str(max(1,min(200,int(page_size)))),"-v")

@tool("download_competition_data", "Download competition files",
      {"comp": {"type": "string"}, "file_name": {"type": "string", "default": ""}, "output_dir": {"type": "string", "default": ""}})
def download_competition_data(comp: str = "", file_name: str = "", output_dir: str = ""):
    e = _need(comp,"comp")
    if e: return e
    out = output_dir or _tmpdir("kg_comp_")
    os.makedirs(out, exist_ok=True)
    args = ["competitions","download",comp,"-p",out,"-o","-q"]
    if file_name: args += ["-f", file_name]
    r = _kaggle(*args, timeout=300)
    if "error" in r: return r
    files = _list_dir(out)
    return {"competition":comp,"download_path":out,"files":files,"file_count":len(files)}

@tool("submit_competition", "Submit predictions file or kernel to a competition",
      {"comp": {"type": "string"}, "file": {"type": "string", "default": ""},
       "kernel": {"type": "string", "default": ""}, "kernel_version": {"type": "string", "default": ""},
       "message": {"type": "string", "default": "Submission via Kaggle MCP"}})
def submit_competition(comp: str = "", file: str = "", kernel: str = "", kernel_version: str = "",
                       message: str = "Submission via Kaggle MCP"):
    e = _need(comp,"comp")
    if e: return e
    if not file and not kernel: return {"error":"Provide file and/or kernel"}
    args = ["competitions","submit",comp,"-m",message or "Submission via Kaggle MCP","-q"]
    if file:
        if not os.path.exists(file): return {"error": f"Submission file not found: {file}"}
        args += ["-f", file]
    if kernel: args += ["-k", kernel]
    if kernel_version: args += ["-v", str(kernel_version)]
    return _kaggle(*args, timeout=180)

@tool("list_competition_submissions", "List your submissions for a competition",
      {"comp": {"type": "string"}, "page_size": {"type": "number", "default": 20}})
def list_competition_submissions(comp: str = "", page_size: int = 20):
    return _need(comp,"comp") or _kaggle("competitions","submissions",comp,"--page-size",str(max(1,min(200,int(page_size)))),"-v")

@tool("competition_leaderboard", "Show competition leaderboard",
      {"comp": {"type": "string"}, "page_size": {"type": "number", "default": 20},
       "download": {"type": "boolean", "default": False}, "output_dir": {"type": "string", "default": ""}})
def competition_leaderboard(comp: str = "", page_size: int = 20, download: bool = False, output_dir: str = ""):
    e = _need(comp,"comp")
    if e: return e
    if download:
        out = output_dir or _tmpdir("kg_lb_")
        os.makedirs(out, exist_ok=True)
        r = _kaggle("competitions","leaderboard",comp,"-d","-p",out,"-q")
        if "error" in r: return r
        return {"competition":comp,"download_path":out,"files":_list_dir(out),"cli":r.get("output","")}
    return _kaggle("competitions","leaderboard",comp,"-s","--page-size",str(max(1,min(200,int(page_size)))),"-v")

@tool("list_team_submissions", "List public submissions for a team ID",
      {"team_id": {"type": "string"}})
def list_team_submissions(team_id: str = ""):
    return _need(team_id,"team_id") or _kaggle("competitions","team-submissions",str(team_id),"-v")

@tool("list_competition_episodes", "List simulation episodes for a submission",
      {"submission_id": {"type": "string"}})
def list_competition_episodes(submission_id: str = ""):
    return _need(submission_id,"submission_id") or _kaggle("competitions","episodes",str(submission_id),"-v")

@tool("download_competition_replay", "Download simulation episode replay",
      {"episode_id": {"type": "string"}, "output_dir": {"type": "string", "default": ""}})
def download_competition_replay(episode_id: str = "", output_dir: str = ""):
    e = _need(episode_id,"episode_id")
    if e: return e
    out = output_dir or _tmpdir("kg_replay_")
    os.makedirs(out, exist_ok=True)
    r = _kaggle("competitions","replay",str(episode_id),"-p",out,"-q")
    if "error" in r: return r
    return {"episode_id":episode_id,"download_path":out,"files":_list_dir(out)}

@tool("download_competition_episode_logs", "Download agent logs for a simulation episode",
      {"episode_id": {"type": "string"}, "agent_index": {"type": "number", "default": 0}, "output_dir": {"type": "string", "default": ""}})
def download_competition_episode_logs(episode_id: str = "", agent_index: int = 0, output_dir: str = ""):
    e = _need(episode_id,"episode_id")
    if e: return e
    out = output_dir or _tmpdir("kg_elog_")
    os.makedirs(out, exist_ok=True)
    r = _kaggle("competitions","logs",str(episode_id),str(int(agent_index)),"-p",out,"-q")
    if "error" in r: return r
    return {"episode_id":episode_id,"agent_index":int(agent_index),"download_path":out,"files":_list_dir(out)}

@tool("list_competition_pages", "List competition pages (rules/description/evaluation)",
      {"comp": {"type": "string"}, "page_name": {"type": "string", "default": ""}, "content": {"type": "boolean", "default": False}})
def list_competition_pages(comp: str = "", page_name: str = "", content: bool = False):
    e = _need(comp,"comp")
    if e: return e
    args = ["competitions","pages",comp,"-v"]
    if page_name: args += ["--page-name", page_name]
    if content: args.append("--content")
    return _kaggle(*args)

@tool("list_competition_topics", "List competition forum topics",
      {"comp": {"type": "string"}, "sort_by": {"type": "string", "default": "hot"}, "page": {"type": "number", "default": 1}})
def list_competition_topics(comp: str = "", sort_by: str = "hot", page: int = 1):
    e = _need(comp,"comp")
    if e: return e
    return _kaggle("competitions","topics","list",comp,"-p",str(max(1,int(page))),"--sort-by",sort_by,"-v")

@tool("show_competition_topic", "Show competition topic thread", {"topic_ref": {"type": "string"}})
def show_competition_topic(topic_ref: str = ""):
    return _need(topic_ref,"topic_ref") or _kaggle("competitions","topics","show",topic_ref,"-v")

# ========================= MODELS =========================

@tool("list_models", "List / search Kaggle models",
      {"search": {"type": "string", "default": ""}, "owner": {"type": "string", "default": ""},
       "sort_by": {"type": "string", "enum": ["hotness","downloadCount","voteCount","recentlyUpdated","recentlyCreated"], "default": "hotness"},
       "limit": {"type": "number", "default": 10}})
def list_models(search: str = "", owner: str = "", sort_by: str = "hotness", limit: int = 10):
    limit = max(1, min(200, int(limit)))
    args = ["models","list","--page-size",str(limit),"--sort-by",sort_by]
    if search: args += ["--search", search]
    if owner: args += ["--owner", owner]
    return _kaggle(*args)

@tool("model_details", "Get model details", {"model_ref": {"type": "string"}})
def model_details(model_ref: str = ""):
    return _need(model_ref,"model_ref") or _kaggle("models","get",model_ref)

@tool("init_model", "Initialize model-metadata.json in folder", {"folder": {"type": "string"}})
def init_model(folder: str = ""):
    e = _need(folder,"folder")
    if e: return e
    os.makedirs(folder, exist_ok=True)
    return _kaggle("models","init","-p",folder)

@tool("create_model", "Create model from folder with model-metadata.json", {"folder": {"type": "string"}})
def create_model(folder: str = ""):
    e = _need(folder,"folder")
    if e: return e
    if not os.path.isdir(folder): return {"error": f"Directory not found: {folder}"}
    return _kaggle("models","create","-p",folder, timeout=180)

@tool("update_model", "Update model metadata from folder", {"folder": {"type": "string"}})
def update_model(folder: str = ""):
    e = _need(folder,"folder")
    if e: return e
    return _kaggle("models","update","-p",folder)

@tool("delete_model", "Delete a model permanently", {"model_ref": {"type": "string"}})
def delete_model(model_ref: str = ""):
    return _need(model_ref,"model_ref") or _kaggle("models","delete",model_ref,"-y")

@tool("list_model_instances", "List model instances/variations for owner/model",
      {"model_ref": {"type": "string"}, "page_size": {"type": "number", "default": 20}})
def list_model_instances(model_ref: str = "", page_size: int = 20):
    return _need(model_ref,"model_ref") or _kaggle("models","instances","list",model_ref,"--page-size",str(max(1,min(200,int(page_size)))),"-v")

@tool("get_model_instance", "Download model-instance-metadata.json",
      {"instance_ref": {"type": "string"}, "output_dir": {"type": "string", "default": ""}})
def get_model_instance(instance_ref: str = "", output_dir: str = ""):
    e = _need(instance_ref,"instance_ref")
    if e: return e
    out = output_dir or _tmpdir("kg_mi_")
    os.makedirs(out, exist_ok=True)
    r = _kaggle("models","instances","get",instance_ref,"-p",out)
    if "error" in r: return r
    return {"instance_ref":instance_ref,"path":out,"files":_list_dir(out),"cli":r.get("output","")}

@tool("init_model_instance", "Init model-instance-metadata.json", {"folder": {"type": "string"}})
def init_model_instance(folder: str = ""):
    e = _need(folder,"folder")
    if e: return e
    os.makedirs(folder, exist_ok=True)
    return _kaggle("models","instances","init","-p",folder)

@tool("create_model_instance", "Create model instance from folder", {"folder": {"type": "string"}})
def create_model_instance(folder: str = ""):
    e = _need(folder,"folder")
    if e: return e
    return _kaggle("models","instances","create","-p",folder, timeout=300)

@tool("update_model_instance", "Update model instance metadata from folder", {"folder": {"type": "string"}})
def update_model_instance(folder: str = ""):
    e = _need(folder,"folder")
    if e: return e
    return _kaggle("models","instances","update","-p",folder)

@tool("delete_model_instance", "Delete a model instance", {"instance_ref": {"type": "string"}})
def delete_model_instance(instance_ref: str = ""):
    return _need(instance_ref,"instance_ref") or _kaggle("models","instances","delete",instance_ref,"-y")

@tool("list_model_instance_versions", "List versions for a model instance",
      {"instance_ref": {"type": "string"}, "page_size": {"type": "number", "default": 20}})
def list_model_instance_versions(instance_ref: str = "", page_size: int = 20):
    return _need(instance_ref,"instance_ref") or _kaggle("models","instances","versions","list",instance_ref,"--page-size",str(max(1,min(200,int(page_size)))),"-v")

@tool("list_model_version_files", "List files in a model instance version",
      {"version_ref": {"type": "string"}, "page_size": {"type": "number", "default": 50}})
def list_model_version_files(version_ref: str = "", page_size: int = 50):
    return _need(version_ref,"version_ref") or _kaggle("models","instances","versions","files",version_ref,"--page-size",str(max(1,min(200,int(page_size)))),"-v")

@tool("download_model_version", "Download model instance version files",
      {"version_ref": {"type": "string"}, "output_dir": {"type": "string", "default": ""}, "untar": {"type": "boolean", "default": False}})
def download_model_version(version_ref: str = "", output_dir: str = "", untar: bool = False):
    e = _need(version_ref,"version_ref")
    if e: return e
    out = output_dir or _tmpdir("kg_mver_")
    os.makedirs(out, exist_ok=True)
    args = ["models","instances","versions","download",version_ref,"-p",out,"-f","-q"]
    if untar: args.append("--untar")
    r = _kaggle(*args, timeout=600)
    if "error" in r: return r
    files = _list_dir(out)
    return {"version_ref":version_ref,"download_path":out,"files":files,"file_count":len(files)}

@tool("create_model_version", "Create new model instance version from folder",
      {"instance_ref": {"type": "string"}, "folder": {"type": "string"}, "version_notes": {"type": "string", "default": "New version"}})
def create_model_version(instance_ref: str = "", folder: str = "", version_notes: str = "New version"):
    e = _need(instance_ref,"instance_ref") or _need(folder,"folder")
    if e: return e
    return _kaggle("models","instances","versions","create",instance_ref,"-p",folder,"-n",version_notes or "New version","-q", timeout=600)

@tool("delete_model_version", "Delete a model instance version", {"version_ref": {"type": "string"}})
def delete_model_version(version_ref: str = ""):
    return _need(version_ref,"version_ref") or _kaggle("models","instances","versions","delete",version_ref,"-y")

@tool("list_model_topics", "List model discussion topics",
      {"model_ref": {"type": "string"}, "page_size": {"type": "number", "default": 20}})
def list_model_topics(model_ref: str = "", page_size: int = 20):
    return _need(model_ref,"model_ref") or _kaggle("models","topics","list",model_ref,"--page-size",str(max(1,min(200,int(page_size)))),"-v")

# ========================= FORUMS / BENCHMARKS / QUOTA =========================

@tool("list_forums", "List Kaggle forums", {})
def list_forums():
    return _kaggle("forums","list","-v")

@tool("list_forum_topics", "List topics in a forum or global search",
      {"forum": {"type": "string", "default": ""}, "search": {"type": "string", "default": ""},
       "sort_by": {"type": "string", "default": "hot"},
       "category": {"type": "string", "enum": ["all","forums","competitions","datasets","competition_write_ups","models","benchmarks"], "default": "all"},
       "page_size": {"type": "number", "default": 20}})
def list_forum_topics(forum: str = "", search: str = "", sort_by: str = "hot", category: str = "all", page_size: int = 20):
    args = ["forums","topics","list","--page-size",str(max(1,min(200,int(page_size)))), "--sort-by",sort_by,"-v"]
    if forum: args.append(forum)
    if search: args += ["-s", search]
    if category and category != "all": args += ["--category", category]
    return _kaggle(*args)

@tool("show_forum_topic", "Show forum topic thread", {"topic_ref": {"type": "string"}})
def show_forum_topic(topic_ref: str = ""):
    return _need(topic_ref,"topic_ref") or _kaggle("forums","topics","show",topic_ref,"-v")

@tool("list_benchmark_tasks", "List your benchmark tasks",
      {"status": {"type": "string", "enum": ["","queued","running","completed","errored"], "default": ""},
       "name_regex": {"type": "string", "default": ""}})
def list_benchmark_tasks(status: str = "", name_regex: str = ""):
    args = ["benchmarks","tasks","list","--all"]
    if status: args += ["--status", status]
    if name_regex: args += ["--name-regex", name_regex]
    return _kaggle(*args)

@tool("list_benchmark_models", "List available benchmark models", {})
def list_benchmark_models():
    return _kaggle("benchmarks","tasks","models")

@tool("benchmark_task_status", "Show benchmark task status", {"task": {"type": "string"}})
def benchmark_task_status(task: str = ""):
    return _need(task,"task") or _kaggle("benchmarks","tasks","status",task)

@tool("get_quota", "Show GPU/TPU quota remaining", {})
def get_quota():
    return _kaggle("quota")

@tool("get_account_info", "Account username + quota snapshot", {})
def get_account_info():
    quota = _kaggle("quota")
    mine = _kaggle("kernels","list","--mine","--page-size","5","-v")
    return {"username": KAGGLE_USER,
            "quota": quota.get("output") if "output" in quota else quota,
            "recent_kernels": mine.get("output") if "output" in mine else mine}

@tool("get_config", "Show kaggle CLI config", {})
def get_config():
    return _kaggle("config","view")

# ========================= MCP TRANSPORT =========================

def _tool_list() -> list:
    result = []
    for name, t in TOOLS.items():
        props, required = {}, []
        for pname, pinfo in t["params"].items():
            ptype = pinfo.get("type","string")
            schema_type = "string"
            if ptype in ("number","integer","int"): schema_type = "number"
            elif ptype in ("boolean","bool"): schema_type = "boolean"
            prop = {"type": schema_type, "description": pinfo.get("description","")}
            if "enum" in pinfo: prop["enum"] = pinfo["enum"]
            if "default" in pinfo: prop["default"] = pinfo["default"]
            else: required.append(pname)
            props[pname] = prop
        result.append({"name": name, "description": t["desc"],
                       "inputSchema": {"type":"object","properties":props,"required":required}})
    return result

def _handle_mcp_request(data: dict):
    msg_id = data.get("id", 0)
    method = data.get("method", "")
    params = data.get("params", {}) or {}
    if method == "initialize":
        return {"jsonrpc":"2.0","id":msg_id,"result":{
            "protocolVersion":"2025-03-26","capabilities":{"tools":{}},
            "serverInfo":{"name":"kaggle-mcp","version":"3.0.0"}}}
    if method == "notifications/initialized":
        log("Client initialized"); return None
    if method == "tools/list":
        return {"jsonrpc":"2.0","id":msg_id,"result":{"tools":_tool_list()}}
    if method == "tools/call":
        name = params.get("name",""); args = params.get("arguments",{}) or {}
        if name not in TOOLS:
            return {"jsonrpc":"2.0","id":msg_id,"error":{"code":-32601,"message":f"Unknown tool: {name}"}}
        try:
            log(f"Calling '{name}' args={json.dumps(args)[:200]}")
            result = TOOLS[name]["fn"](**args)
            return {"jsonrpc":"2.0","id":msg_id,"result":{"content":[{"type":"text","text":json.dumps(result, indent=2, ensure_ascii=False)}]}}
        except TypeError as e:
            return {"jsonrpc":"2.0","id":msg_id,"error":{"code":-32602,"message":f"Invalid arguments: {e}"}}
        except Exception as e:
            log(f"Error in '{name}': {e}")
            return {"jsonrpc":"2.0","id":msg_id,"error":{"code":-32603,"message":str(e)[:500]}}
    if method == "resources/list":
        return {"jsonrpc":"2.0","id":msg_id,"result":{"resources":[]}}
    if method == "ping":
        return {"jsonrpc":"2.0","id":msg_id,"result":{}}
    return {"jsonrpc":"2.0","id":msg_id,"result":{}}

def _run_stdio():
    log(f"STDIO mode — {len(TOOLS)} tools — user={KAGGLE_USER}")
    print(json.dumps({"tools_loaded":len(TOOLS),"mode":"stdio","version":"3.0.0"}), file=sys.stderr, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try:
            resp = _handle_mcp_request(json.loads(line))
            if resp is not None:
                sys.stdout.write(json.dumps(resp)+"\n"); sys.stdout.flush()
        except json.JSONDecodeError:
            log(f"Invalid JSON: {line[:100]}")
        except KeyboardInterrupt:
            break

def _run_http(port: int):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    sessions = {}
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            p = urllib.parse.urlparse(self.path)
            if p.path == "/sse": self._sse()
            elif p.path == "/health": self._json({"status":"ok","tools":len(TOOLS),"version":"3.0.0"})
            elif p.path == "/tools": self._json({"tools":_tool_list()})
            else: self._json({"error":"not found"}, 404)
        def do_POST(self):
            p = urllib.parse.urlparse(self.path)
            if p.path in ("/messages","/rpc","/"):
                n = int(self.headers.get("Content-Length",0))
                body = self.rfile.read(n).decode() if n else "{}"
                try: data = json.loads(body)
                except json.JSONDecodeError: return self._json({"error":"invalid JSON"}, 400)
                self._json(_handle_mcp_request(data) or {})
            else: self._json({"error":"not found"}, 404)
        def do_OPTIONS(self):
            self.send_response(200); self._cors(); self.end_headers()
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers","Content-Type, Authorization")
        def _sse(self):
            sid = str(uuid.uuid4()); sessions[sid] = {}
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream")
            self.send_header("Cache-Control","no-cache"); self.send_header("Connection","keep-alive")
            self._cors(); self.end_headers()
            self.wfile.write(f"event: endpoint\ndata: {json.dumps({'endpoint':f'/messages?sessionId={sid}'})}\n\n".encode()); self.wfile.flush()
            self.wfile.write(f"event: message\ndata: {json.dumps({'jsonrpc':'2.0','method':'notifications/initialized','params':{}})}\n\n".encode()); self.wfile.flush()
            try:
                while sid in sessions:
                    time.sleep(1); self.wfile.write(b": heartbeat\n\n"); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass
            finally: sessions.pop(sid, None)
        def _json(self, data, code=200):
            self.send_response(code); self.send_header("Content-Type","application/json"); self._cors(); self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
        def log_message(self, fmt, *args):
            try: log(f"HTTP: {fmt % args}")
            except Exception: log(f"HTTP: {fmt} {args}")
    srv = HTTPServer(("127.0.0.1", port), H)
    log(f"HTTP http://127.0.0.1:{port} — {len(TOOLS)} tools — user={KAGGLE_USER}")
    print(f"http://127.0.0.1:{port}", flush=True)
    try: srv.serve_forever()
    except KeyboardInterrupt: srv.server_close()

def print_usage():
    print(__doc__); print(f"\nTools ({len(TOOLS)}):")
    for n in sorted(TOOLS): print(f"  {n:36s} {', '.join(TOOLS[n]['params'])}")
    sys.exit(0)

def main(argv=None):
    if argv is not None: sys.argv = [sys.argv[0], *argv]
    if "--help" in sys.argv or "-h" in sys.argv: print_usage()
    if "--list-tools" in sys.argv:
        print(json.dumps(_tool_list(), indent=2)); return
    if "--stdio" in sys.argv: _run_stdio(); return
    if any(a.startswith("--port") for a in sys.argv):
        try:
            idx = [a for a in sys.argv if a.startswith("--port")][0]
            port = int(idx.split("=")[-1] if "=" in idx else sys.argv[sys.argv.index(idx)+1])
        except (ValueError, IndexError): port = 8234
        _run_http(port); return
    if sys.stdin.isatty():
        print("Use --stdio or --port N. Default HTTP 8234.", file=sys.stderr); _run_http(8234)
    else:
        _run_stdio()

if __name__ == "__main__":
    main()
