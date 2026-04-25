from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AppPaths:
    repo_root: Path
    vault_path: Path | None
    sqlite_path: Path
    chroma_path: Path
    bronze_root: Path
    artifacts_root: Path
    logs_root: Path
    state_root: Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def load_yaml_config(name: str) -> dict[str, Any]:
    return _read_yaml(repo_root() / "config" / name)


def load_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def ensure_dirs(paths: AppPaths) -> None:
    for path in [
        paths.bronze_root,
        paths.artifacts_root,
        paths.logs_root,
        paths.state_root,
        paths.sqlite_path.parent,
        paths.chroma_path,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def load_paths() -> AppPaths:
    env = load_env_file(repo_root() / ".env")
    cfg = load_yaml_config("paths.yaml").get("paths", {})
    vault_value = os.environ.get("OTTO_VAULT_PATH") or env.get("OTTO_VAULT_PATH") or cfg.get("vault_path") or ""
    vault_path = Path(vault_value).expanduser().resolve() if vault_value else None

    sqlite_value = os.environ.get("OTTO_SQLITE_PATH") or env.get("OTTO_SQLITE_PATH") or cfg.get("sqlite_path", "external/sqlite/otto_silver.db")
    chroma_value = os.environ.get("OTTO_CHROMA_PATH") or env.get("OTTO_CHROMA_PATH") or cfg.get("chroma_path", "external/chroma_store")
    bronze_value = os.environ.get("OTTO_BRONZE_ROOT") or env.get("OTTO_BRONZE_ROOT") or cfg.get("bronze_root", "data/bronze")
    artifacts_value = os.environ.get("OTTO_ARTIFACTS_ROOT") or env.get("OTTO_ARTIFACTS_ROOT") or cfg.get("artifacts_root", "artifacts")
    logs_value = os.environ.get("OTTO_LOGS_ROOT") or env.get("OTTO_LOGS_ROOT") or cfg.get("logs_root", "logs")
    state_value = os.environ.get("OTTO_STATE_ROOT") or env.get("OTTO_STATE_ROOT") or cfg.get("state_root", "state")

    base = repo_root()
    paths = AppPaths(
        repo_root=base,
        vault_path=vault_path,
        sqlite_path=(base / sqlite_value).resolve() if not Path(sqlite_value).is_absolute() else Path(sqlite_value),
        chroma_path=(base / chroma_value).resolve() if not Path(chroma_value).is_absolute() else Path(chroma_value),
        bronze_root=(base / bronze_value).resolve() if not Path(bronze_value).is_absolute() else Path(bronze_value),
        artifacts_root=(base / artifacts_value).resolve() if not Path(artifacts_value).is_absolute() else Path(artifacts_value),
        logs_root=(base / logs_value).resolve() if not Path(logs_value).is_absolute() else Path(logs_value),
        state_root=(base / state_value).resolve() if not Path(state_value).is_absolute() else Path(state_value),
    )
    ensure_dirs(paths)
    return paths


def load_models() -> dict[str, Any]:
    return load_yaml_config("models.yaml")


def load_retrieval_config() -> dict[str, Any]:
    return load_yaml_config("retrieval.yaml")


def load_kairos_config() -> dict[str, Any]:
    return load_yaml_config("kairos.yaml")


def load_wellbeing() -> dict[str, Any]:
    return load_yaml_config("wellbeing.yaml").get("wellbeing", {})


def load_docker_config() -> dict[str, Any]:
    return load_yaml_config("docker.yaml").get("docker", {})


def load_postgres_config() -> dict[str, Any]:
    return load_yaml_config("postgres.yaml").get("postgres", {})


def write_env(updates: dict[str, str]) -> Path:
    env_file = repo_root() / ".env"
    existing = load_env_file(env_file)
    existing.update({k: str(v) for k, v in updates.items()})
    env_file.write_text("\n".join(f"{k}={v}" for k, v in sorted(existing.items())) + "\n", encoding="utf-8")
    return env_file


def save_local_bootstrap_summary(summary: dict[str, Any]) -> Path:
    out = repo_root() / "state" / "bootstrap" / "latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
