# Data Zones

## Bronze
Purpose:
- raw note inventory
- frontmatter extraction
- links / tags / sizes
- minimal assumptions

Rules:
- never train from Bronze
- never dump Bronze into the model by default

## Silver
Purpose:
- clean relational storage
- queryable note metadata
- folder and note normalization
- SQL-backed retrieval

Rules:
- first structured source for fast retrieval
- source of truth for note metadata

## Gold
Purpose:
- decision-ready summaries
- folder risk scoring
- training readiness
- retrieval bundles
- KAIROS-ready strategy input

Rules:
- main package for Codex answers
- reviewed Gold only for training export
