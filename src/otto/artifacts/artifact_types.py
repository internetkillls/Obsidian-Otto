from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


VALID_ARTIFACT_TYPES = {"song", "midi_sketch", "lyrics", "prose", "essay", "skill_drill", "inspo_pack"}


DEFAULT_ARTIFACT_TYPE_POLICY: dict[str, Any] = {
    "version": 1,
    "artifact_types": {
        "song": {
            "required_parts": [
                "concept",
                "mood",
                "lyrics_or_vocal_direction",
                "harmonic_or_midi_sketch",
                "arrangement_notes",
                "sound_palette",
                "mix_reference",
                "release_intent",
            ],
            "outputs": ["song_brief", "lyrics", "midi_sketch", "arrangement_plan", "mix_notes"],
            "review_required_before_publication": True,
        },
        "midi_sketch": {
            "required_parts": ["tempo", "meter", "key_or_mode", "chord_logic", "motif", "section_map"],
            "outputs": ["midi_spec", "piano_roll_description", "export_instruction"],
            "review_required_before_publication": False,
        },
        "lyrics": {
            "required_parts": ["voice", "theme", "imagery", "structure", "emotional_turn", "prosody_notes"],
            "outputs": ["lyric_draft", "rhyme_map", "revision_notes"],
            "review_required_before_publication": True,
        },
        "prose": {
            "required_parts": ["voice", "fragment_source", "scene_or_argument", "tone", "publication_shape"],
            "outputs": ["prose_draft", "editorial_notes", "anthology_slot"],
            "review_required_before_publication": True,
        },
        "essay": {
            "required_parts": ["thesis", "question", "source_refs", "argument_map", "counterargument", "audience"],
            "outputs": ["essay_brief", "outline", "draft", "bibliographic_notes"],
            "review_required_before_publication": True,
        },
        "skill_drill": {
            "required_parts": ["skill", "blocker", "current_level", "next_micro_task", "done_signal"],
            "outputs": ["practice_task", "rubric", "reflection_prompt"],
            "review_required_before_publication": False,
        },
        "inspo_pack": {
            "required_parts": ["query", "source_preference", "usage_note"],
            "outputs": ["reference_pointer"],
            "review_required_before_publication": True,
        },
    },
}


DEFAULT_CREATIVE_COUNCIL_POLICY: dict[str, Any] = {
    "version": 1,
    "lenses": [
        {"id": "producer", "question": "What makes this artifact finishable and emotionally coherent?"},
        {"id": "audio_engineer", "question": "What sonic decisions are needed for translation and impact?"},
        {"id": "philosopher", "question": "What concept is actually being argued or expressed?"},
        {"id": "editor", "question": "What should be cut, clarified, or continued?"},
        {"id": "audience_advocate", "question": "Why would a human care about this?"},
        {"id": "contrarian", "question": "Where is this artifact self-indulgent, unclear, or unfinished?"},
        {"id": "craft_mentor", "question": "What is the next practice move?"},
    ],
    "synthesis_must_include": [
        "artifact_strength",
        "weakness_point",
        "next_revision",
        "finishability_score",
        "human_meaning",
        "publication_readiness",
    ],
}


def artifact_type_policy_path() -> Path:
    return state_root() / "artifacts" / "artifact_type_policy.json"


def creative_council_policy_path() -> Path:
    return state_root() / "artifacts" / "creative_council_policy.json"


def load_artifact_type_policy() -> dict[str, Any]:
    return ensure_json(artifact_type_policy_path(), DEFAULT_ARTIFACT_TYPE_POLICY)


def load_creative_council_policy() -> dict[str, Any]:
    return ensure_json(creative_council_policy_path(), DEFAULT_CREATIVE_COUNCIL_POLICY)
