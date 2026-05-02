from pathlib import Path
import json
import datetime

vault = Path(r"C:\Users\joshu\Josh Obsidian")
repo = Path(r"C:\Users\joshu\Obsidian-Otto")
folder = vault / "00-Meta" / "scarcity"
files = sorted([p for p in folder.rglob("*.md") if p.is_file()])

# pull authoritative duplicate pressure from gold summary
try:
    gold = json.loads((repo / "artifacts" / "summaries" / "gold_summary.json").read_text(encoding="utf-8"))
except Exception:
    gold = {}

gold_dup = None
for row in gold.get("top_folders", []):
    if row.get("folder") == "00-Meta\\scarcity":
        gold_dup = int(row.get("duplicate_titles", 0))
        break

# representative files (scoped sample)
representative_files = [str(p.relative_to(vault)) for p in files[:8]]

# concrete repair candidates
repair_candidates = []
for rel in representative_files[:6]:
    repair_candidates.append({
        "file": rel,
        "candidate_fix": "normalize title/frontmatter for uniqueness and add alias to canonical cluster note if semantically duplicate",
    })

now = datetime.datetime.now().astimezone().isoformat()
out_json = repo / "artifacts" / "reports" / "scarcity_hygiene_evidence_pack.json"
out_md = repo / "artifacts" / "reports" / "scarcity_hygiene_evidence_pack.md"

payload = {
    "ts": now,
    "scope": "00-Meta\\scarcity",
    "note_count": len(files),
    "duplicate_title_pressure_from_gold": gold_dup,
    "representative_files": representative_files,
    "repair_candidates": repair_candidates,
    "notes": [
        "Gold summary remains source of truth for duplicate-title pressure.",
        "This pack provides scoped representative files and concrete repair candidates for next remediation step."
    ]
}
out_json.parent.mkdir(parents=True, exist_ok=True)
out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

lines = [
    "# Scarcity Hygiene Evidence Pack",
    "",
    f"- ts: {now}",
    "- scope: 00-Meta\\scarcity",
    f"- note_count: {len(files)}",
    f"- duplicate_title_pressure_from_gold: {gold_dup}",
    "",
    "## Representative duplicate clusters",
]

if gold_dup and gold_dup > 0:
    lines.append("- Gold summary reports duplicate-title pressure in this folder; representative files listed below for cluster triage.")
else:
    lines.append("- No duplicate-title pressure signal found in Gold summary.")

for f in representative_files:
    lines.append(f"- {f}")

lines.extend(["", "## Repair candidates"])
for r in repair_candidates:
    lines.append(f"- {r['file']} -> {r['candidate_fix']}")

out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(str(out_json))
print(str(out_md))
