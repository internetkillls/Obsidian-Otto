from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from otto.app.status import build_status  # noqa: E402
from otto.openclaw_support import decide_openclaw_fallback  # noqa: E402
from otto.orchestration.dream import run_dream_once  # noqa: E402
from otto.orchestration.kairos import run_kairos_once  # noqa: E402
from otto.pipeline import run_pipeline  # noqa: E402
from otto.retrieval.memory import retrieve  # noqa: E402


PROMISED = [
    "scripts/shell/initial.bat",
    "scripts/shell/tui.bat",
    "scripts/shell/status.bat",
    "scripts/shell/reindex.bat",
    "scripts/shell/kairos.bat",
    "scripts/shell/dream.bat",
    "scripts/shell/start.bat",
    "scripts/shell/stop.bat",
    "scripts/shell/metadata-enrich.bat",
    "scripts/shell/docker-clean.bat",
    "scripts/manage/run_metadata_enrichment.py",
    "config/metadata_enrichment.yaml",
    "main.bat",
    "AGENTS.md",
    ".codex/config.toml",
    ".agents/skills/memory-fast/SKILL.md",
    ".agents/skills/memory-deep/SKILL.md",
    ".agents/skills/hygiene-audit/SKILL.md",
    ".agents/skills/dream-consolidation/SKILL.md",
    "docs/openclud-injection-map.md",
    "data/sample/vault/Inbox/Daily Note.md",
    "tests/test_pipeline.py",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run_checks(include_pipeline: bool = True) -> dict:
    promised = {p: (REPO_ROOT / p).exists() for p in PROMISED}
    status = build_status()
    retrieval = retrieve("policy", mode="fast")
    fallback_probe = decide_openclaw_fallback(529, emit_event=False)

    pipeline_checkpoint = {}
    if include_pipeline:
        pipeline = run_pipeline(scope=None, full=True)
        pipeline_checkpoint = pipeline["checkpoint"]
        kairos = run_kairos_once()
        dream = run_dream_once()
        kairos_summary = kairos
        dream_summary = dream
    else:
        kairos_summary = {"note": "skipped (use --pipeline to enable)"}
        dream_summary = {"note": "skipped (use --pipeline to enable)"}

    return {
        "repo_root": str(REPO_ROOT),
        "promised_files": promised,
        "all_promised_present": all(promised.values()),
        "pipeline_checkpoint": pipeline_checkpoint,
        "issues": status.get("issues", []),
        "status_summary": {
            "training_ready": status.get("training_ready"),
            "active_tasks": status.get("active_tasks"),
            "runtime_status": status.get("runtime", {}).get("status"),
            "docker_status": status.get("docker", {}).get("status"),
            "top_folder_count": len(status.get("top_folders", [])),
            "openclaw_config_sync": status.get("openclaw_config_sync"),
            "anthropic_ready": status.get("anthropic_ready"),
            "hf_fallback_ready": status.get("hf_fallback_ready"),
            "vector_enabled": status.get("vector", {}).get("enabled"),
            "vector_note": status.get("vector", {}).get("note"),
        },
        "retrieval_summary": {
            "enough_evidence": retrieval.get("enough_evidence"),
            "needs_deepening": retrieval.get("needs_deepening"),
            "note_hits": len(retrieval.get("note_hits", [])),
            "folder_hits": len(retrieval.get("folder_hits", [])),
        },
        "openclaw_summary": {
            "fallback_probe": fallback_probe,
            "health": status.get("openclaw", {}),
        },
        "kairos_summary": kairos_summary,
        "dream_summary": dream_summary,
    }


def write_reports(report: dict) -> None:
    reports = REPO_ROOT / "artifacts" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "sanity_check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Sanity Check",
        "",
        f"- all_promised_present: {report['all_promised_present']}",
        f"- training_ready: {report['status_summary']['training_ready']}",
        f"- runtime_status: {report['status_summary']['runtime_status']}",
        f"- docker_status: {report['status_summary']['docker_status']}",
        f"- top_folder_count: {report['status_summary']['top_folder_count']}",
        f"- retrieval_note_hits: {report['retrieval_summary']['note_hits']}",
        f"- openclaw_config_sync: {report['status_summary']['openclaw_config_sync']}",
        f"- anthropic_ready: {report['status_summary']['anthropic_ready']}",
        f"- hf_fallback_ready: {report['status_summary']['hf_fallback_ready']}",
        f"- vector_enabled: {report['status_summary']['vector_enabled']}",
        f"- vector_note: {report['status_summary']['vector_note']}",
        "",
        "## Missing promised files",
    ]
    missing = [p for p, ok in report["promised_files"].items() if not ok]
    lines.extend([f"- {p}" for p in missing] or ["- none"])
    lines.extend(["", "## Active tasks"])
    lines.extend([f"- {p}" for p in report["status_summary"]["active_tasks"]] or ["- none"])
    (reports / "sanity_check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_summary(report: dict) -> str:
    lines = [
        "Obsidian-Otto Sanity Check",
        "",
        f"Promised files present: {report['all_promised_present']}",
        f"Training ready: {report['status_summary']['training_ready']}",
        f"Runtime status: {report['status_summary']['runtime_status']}",
        f"Docker status: {report['status_summary']['docker_status']}",
        f"Top folder count: {report['status_summary']['top_folder_count']}",
        f"Retrieval note hits: {report['retrieval_summary']['note_hits']}",
        f"OpenClaw config sync: {report['status_summary']['openclaw_config_sync']}",
        f"HF fallback ready: {report['status_summary']['hf_fallback_ready']}",
        f"Vector enabled: {report['status_summary']['vector_enabled']}",
        "",
        "Active tasks",
    ]
    lines.extend([f"- {item}" for item in report["status_summary"]["active_tasks"]] or ["- none"])
    missing = [p for p, ok in report["promised_files"].items() if not ok]
    lines.extend(["", "Missing promised files"])
    lines.extend([f"- {item}" for item in missing] or ["- none"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Otto sanity check")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--pipeline", action="store_true", help="Run full pipeline (slow, LLM calls). Default: fast checks only.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = run_checks(include_pipeline=args.pipeline)
    if args.write_report:
        write_reports(report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_summary(report), end="")
    has_issues = bool(report.get("issues")) or not report.get("all_promised_present")
    return 1 if has_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
