from __future__ import annotations

from pathlib import Path
from typing import Any

from ..corridor import ensure_jsonl_row
from ..governance_utils import find_jsonl, make_id, public_result, state_root
from .artifact_affinity import artifact_affinities
from .attention_vector import attention_metrics
from .profile_signal_vector import profile_signal_metrics
from .research_affinity import research_onboarding_fit
from .skill_vector import skill_gap_relevance
from .suffering_vector import suffering_vector_intensity


def feature_vectors_path() -> Path:
    return state_root() / "features" / "feature_vectors.jsonl"


def suffering_vectors_path() -> Path:
    return state_root() / "features" / "suffering_vectors.jsonl"


def skill_vectors_path() -> Path:
    return state_root() / "features" / "skill_vectors.jsonl"


def attention_vectors_path() -> Path:
    return state_root() / "features" / "attention_vectors.jsonl"


def profile_signal_vectors_path() -> Path:
    return state_root() / "features" / "profile_signal_vectors.jsonl"


def load_silver_event(event_id: str) -> dict[str, Any] | None:
    from ..normalize.source_normalizer import silver_events_path

    return find_jsonl(silver_events_path(), "event_id", event_id)


def create_feature_vector(event_id: str, *, dry_run: bool = True) -> dict[str, Any]:
    event = load_silver_event(event_id)
    if not event:
        return public_result(False, reason="event-id-not-found", event_id=event_id)
    text = str((event.get("content_unit") or {}).get("text") or "")
    entities = [str(item) for item in (event.get("entities") or [])]
    artifact = artifact_affinities(text)
    attention = attention_metrics(text)
    profile = profile_signal_metrics(text)
    suffering = suffering_vector_intensity(text)
    skill = skill_gap_relevance(text)
    research = research_onboarding_fit(text, entities)
    meaning_density = min(0.25 + len(text.split()) / 40.0, 0.98)
    training_value = min(
        (
            meaning_density
            + artifact["artifact_affinity_paper"]
            + artifact["artifact_affinity_prose"]
            + attention["memento_value"]
        )
        / 4.0,
        0.99,
    )
    payload = {
        "feature_vector_id": make_id("fv"),
        "from_event_id": event_id,
        "state": "FEATURE_VECTOR",
        "vector_type": "diagnostic_generative",
        "dimensions": {
            "meaning_density": round(meaning_density, 4),
            **{key: round(value, 4) for key, value in artifact.items()},
            "research_onboarding_fit": round(research, 4),
            "song_seed_affinity": round(artifact["artifact_affinity_song"], 4),
            "skill_gap_relevance": round(skill, 4),
            "weakness_relevance": round(profile["weakness_relevance"], 4),
            "suffering_vector_intensity": round(suffering, 4),
            "attention_reentry_value": round(attention["attention_reentry_value"], 4),
            "memento_value": round(attention["memento_value"], 4),
            "training_value": round(training_value, 4),
            "training_export_risk": round(profile["training_export_risk"], 4),
            "sensitivity_risk": round(profile["sensitivity_risk"], 4),
        },
        "qmd_index_allowed": False,
        "evidence_refs": [event_id],
    }
    if not dry_run:
        ensure_jsonl_row(feature_vectors_path(), payload)
        ensure_jsonl_row(suffering_vectors_path(), {"feature_vector_id": payload["feature_vector_id"], "value": payload["dimensions"]["suffering_vector_intensity"]})
        ensure_jsonl_row(skill_vectors_path(), {"feature_vector_id": payload["feature_vector_id"], "value": payload["dimensions"]["skill_gap_relevance"]})
        ensure_jsonl_row(attention_vectors_path(), {"feature_vector_id": payload["feature_vector_id"], **attention})
        ensure_jsonl_row(profile_signal_vectors_path(), {"feature_vector_id": payload["feature_vector_id"], **profile})
    return public_result(True, dry_run=dry_run, feature_vector=payload)
