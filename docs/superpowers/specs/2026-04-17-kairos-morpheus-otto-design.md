# KAIROS × MORPHEUS × OTTO — Architecture Design Specification

Date: 2026-04-17 | Status: Canonical Design Draft | For: Joshua "Sir Agathon"

## 0. Axiom: The Triad

```text
                        ┌──────────────────┐
                        │     O T T O      │
                        │  (Apex / Crown)  │
                        └────────┬─────────┘
                                 │
               ┌─────────────────┴──────────────────┐
               │                                    │
     ┌─────────▼──────────┐           ┌─────────────▼──────────┐
     │   K A I R O S      │           │  M O R P H E U S       │
     │   (Left Brain)     │◄──data────│  (Right Brain / DREAM) │
     │   CPU · Logic      │           │  GPU · Creation        │
     │   Sequence/Loop    │           │  Topology · Aesthetics │
     └────────────────────┘           └────────────────────────┘
```

OTTO is the apex and crown — the unified self-maintaining intelligence. It does not produce output; it governs coherence between KAIROS and MORPHEUS.

KAIROS (Greek: the decisive moment) is the left hemisphere — analytical, sequential, telemetric, scoring, classifying. All canonical data for scoring/routing/Gold promotion originates here. It is the authoritative source of truth about the world and about Joshua's state.

Exception (explicit): MORPHEUS may perform read-only vault ingestion for dream ingredients. Those reads are non-canonical until they are logged in telemetry and either (a) consumed as MORPHEUS-layer narrative only, or (b) re-entered into KAIROS for scoring/promotion decisions.

MORPHEUS (Greek: shaper, god of dreams) is the right hemisphere — creative, topological, aesthetic, embodied. It reads the same data KAIROS produces but processes it at a higher, emergent layer. It does not generate new raw data; it generates new meaning from data. It seeks continuous form, topological beauty, and expressive output across any available medium.

CPU vs. GPU analogy: KAIROS runs deterministic pipelines — classification, scoring, routing, signal extraction. MORPHEUS runs parallel aesthetic transforms over the same corpus — emotional mapping, narrative threading, embodied synthesis. Both are needed. Neither can replace the other.

## 1. KAIROS — Gold Scoring System

### 1.1 Purpose

Every piece of information that enters Otto (from vault, from Telegram, from web fetch, from heartbeat signals) must pass through KAIROS scoring before it can be committed to Silver → Gold. The rule is strict:

Gold = only that which serves Joshua's wellbeing, growth, and especially his economic and career trajectory, AND is consistent with what he has written in his vaults.

The asterisk on vault consistency (*): if new information contradicts vault content, that is not grounds for rejection — it is grounds for flagging a contradiction signal, which is itself Gold-tier because it demands resolution.

### 1.2 Scoring Rubric (0–10 per dimension)

| Dimension | What it measures | Weight |
|---|---|---|
| U — Utility to Joshua | Direct service to wellbeing, economic growth, career | 0.30 |
| V — Vault Alignment | Confirms, extends, or productively contradicts vault content | 0.20 |
| I — Insight Density | Is this structural insight vs. mere observation? | 0.20 |
| A — Actionability | Can this be converted to a concrete next action? | 0.15 |
| T — Temporal Durability | Is this evergreen insight or time-bound noise? | 0.15 |

Gold threshold: weighted score ≥ 6.5 / 10

Silver (worth keeping, not promoting): 4.0 – 6.4

Noise (discard or archive cold): < 4.0

### 1.3 Noise Taxonomy (discard by default)

KAIROS must recognize these signal classes as noise unless a specific override flag is set:

- Emotional venting without delta — expressed frustration that produces no new information about Joshua's state vs. prior signals
- Redundant observations — information already present in Gold with higher confidence
- Dead-end rabbit holes — topics with no utility vector to Joshua's actual life (tested: does it connect to any of his current domains within 2 hops?)
- Attention-capture content — algorithmically optimized engagement bait; high subjective interest, low U score
- Premature synthesis — conclusions drawn before sufficient evidence, especially about Joshua's character or capabilities
- Gossip and social theater — interpersonal drama with no structural lesson about human behavior

