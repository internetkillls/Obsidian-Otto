from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..state import OttoState, now_iso, write_json


REPO_TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".bat",
    ".ps1",
    ".sh",
}
EXCLUDED_PARTS = {
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".git",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
}
EXCLUDED_PATH_PATTERNS = (
    "scripts/vault-home-extract/",
    "packages/obsidian-mcp/node_modules/",
    "packages/obsidian-mcp/dist/",
    "packages/obsidian-scripts-mcp/node_modules/",
    "packages/obsidian-scripts-mcp/dist/",
)
CORE_PATH_HINTS = (
    "otto.bat",
    "initial.bat",
    "main.bat",
    "src/otto/",
    "scripts/manage/",
)
SCRATCH_NAME_RE = re.compile(r"^(temp_|scratch_|debug_).+", re.IGNORECASE)
VERSION_SUFFIX_RE = re.compile(r"(.+)_v\d+$", re.IGNORECASE)


@dataclass
class AuditFile:
    path: str
    abs_path: str
    surface: str
    language: str
    kind: str
    category: str = "reachable but weakly exercised"
    reasons: list[str] | None = None
    references: int = 0
    test_references: int = 0
    runtime_references: int = 0
    docs_references: int = 0
    wrapper: bool = False
    governance_lane: str | None = None
    governance_backed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "abs_path": self.abs_path,
            "surface": self.surface,
            "language": self.language,
            "kind": self.kind,
            "category": self.category,
            "reasons": self.reasons or [],
            "references": self.references,
            "test_references": self.test_references,
            "runtime_references": self.runtime_references,
            "docs_references": self.docs_references,
            "wrapper": self.wrapper,
            "governance_lane": self.governance_lane,
            "governance_backed": self.governance_backed,
        }


def _normalize_rel(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def _looks_excluded(path: Path, root: Path) -> bool:
    rel = _normalize_rel(path, root)
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return True
    if any(rel.startswith(pattern) for pattern in EXCLUDED_PATH_PATTERNS):
        return True
    if path.suffix == ".pyc":
        return True
    return False


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _language_for(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".py": "python",
        ".bat": "batch",
        ".ps1": "powershell",
        ".sh": "shell",
        ".js": "javascript",
        ".ts": "typescript",
        ".mjs": "javascript",
        ".cjs": "javascript",
    }.get(suffix, suffix.lstrip(".") or "unknown")


def _iter_repo_inventory(root: Path, include_packages: bool) -> list[AuditFile]:
    files: list[AuditFile] = []

    def add(path: Path, surface: str, kind: str) -> None:
        if not path.exists() or _looks_excluded(path, root):
            return
        files.append(
            AuditFile(
                path=_normalize_rel(path, root),
                abs_path=str(path),
                surface=surface,
                language=_language_for(path),
                kind=kind,
                reasons=[],
            )
        )

    for pattern in ("*.bat", "*.ps1", "*.sh"):
        for path in root.glob(pattern):
            add(path, "repo_control", "launcher_script")

    for folder in (root / "src" / "otto", root / "scripts" / "manage"):
        if not folder.exists():
            continue
        for path in folder.rglob("*.py"):
            add(path, "repo_control", "python_module")

    for folder in (root / "src" / "app", root / "src" / "orchestration", root / "src" / "retrieval", root / "src" / "tooling"):
        if not folder.exists():
            continue
        for path in folder.rglob("*.py"):
            add(path, "compat_shadow", "compat_wrapper")

    if include_packages:
        for package_json in (root / "packages").glob("*/package.json"):
            if _looks_excluded(package_json, root):
                continue
            package_root = package_json.parent
            try:
                payload = json.loads(_read_text(package_json))
            except json.JSONDecodeError:
                continue
            entries: set[str] = set()
            main = payload.get("main")
            if isinstance(main, str):
                entries.add(main)
            bin_cfg = payload.get("bin")
            if isinstance(bin_cfg, str):
                entries.add(bin_cfg)
            elif isinstance(bin_cfg, dict):
                entries.update(str(value) for value in bin_cfg.values())
            for rel_entry in sorted(entries):
                entry_path = (package_root / rel_entry).resolve()
                if entry_path.exists():
                    add(entry_path, "package_entrypoint", "package_entrypoint")

    return files


def _iter_vault_inventory(vault_root: Path) -> list[AuditFile]:
    script_root = vault_root / ".Otto-Realm" / "Scripts"
    files: list[AuditFile] = []
    if not script_root.exists():
        return files
    for path in script_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".py", ".ps1", ".sh"}:
            continue
        files.append(
            AuditFile(
                path=str(path),
                abs_path=str(path),
                surface="vault_runtime",
                language=_language_for(path),
                kind="vault_script",
                reasons=[],
            )
        )
    return files


