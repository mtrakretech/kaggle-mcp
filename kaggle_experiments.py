"""Local experiment provenance. No network access, code execution or credentials."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

MAX_NOTEBOOK_BYTES = 20 * 1024 * 1024
REF = re.compile(r"^[A-Za-z0-9_-]+/[A-Za-z0-9_-]+$")
DATASET = re.compile(r"^[A-Za-z0-9_-]+/[A-Za-z0-9_-]+(?:/[1-9][0-9]*)?$")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


@contextmanager
def _db():
    path = Path(os.environ.get("KAGGLE_MCP_EXPERIMENT_DB", str(Path.home() / ".kaggle-mcp" / "experiments.sqlite3"))).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create with private permissions, including on first open, where supported.
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS experiments (
        id TEXT PRIMARY KEY, created_at TEXT NOT NULL, plan TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS observations (
        id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(id),
        created_at TEXT NOT NULL, payload TEXT NOT NULL);
    ''')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def inspect_notebook(path):
    """Validate notebook structure; hash full bytes and code separately. Never execute."""
    p = Path(path).expanduser()
    if p.suffix.lower() != ".ipynb" or not p.is_file():
        raise ValueError("path must name an existing .ipynb file")
    with p.open("rb") as source:
        raw = source.read(MAX_NOTEBOOK_BYTES + 1)
    if len(raw) > MAX_NOTEBOOK_BYTES:
        raise ValueError("notebook exceeds 20 MiB limit")
    nb = json.loads(raw)
    if not isinstance(nb, dict) or nb.get("nbformat") != 4 or not isinstance(nb.get("cells"), list):
        raise ValueError("expected a version 4 notebook with a cells array")
    code, outputs, executed = [], 0, 0
    for cell in nb["cells"]:
        if not isinstance(cell, dict) or cell.get("cell_type") not in ("code", "markdown", "raw"):
            raise ValueError("invalid notebook cell")
        src = cell.get("source", "")
        if isinstance(src, list) and all(isinstance(s, str) for s in src):
            src = "".join(src)
        if not isinstance(src, str):
            raise ValueError("cell source must be text or an array of text")
        if cell["cell_type"] == "code":
            code.append(src)
            outputs += bool(cell.get("outputs"))
            executed += cell.get("execution_count") is not None
    warnings = []
    if not code:
        warnings.append("Notebook contains no code cells.")
    if outputs:
        warnings.append("Saved outputs may contain private data; review before publishing.")
    if executed:
        warnings.append("Execution counts do not prove a clean, top-to-bottom run.")
    return {"notebook_sha256": hashlib.sha256(raw).hexdigest(),
            "code_sha256": hashlib.sha256(_json(code).encode()).hexdigest(),
            "size_bytes": len(raw), "code_cells": len(code), "warnings": warnings}


def plan_experiment(path, name, datasets_json="[]", parameters_json="{}", seed=42,
                    accelerator="cpu", internet=False, evaluation_protocol=""):
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError("name must contain 1–200 characters")
    if type(seed) is not int or seed < 0 or seed > 2**32 - 1:
        raise ValueError("seed must be an integer between 0 and 4294967295")
    if accelerator not in ("cpu", "gpu", "tpu") or type(internet) is not bool:
        raise ValueError("invalid accelerator or internet flag")
    datasets = json.loads(datasets_json)
    parameters = json.loads(parameters_json)
    if not isinstance(datasets, list) or len(datasets) > 100 or not all(isinstance(x, str) and DATASET.fullmatch(x) for x in datasets):
        raise ValueError("datasets_json must be an array of owner/slug or owner/slug/version references")
    if not isinstance(parameters, dict) or len(_json(parameters)) > 65536:
        raise ValueError("parameters_json must be a JSON object of at most 64 KiB")
    if not isinstance(evaluation_protocol, str) or len(evaluation_protocol) > 4000:
        raise ValueError("evaluation_protocol must be text of at most 4000 characters")
    preflight = inspect_notebook(path)
    warnings = preflight.pop("warnings")
    if any(len(x.split("/")) != 3 for x in datasets):
        warnings.append("Unversioned datasets may change; pin versions for reproducibility.")
    if not evaluation_protocol.strip():
        warnings.append("Define a common validation split and metric before comparing results.")
    if internet:
        warnings.append("Internet dependencies may change; pin package versions and external inputs.")
    plan = {"name": name.strip(), **preflight, "datasets": sorted(set(datasets)),
            "parameters": parameters, "seed": seed, "accelerator": accelerator,
            "internet": internet, "evaluation_protocol": evaluation_protocol.strip()}
    fingerprint = hashlib.sha256(_json(plan).encode()).hexdigest()
    experiment_id = uuid.uuid4().hex
    with _db() as db:
        db.execute("INSERT INTO experiments VALUES (?, ?, ?)", (experiment_id, _now(), _json(plan)))
    return {"experiment_id": experiment_id, "plan_sha256": fingerprint, "plan": plan,
            "warnings": warnings, "status": "planned", "remote_action": "none",
            "note": "Records intent only; seed/settings are not injected into notebook code. No notebook is uploaded or executed."}


def _get(db, experiment_id):
    row = db.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()
    if row is None:
        raise ValueError("unknown experiment_id")
    return {"experiment_id": row["id"], "created_at": row["created_at"], "plan": json.loads(row["plan"])}


def get_experiment(experiment_id):
    with _db() as db:
        experiment = _get(db, experiment_id)
        experiment["observations"] = [{"observation_id": row["id"], "created_at": row["created_at"], **json.loads(row["payload"])}
            for row in db.execute("SELECT * FROM observations WHERE experiment_id=? ORDER BY rowid", (experiment_id,))]
    return experiment


def verify_experiment(experiment_id, path):
    experiment = get_experiment(experiment_id)
    current = inspect_notebook(path)
    return {"experiment_id": experiment_id, "matches_notebook": current["notebook_sha256"] == experiment["plan"]["notebook_sha256"],
            "matches_code": current["code_sha256"] == experiment["plan"]["code_sha256"], "current": current}


def record_experiment_result(experiment_id, metrics_json, kernel_ref="", notes=""):
    metrics = json.loads(metrics_json)
    if not isinstance(metrics, dict) or not metrics or len(metrics) > 100:
        raise ValueError("metrics_json must be a nonempty object with at most 100 metrics")
    if not all(isinstance(k, str) and 0 < len(k) <= 100 and type(v) in (int, float) and math.isfinite(v) for k, v in metrics.items()):
        raise ValueError("metric names must be 1–100 characters and values must be finite numbers")
    if kernel_ref and not REF.fullmatch(kernel_ref):
        raise ValueError("kernel_ref must be owner/slug")
    if not isinstance(notes, str) or len(notes) > 4000:
        raise ValueError("notes must contain at most 4000 characters")
    observation_id = uuid.uuid4().hex
    payload = {"metrics": metrics, "kernel_ref": kernel_ref, "notes": notes, "source": "user_reported"}
    with _db() as db:
        _get(db, experiment_id)
        db.execute("INSERT INTO observations VALUES (?, ?, ?, ?)", (observation_id, experiment_id, _now(), _json(payload)))
    return {"observation_id": observation_id, "experiment_id": experiment_id, **payload}


def list_experiments(limit=20, offset=0):
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise ValueError("limit must be 1–100 and offset must be nonnegative integers")
    with _db() as db:
        total = db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
        rows = db.execute("SELECT * FROM experiments ORDER BY rowid DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return {"total": total, "experiments": [{"experiment_id": r["id"], "created_at": r["created_at"], "plan": json.loads(r["plan"])} for r in rows],
            "next_offset": offset + limit if offset + limit < total else None}


def compare_experiments(experiment_ids_json, metric, mode="min"):
    ids = json.loads(experiment_ids_json)
    if not isinstance(ids, list) or not 2 <= len(ids) <= 100 or not all(isinstance(x, str) for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("provide 2–100 distinct experiment IDs")
    if mode not in ("min", "max") or not isinstance(metric, str) or not metric:
        raise ValueError("provide metric and mode=min or max")
    experiments = [get_experiment(x) for x in ids]
    # Comparing different splits/data is misleading, even if the metric has the same name.
    signature = lambda e: (e["plan"]["datasets"], e["plan"]["evaluation_protocol"])
    if not experiments[0]["plan"]["evaluation_protocol"] or any(signature(e) != signature(experiments[0]) for e in experiments[1:]):
        raise ValueError("comparison requires identical datasets and a nonempty, identical evaluation_protocol")
    ranked, missing = [], []
    for e in experiments:
        latest = e["observations"][-1] if e["observations"] else None
        if latest is None or metric not in latest["metrics"]:
            missing.append(e["experiment_id"])
            continue
        ranked.append({"experiment_id": e["experiment_id"], "name": e["plan"]["name"],
                       "value": latest["metrics"][metric], "observation_id": latest["observation_id"]})
    ranked.sort(key=lambda r: r["value"], reverse=mode == "max")
    return {"metric": metric, "mode": mode, "ranked": ranked, "missing_metric": missing,
            "basis": "latest user-reported observation per experiment; no independent verification",
            "warning": "Matching declared evaluation protocols cannot prove absence of leakage or statistical significance."}
