"""Agent runtime must handle invalid model tool arguments without calling tools."""
from __future__ import annotations

import os
import sys
import types
import unittest
from unittest.mock import patch

from dependency.agents.runtime import run_agent


class FakeResponse:
    def __init__(self, output, text="", identifier="fake-response"):
        self.output = output
        self.output_text = text
        self.id = identifier


class FakeClient:
    def __init__(self, responses):
        self.responses = types.SimpleNamespace(create=self.create)
        self.pending = iter(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return next(self.pending)


class RuntimeArgumentTests(unittest.TestCase):
    def _run(self, arguments):
        calls = [types.SimpleNamespace(
            type="function_call", name="safe_tool", call_id="call-1",
            arguments=arguments,
        )]
        client = FakeClient([FakeResponse(calls), FakeResponse([], "Recovered")])
        fake_openai = types.SimpleNamespace(OpenAI=lambda: client)
        spec = types.SimpleNamespace(
            name="Test", role="test", instructions="test",
            tool_names=("safe_tool",),
        )
        with patch.dict(sys.modules, {"openai": fake_openai}), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "unit-test-key"}), \
             patch("dependency.agents.runtime.dispatch_tool") as dispatch, \
             patch("dependency.agents.runtime._tool_subset", return_value=[]):
            result = run_agent(spec=spec, task="test", model="test-model")
            dispatch.assert_not_called()
        self.assertEqual(result["output_text"], "Recovered")
        self.assertEqual(result["tool_rounds"], 1)
        self.assertEqual(result["tool_trace"][0]["result"]["error"], "INVALID_TOOL_ARGUMENTS")
        self.assertEqual(
            client.requests[1]["input"][0]["type"],
            "function_call_output",
        )

    def test_malformed_json(self):
        self._run("{not valid json")

    def test_non_object_json(self):
        self._run("[1, 2]")

    def test_non_mapping_arguments(self):
        self._run(42)


if __name__ == "__main__":
    unittest.main()
