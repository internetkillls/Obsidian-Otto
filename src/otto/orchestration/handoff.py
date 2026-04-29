from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import state_root
from ..memory.gold import gold_counts
from ..memory.review_queue import review_counts
from ..profile.profile_policy import profile_policy_health
from ..state import now_iso, write_json
from .action_queue import default_action


def daily_handoff_path() -> Path:
    return state_root() / "human" / "daily_handoff.json"


def build_daily_handoff() -> dict[str, Any]:
    action = default_action()
    profile = profile_policy_health()
    reviews = review_counts()
    gold = gold_counts()
    return {
        "version": 1,
        "handoff_id": "handoff_" + now_iso()[:10],
        "state": "HL1_DAILY_HANDOFF_READY",
        "date": now_iso()[:10],
        "mode": "dry_run",
        "generated_at": now_iso(),
        "runtime_summary": {
            "runtime_state": "S2C_WSL_SHADOW_GATEWAY_READY",
            "runtime_smoke": "AVAILABLE",
            "qmd_state": "Q6_RETRIEVAL_READY",
            "openclaw_shadow_gateway": "reachable_or_pending_probe",
            "telegram_shadow_enabled": False,
        },
        "memory_summary": {
            **reviews,
            **gold,
            "candidate_items_blocked_from_qmd": True,
        },
        "profile_council_summary": {
            "profile_policy": profile["profile_policy"],
            "diagnostic_inference_allowed": False,
            "support_contexts": ["AuDHD", "BD"],
            "council_policy": "green",
            "unreviewed_council_to_qmd_blocked": True,
        },
        "what_changed": [
            "Writeback, memory spine, review queue, and profile/council policies are available.",
            "Otto can now create candidates without treating them as durable truth.",
        ],
        "why_it_matters": [
            "The system can help choose actions instead of only maintaining infrastructure.",
            "Weakness/support framing stays reviewed and non-diagnostic.",
        ],
        "active_weakness_or_support_lens": {
            "lens": "context_switching_cost",
            "safe_framing": "re-entry support need, not pathology",
            "support_hint": "Use a small action and a handoff anchor.",
        },
        "smallest_meaningful_next_action": action,
        "what_not_to_do_yet": [
            "Do not start Instagram production OAuth.",
            "Do not enable Telegram canary.",
            "Do not write unreviewed council/profile statements to Vault.",
            "Do not expand into prediction models before outcome capture exists.",
        ],
        "what_needs_review_before_memory": [
            "Any profile hypothesis",
            "Any council synthesis",
            "Any weakness statement intended for Vault/QMD",
        ],
    }


def write_daily_handoff() -> dict[str, Any]:
    handoff = build_daily_handoff()
    write_json(daily_handoff_path(), handoff)
    return {"ok": True, "path": str(daily_handoff_path()), "handoff": handoff}