def _repo_text_corpus(root: Path) -> dict[str, str]:
    corpus: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in REPO_TEXT_SUFFIXES:
            continue
        if _looks_excluded(path, root):
            continue
        corpus[_normalize_rel(path, root)] = _read_text(path)
    return corpus


def _module_name(root: Path, path: Path) -> str | None:
    try:
        rel = path.relative_to(root / "src").with_suffix("")
    except ValueError:
        return None
    return ".".join(rel.parts)


def _is_compat_wrapper(path: Path, text: str) -> bool:
    if path.suffix != ".py":
        return False
    rel = path.as_posix()
    if not any(rel.startswith(prefix) for prefix in ("src/app/", "src/orchestration/", "src/retrieval/", "src/tooling/")):
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    if len(lines) > 4:
        return False
    return any("from otto." in line for line in lines)


def _reference_counts(record: AuditFile, corpus: dict[str, str], root: Path) -> tuple[int, int, int, int]:
    basename = Path(record.path).name
    path_posix = record.path.replace("\\", "/")
    module_name = None
    try:
        module_name = _module_name(root, Path(record.abs_path))
    except Exception:
        module_name = None

    total = tests = runtime = docs = 0
    for other_path, text in corpus.items():
        if other_path == path_posix:
            continue
        hit = basename in text or path_posix in text or path_posix.replace("/", "\\") in text
        if not hit and module_name:
            hit = re.search(rf"(?<![\w.]){re.escape(module_name)}(?![\w.])", text) is not None
        if not hit:
            continue
        total += 1
        if other_path.startswith("tests/"):
            tests += 1
        elif other_path.endswith((".md", ".toml", ".yaml", ".yml", ".json")):
            docs += 1
        else:
            runtime += 1
    return total, tests, runtime, docs


def _python_import_breakdown(records: list[AuditFile], root: Path) -> dict[str, tuple[int, int, int, int]]:
    module_to_path: dict[str, str] = {}
    for record in records:
        abs_path = Path(record.abs_path)
        if abs_path.suffix != ".py":
            continue
        module_name = _module_name(root, abs_path)
        if module_name:
            module_to_path[module_name] = record.path.replace("\\", "/")

    breakdown: dict[str, list[int]] = {}
    for record in records:
        abs_path = Path(record.abs_path)
        if abs_path.suffix != ".py":
            continue
        try:
            tree = ast.parse(_read_text(abs_path))
        except SyntaxError:
            continue
        source_rel = record.path.replace("\\", "/")
        source_module = _module_name(root, abs_path) or ""
        parent_parts = source_module.split(".")[:-1]
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module == "__future__":
                    continue
                if node.level:
                    anchor = parent_parts[: len(parent_parts) - node.level + 1]
                    imported = ".".join([*anchor, *(node.module or "").split(".")]).strip(".")
                else:
                    imported = (node.module or "").strip(".")
                if imported:
                    imported_modules.add(imported)
        for module_name in imported_modules:
            target_rel = module_to_path.get(module_name)
            if not target_rel or target_rel == source_rel:
                continue
            counts = breakdown.setdefault(target_rel, [0, 0, 0, 0])
            counts[0] += 1
            if source_rel.startswith("tests/"):
                counts[1] += 1
            else:
                counts[2] += 1
    return {key: tuple(value) for key, value in breakdown.items()}


