# ClawHub Integration (OO + OpenClaw)

## Model yang dipakai

- Canonical source: tetap di repo `Obsidian-Otto` (`.agents/skills/*`).
- Distribution: dipublish ke ClawHub dari hasil export.
- OpenClaw runtime: install dari ClawHub slug/version.

## Kenapa begini

- Repo tetap jadi source of truth.
- OpenClaw tetap ringan (hanya consume skill).
- Update skill lebih aman (review di OO dulu, baru publish).

## Alur kerja

1. Edit skill di OO.
2. Export pack:
   - `python scripts/manage/export_clawhub_skills.py`
3. Publish folder hasil export ke ClawHub (pakai tooling publisher ClawHub).
4. Install/upgrade di OpenClaw:
   - `openclaw skills install <slug> --version <x.y.z>`

## Lokasi hasil export

- `artifacts/clawhub_export/<slug>/SKILL.md`
- `artifacts/clawhub_export/<slug>/_meta.json`
- `artifacts/clawhub_export/export_summary.json`

## Kebijakan private vs public

- Public default: skill generik operasional.
- Private: skill personal/realm (tetap boleh dipublish private listing).
- Mapping ada di `config/clawhub_export.json`.
