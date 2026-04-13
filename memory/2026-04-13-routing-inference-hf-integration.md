---
name: 2026-04-13-routing-inference-hf-integration
description: Otto-Obsidian routing inference engine + HuggingFace integration planning
type: project
date: 2026-04-13
---

# Session: Otto Routing Inference + HF Integration

## What Was Built Today

### 1. Otto Routing Inference Engine (8 tasks, committed)

Files created/modified:
- `config/routing.yaml` — 13 intent registry, LLM router, pattern fallback, 4-tier dispatch
- `config/kernelization.yaml` — 5 kernel components, 11 schemas, application matrix
- `config/heartbeat_telemetry.yaml` — telemetry schema, 8 metrics, feedback rules
- `config/personas.yaml` — inference fields on all 7 personas
- `AGENTS.md` — routing protocol, 4-tier table, guardrails, checkpoint/handoff
- `openclaw.json` — skill-routing plugin, routing-aware heartbeat
- 6 Otto skill SKILL.md frontmatter — routing metadata

### 2. Design Spec + Plan
- `docs/superpowers/specs/2026-04-13-otto-routing-inference-design.md`
- `docs/superpowers/plans/2026-04-13-otto-routing-inference-plan.md`

## Key Decisions Made

- **Routing approach**: D (hybrid — keyword trigger + LLM fallback + model-tier escalation)
- **Model tier**: Context-aware (query + persona weights + time-of-day)
- **Kernelization**: D (all 3: context isolation + tool commitment + output schema)
- **HF Inference Provider**: Decision 2 — HF Inference via Together/Cerebras (laptop small, no local GPU)
- **smolagents**: Only as emergency reasoning agent for novel intents (confidence < 40), NOT primary routing
- **OpenClaw stays primary interface** — smolagents is "emergency sun" not second sun

## Architecture

```
OpenClaw (interface + orchestration)
    │
    ├── heartbeat cycle
    ├── Telegram (Otto-Obscene)
    ├── tool execution
    └── Plugin: skill-routing
            │
            ├── Known intents (13) → pattern match → skill dispatch
            └── Novel intent (conf < 40) → HF Inference (smolagents) → reasoning trace
```

## 2-Matri Collision Point

CLAUDE.md (Vault Scarcity Architecture) and Routing Inference are complementary:

- CLAUDE.md = operational pipeline (scan, cluster, wire vault scarcity tags)
- Routing Inference = agent behavior (skill, persona, model tier)
- Phase 5 of CLAUDE.md wires Otto Bronze to scarcity tags → routing can read scarcity patterns

Both agree on: read-only on user notes, no deletion, checkpoint gates, rollback, audit log.

## HF Integration Stack

- **smolagents** (subprocess, JSONL stdout) — emergency reasoning when pattern match fails
- **sentence-transformers** — vault semantic indexing (future)
- **HF Inference Providers** — Llama-3.3-70B-Instruct via Together/Cerebras
- **HF Token**: `internetkillls` / `Josh-Obsidian` — verified active

## What's Pending / Next

1. **Implement CLAUDE.md phases** (scan_scarcity.py, gen_base_views.py, canvas_companion.py, audit_delta.py)
2. **Wire Phase 5** — Otto bronze_ingest.py reads scarcity tags
3. **HF Inference Provider** — add HuggingFace as model backend in openclaw.json
4. **smolagents emergency agent** — callable when novel intent detected (confidence < 40)
5. **sentence-transformers vault index** — semantic retrieval for heartbeat profiling

## Otto's AIM (Purpose)

Otto as philosopher between Ezra Pound, Poincaré, Gödel, Kahneman:
- Tests Sir Agathon with SM-2 Algorithm for spaced repetition
- Memento-99 pattern enrichment
- Explains why projects mangkrak (bounded rationality analysis)
- Otto-Realm = agent shared workspace (Otto's private sub-vault in Josh Obsidian)
- Telegram bot: Otto-Obscene

## Otto's Binding Docs (Read First)

1. `C:/Users/joshu/Obsidian-Otto/SOUL.md` — Otto identity, transducer rule, planner/executor split
2. `C:/Users/joshu/Obsidian-Otto/TEAM_GUIDE.md` — guidance hierarchy
3. `C:/Users/joshu/Obsidian-Otto/TOOLS.md` — paths, channels, models
4. `C:/Users/joshu/Josh Obsidian/AGENT.md` — vault operating rubric, metrics (metadata_completeness, link_density, orphan_ratio, etc.), recurring patterns
5. `C:/Users/joshu/Josh Obsidian/Otto-Realm/Profile Snapshot.md` — Otto's latest profile
6. `C:/Users/joshu/Josh Obsidian/Otto-Realm/Central Schedule.md` — schedule anchors
7. `C:/Users/joshu/Josh Obsidian/Otto-Realm/Weekly/*.md` — weekly overhauls
8. `C:/Users/joshu/Josh Obsidian/Otto-Realm/Heartbeats/*.md` — heartbeat logs

## AGENT.md Latest Summary (2026-04-13T04:31)

- metadata_completeness: 97.28
- link_density: 1.56
- orphan_ratio: 0.5
- duplicate_pressure: 22.15
- inbox_triage_pressure: 77.43
- synthesis_depth_proxy: 10.95
- Recurring: shallow synthesis (97×), incomplete linking (97×), fragmentation (88×), over-capture (83×)
- Status: needs-reset-routine

## Vault Skills (5 in Josh Obsidian/Skills/)

1. `scholarly-explore-remap` — academic literature review, source-grounded exploration
2. `visual-precedent-execution` — visual refs → executable design thinking
3. `obsidian-cli-expert-system` — governed Obsidian CLI, MCP queues, long-running routines
4. `typst-luxury-layout` — typst-first document system, cross-format publishing
5. `josh-thought-partner` — philosophical engagement, behavioral contract: no flattery, push sharpest claim, end with move

## Model Backends Configured

- openai-codex/gpt-5.4-mini (fast)
- openai-codex/gpt-5.4 (standard)
- claude-cli/claude-sonnet-4-6 (sonnet, via --allow-dangerously-skip-permission --bypassPermissions)
- claude-cli/claude-opus-4-6 (premium, same flags)
- HF Inference via Together/Cerebras (planned, token verified)
