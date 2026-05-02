from __future__ import annotations

import json
from pathlib import Path

from otto.app.system_audit import run_system_audit


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_system_audit_classifies_repo_and_vault_surfaces(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    vault = tmp_path / "vault"
    _write(repo / "otto.bat", "python scripts/manage/run_launcher.py -- %*\n")
    _write(repo / "temp_scan.ps1", "Write-Host 'scratch'\n")
    _write(repo / "src" / "otto" / "cli.py", "def main():\n    return 0\n")
    _write(repo / "src" / "app" / "cli.py", "from otto.cli import main\n")
    _write(repo / "scripts" / "manage" / "run_launcher.py", "from otto.cli import main\n")
    _write(repo / "scripts" / "vault-home-extract" / "noise.py", "raise SystemExit('ignore me')\n")
    _write(repo / "packages" / "obsidian-mcp" / "node_modules" / "ignored.js", "console.log('ignored')\n")

    _write(vault / "CLAUDE.md", "# Phase C\n")
    _write(vault / "00-Meta" / "RUNTIME_ARCHITECTURE.md", "runtime lanes\n")
    _write(
        vault / "00-Meta" / "OTTO_ARCHITECTURE.md",
        "scripts/save_research_session.py\nscripts/otto_art_heartbeat.py\n",
    )
    _write(vault / "00-Meta" / "VAULT_COHERENCE.md", "governance\n")
    _write(vault / ".Otto-Realm" / "Scripts" / "save_research_session.py", "print('ok')\n")
    _write(vault / ".Otto-Realm" / "Scripts" / "fix_remaining_broken.py", "print('v1')\n")
    _write(vault / ".Otto-Realm" / "Scripts" / "fix_remaining_broken_v2.py", "print('v2')\n")

    monkeypatch.setenv("OTTO_VAULT_PATH", str(vault))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(repo / "state"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(repo / "artifacts"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(repo / "logs"))
    monkeypatch.setenv("OTTO_BRONZE_ROOT", str(repo / "data" / "bronze"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(repo / "external" / "sqlite" / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(repo / "external" / "chroma"))

    report = run_system_audit(root=repo, scope="both", vault_root=vault, include_tests=False, include_packages=False, run_stress=False)

    by_path = {item["path"]: item for item in report["files"]}
    assert by_path["temp_scan.ps1"]["category"] == "hygiene-only cleanup"
    assert by_path["src/app/cli.py"]["category"] == "compatibility wrapper"
    assert by_path["src/otto/cli.py"]["category"] == "active"
    assert by_path[str(vault / ".Otto-Realm" / "Scripts" / "save_research_session.py")]["category"] == "governance-backed"
    assert by_path[str(vault / ".Otto-Realm" / "Scripts" / "fix_remaining_broken_v2.py")]["category"] == "obsolete candidate"
    assert "scripts/vault-home-extract/noise.py" not in by_path
    assert report["governance_docs"]["otto_architecture"] is True
    assert Path(report["outputs"]["markdown"]).exists()
    assert Path(report["outputs"]["json"]).exists()


def test_system_audit_finds_unused_imports_without_flagging_future(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    vault = tmp_path / "vault"
    _write(repo / "src" / "otto" / "unused_sample.py", "from __future__ import annotations\nimport os\nimport json\nprint(os.name)\n")
    _write(repo / "scripts" / "manage" / "dummy.py", "print('ok')\n")
    _write(vault / "CLAUDE.md", "ok\n")
    _write(vault / "00-Meta" / "RUNTIME_ARCHITECTURE.md", "ok\n")
    _write(vault / "00-Meta" / "OTTO_ARCHITECTURE.md", "ok\n")
    _write(vault / "00-Meta" / "VAULT_COHERENCE.md", "ok\n")

    monkeypatch.setenv("OTTO_VAULT_PATH", str(vault))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(repo / "state"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(repo / "artifacts"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(repo / "logs"))
    monkeypatch.setenv("OTTO_BRONZE_ROOT", str(repo / "data" / "bronze"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(repo / "external" / "sqlite" / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(repo / "external" / "chroma"))

    report = run_system_audit(root=repo, scope="repo", vault_root=vault, include_tests=False, include_packages=False, run_stress=False)
    unused = {(item["file"], item["name"]) for item in report["unused_imports"]}
    assert ("src/otto/unused_sample.py", "json") in unused
    assert ("src/otto/unused_sample.py", "annotations") not in unused
