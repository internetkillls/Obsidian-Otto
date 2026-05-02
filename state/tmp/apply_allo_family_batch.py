from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import sys

REPO = Path(r"C:\Users\joshu\Obsidian-Otto")
VAULT = Path(r"C:\Users\joshu\Josh Obsidian")
PLAN_PATH = REPO / "state" / "run_journal" / "graph_demotion_plan.json"
MAX_WRITES = 3

sys.path.insert(0, str(REPO / "scripts"))
import c4_graph_rollup_audit as g  # noqa: E402

plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
entries = [
    e
    for e in (plan.get("plans") or [])
    if str(e.get("kind") or "") == "allocation"
    and str(e.get("merge_target") or "") == "ALLOCATION-FAMILY"
    and str(e.get("decision") or "") == "demote_frontmatter"
]

applied = []
skipped = []
count = 0
for entry in entries:
    note_rel = str(entry.get("note") or "")
    note_path = VAULT / note_rel
    if not note_path.exists():
        skipped.append({"note": note_rel, "reason": "missing_note"})
        continue
    if count >= MAX_WRITES:
        skipped.append({"note": note_rel, "reason": "bounded_batch_limit"})
        continue
    text = note_path.read_text(encoding="utf-8", errors="replace")
    _, body, fm = g._split_frontmatter_raw(text)
    updated_fm = g._apply_plan_entry_to_frontmatter(fm, entry)
    updated = g._render_note_frontmatter(updated_fm, body)
    if updated == text:
        skipped.append({"note": note_rel, "reason": "no_change"})
        continue
    note_path.write_text(updated, encoding="utf-8")
    count += 1
    applied.append(
        {
            "note": note_rel,
            "action": entry.get("action"),
            "decision": entry.get("decision"),
            "reason": entry.get("reason"),
            "current_value": entry.get("current_value"),
        }
    )

now = datetime.now(ZoneInfo("Asia/Bangkok"))
stamp = now.strftime("%Y-%m-%d_%H%M%S")
out_path = REPO / "state" / "run_journal" / "checkpoints" / f"{stamp}_allo_family_apply.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
summary = {
    "ts": now.isoformat(),
    "status": "applied" if applied else "no_change",
    "family": "ALLOCATION-FAMILY",
    "mode": "ALLO-only",
    "source_plan": str(PLAN_PATH),
    "candidate_count": len(entries),
    "max_writes": MAX_WRITES,
    "applied_count": len(applied),
    "skipped_count": len(skipped),
    "applied": applied,
    "skipped": skipped,
    "output_path": str(out_path),
}
out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
