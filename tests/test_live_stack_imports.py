"""Prove deterministic event ingestion does not import the AI agent stack."""
from __future__ import annotations

import subprocess
import sys
import unittest


class LiveStackImportBoundaryTests(unittest.TestCase):
    def test_import_and_cli_help_work_without_agent_dependencies(self):
        probe = """
import builtins
import sys
real_import = builtins.__import__
def no_ai_import(name, *args, **kwargs):
    if name == 'rapidfuzz' or name.startswith('rapidfuzz.') or name == 'openai' or name.startswith('openai.'):
        raise ModuleNotFoundError('AI dependency deliberately blocked: ' + name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = no_ai_import
from dependency.automation.orchestrator import process_pending_events
from scripts.run_live_stack import run_cycle, main
assert 'dependency.agents.orchestrator' not in sys.modules
assert 'dependency.agents.tools' not in sys.modules
assert callable(process_pending_events) and callable(run_cycle)
sys.argv = ['python -m scripts.run_live_stack', '--help']
try:
    main()
except SystemExit as exc:
    assert exc.code == 0, exc.code
"""
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--watch", result.stdout)


if __name__ == "__main__":
    unittest.main()