def _governance_docs(vault_root: Path) -> tuple[dict[str, str], str]:
    targets = {
        "claude": vault_root / "CLAUDE.md",
        "runtime_architecture": vault_root / "00-Meta" / "RUNTIME_ARCHITECTURE.md",
        "otto_architecture": vault_root / "00-Meta" / "OTTO_ARCHITECTURE.md",
        "vault_coherence": vault_root / "00-Meta" / "VAULT_COHERENCE.md",
    }
    docs: dict[str, str] = {}
    combined: list[str] = []
    for key, path in targets.items():
        if path.exists():
            text = _read_text(path)
            docs[key] = text
            combined.append(text)
        else:
            docs[key] = ""
    return docs, "\n".join(combined)


def _vault_lane_for(path: Path, docs_text: str) -> tuple[bool, str | None, list[str]]:
    name = path.name.lower()
    stem = path.stem.lower()
    reasons: list[str] = []

    if name in docs_text.lower():
        reasons.append("Script is named directly in governance/runtime docs.")
    if stem in {"save_research_session", "otto_art_heartbeat"}:
        return True, "research / studio / heartbeat lane", reasons or ["Canonical script called out by Otto architecture docs."]
    if stem.startswith(("scan_scarcity", "normalize_", "orphan_", "_scarcity", "b2_", "c0_", "c2_", "c3_", "c4_", "c_postprocess")):
        return True, "scarcity / normalization lane", reasons or ["Filename matches scarcity or normalization lane."]
    if stem.startswith(("context_", "audit_", "fix_", "rebuild_", "convert_", "bulk_replace")):
        return True, "context / contradiction / metadata lane", reasons or ["Filename matches context or metadata maintenance lane."]
    if stem.startswith(("_", "clean_", "cleanup_", "delete_", "phase_f_", "xraw_", "c_regen")) or stem == "draft_guard":
        return True, "maintenance helper lane", reasons or ["Filename matches maintenance helper lane."]
    if stem.startswith(("install_task", "run_agent")):
        return True, "install/task helper lane", reasons or ["Filename matches install/task helper lane."]
    if reasons:
        return True, "governance-backed runtime lane", reasons
    return False, None, reasons


