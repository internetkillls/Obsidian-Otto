# Domain Model

## Main objects

### VaultNote
A markdown note discovered during vault scan.

### BronzeRecord
Raw extracted note inventory before normalization.

### SilverNote
Normalized relational representation of a note inside SQLite.

### GoldSignal
Curated, decision-ready evidence:
- folder risk
- metadata quality
- retrieval summary
- training readiness
- optional wellbeing / SWOT signals if explicitly enabled

### HandoffPacket
Continuity state between sessions.

### KairosHeartbeat
Periodic status sample:
- freshness
- retrieval misses
- risk changes
- training blockers
- strategy hint

### DreamSummary
Compressed memory of:
- repeated lessons
- unresolved problems
- useful stable facts
- AGENTS update candidates
