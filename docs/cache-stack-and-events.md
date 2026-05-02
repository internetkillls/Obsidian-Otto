# Cache Stack and Event Flow

## Goal

Make Bronze, Silver, Gold, SQL, and Chroma cooperate through one predictable event flow.

## Data zones

### Bronze
- raw vault inventory
- markdown notes
- attachments
- minimal parsing only

### Silver
- SQLite normalization
- queryable note metadata
- folder risk tables
- FTS search

### Gold
- decision-ready summaries
- training readiness
- KAIROS inputs
- reviewed wellbeing / SWOT signals only if enabled

## Optional local services

### Container 1
- Postgres or SQLite-compatible analytics store
- default local repo uses SQLite first

### Container 2
- ChromaDB vector cache

### Container 3
- optional worker / indexer sidecar

Docker stays optional.
Local-first remains the default.

## Event flow

```text
pipeline.bronze.built
  -> cache.raw.ready
  -> pipeline.silver.built
  -> cache.sql.ready
  -> pipeline.gold.built
  -> cache.vector.ready
  -> dataset.gold.ready
  -> training.review.required
  -> kairos.heartbeat
  -> dream.run
```

## Practical meaning

- Bronze is never sent to the model by default.
- Silver serves fast local retrieval.
- Gold is the main package for Codex.
- Chroma is a helper, not the source of truth.
- KAIROS watches drift, misses, and recurring hygiene problems.
- Dream consolidates state after the fact.

## Stable chain process

1. Router classifies the question cheaply.
2. Fast retrieval asks Gold + Silver first.
3. If weak evidence, deep retrieval widens scope.
4. If still weak, scoped reindex refreshes Bronze -> Silver -> Gold.
5. KAIROS records recurring misses and proposes next-day fixes.
6. Dream compresses stable facts and unresolved blockers.

## Training boundary

Only reviewed Gold can become training export.
Never train directly from raw journals or messy Bronze.