def _duplicate_groups(vault_files: list[AuditFile]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for record in vault_files:
        stem = Path(record.abs_path).stem
        match = VERSION_SUFFIX_RE.match(stem)
        base = match.group(1) if match else stem
        groups.setdefault(base, []).append(record.abs_path)
    return {base: members for base, members in groups.items() if len(members) > 1}


def _ast_unused_imports(root: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    scan_roots = [root / "src" / "otto", root / "scripts" / "manage"]
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for path in scan_root.rglob("*.py"):
            if path.name == "__init__.py" or _looks_excluded(path, root):
                continue
            try:
                tree = ast.parse(_read_text(path))
            except SyntaxError:
                continue
            used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        local = alias.asname or alias.name.split(".")[0]
                        if alias.name == "__future__":
                            continue
                        if local not in used_names:
                            results.append(
                                {
                                    "file": _normalize_rel(path, root),
                                    "line": node.lineno,
                                    "name": local,
                                    "target": alias.name,
                                }
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module == "__future__":
                        continue
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        local = alias.asname or alias.name
                        if local not in used_names:
                            results.append(
                                {
                                    "file": _normalize_rel(path, root),
                                    "line": node.lineno,
                                    "name": local,
                                    "target": f"{node.module}.{alias.name}",
                                }
                            )
    return results


def _run_command(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _stress_results(root: Path, include_tests: bool) -> dict[str, Any]:
    base_temp = root / "state" / "system_audit" / "pytest"
    temp_env = os.environ.copy()
    temp_env["TMP"] = str(base_temp / "temp")
    temp_env["TEMP"] = str(base_temp / "temp")
    temp_env["TMPDIR"] = str(base_temp / "temp")
    (base_temp / "temp").mkdir(parents=True, exist_ok=True)
    results = {
        "pytest_collect": _run_command(
            [sys.executable, "-m", "pytest", "--basetemp", str(base_temp / "collect"), "--collect-only", "-q"],
            root,
            env=temp_env,
        ),
        "compileall": _run_command([sys.executable, "-m", "compileall", "-q", "src", "scripts/manage", "tests"], root),
        "import_smoke": _run_command(
            [
                sys.executable,
                "-c",
                (
                    "import importlib, sys; "
                    "sys.path.insert(0, 'src'); "
                    "mods=['otto.cli','otto.runtime','otto.openclaw_support','otto.app.launcher','otto.app.loop','otto.app.repair','otto.retrieval.memory']; "
                    "[importlib.import_module(m) for m in mods]; print('OK')"
                ),
            ],
            root,
            env=temp_env,
        ),
    }
    if include_tests:
        results["pytest"] = _run_command(
            [sys.executable, "-m", "pytest", "--basetemp", str(base_temp / "full"), "-q"],
            root,
            env=temp_env,
        )
    return results


def _categorize_records(records: list[AuditFile], duplicate_groups: dict[str, list[str]]) -> None:
    for record in records:
        record.reasons = record.reasons or []
        path_name = Path(record.abs_path).name
        if SCRATCH_NAME_RE.match(path_name):
            record.category = "hygiene-only cleanup"
            record.reasons.append("Filename matches scratch/debug temp pattern.")
            continue

        stem = Path(record.abs_path).stem
        duplicate_base = VERSION_SUFFIX_RE.match(stem)
        if record.surface == "vault_runtime" and duplicate_base:
            base = duplicate_base.group(1)
            if len(duplicate_groups.get(base, [])) > 1:
                record.category = "obsolete candidate"
                record.reasons.append(f"Part of duplicate version chain: {base}")
                continue

        if record.wrapper:
            record.category = "compatibility wrapper"
            record.reasons.append("Thin wrapper or re-export compatibility surface.")
            continue
        if record.governance_backed:
            record.category = "governance-backed"
            continue

        if record.references == 0:
            record.category = "dead-end candidate"
            record.reasons.append("No repo runtime, test, or docs references found.")
        elif record.runtime_references == 0 and record.test_references == 0:
            record.category = "reachable but weakly exercised"
            record.reasons.append("Referenced only from docs/config surfaces.")
        else:
            record.category = "active"
            if record.runtime_references:
                record.reasons.append("Has runtime/control-plane references.")
            if record.test_references:
                record.reasons.append("Covered by tests or test fixtures.")


def _markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# System Loop Audit",
        "",
        f"- timestamp: {report['ts']}",
        f"- scope: {report['scope']}",
        f"- repo_root: {report['repo_root']}",
        f"- vault_root: {report.get('vault_root') or 'not configured'}",
        "",
        "## Summary",
        "",
    ]
    for key, value in sorted(report["counts"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## High-confidence hygiene cleanup", ""])
    hygiene = [item for item in report["files"] if item["category"] == "hygiene-only cleanup"]
    lines.extend([f"- `{item['path']}` — {'; '.join(item['reasons'])}" for item in hygiene] or ["- none"])

    lines.extend(["", "## Compatibility wrappers", ""])
    wrappers = [item for item in report["files"] if item["category"] == "compatibility wrapper"]
    lines.extend([f"- `{item['path']}`" for item in wrappers] or ["- none"])

    lines.extend(["", "## Dead-end candidates", ""])
    dead = [item for item in report["files"] if item["category"] == "dead-end candidate"]
    lines.extend([f"- `{item['path']}` — {'; '.join(item['reasons'])}" for item in dead] or ["- none"])

    lines.extend(["", "## Obsolete candidates", ""])
    obsolete = [item for item in report["files"] if item["category"] == "obsolete candidate"]
    lines.extend([f"- `{item['path']}` — {'; '.join(item['reasons'])}" for item in obsolete] or ["- none"])

    lines.extend(["", "## Governance-backed vault scripts", ""])
    gov = [item for item in report["files"] if item["category"] == "governance-backed"]
    lines.extend(
        [f"- `{Path(item['path']).name}` — {item.get('governance_lane') or 'governance-backed'}" for item in gov[:20]]
        or ["- none"]
    )

    lines.extend(["", "## Unused imports (high-confidence subset)", ""])
    for item in report["unused_imports"][:25]:
        lines.append(f"- `{item['file']}:{item['line']}` — `{item['name']}` from `{item['target']}`")
    if not report["unused_imports"]:
        lines.append("- none")

    lines.extend(["", "## Stress checks", ""])
    for key, value in report["stress"].items():
        lines.append(f"- {key}: rc={value['returncode']}")
    return "\n".join(lines) + "\n"


def run_system_audit(
    *,
    root: Path | None = None,
    scope: str = "both",
    include_tests: bool = True,
    include_packages: bool = True,
    strict: bool = False,
    vault_root: Path | None = None,
    run_stress: bool = True,
) -> dict[str, Any]:
    paths = load_paths()
    root = root or paths.repo_root
    if vault_root is None:
        vault_root = paths.vault_path

    repo_files = _iter_repo_inventory(root, include_packages=include_packages) if scope in {"repo", "both"} else []
    vault_files = _iter_vault_inventory(vault_root) if vault_root and scope in {"vault", "both"} else []

    corpus = _repo_text_corpus(root)
    import_breakdown = _python_import_breakdown(repo_files, root)
    for record in repo_files:
        abs_path = Path(record.abs_path)
        record.wrapper = _is_compat_wrapper(Path(record.path), _read_text(abs_path)) if abs_path.suffix == ".py" else False
        record.references, record.test_references, record.runtime_references, record.docs_references = _reference_counts(record, corpus, root)
        import_total, import_tests, import_runtime, import_docs = import_breakdown.get(record.path.replace("\\", "/"), (0, 0, 0, 0))
        record.references += import_total
        record.test_references += import_tests
        record.runtime_references += import_runtime
        record.docs_references += import_docs

    docs_map, docs_text = _governance_docs(vault_root) if vault_root else ({}, "")
    for record in vault_files:
        backed, lane, reasons = _vault_lane_for(Path(record.abs_path), docs_text)
        record.governance_backed = backed
        record.governance_lane = lane
        record.reasons = reasons

    duplicates = _duplicate_groups(vault_files)
    all_records = repo_files + vault_files
    _categorize_records(all_records, duplicates)

    stress = _stress_results(root, include_tests=include_tests) if run_stress else {}
    unused_imports = _ast_unused_imports(root)

    counts: dict[str, int] = {}
    for record in all_records:
        counts[record.category] = counts.get(record.category, 0) + 1

    state = OttoState.load()
    state.ensure()
    ts = now_iso().replace(":", "").replace("+", "_plus_")
    json_path = state.run_journal / "system_loop_audit" / f"{ts}.json"
    markdown_path = paths.artifacts_root / "reports" / "system_loop_audit.md"
    report = {
        "ts": now_iso(),
        "scope": scope,
        "repo_root": str(root),
        "vault_root": str(vault_root) if vault_root else None,
        "governance_docs": {key: bool(value) for key, value in docs_map.items()},
        "counts": counts,
        "files": [record.to_dict() for record in sorted(all_records, key=lambda item: (item.category, item.path))],
        "duplicate_groups": duplicates,
        "unused_imports": unused_imports,
        "stress": stress,
        "outputs": {
            "json": str(json_path),
            "markdown": str(markdown_path),
        },
    }

    if strict:
        blockers = counts.get("dead-end candidate", 0) + counts.get("obsolete candidate", 0)
        report["strict_failure"] = blockers > 0
    else:
        report["strict_failure"] = False
    write_json(json_path, report)
    write_json(state.run_journal / "system_loop_audit" / "latest.json", report)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    return report
