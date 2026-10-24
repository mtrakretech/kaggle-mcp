"""Offline demonstration using synthetic metrics; no Kaggle account required.
Run from a checkout: python examples/experiment_demo.py
"""
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kaggle_experiments as e


def main():
    with tempfile.TemporaryDirectory() as folder:
        previous = os.environ.get("KAGGLE_MCP_EXPERIMENT_DB")
        os.environ["KAGGLE_MCP_EXPERIMENT_DB"] = str(Path(folder) / "demo.sqlite3")
        try:
            notebook = Path(folder) / "train.ipynb"
            notebook.write_text(json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
                {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": "print('demo only')"}]}))
            ids = []
            for name, rate, rmse in [("baseline", 0.1, 0.45), ("candidate", 0.05, 0.41)]:
                run = e.plan_experiment(str(notebook), name, datasets_json='["example/synthetic/1"]',
                    parameters_json=json.dumps({"learning_rate": rate}),
                    evaluation_protocol="SYNTHETIC DEMO: fixed split, RMSE")
                ids.append(run["experiment_id"])
                e.record_experiment_result(ids[-1], json.dumps({"rmse": rmse}), notes="Synthetic metric, not measured")
            print(json.dumps(e.compare_experiments(json.dumps(ids), "rmse"), indent=2))
        finally:
            if previous is None:
                os.environ.pop("KAGGLE_MCP_EXPERIMENT_DB", None)
            else:
                os.environ["KAGGLE_MCP_EXPERIMENT_DB"] = previous


if __name__ == "__main__":
    main()