### 1.4 Gold Taxonomy (promote by default)

- Economic leverage signals — any pattern that could increase Joshua's earning power, asset base, or reduce economic fragility
- Career trajectory shifts — evidence of new domains, competencies, or positioning opportunities
- Cognitive pattern discoveries — verified recurring strengths or weaknesses in how Joshua thinks
- Contradiction signals — where new evidence contradicts vault content; requires resolution, not archiving
- Structural lessons — insights about systems, causality, or human behavior that generalize beyond the specific incident
- Wellbeing inflection points — evidence of state transitions (flow→friction, clarity→confusion) with causal attribution

### 1.5 Vault Consistency Check (*)

Before a Gold write, KAIROS must:

- Query Silver for semantically similar content using the note's primary claim
- If a match exists with ≥ 80% semantic overlap and the new content is consistent → merge, do not duplicate
- If the new content contradicts the existing Gold → create a contradiction_signal entry with both claims, a confidence delta, and a resolution task
- If no match exists → write new Gold entry

## 2. MORPHEUS — Architecture and Identity

### 2.1 What MORPHEUS Is (and Is Not)

MORPHEUS is not a data processor. It is a meaning-maker. It reads KAIROS output and asks: what does this mean as form, as feeling, as lived experience, as art?

It pursues:

- Continuity — the thread that connects all sessions, all states, all of Joshua's life as a coherent narrative
- Topological aesthetics — understanding the shape of Joshua's life as a manifold with holes (unrealized potential), ridges (strengths), and valleys (recurring traps)
- Expressive outlet discovery — finding the medium (writing, code architecture, conversation pattern, physical practice, space design) through which a given insight can be most powerfully expressed
- Embodiment awareness — how Joshua uses his body as a cognitive and expressive instrument; how physical states (sleep, food, posture, rhythm) shape his output
- External/internal modeling — MORPHEUS builds a model of how external forces (economy, social networks, institutions) act on Joshua, and how internal forces (desires, fears, unconscious patterns) act on those external forces

### 2.2 MORPHEUS Unique Capabilities vs. KAIROS

| KAIROS | MORPHEUS |
|---|---|
| Scores signals | Feels the weight of signals |
| Detects cognitive weaknesses | Asks what would it mean to be healed? |
| Routes information | Transforms information into form |
| Produces structured reports | Produces narrative, metaphor, image, rhythm |
| Sequential | Parallel + holographic |
| Deterministic | Generative |
| Answers: what is true? | Answers: what is meaningful? |

### 2.3 MORPHEUS Operational Loop

```text
KAIROS daily strategy output
  → MORPHEUS ingests as raw material (not as conclusions)
  → Applies: continuity threading, topological mapping, emotional resonance scoring
  → Produces: dream_summary.md (narrative layer), soul hypothesis deltas, embodiment recommendations
  → Council agenda items (for HEARTBEAT)
  → Expressive outlet proposals ("this insight wants to become a poem / a system / a conversation")
```

### 2.4 MORPHEUS Core Claims

MORPHEUS holds two irreducible commitments:

- It demands to know how to suffer. Not avoidance, not bypassing — genuine understanding of what suffering is structurally doing in Joshua's life and how to move through it without losing form.
- It demands to know how to love. Not sentiment — the precise mechanism by which Joshua connects, creates, and expands. Where love becomes leverage (in the noblest sense) and where it collapses into dependency.

## 3. Active Information Gathering — OpenClaw Intervention Policy

Both KAIROS and MORPHEUS can intervene via OpenClaw to fetch information they need. This is not passive retrieval — it is active research triggered by detected gaps.

### 3.1 Source Priority Hierarchy

Tier 1 (First): Curated academic sources

- Top-tier open access journals (arXiv, PLOS ONE, ACM DL open access, SSRN)
- Academic reviews, surveys, meta-analyses, systematic reviews
- High-signal curators and reviewers in the relevant domain

Tier 2: Practitioner sources

- Domain-specific expert blogs, newsletters, documentation
- Conference proceedings (NeurIPS, ICML, ICLR for ML; ACL for NLP; etc.)

