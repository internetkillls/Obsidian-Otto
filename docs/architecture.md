# Architecture

## Goal

Turn a mixed Obsidian automation workspace into a **stable Codex-native assistant core**.

## High-level shape

```text
User / Telegram / TUI
  -> Otto Runtime
  -> Retrieval controller
  -> Bronze / Silver / Gold data stack
  -> KAIROS telemetry
  -> Dream consolidation
  -> Codex skills + AGENTS + optional custom agents
```

## Core loops

### 1. Retrieval loop

User query  
→ fast retrieval  
→ if enough evidence: answer  
→ else scoped deep refresh  
→ deep retrieval  
→ answer

### 2. Dataset loop

Raw vault  
→ Bronze scan  
→ Silver normalization  
→ Gold curation  
→ training export candidate

### 3. Operational loop

runtime start  
→ logs  
→ KAIROS heartbeat  
→ Dream consolidation  
→ next batch strategy

## Supporting docs

- `docs/cache-stack-and-events.md`
- `docs/model-routing.md`
- `docs/state-model.md`
