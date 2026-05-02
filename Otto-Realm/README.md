# Otto-Realm

This folder is a sample mirror for the Obsidian-Otto control plane.
The canonical Otto-Realm lives at `C:\Users\joshu\Josh Obsidian\Otto-Realm\`.

## Otto-Otto ↔ Otto-Realm Arrangement

| Concern | Location |
|---|---|
| Otto agent workspace (OpenClaw) | `C:\Users\joshu\Josh Obsidian` |
| Otto control plane state | `C:\Users\joshu\Obsidian-Otto\state\` |
| Otto brain / persona | `C:\Users\joshu\Josh Obsidian\Otto-Realm\` |
| Otto vault_path (paths.yaml) | `C:\Users\joshu\Josh Obsidian` |
| Dream ingredients | Otto-Realm canonical areas (see below) |

## Otto-Realm Dream Areas

These areas are used as dream ingredient sources (see `docs/superpowers/specs/2026-04-17-vault-dream-ingredients-design.md`):

| Area | Purpose in Dream |
|---|---|
| `Otto-Realm/Brain/` | Self-model snapshots, profile updates |
| `Otto-Realm/Heartbeats/` | Recent care signals, cadence, Josh state |
| `Otto-Realm/Memory-Tiers/` | Fact / interpretation / speculation tiers |
| `Otto-Realm/Predictions/` | Predictive scaffold outputs |
| `Otto-Realm/Rituals/` | Ritual cycle artifacts |

## Write boundary

Otto may:

- Write new notes in the canonical Otto-Realm
- Link `[[...]]` to action or project outcomes
- Create future links to anticipated notes
- Write in `Memory-Tiers/` with appropriate tier tags

Otto may not:

- Rewrite vault past content without explicit Sir Agathon consent
- Edit Sir Agathon's notes without consent
- Claim speculation as fact

## Otto-Otto state vs Otto-Realm

Otto-Otto's own state files (handoff, checkpoints, dream, kairos, run journal) live in the Otto repo under `state/`. Otto-Realm is the brain and persona — Otto reads from it but its own control-plane state stays in the Otto repo.
