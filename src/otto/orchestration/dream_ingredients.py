from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..state import now_iso, read_json, write_json


@dataclass
class DreamMaterial:
    area: str
    source_path: str
    mtime: str
    content_excerpt: str
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.8

    def as_corpus_line(self) -> str:
        return (
            f"[{self.area}] [{self.source_path}] "
            f"(conf={self.confidence:.1f}) {self.content_excerpt[:200]}"
        )


@dataclass
class AreaState:
    mtime: str
    note_count: int


@dataclass
class VaultIngestionManifest:
    version: int = 1
    last_dream_ts: str = ""
    areas: dict[str, AreaState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "last_dream_ts": self.last_dream_ts,
            "areas": {
                name: {"mtime": s.mtime, "note_count": s.note_count}
                for name, s in self.areas.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VaultIngestionManifest:
        areas: dict[str, AreaState] = {}
        for name, v in data.get("areas", {}).items():
            areas[name] = AreaState(
                mtime=v.get("mtime", ""),
                note_count=v.get("note_count", 0),
            )
        return cls(
            version=data.get("version", 1),
            last_dream_ts=data.get("last_dream_ts", ""),
            areas=areas,
        )


class VaultDreamSource:
    AREAS = [
        ("brain", ".Otto-Realm/Brain"),
        ("heartbeats", ".Otto-Realm/Heartbeats"),
        ("memory-tiers", ".Otto-Realm/Memory-Tiers"),
        ("rituals", ".Otto-Realm/Rituals"),
        ("predictions", ".Otto-Realm/Predictions"),
    ]
    MAX_EXCERPT = 500
    MANIFEST_NAME = "vault_ingestion.json"

    def __init__(self, vault_path: Path | None = None):
        paths = load_paths()
        self.vault_path = vault_path or paths.vault_path
        if self.vault_path is None:
            raise RuntimeError("Vault path not configured.")
        self.manifest_path = paths.state_root / "dream" / self.MANIFEST_NAME

    def _load_manifest(self) -> VaultIngestionManifest:
        data = read_json(self.manifest_path, None)
        if data is None:
            return VaultIngestionManifest()
        try:
            return VaultIngestionManifest.from_dict(data)
        except Exception:
            return VaultIngestionManifest()

    def _save_manifest(self, manifest: VaultIngestionManifest) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(self.manifest_path, manifest.to_dict())

    def _read_frontmatter(
        self, text: str
    ) -> tuple[dict[str, str], str]:
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if not fm_match:
            return {}, text
        fm: dict[str, str] = {}
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
        body = text[fm_match.end():].strip()
        return fm, body

    def _strip_diary_headers(self, body: str) -> str:
        lines = body.splitlines()
        cleaned = []
        skip_next = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("*") and stripped.endswith("*"):
                continue
            if re.match(r"^\[openclaw:dreaming:", stripped, re.IGNORECASE):
                continue
            cleaned.append(line)
        return "\n".join(cleaned).strip()

    def _scan_area(self, area_name: str, area_rel: str) -> list[DreamMaterial]:
        area_dir = self.vault_path / area_rel
        if not area_dir.exists():
            return []

        materials: list[DreamMaterial] = []
        try:
            for md_file in sorted(area_dir.rglob("*.md")):
                try:
                    text = md_file.read_text(encoding="utf-8", errors="replace")
                    fm, body = self._read_frontmatter(text)

                    body = self._strip_diary_headers(body)
                    if not body:
                        continue

                    excerpt = body[: self.MAX_EXCERPT]
                    if len(body) > self.MAX_EXCERPT:
                        excerpt += "..."

                    mtime_iso = now_iso()
                    try:
                        mtime_epoch = md_file.stat().st_mtime
                        from datetime import datetime, timezone

                        mtime_iso = (
                            datetime.fromtimestamp(mtime_epoch, tz=timezone.utc)
                            .astimezone()
                            .isoformat(timespec="seconds")
                        )
                    except Exception:
                        pass

                    tags = [t.strip() for t in fm.get("tags", "").split(",") if t.strip()]
                    if not tags and area_name == "memory-tiers":
                        tier_tag = fm.get("tier", "")
                        if tier_tag:
                            tags = [tier_tag]

                    materials.append(
                        DreamMaterial(
                            area=area_name,
                            source_path=str(md_file.relative_to(self.vault_path)),
                            mtime=mtime_iso,
                            content_excerpt=excerpt,
                            tags=tags,
                            confidence=0.8,
                        )
                    )
                except Exception:
                    continue
        except Exception:
            pass
        return materials

    def ingest(self) -> list[DreamMaterial]:
        manifest = self._load_manifest()
        all_materials: list[DreamMaterial] = []
        new_areas: dict[str, AreaState] = {}

        for area_name, area_rel in self.AREAS:
            materials = self._scan_area(area_name, area_rel)
            all_materials.extend(materials)

            latest_mtime = ""
            if materials:
                latest_mtime = max(m.mtime for m in materials)
            elif area_name in manifest.areas:
                latest_mtime = manifest.areas[area_name].mtime

            new_areas[area_name] = AreaState(
                mtime=latest_mtime,
                note_count=len(materials),
            )

        new_manifest = VaultIngestionManifest(
            version=1,
            last_dream_ts=now_iso(),
            areas=new_areas,
        )
        self._save_manifest(new_manifest)
        return all_materials

    def ingest_since_last(self) -> list[DreamMaterial]:
        manifest = self._load_manifest()
        all_materials: list[DreamMaterial] = []

        for area_name, area_rel in self.AREAS:
            if area_name not in manifest.areas:
                materials = self._scan_area(area_name, area_rel)
                all_materials.extend(materials)
                continue

            last_mtime_str = manifest.areas[area_name].mtime
            if not last_mtime_str:
                materials = self._scan_area(area_name, area_rel)
                all_materials.extend(materials)
                continue

            area_dir = self.vault_path / area_rel
            if not area_dir.exists():
                continue

            for md_file in area_dir.rglob("*.md"):
                try:
                    mtime_epoch = md_file.stat().st_mtime
                    from datetime import datetime, timezone

                    file_mtime = (
                        datetime.fromtimestamp(mtime_epoch, tz=timezone.utc)
                        .astimezone()
                        .isoformat(timespec="seconds")
                    )
                    if file_mtime <= last_mtime_str:
                        continue
                except Exception:
                    pass

                try:
                    text = md_file.read_text(encoding="utf-8", errors="replace")
                    fm, body = self._read_frontmatter(text)
                    body = self._strip_diary_headers(body)
                    if not body:
                        continue

                    excerpt = body[: self.MAX_EXCERPT]
                    if len(body) > self.MAX_EXCERPT:
                        excerpt += "..."

                    mtime_iso = file_mtime if "file_mtime" in dir() else now_iso()
                    tags = [
                        t.strip() for t in fm.get("tags", "").split(",") if t.strip()
                    ]

                    all_materials.append(
                        DreamMaterial(
                            area=area_name,
                            source_path=str(md_file.relative_to(self.vault_path)),
                            mtime=mtime_iso,
                            content_excerpt=excerpt,
                            tags=tags,
                            confidence=0.8,
                        )
                    )
                except Exception:
                    continue

        # save updated manifest with latest mtime per area
        manifest = self._load_manifest()
        for area_name, area_rel in self.AREAS:
            area_dir = self.vault_path / area_rel
            if not area_dir.exists():
                continue
            latest = ""
            count = 0
            for mf in area_dir.rglob("*.md"):
                try:
                    from datetime import datetime, timezone
                    mtime_epoch = mf.stat().st_mtime
                    ftime = datetime.fromtimestamp(mtime_epoch, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
                    if not latest or ftime > latest:
                        latest = ftime
                    count += 1
                except Exception:
                    count += 1
            manifest.areas[area_name] = AreaState(mtime=latest, note_count=count)
        manifest.last_dream_ts = now_iso()
        self._save_manifest(manifest)
        return all_materials

    def append_to_dreams_corpus(self, materials: list[DreamMaterial]) -> Path:
        from ..config import load_paths

        paths = load_paths()
        corpus_dir = paths.repo_root / "memory" / ".dreams" / "session-corpus"
        corpus_dir.mkdir(parents=True, exist_ok=True)

        from ..state import now_iso

        ts_stamp = now_iso()[:10]
        existing = list(corpus_dir.glob(f"*-vault-*.txt"))
        next_num = len(existing) + 1
        corpus_file = corpus_dir / f"2026-{ts_stamp[5:]}-vault-{next_num:02d}.txt"

        lines = [
            f"# Vault Dream Materials — {now_iso()}",
            "",
        ]
        for m in materials:
            lines.append(m.as_corpus_line())
            lines.append("")

        corpus_file.write_text("\n".join(lines), encoding="utf-8")
        return corpus_file
