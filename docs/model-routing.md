# Model Routing

This repo defaults to the most stable GPT-5 family route:
- first pass cheap
- deeper pass stronger
- only rare planning uses the most expensive tier

## Default routing

| Task class | Model | Effort | Why |
|---|---|---:|---|
| first query router | gpt-5.4-nano | none | cheapest classifier |
| first query handler | gpt-5.4-mini | low | fast and strong for most memory control |
| memory fast | gpt-5.4-mini | low | low latency retrieval |
| memory deep | gpt-5.4 | medium | stable multi-step synthesis |
| code light | gpt-5.4-mini | low | cheap light coding |
| code-heavy deep | gpt-5.4 | medium | stable default coding and implementation |
| code-heavy fallback | gpt-5.3-codex | high | optional legacy coding specialist |
| critic verify | gpt-5.4-mini | medium | cheap second pass |
| KAIROS daily | gpt-5.4 | medium | strategy synthesis |
| Dreaming | gpt-5.4 | medium | consolidation |
| rare xdeep | gpt-5.4-pro | high | only for hard long-form planning |

## Compatibility aliases

- `gpt-5.1-mini-tier` → `gpt-5.1-codex-mini`
- `gpt-5.3-high-tier` → `gpt-5.3-codex`
- `stable-default` → `gpt-5.4`
- `stable-mini` → `gpt-5.4-mini`
- `stable-nano` → `gpt-5.4-nano`

## Rule of thumb

- Router only classifies.
- Fast path answers from local evidence packs.
- Deep path synthesizes across state + SQL + vector.
- Rare xdeep is for difficult plans, not routine chat.

## Fine-tuning note

Do not fine-tune the main controller.
Fine-tune only secondary specialist models, and only from reviewed Gold.
