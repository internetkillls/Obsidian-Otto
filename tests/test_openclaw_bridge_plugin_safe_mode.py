from __future__ import annotations

from pathlib import Path


def test_openclaw_bridge_plugin_avoids_child_process_execution():
    plugin_path = Path("packages/openclaw-otto-bridge/index.js")
    source = plugin_path.read_text(encoding="utf-8")

    assert "node:child_process" not in source
    assert "spawn(" not in source
    assert '"execution_mode": "manual_required"' in source or 'execution_mode: "manual_required"' in source
