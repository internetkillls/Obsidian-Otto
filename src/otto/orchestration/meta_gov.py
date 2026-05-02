from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..config import load_paths
from ..state import now_iso, write_json


@dataclass
class MetaGovFinding:
    level: str
    flag: str
    condition: str
    action: str
    evidence: str

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "flag": self.flag,
            "condition": self.condition,
            "action": self.action,
            "evidence": self.evidence,
        }


class MetaGovObserver:
    def __init__(self) -> None:
        self.paths = load_paths()

    def _load_events(self, limit: int = 500) -> list[dict]:
        path = self.paths.state_root / "run_journal" / "events.jsonl"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        events: list[dict] = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    @staticmethod
    def _parse_ts(raw: str | None) -> datetime:
        if not raw:
            return datetime.now(timezone.utc)
        try:
            dt = datetime.fromisoformat(str(raw))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)

    def _heartbeat_usability(self) -> MetaGovFinding | None:
        vault = self.paths.vault_path
        if vault is None:
            return None
        heartbeat_dir = vault / ".Otto-Realm" / "Heartbeats"
        if not heartbeat_dir.exists():
            return MetaGovFinding(
                level="medium",
                flag="usability_failure",
                condition=".Otto-Realm heartbeat directory is present for write-back validation",
                action="Create or restore the heartbeat target path before relying on usability checks",
                evidence=str(heartbeat_dir),
            )
        latest = max((p.stat().st_mtime for p in heartbeat_dir.rglob("*.md")), default=0.0)
        if latest == 0.0:
            return MetaGovFinding(
                level="medium",
                flag="usability_failure",
                condition="No human-readable heartbeat artifacts exist yet",
                action="Write the next enriched heartbeat .Otto-Realm/Heartbeats and re-check adoption",
                evidence=str(heartbeat_dir),
            )
        return None

    def _economic_staleness(self) -> list[MetaGovFinding]:
        """Economic or career signals unresolved ≥7 days → mandatory council debate."""
        findings: list[MetaGovFinding] = []
        path = self.paths.state_root / "run_journal" / "contradiction_signals.jsonl"
        if not path.exists():
            return findings

        economic_keywords = [
            "economic", "revenue", "income", "market", "pricing",
            "asset", "fragility", "career", "financial", "burnout",
        ]
        now = datetime.now(timezone.utc)
        stale_economic: list[tuple[str, str, int]] = []  # (note_path, claim, days)

        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if bool(record.get("resolved")):
                continue

            note_path = str(record.get("note_path", ""))
            claim = str(record.get("primary_claim", ""))
            ts_raw = str(record.get("ts", ""))

            is_economic = any(kw in claim.lower() or kw in note_path.lower() for kw in economic_keywords)
            if not is_economic:
                continue

            ts = self._parse_ts(ts_raw)

            days_old = (now - ts).days
            if days_old >= 7:
                stale_economic.append((note_path, claim, days_old))

        for note_path, claim, days in stale_economic[:3]:
            findings.append(
                MetaGovFinding(
                    level="critical",
                    flag="economic_threat_stale",
                    condition=f"Economic/career signal unresolved for {days} days",
                    action="Trigger mandatory council debate — economic signals cannot accumulate",
                    evidence=f"Path: {note_path} | Claim excerpt: {claim[:120]}",
                )
            )
        return findings

    def _vault_write_consistency(self) -> list[MetaGovFinding]:
        """Gold high-value areas vs recent vault writes → contradiction audit findings."""
        findings: list[MetaGovFinding] = []
        summary_path = self.paths.artifacts_root / "summaries" / "gold_summary.json"
        scored_path = self.paths.state_root / "kairos" / "gold_scored_latest.json"
        if not summary_path.exists() or not self.paths.sqlite_path.exists():
            return findings

        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return findings
        scored = {}
        if scored_path.exists():
            try:
                scored = json.loads(scored_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                scored = {}

        target_areas: set[str] = set()
        for row in summary.get("top_folders", [])[:6]:
            folder = str(row.get("folder", "")).replace("\\", "/").strip("/")
            if folder:
                target_areas.add(folder.split("/", 1)[0])
        for path in scored.get("promoted_paths", []) or []:
            folder = str(path).replace("\\", "/").strip("/")
            if folder:
                target_areas.add(folder.split("/", 1)[0])
        if not target_areas:
            return findings

        now = datetime.now(timezone.utc)
        threshold_days = 14
        summary_mtime = datetime.fromtimestamp(summary_path.stat().st_mtime, tz=timezone.utc)
        conn = sqlite3.connect(self.paths.sqlite_path)
        try:
            for area in sorted(target_areas):
                pattern = f"{area.replace('\\', '/')}/%"
                row = conn.execute(
                    """
                    SELECT MAX(mtime) AS max_mtime, COUNT(*) AS note_count
                    FROM notes
                    WHERE REPLACE(path, '\\', '/') LIKE ?
                    """,
                    (pattern,),
                ).fetchone()
                if not row or row[0] in (None, ""):
                    continue
                max_mtime = float(row[0])
                note_count = int(row[1] or 0)
                area_last_write = datetime.fromtimestamp(max_mtime, tz=timezone.utc)
                days_since = (now - area_last_write).days

                if days_since >= threshold_days:
                    findings.append(
                        MetaGovFinding(
                            level="high",
                            flag="gold_vault_inconsistency",
                            condition=f"Gold high-value area '{area}' is silent for {days_since} days",
                            action="Run contradiction audit and decide: refresh Gold mark or restart writes in this area",
                            evidence=f"area={area} note_count={note_count} last_write={area_last_write.isoformat()}",
                        )
                    )
                    continue

                if area_last_write > summary_mtime + timedelta(days=2):
                    findings.append(
                        MetaGovFinding(
                            level="medium",
                            flag="gold_vault_inconsistency",
                            condition=f"Vault writes in '{area}' are newer than current Gold record",
                            action="Run contradiction audit to reconcile Gold with recent vault writes",
                            evidence=f"gold_summary_ts={summary_mtime.isoformat()} latest_area_write={area_last_write.isoformat()}",
                        )
                    )
        finally:
            conn.close()
        return findings

    def observe(self) -> list[MetaGovFinding]:
        events = self._load_events()
        findings: list[MetaGovFinding] = []
        now = datetime.now(timezone.utc)
        recent_window = now - timedelta(hours=24)

        council_by_category: dict[str, int] = {}
        kairos_gold_events = 0
        openclaw_failures = 0
        for event in events:
            ts_raw = event.get("ts")
            ts = self._parse_ts(str(ts_raw) if ts_raw else None)
            payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}
            if event.get("type") == "council.debate":
                category = str(payload.get("trigger_category", "unknown"))
                council_by_category[category] = council_by_category.get(category, 0) + 1
            if event.get("type") == "kairos.gold.scored" and ts >= recent_window:
                kairos_gold_events += int(payload.get("gold_promoted_count", 0))
            if event.get("type") == "openclaw.fallback.triggered":
                openclaw_failures += 1

        for category, count in council_by_category.items():
            if count >= 3:
                findings.append(
                    MetaGovFinding(
                        level="high",
                        flag="council_repeat",
                        condition=f"Council trigger '{category}' has repeated {count} times",
                        action="Escalate to urgent review before the next heartbeat cycle",
                        evidence=f"{count} council.debate events in recent log",
                    )
                )

        if kairos_gold_events <= 2:
            # Bootstrap guard: only fire if we have ≥3 scored events in history
            scored_count = sum(
                1 for e in events
                if e.get("type") == "kairos.gold.scored"
            )
            if scored_count >= 3:
                findings.append(
                    MetaGovFinding(
                        level="medium",
                        flag="gold_low",
                        condition="Gold promotion volume is low over the last 24 hours",
                        action="Review scoring calibration and whether the intake stream is too sparse",
                        evidence=f"gold_promoted_count_24h={kairos_gold_events} (scored_events={scored_count})",
                    )
                )

        if openclaw_failures >= 2:
            findings.append(
                MetaGovFinding(
                    level="high",
                    flag="openclaw_fallback",
                    condition="OpenClaw fallback has triggered repeatedly",
                    action="Use cached Tier 1 sources only until fetch reliability is restored",
                    evidence=f"openclaw_failures={openclaw_failures}",
                )
            )

        usability = self._heartbeat_usability()
        if usability is not None:
            findings.append(usability)

        # Phase 5 spec gaps
        findings.extend(self._economic_staleness())
        findings.extend(self._vault_write_consistency())

        write_json(
            self.paths.state_root / "run_journal" / "meta_gov_latest.json",
            {"ts": now_iso(), "findings": [item.as_dict() for item in findings]},
        )
        return findings