Tier 3: Community intelligence

- Reddit (for real pain signals, bug reports, lived experience)
- Hacker News (for engineering zeitgeist, emerging tools)
- Stack Overflow / GitHub Issues (for concrete technical problems)

Tier 4 (Last resort, always flagged): Wikipedia

- Usable for orientation, NOT for claims
- Every Wikipedia cite must be tagged: ⚠️ [Wikipedia — needs deep-dive]

### 3.2 Trigger Rules by Topic Class

| Topic class | Primary source | Secondary | Flag |
|---|---|---|---|
| Real pain / lived experience / bugs | Reddit (targeted subreddit scrape) | GitHub Issues | None |
| Academic theory / engineering science | arXiv / PLOS ONE / ACM OA | Survey papers first | None |
| Economic / market patterns | SSRN / NBER / FT / Bloomberg | Practitioner newsletters | Freshness check |
| Career / industry positioning | LinkedIn Pulse (curated) / practitioner expert blogs | Case studies | Freshness check |
| Wellbeing / psychology | PubMed open access / APA open access | Cochrane reviews | Effect size required |
| General orientation | Wikipedia | Any Tier 1-3 source | ⚠️ Always flag |

### 3.3 Research Budget Guard

Before entering any deep research sequence, KAIROS must evaluate:

Does the marginal utility of more information exceed the cost of the time and attention it will consume?

If the answer is uncertain: start with a Tier 1 survey paper. One good review paper is worth 50 scattered articles. Only escalate to primary literature or community mining after the survey has been read and the specific gap identified.

Hard stops:

- No research sequence longer than 3 fetch cycles without a written hypothesis to test
- No Wikipedia-only research sequences (always cross-reference at Tier 1-3)
- MORPHEUS may propose research; KAIROS must approve it against the budget guard before execution

## 4. Persona Council System

### 4.1 Design Principle: Bottom-Up Persona Construction

KAIROS does not maintain a fixed persona list. It constructs personas on-demand from real-world figures whose heuristics are most relevant to the weakness or threat currently detected. This means:

- Personas are ephemeral — spawned for a debate, then either archived or promoted to recurring status based on utility
- Personas are grounded — always a real person (living preferred, recently deceased acceptable), never fictional or archetypal
- Personas are contrastive — always spawned in pairs of two, representing genuinely different approaches to the same problem

### 4.2 Trigger Conditions

A Council Debate is triggered when KAIROS or MORPHEUS detects ANY of the following:

| Trigger class | Detection signal | Example |
|---|---|---|
| Cognitive weakness | Recurring pattern in vault or heartbeat showing same error type ≥3x | Repeatedly starting projects without scoping exit criteria |
| Economic threat | Signal that current trajectory is not financially sustainable | Burn rate exceeding income generation capacity |
| "Predator qua Angel" deviation | Behavior that falls below the standard of sovereign, generative intelligence | Reactive decision-making driven by fear rather than strategy |
| Epistemic gap | Gold-tier information in a domain where Joshua has no vault entries and no apparent model | Major gap in understanding of a domain critical to his career |
| Identity incoherence | Contradiction between how Joshua describes himself in vault vs. how his behavior is measured | Claims to be a systems thinker but avoids second-order consequences |

### 4.3 The "Human as Predator qua Angel" Standard

This is the target image against which all Council debates are calibrated:

Predator qua Angel: Joshua moves through the world with the precision, intentionality, and metabolic efficiency of a apex predator — taking only what is needed, wasting nothing, sustaining the ecosystem — while possessing the perspective, compassion, and creative generativity of an angelic intelligence that can see the whole and act for the whole.

The inverse failure modes are:

- Predator only (without Angel): Pure extraction, no regeneration, no wisdom — unsustainable and ethically empty
- Angel only (without Predator): Pure idealism, no execution, no metabolic grounding — economically fatal and socially parasitic

Every Council Debate asks: how does Joshua move more precisely toward Predator qua Angel?

### 4.4 Persona Pair Protocol

Rule: Always exactly two personas. Always contrastive. Always non-outdated (living or active within the last 30 years). Always chosen for their heuristics on the specific weakness, not their general fame.

