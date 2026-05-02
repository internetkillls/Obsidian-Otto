from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from otto.config import load_env_file, load_yaml_config, save_local_bootstrap_summary, write_env  # noqa: E402
from otto.openclaw_support import sync_openclaw_config  # noqa: E402
from otto.pipeline import run_pipeline  # noqa: E402


def prompt_bool(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    try:
        answer = input(prompt + suffix).strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in {"y", "yes", "1", "true"}


def choose_vault(user_value: str | None) -> str:
    normalized = (user_value or "").strip()
    if normalized in {'""', "''"}:
        normalized = ""
    if normalized:
        return normalized
    env = load_env_file(REPO_ROOT / ".env")
    configured = (
        env.get("OTTO_VAULT_PATH")
        or (load_yaml_config("paths.yaml").get("paths") or {}).get("vault_path")
        or ""
    ).strip()
    if configured:
        return configured
    sample = str((REPO_ROOT / "data" / "sample" / "vault").resolve())
    if not sys.stdin.isatty():
        return sample
    print("Enter your Obsidian vault path.")
    print("Press Enter to use the bundled sample vault:")
    print(sample)
    try:
        raw = input("Vault path: ").strip()
    except EOFError:
        return sample
    return raw or sample


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Obsidian-Otto")
    parser.add_argument("--vault-path", default=None)
    parser.add_argument("--docker", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args(argv)

    vault = choose_vault(args.vault_path)
    docker_enabled = args.docker
    if not args.non_interactive and not args.docker and sys.stdin.isatty():
        docker_enabled = prompt_bool("Enable optional Docker helpers?", default=False)

    env_path = write_env({
        "OTTO_VAULT_PATH": vault,
        "OTTO_DOCKER_ENABLED": "1" if docker_enabled else "0",
        "OTTO_SQLITE_PATH": "external/sqlite/otto_silver.db",
        "OTTO_CHROMA_PATH": "external/chroma_store",
    })
    sync_result = sync_openclaw_config()

    result = run_pipeline(scope=None, full=True)
    summary = {
        "vault_path": vault,
        "docker_enabled": docker_enabled,
        "env_file": str(env_path),
        "openclaw_config_sync": sync_result["openclaw_config_sync"],
        "hf_fallback_ready": sync_result["hf_fallback_ready"],
        "training_ready": result["checkpoint"]["training_ready"],
        "gold_top_folders": result["checkpoint"]["gold_top_folders"],
    }
    save_local_bootstrap_summary(summary)
    print("Bootstrap complete.")
    print(f"Vault: {vault}")
    print(f"Docker helpers: {docker_enabled}")
    print("Next: run tui.bat or status.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
