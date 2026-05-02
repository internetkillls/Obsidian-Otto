from __future__ import annotations

import json

from otto.openclaw_shadow import (
    build_ubuntu_live_config,
    build_ubuntu_shadow_config,
    sanitize_plugins_for_ubuntu_shadow,
    write_ubuntu_shadow_config,
)


def test_build_ubuntu_shadow_config_converts_paths_and_disables_telegram():
    config = {
        "channels": {"telegram": {"enabled": True}},
        "gateway": {"controlUi": {"allowedOrigins": ["http://localhost:18789"]}},
        "plugins": {
            "local": {"paths": [r"C:\Users\joshu\Obsidian-Otto\packages\openclaw-otto-bridge"]},
            "entries": {"obsidian-otto-bridge": {"enabled": True}},
            "load": {"paths": [r"C:\Users\joshu\Obsidian-Otto\packages\openclaw-otto-bridge"]},
            "installs": {
                "obsidian-otto-bridge": {
                    "sourcePath": r"C:\Users\joshu\Obsidian-Otto\packages\openclaw-otto-bridge",
                    "installPath": r"C:\Users\joshu\Obsidian-Otto\packages\openclaw-otto-bridge",
                }
            },
        },
        "memory": {
            "backend": "qmd",
            "qmd": {
                "command": r"C:\Users\joshu\Obsidian-Otto\scripts\shell\qmd-wsl.js",
                "paths": [
                    {
                        "name": "otto-brain",
                        "path": r"C:\Users\joshu\Josh Obsidian\.Otto-Realm\Brain",
                    }
                ],
            },
        },
    }

    shadow = build_ubuntu_shadow_config(config, port=18790)

    assert shadow["memory"]["qmd"]["command"] == "/usr/bin/qmd"
    assert shadow["memory"]["qmd"]["paths"][0]["path"] == "/mnt/c/Users/joshu/Josh Obsidian/.Otto-Realm/Brain"
    assert shadow["channels"]["telegram"]["enabled"] is False
    assert "shadowDisabled" not in shadow["channels"]["telegram"]
    assert shadow["gateway"]["port"] == 18790
    assert "http://127.0.0.1:18790" in shadow["gateway"]["controlUi"]["allowedOrigins"]
    assert "plugins" not in shadow


def test_build_ubuntu_live_config_enables_telegram_without_shadow_metadata():
    config = {
        "channels": {"telegram": {"enabled": False, "shadowDisabled": True}},
        "memory": {"qmd": {"paths": []}},
    }

    live = build_ubuntu_live_config(config, port=18790)

    assert live["channels"]["telegram"]["enabled"] is True
    assert "shadowDisabled" not in live["channels"]["telegram"]
    assert live["memory"]["qmd"]["command"] == "/usr/bin/qmd"


def test_shadow_config_removes_plugins_local():
    config = {
        "plugins": {
            "local": ["/mnt/c/Users/joshu/Obsidian-Otto/packages/openclaw-otto-bridge"],
            "entries": {},
        }
    }

    removed = sanitize_plugins_for_ubuntu_shadow(config)

    assert "plugins.local" in removed
    assert "local" not in config["plugins"]


def test_shadow_config_removes_empty_plugins_object():
    config = {"plugins": {"local": ["/some/path"]}}

    removed = sanitize_plugins_for_ubuntu_shadow(config)

    assert removed == ["plugins.local"]
    assert "plugins" not in config


def test_shadow_config_removes_stale_bridge_plugin_config():
    config = {
        "plugins": {
            "entries": {"obsidian-otto-bridge": {"enabled": True}},
            "installs": {"obsidian-otto-bridge": {"sourcePath": "/mnt/c/repo/packages/openclaw-otto-bridge"}},
            "load": {"paths": ["/mnt/c/repo/packages/openclaw-otto-bridge"]},
        }
    }

    removed = sanitize_plugins_for_ubuntu_shadow(config)

    assert removed == [
        "plugins.entries.obsidian-otto-bridge",
        "plugins.installs.obsidian-otto-bridge",
        "plugins.load.paths.openclaw-otto-bridge",
    ]
    assert "plugins" not in config


def test_write_ubuntu_shadow_config_reports_safe_summary(tmp_path):
    source = tmp_path / "openclaw.json"
    output = tmp_path / "shadow" / "openclaw.json"
    source.write_text(
        json.dumps(
            {
                "channels": {"telegram": {"enabled": True}},
                "memory": {"qmd": {"paths": [{"name": "one", "path": r"C:\Users\joshu\Vault"}]}},
            }
        ),
        encoding="utf-8",
    )

    result = write_ubuntu_shadow_config(source=source, output=output, install=True, install_path=tmp_path / ".openclaw" / "openclaw.json")

    assert result["ok"] is True
    assert result["telegram_enabled"] is False
    assert result["qmd_command"] == "/usr/bin/qmd"
    assert result["qmd_source_count"] == 1
    assert result["warnings"] == []
    assert output.exists()
    assert result["installed_path"] is not None
    assert result["installed_metadata"] is not None
    assert "removed_invalid_keys" not in json.loads(output.read_text(encoding="utf-8"))
    assert json.loads((tmp_path / ".openclaw" / "openclaw.shadow.meta.json").read_text(encoding="utf-8"))["runtime"] == "ubuntu-wsl-shadow"