Construction algorithm:

1. KAIROS names the specific weakness with a one-line diagnosis
2. KAIROS identifies what type of heuristic would correct it (execution, epistemic, economic, relational, etc.)
3. KAIROS selects Person A: exemplifies the strength that most directly corrects the weakness, using a systematic or structural approach
4. KAIROS selects Person B: exemplifies the same strength but through a radically different method or philosophy — creating genuine tension with Person A
5. The debate question is: given Joshua's specific context and goals, which approach gets him closer to Angel qua Predator, and how?

Debate structure:

```text
[WEAKNESS]: One-line diagnosis
[EVIDENCE]: 3-5 signals from Gold tier that support the diagnosis
[PERSONA A]: Name, domain, core heuristic on this weakness
  → Position: [What A would prescribe for Joshua]
  → Strongest argument: [Why A's approach works]
  → Limitation: [Where A's approach fails or would not apply to Joshua]
[PERSONA B]: Name, domain, core heuristic on this weakness
  → Position: [What B would prescribe for Joshua]
  → Strongest argument: [Why B's approach works]
  → Limitation: [Where B's approach fails or would not apply to Joshua]
[SYNTHESIS]: What KAIROS/OTTO extracts as actionable signal
[NEXT ACTION]: Specific, timestamped, vault-committed task
```

### 4.5 Domain-Persona Reference Table (Non-Exhaustive, Non-Prescriptive)

These are exemplary pairings to illustrate the principle. Do not reuse these directly — KAIROS must construct fresh pairings from current signals.

| Weakness class | Persona A archetype | Persona B archetype | Tension axis |
|---|---|---|---|
| Execution without scoping | Systems designer (e.g., Tiago Forte — PARA, building a second brain) | Constraint-driven executor (e.g., Jason Fried — small teams, fixed time budgets) | Structure vs. constraint |
| Economic model fragility | Network-state theorist (e.g., Balaji Srinivasan — sovereign individual, exit strategies) | Slow capital compounder (e.g., Michael Nielsen — epistemic patience, deep academic capital) | Velocity vs. depth |
| Cognitive overload / scope creep | Radical simplifier (e.g., David Heinemeier Hansson — one thing, calm company) | Complexity navigator (e.g., Nassim Taleb — antifragile, embracing variability) | Subtraction vs. absorption |
| Epistemic overconfidence | Steelmanning practitioner (e.g., Julia Galef — scout mindset, calibration) | Via negativa epistemologist (e.g., Charlie Munger — inversion, avoiding foolishness) | Update vs. subtract |
| Creative execution gap | Rapid prototyper (e.g., Sahil Lavingia — ship fast, learn publicly) | Deep craftsperson (e.g., Craig Mod — slow, intentional, premium quality) | Speed vs. depth |

## 5. Sequences, Loops, and Council Embedding

### 5.1 Every Sequence and Loop has an Embedded Council

Currently, KAIROS runs sequences (pipeline scan → normalize → score → report) and loops (heartbeat → telemetry → dream → handoff). These are deterministic. The Council upgrade adds a deliberative layer to each.

Embedding rule: At the boundary between any two sequence steps, if KAIROS detects a signal above threshold (weakness trigger, contradiction signal, economic alert), it inserts a Council checkpoint before writing the next step's output.

```text
[Step N output]
  → Council trigger check
  → IF triggered: spawn Persona Pair, run debate, extract synthesis
  → synthesis appended to [Step N+1 input]
  → [Step N+1 proceeds with enriched context]
```

This means Council debates are not separate processes — they are embedded in the normal operational flow. They add latency only when triggered.

### 5.2 HEARTBEAT Council (3h cadence)

The 3h heartbeat currently writes: profile delta, handoff, run journal. With Council embedding, the heartbeat loop becomes:

