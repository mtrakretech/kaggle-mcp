import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import kaggle_experiments as e
import kaggle_mcp as m


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patch = patch.dict(os.environ, {"KAGGLE_MCP_EXPERIMENT_DB": str(self.root / "runs.sqlite3")})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.notebook = self.root / "train.ipynb"
        self.nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
            {"cell_type": "code", "source": ["print(42)"], "outputs": [], "execution_count": None, "metadata": {}}]}
        self.write()

    def write(self):
        self.notebook.write_text(json.dumps(self.nb), encoding="utf-8")

    def plan(self, **kw):
        return e.plan_experiment(str(self.notebook), "baseline", datasets_json='["owner/data/3"]',
                                 evaluation_protocol="fixed holdout v1; RMSE", **kw)["experiment_id"]

    def test_hashes_distinguish_outputs_from_code(self):
        run = self.plan()
        self.nb["cells"][0]["outputs"] = [{"output_type": "stream", "name": "stdout", "text": "42"}]
        self.write()
        verified = e.verify_experiment(run, str(self.notebook))
        self.assertFalse(verified["matches_notebook"])
        self.assertTrue(verified["matches_code"])
        self.nb["cells"][0]["source"] = "print(43)"
        self.write()
        self.assertFalse(e.verify_experiment(run, str(self.notebook))["matches_code"])

    def test_plan_never_starts_kaggle(self):
        with patch("subprocess.run", side_effect=AssertionError("must not execute")):
            run = self.plan()
            self.assertEqual(e.get_experiment(run)["observations"], [])

    def test_append_only_and_latest_comparison(self):
        a, b = self.plan(), self.plan()
        e.record_experiment_result(a, '{"rmse": 3}')
        e.record_experiment_result(a, '{"rmse": 1}')
        e.record_experiment_result(b, '{"rmse": 2}')
        self.assertEqual(len(e.get_experiment(a)["observations"]), 2)
        ids = json.dumps([a, b])
        self.assertEqual(e.compare_experiments(ids, "rmse")["ranked"][0]["experiment_id"], a)
        self.assertEqual(e.compare_experiments(ids, "rmse", "max")["ranked"][0]["experiment_id"], b)

    def test_comparison_rejects_incompatible_data(self):
        a = self.plan()
        b = e.plan_experiment(str(self.notebook), "other", evaluation_protocol="other split")["experiment_id"]
        with self.assertRaisesRegex(ValueError, "identical"):
            e.compare_experiments(json.dumps([a, b]), "rmse")

    def test_invalid_metrics_leave_history_unchanged(self):
        run = self.plan()
        for metrics in ('{}', '{"x": true}', '{"x": NaN}', '{"x": Infinity}', '[]'):
            with self.subTest(metrics=metrics), self.assertRaises(ValueError):
                e.record_experiment_result(run, metrics)
        self.assertEqual(e.get_experiment(run)["observations"], [])

    def test_unknown_experiment(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            e.record_experiment_result("missing", '{"x": 1}')

    def test_pagination(self):
        self.plan()
        self.plan()
        first = e.list_experiments(1)
        second = e.list_experiments(1, first["next_offset"])
        self.assertEqual(first["total"], 2)
        self.assertNotEqual(first["experiments"], second["experiments"])
        self.assertIsNone(second["next_offset"])

    def test_bad_notebook_and_inputs(self):
        for data in ([], {"nbformat": 3, "cells": []}, {"nbformat": 4, "cells": [None]}):
            self.notebook.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                e.inspect_notebook(str(self.notebook))
        self.write()
        for kw in ({"seed": True}, {"seed": -1}, {"parameters_json": '[]'}, {"accelerator": "magic"}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.plan(**kw)

    def test_unpinned_warning(self):
        result = e.plan_experiment(str(self.notebook), "demo", datasets_json='["owner/data"]')
        self.assertTrue(any("Unversioned" in x for x in result["warnings"]))


class ProtocolTests(unittest.TestCase):
    def call(self, name, args):
        return m._handle_mcp_request({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": name, "arguments": args}})

    def test_notifications_have_no_side_effects(self):
        with patch.dict(m.TOOLS, {"test": {"fn": lambda: self.fail("notification executed"), "params": {}, "desc": "test"}}):
            result = m._handle_mcp_request({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "test"}})
        self.assertIsNone(result)

    def test_invalid_envelopes(self):
        for value in (None, [], 3, {}, {"jsonrpc": "1", "method": "ping"}):
            self.assertEqual(m._handle_mcp_request(value)["error"]["code"], -32600)

    def test_unknown_method(self):
        self.assertEqual(m._handle_mcp_request({"jsonrpc": "2.0", "id": 1, "method": "nope"})["error"]["code"], -32601)

    def test_argument_validation_prevents_dispatch(self):
        with patch.dict(m.TOOLS["search_kernels"], {"fn": lambda **kw: self.fail("invalid input dispatched")}):
            for args in ({"query": 7}, {"query": "x", "limit": True}, {"query": "x", "sort_by": "bad"}, {"query": "x", "extra": 1}, [], None):
                self.assertEqual(self.call("search_kernels", args)["error"]["code"], -32602)

    def test_tool_errors_are_visible(self):
        with patch.dict(m.TOOLS["get_quota"], {"fn": lambda: {"error": "rate limited"}}):
            self.assertTrue(self.call("get_quota", {})["result"]["isError"])

    def test_metadata_optional_and_integer_schema(self):
        tools = {t["name"]: t for t in m._tool_list()}
        self.assertEqual(tools["update_kernel"]["inputSchema"]["required"], ["ref"])
        self.assertEqual(tools["plan_experiment"]["inputSchema"]["properties"]["seed"]["type"], "integer")
        self.assertFalse(tools["plan_experiment"]["annotations"]["openWorldHint"])
        self.assertTrue(tools["delete_dataset"]["annotations"]["destructiveHint"])

    def test_private_arguments_not_logged(self):
        with patch("sys.stderr") as err, patch.dict(m.TOOLS["kernel_status"], {"fn": lambda **kw: {"ok": True}}):
            self.call("kernel_status", {"ref": "private/sensitive-project"})
            self.assertNotIn("sensitive-project", str(err.write.call_args_list))

    def test_stdio_parse_error_recovers(self):
        import io
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO('invalid\n[]\n{"jsonrpc":"2.0","id":9,"method":"ping"}\n')), patch("sys.stdout", output):
            m._run_stdio()
        responses = [json.loads(x) for x in output.getvalue().splitlines()]
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertEqual(responses[1]["error"]["code"], -32600)
        self.assertEqual(responses[2]["id"], 9)


if __name__ == "__main__":
    unittest.main()
