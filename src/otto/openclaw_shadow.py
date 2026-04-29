from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .config import repo_root
from .path_compat import windows_path_to_wsl

DEFAULT_SHADOW_PORT = 18790


def default_shadow_install_path() -> Path:
    wsl_user_home = Path("/home/joshu")
    if wsl_user_home.exists():
        return wsl_user_home / ".openclaw" / "openclaw.json"
    return Path.home() / ".openclaw" / "openclaw.json"


def _convert_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _convert_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_convert_value(item) for item in value]
    if isinstance(value, str):
        return windows_path_to_wsl(value)
    return value


def sanitize_plugins_for_ubuntu_shadow(config: dict[str, Any]) -> list[str]:
    """Remove config keys that are not valid in current OpenClaw schema.

    The shadow generator must not invent OpenClaw config keys. Local/plugin
    linking should happen through `openclaw plugins install`, not by writing
    guessed plugin keys into openclaw.json.
    """
    removed: list[str] = []

    plugins = config.get("plugins")
    if not isinstance(plugins, dict):
        return removed

    if "local" in plugins:
        plugins.pop("local", None)
        removed.append("plugins.local")

    entries = plugins.get("entries")
    if isinstance(entries, dict) and "obsidian-otto-bridge" in entries:
        entries.pop("obsidian-otto-bridge", None)
        removed.append("plugins.entries.obsidian-otto-bridge")
        if not entries:
            plugins.pop("entries", None)

    installs = plugins.get("installs")
    if isinstance(installs, dict) and "obsidian-otto-bridge" in installs:
        installs.pop("obsidian-otto-bridge", None)
        removed.append("plugins.installs.obsidian-otto-bridge")
        if not installs:
            plugins.pop("installs", None)

    load = plugins.get("load")
    if isinstance(load, dict):
        paths = load.get("paths")
        if isinstance(paths, list):
            filtered = [
                item
                for item in paths
                if "openclaw-otto-bridge" not in str(item).replace("\\", "/")
            ]
            if len(filtered) != len(paths):
                removed.append("plugins.load.paths.openclaw-otto-bridge")
            if filtered:
                load["paths"] = filtered
            else:
                load.pop("paths", None)
        if not load:
            plugins.pop("load", None)

    if not plugins:
        config.pop("plugins", None)

    return removed


def _build_ubuntu_runtime_config_with_removed(
    config: dict[str, Any],
    *,
    port: int = DEFAULT_SHADOW_PORT,
    telegram_enabled: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    shadow = _convert_value(copy.deepcopy(config))

    memory = shadow.setdefault("memory", {})
    qmd = memory.setdefault("qmd", {})
    memory["backend"] = "qmd"
    qmd["command"] = "/usr/bin/qmd"

    channels = shadow.setdefault("channels", {})
    telegram = channels.setdefault("telegram", {})
    telegram["enabled"] = telegram_enabled
    telegram.pop("shadowDisabled", None)

    gateway = shadow.setdefault("gateway", {})
    gateway["port"] = port
    control_ui = gateway.setdefault("controlUi", {})
    origins = control_ui.setdefault("allowedOrigins", [])
    for origin in [f"http://localhost:{port}", f"http://127.0.0.1:{port}"]:
        if origin not in origins:
            origins.append(origin)

    removed_invalid_keys = sanitize_plugins_for_ubuntu_shadow(shadow)
    return shadow, removed_invalid_keys


def build_ubuntu_shadow_config(config: dict[str, Any], *, port: int = DEFAULT_SHADOW_PORT) -> dict[str, Any]:
    shadow, _removed_invalid_keys = _build_ubuntu_runtime_config_with_removed(
        config,
        port=port,
        telegram_enabled=False,
    )
    return shadow


def build_ubuntu_live_config(config: dict[str, Any], *, port: int = DEFAULT_SHADOW_PORT) -> dict[str, Any]:
    live, _removed_invalid_keys = _build_ubuntu_runtime_config_with_removed(
        config,
        port=port,
        telegram_enabled=True,
    )
    return live


def build_ubuntu_shadow_metadata(
    *,
    source: Path,
    output: Path,
    install_path: Path | None,
    port: int,
    removed_invalid_keys: list[str],
) -> dict[str, Any]:
    return {
        "runtime": "ubuntu-wsl-shadow",
        "source": str(source),
        "output": str(output),
        "install_path": str(install_path) if install_path else None,
        "telegram": "disabled",
        "gateway_port": port,
        "removed_invalid_keys": removed_invalid_keys,
        "bridge_linking": {
            "mode": "manual-cli",
            "command": "cp -R /mnt/c/Users/joshu/Obsidian-Otto/packages/openclaw-otto-bridge /home/joshu/.openclaw/plugins-local/obsidian-otto-bridge && openclaw plugins install -l /home/joshu/.openclaw/plugins-local/obsidian-otto-bridge",
            "note": "Do not keep the bridge path in openclaw.json; mirror the plugin into a WSL-local path before linking because /mnt/c paths may be world-writable and blocked by OpenClaw.",
        },
    }


def _path_is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def write_ubuntu_shadow_config(
    *,
    source: Path | None = None,
    output: Path | None = None,
    port: int = DEFAULT_SHADOW_PORT,
    install: bool = False,
    install_path: Path | None = None,
) -> dict[str, Any]:
    source = source or repo_root() / ".openclaw" / "openclaw.json"
    output = output or repo_root() / "state" / "openclaw" / "ubuntu-shadow" / "openclaw.json"
    config = json.loads(source.read_text(encoding="utf-8"))
    shadow, removed_invalid_keys = _build_ubuntu_runtime_config_with_removed(
        config,
        port=port,
        telegram_enabled=False,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(shadow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    installed_path: Path | None = None
    metadata_path = output.with_suffix(".meta.json")
    install_metadata_path: Path | None = None
    warnings: list[str] = []
    if install:
        installed_path = install_path or default_shadow_install_path()
        if not _path_is_under(installed_path, Path.home()):
            warnings.append(f"install_path outside current HOME: {installed_path}")
        installed_path.parent.mkdir(parents=True, exist_ok=True)
        installed_path.write_text(json.dumps(shadow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        install_metadata_path = installed_path.with_name("openclaw.shadow.meta.json")
    metadata = build_ubuntu_shadow_metadata(
        source=source,
        output=output,
        install_path=installed_path,
        port=port,
        removed_invalid_keys=removed_invalid_keys,
    )
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if install_metadata_path is not None:
        install_metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    qmd_paths = shadow.get("memory", {}).get("qmd", {}).get("paths", [])
    return {
        "ok": True,
        "source": str(source),
        "output": str(output),
        "metadata": str(metadata_path),
        "installed_path": str(installed_path) if installed_path else None,
        "installed_metadata": str(install_metadata_path) if install_metadata_path else None,
        "port": port,
        "qmd_command": shadow.get("memory", {}).get("qmd", {}).get("command"),
        "telegram_enabled": shadow.get("channels", {}).get("telegram", {}).get("enabled"),
        "qmd_source_count": len(qmd_paths) if isinstance(qmd_paths, list) else 0,
        "removed_invalid_keys": removed_invalid_keys,
        "warnings": warnings,
    }