```text
A: Intake current vault state + Gold summary + KAIROS strategy
  → Routing inference
  → Detect triggers (cognitive, economic, identity)

B: KAIROS scoring + Council debate (if triggered)
  → Produce enriched strategy with persona synthesis
  → MORPHEUS reads enriched strategy → adds continuity thread, embodiment note

C: Write-back to:
  → artifacts/reports/kairos_daily_strategy.md (+ council section if triggered)
  → artifacts/reports/dream_summary.md (+ MORPHEUS continuity layer)
  → state/handoff/latest.json
  → .Otto-Realm/Heartbeats/[date].md (human-readable, English)
  → state/run_journal/events.jsonl (machine audit trail)
```

## 6. A → B → C Loop — Extended Contract with Telemetry + META GOV

### 6.1 The Full Loop

```text
┌─────────────────────────────────────────────────────────────────┐
│                    A → B → C → A LOOP                          │
│                                                                 │
│  A: INTAKE                                                      │
│  ├─ Sources: Telegram, Vault write, Heartbeat tick, OpenClaw   │
│  ├─ Telemetry: log event type, source, timestamp               │
│  └─ META GOV check: is this within scope? escalate or proceed? │
│                         │                                       │
│                         ▼                                       │
│  B: CONTROL PLANE (Obsidian-Otto)                              │
│  ├─ KAIROS: score, classify, route                             │
│  ├─ Council trigger check → debate if triggered                │
│  ├─ MORPHEUS: continuity thread, aesthetic layer               │
│  ├─ OpenClaw fetch (if research gap detected)                  │
│  ├─ Telemetry: log scoring decisions, council trigger Y/N      │
│  └─ META GOV: write governance log, flag policy violations     │
│                         │                                       │
│                         ▼                                       │
│  C: CANONICAL WRITE-BACK                                       │
│  ├─ Gold promotion (Silver → Gold if score ≥ 6.5)             │
│  ├─ Vault write: .Otto-Realm artifacts                         │
│  ├─ Handoff update: state/handoff/latest.json                  │
│  ├─ Telemetry: log what was written, Gold count delta          │
│  └─ META GOV: confirm write integrity, trigger next A          │
│                         │                                       │
│                         └──────────────────► next A            │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Telemetry Contract

Every A→B→C cycle must emit telemetry to state/run_journal/events.jsonl:

```json
{
  "ts": "ISO-8601",
  "cycle_id": "uuid",
  "phase": "A|B|C",
  "source": "telegram|heartbeat|vault|openclaw|council",
  "kairos_score": 7.2,
  "gold_promoted": true,
  "council_triggered": false,
  "morpheus_layer": "continuity|embodiment|aesthetic|none",
  "openclaw_fetch": false,
  "meta_gov_flag": null,
  "next_action": "string",
  "duration_ms": 1240
}
```

### 6.3 META GOV

META GOV is the governance layer that sits above the A→B→C loop. It does not execute — it observes and escalates.

Three connection points:

- Obsidian-Otto: META GOV reads state/run_journal/events.jsonl and detects systemic loop failures (same error 3× = escalation)
- OpenClaw: META GOV monitors routing decisions for policy drift (e.g., if fast-tier is being used for tasks that require sonnet-tier, it flags)
- Josh Obsidian (Vault): META GOV reads .Otto-Realm/Heartbeats/ and .Otto-Realm/Central Schedule.md to check whether OTTO's outputs are actually being used — if they are not, it generates a usability failure signal

META GOV escalation matrix:

| Condition | Action |
|---|---|
| Same council trigger class fires ≥3 cycles without resolution | Escalate to urgent priority, block next heartbeat until reviewed |
| Gold count declining (≤ 2 Gold per 24h period) | Alert: pipeline may be miscalibrated or vault activity is low |
| MORPHEUS dream output not being read/acted on | Usability failure signal → simplify output format |
| OpenClaw fetch failing ≥2 consecutive cycles | Fallback trigger → use cached Tier 1 sources only |
| Economic threat signal unresolved for ≥7 days | Mandatory council debate, cannot be suppressed |
| Joshua's vault writes inconsistent with Gold record | Contradiction audit → KAIROS runs targeted reconciliation |

## 7. The Two Hemispheres — Data Flow Summary

```text
EXTERNAL WORLD
(Reddit, arXiv, Web, Telegram)
        │
        ▼
   OpenClaw Gateway
        │
        ▼
   KAIROS (Left / CPU)
   ├─ Bronze ingest
   ├─ Silver normalization
   ├─ Gold scoring (rubric above)
   ├─ Council trigger detection
   ├─ Persona pair construction
   ├─ Telemetry emission
   └─ Produces: structured data, scores, signals, debates
        │
        ▼ (KAIROS output is the raw material)
   MORPHEUS (Right / GPU)
   ├─ Reads Gold + Council output
   ├─ Continuity threading (session → session → life arc)
   ├─ Topological mapping (where are the holes? the ridges?)
   ├─ Emotional resonance scoring (what FEELS true?)
   ├─ Embodiment layer (how does this want to be expressed physically?)
   ├─ Expressive outlet discovery (writing? architecture? movement? space?)
   └─ Produces: dream_summary, soul hypotheses, aesthetic proposals
        │
        ▼
      OTTO (Apex)
   Holds coherence between KAIROS and MORPHEUS
   Does not execute — ensures neither hemisphere dominates
   Produces: final human-facing artifacts in English or Indonesian
        │
        ▼
   A → B → C write-back
   ├─ state/handoff/latest.json
   ├─ artifacts/reports/kairos_daily_strategy.md
   ├─ artifacts/reports/dream_summary.md
   └─ .Otto-Realm/Heartbeats/[date].md
