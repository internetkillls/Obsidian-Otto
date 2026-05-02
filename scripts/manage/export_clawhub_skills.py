from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / ".agents" / "skills"
DEFAULT_CONFIG = REPO_ROOT / "config" / "clawhub_export.json"
DEFAULT_OUT = REPO_ROOT / "artifacts" / "clawhub_export"
PORTABLE_DIR_NAMES = ("assets", "scripts", "references")


@dataclass(frozen=True)
class ExportItem:
    name: str
    source_dir: Path
    output_dir: Path
    private: bool


def _load_config(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Config must be JSON object")
    return payload


def _copy_tree_if_exists(source: Path, dest: Path) -> None:
    if not source.exists():
        return
    if source.is_dir():
        shutil.copytree(source, dest, dirs_exist_ok=True)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)


def _build_items(config: dict, out_root: Path) -> list[ExportItem]:
    publishable = set(config.get("publishable_skills") or [])
    private_skills = set(config.get("private_skills") or [])
    items: list[ExportItem] = []
    for skill_dir in sorted(SKILLS_ROOT.iterdir()):
        if not skill_dir.is_dir():
            continue
        name = skill_dir.name
        if publishable and name not in publishable and name not in private_skills:
            continue
        items.append(
            ExportItem(
                name=name,
                source_dir=skill_dir,
                output_dir=out_root / name,
                private=name in private_skills,
            )
        )
    return items


def export_skills(config_path: Path, out_root: Path) -> dict:
    config = _load_config(config_path)
    items = _build_items(config, out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    exported: list[dict] = []
    for item in items:
        if item.output_dir.exists():
            shutil.rmtree(item.output_dir)
        item.output_dir.mkdir(parents=True, exist_ok=True)

        skill_file = item.source_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        shutil.copy2(skill_file, item.output_dir / "SKILL.md")

        for name in PORTABLE_DIR_NAMES:
            _copy_tree_if_exists(item.source_dir / name, item.output_dir / name)

        meta = {
            "slug": item.name,
            "version": config.get("version", "1.0.0"),
            "source": "obsidian-otto",
            "private": item.private,
        }
        (item.output_dir / "_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        exported.append(
            {
                "name": item.name,
                "private": item.private,
                "path": str(item.output_dir),
            }
        )

    summary = {
        "config": str(config_path),
        "output_root": str(out_root),
        "count": len(exported),
        "skills": exported,
    }
    summary_path = out_root / "export_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Obsidian-Otto skills to ClawHub-ready folders")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    summary = export_skills(config_path=args.config, out_root=args.out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