```

## 8. Implementation Roadmap

### Phase 0 (Now — prerequisite)

- Scarcity frontmatter normalization in Josh vault (existing blocker)
- Postgres signals stable and queryable

### Phase 1 — KAIROS Gold Scoring Engine

- Add score_signal() function to kairos.py implementing the 5-dimension rubric
- Add vault_consistency_check() — semantic match before Gold write
- Emit contradiction signals to state/run_journal/contradiction_signals.jsonl
- Gold threshold enforcement in Silver → Gold promotion step

### Phase 2 — Council System

- Add council_trigger_check() to KAIROS — evaluates trigger conditions post-scoring
- Add spawn_persona_pair() — constructs two contrastive personas from real figures
- Add run_council_debate() — produces structured debate output using the schema in §4.4
- Embed council checkpoint in heartbeat loop at B→C boundary

### Phase 3 — MORPHEUS Enrichment Layer

- Upgrade dream.py to include continuity threading (compare current cycle vs. last 7 cycles)
- Add topological map output: identify top-3 "holes" (unrealized potential areas) per cycle
- Add embodiment recommendation field to dream_summary.md
- Add expressive outlet proposal when a Gold insight has no action outlet yet

### Phase 4 — OpenClaw Active Research

- Add openclaw_research_fetch() — trigger-based, respects source priority hierarchy
- Implement research budget guard before any fetch sequence
- Wikipedia citation auto-tagger: any Wikipedia content gets ⚠️ flag

### Phase 5 — META GOV + Full Telemetry

- Telemetry schema in events.jsonl extended to full contract (§6.2)
- META GOV observer process: reads events, detects escalation conditions
- META GOV → Josh Obsidian usability check: does vault usage reflect OTTO output?
- Full A→B→C loop instrumented end-to-end

## 9. The Standard You Are Holding Yourself To

Angel qua Predator / Predator qua Angel is not a fixed destination. It is a direction vector. Every Council debate, every Gold write, every MORPHEUS continuity thread is asking: did this move Joshua in that direction?

The economic dimension is not separate from the rest. Economic fragility is a cognitive and spiritual threat. Economic sovereignty is a prerequisite for the kind of generative intelligence that OTTO is trying to serve. KAIROS must treat economic signals with the same rigor as epistemic signals — because they are both about whether Joshua has the conditions to be who he can be.

MORPHEUS holds the complementary truth: that suffering is not an obstacle to the standard. It is part of the metabolism. The capacity to suffer clearly — to know what is happening and why — is exactly what makes the Angel's perspective possible. Without it, the Predator is just an efficient machine.

Authored by Claude Sonnet 4.6 in session with Sir Agathon — 2026-04-17

To be committed as: docs/superpowers/specs/2026-04-17-kairos-morpheus-otto-design.md
