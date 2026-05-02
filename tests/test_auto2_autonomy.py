from __future__ import annotations

from types import SimpleNamespace


def _patch_paths(monkeypatch, tmp_path):
    paths = SimpleNamespace(
        repo_root=tmp_path,
        vault_path=tmp_path / "vault",
        sqlite_path=tmp_path / "sqlite.db",
        chroma_path=tmp_path / "chroma",
        bronze_root=tmp_path / "bronze",
        artifacts_root=tmp_path / "artifacts",
        logs_root=tmp_path / "logs",
        state_root=tmp_path / "state",
    )
    monkeypatch.setattr("otto.config.load_paths", lambda: paths)
    monkeypatch.setattr("otto.governance_utils.load_paths", lambda: paths)
    monkeypatch.setattr("otto.autonomy.note_vector.load_paths", lambda: paths)
    return paths


def _seed(score_song: float = 0.9) -> dict:
    return {
        "seed_id": "seed_song_1",
        "kind": "song",
        "source": "reviewed_private_sources",
        "source_vector_id": "nmv_test",
        "source_refs": ["state/handoff/latest.json"],
        "evidence_refs": ["state/handoff/latest.json"],
        "anchors": ["Continuity Prosthesis", "music", "memory"],
        "existential_atoms": [
            "I build systems because returning to myself is hard.",
            "The archive is not memory unless it calls me back.",
        ],
        "suffering_vector": {"longing": 0.82, "fatigue": 0.61, "tenderness": 0.74},
        "artifact_affinity": {"song": score_song, "paper_onboarding": 0.4},
        "review_required": True,
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
    }


def test_steering_vector_loads_required_song_and_research_rules(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    from otto.autonomy.steering_vector import load_steering_vector, steering_vector_health

    vector = load_steering_vector(write=False)
    health = steering_vector_health(vector)

    assert health["ok"] is True
    assert vector["identity"]["audio_engineer"] is True
    assert vector["identity"]["music_producer"] is True
    assert vector["song_rules"]["chord_first"] is True
    assert vector["song_rules"]["hash_is_context_anchor"] is True
    assert vector["song_rules"]["at_is_existential_atom"] is True
    assert vector["song_rules"]["one_atom_max_one_chord_cycle"] is True
    assert vector["song_rules"]["minimum_rhythm_routes"] >= 4
    assert vector["song_rules"]["midi_human_velocity_timing"] is True
    assert vector["research_rules"]["onboarding_before_critique"] is True
    assert vector["research_rules"]["school_community_as_social_room"] is True


def test_note_vector_requires_evidence_refs_and_never_qmd_indexes_raw_notes(monkeypatch, tmp_path):
    paths = _patch_paths(monkeypatch, tmp_path)
    (paths.repo_root / "state" / "handoff").mkdir(parents=True, exist_ok=True)
    (paths.repo_root / "state" / "handoff" / "latest.json").write_text('{"summary":"continuity memory music"}', encoding="utf-8")
    brain = paths.vault_path / ".Otto-Realm" / "Brain"
    brain.mkdir(parents=True, exist_ok=True)
    (brain / "continuity.md").write_text("# Returning to the Thread\nmusic memory archive", encoding="utf-8")

    from otto.autonomy.note_vector import build_note_vector

    result = build_note_vector(write=False)
    vector = result["note_vector"]

    assert result["ok"] is True
    assert vector["evidence_refs"]
    assert vector["raw_notes_dumped"] is False
    assert vector["qmd_index_allowed"] is False
    assert vector["review_required"] is True


def test_note_vector_without_sources_returns_no_evidence(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    from otto.autonomy.note_vector import build_note_vector, load_note_vectors

    result = build_note_vector(write=False)

    assert result["ok"] is False
    assert result["note_vector"]["evidence_refs"] == []
    assert load_note_vectors() == []


def test_seed_selector_chooses_highest_scoring_seed(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    high = {**_seed(0.95), "vector_id": "nmv_high", "anchors": ["music", "memory"], "artifact_affinity": {"song": 0.95}}
    low = {**_seed(0.3), "vector_id": "nmv_low", "anchors": ["paper"], "artifact_affinity": {"song": 0.3}}
    monkeypatch.setattr("otto.autonomy.seed_selector.load_note_vectors", lambda: [low, high])

    from otto.autonomy.seed_selector import select_seed

    result = select_seed("song", write=False)

    assert result["ok"] is True
    assert result["seed"]["source_vector_id"] == "nmv_high"
    assert result["seed"]["score"]["artifact_fit"] == 0.95


def test_autonomous_song_derives_hash_and_at_from_seed_and_stays_review_gated(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    from otto.creative.autonomous_song import build_autonomous_song_candidate

    result = build_autonomous_song_candidate(dry_run=True, seed=_seed())
    candidate = result["candidate"]

    assert result["ok"] is True
    assert candidate["derived_seed"]["context_anchors"][:2] == ["Continuity Prosthesis", "music"]
    assert "I build systems" in candidate["derived_seed"]["existential_atoms"][0]
    assert candidate["song_rules_applied"]["one_atom_max_one_chord_cycle"] is True
    assert len(candidate["rhythm_routes"]) >= 4
    assert candidate["midi_spec"]["humanize"]["velocity_variance"] > 0
    assert candidate["midi_spec"]["humanize"]["timing_ms_min"] > 0
    assert candidate["midi_spec"]["humanize"]["timing_ms_max"] > candidate["midi_spec"]["humanize"]["timing_ms_min"]
    assert candidate["review_required"] is True
    assert candidate["qmd_index_allowed"] is False
    assert candidate["vault_writeback_allowed"] is False
    assert candidate["auto_publish"] is False


def test_autonomous_paper_emits_onboarding_fields_and_stays_review_gated(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    from otto.research.autonomous_paper import build_autonomous_paper_candidate

    result = build_autonomous_paper_candidate(dry_run=True, seed={**_seed(), "anchors": ["interface", "constraint"]})
    candidate = result["candidate"]
    human_entry = candidate["human_entry"]

    assert result["ok"] is True
    assert candidate["onboarding_mode"] is True
    assert "who_are_these_people" in human_entry
    assert "what_problem_are_they_living_inside" in human_entry
    assert "what_is_obvious_to_them_but_not_to_me" in human_entry
    assert "what_jargon_should_i_survive_first" in human_entry
    assert "what_should_i_read_first" in human_entry
    assert "how_this_connects_to_my_work" in human_entry
    assert candidate["review_required"] is True
    assert candidate["qmd_index_allowed"] is False
    assert candidate["vault_writeback_allowed"] is False
    assert candidate["auto_publish"] is False


def test_autonomous_heartbeat_runs_due_jobs_without_human_reply(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("otto.autonomy.autonomous_generation.load_autonomous_generation_policy", lambda: {"version": 1})
    monkeypatch.setattr("otto.autonomy.autonomous_generation.autonomous_policy_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.autonomy.autonomous_generation.write_steering_vector", lambda: {"steering_vector": {}})
    monkeypatch.setattr("otto.autonomy.autonomous_generation.steering_vector_health", lambda vector=None: {"ok": True})
    monkeypatch.setattr("otto.autonomy.autonomous_generation.build_note_vector", lambda write=False: {"ok": True, "note_vector": {"evidence_refs": ["x"]}})
    monkeypatch.setattr(
        "otto.autonomy.autonomous_generation.next_due_autonomous_jobs",
        lambda: {"ok": True, "due_count": 1, "due": [{"job": "autonomous_song_skeleton", "kind": "song"}]},
    )
    monkeypatch.setattr(
        "otto.autonomy.autonomous_generation.generate_autonomous_candidate",
        lambda kind, dry_run=True: {"ok": True, "kind": kind, "candidate": {"review_required": True}},
    )

    from otto.autonomy.autonomous_generation import run_autonomous_heartbeat

    result = run_autonomous_heartbeat(dry_run=True)

    assert result["ok"] is True
    assert result["outputs"][0]["kind"] == "song"
    assert result["no_output_reason"] is None


def test_autonomous_heartbeat_no_seed_returns_no_output_reason(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("otto.autonomy.autonomous_generation.load_autonomous_generation_policy", lambda: {"version": 1})
    monkeypatch.setattr("otto.autonomy.autonomous_generation.autonomous_policy_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.autonomy.autonomous_generation.write_steering_vector", lambda: {"steering_vector": {}})
    monkeypatch.setattr("otto.autonomy.autonomous_generation.steering_vector_health", lambda vector=None: {"ok": True})
    monkeypatch.setattr("otto.autonomy.autonomous_generation.build_note_vector", lambda write=False: {"ok": False, "note_vector": {"evidence_refs": []}})
    monkeypatch.setattr(
        "otto.autonomy.autonomous_generation.next_due_autonomous_jobs",
        lambda: {"ok": True, "due_count": 1, "due": [{"job": "autonomous_song_skeleton", "kind": "song"}]},
    )
    monkeypatch.setattr(
        "otto.autonomy.autonomous_generation.generate_autonomous_candidate",
        lambda kind, dry_run=True: {"ok": False, "kind": kind, "no_output_reason": "no_note_vectors_available"},
    )

    from otto.autonomy.autonomous_generation import run_autonomous_heartbeat

    result = run_autonomous_heartbeat(dry_run=True)

    assert result["ok"] is True
    assert result["outputs"][0]["ok"] is False
    assert result["no_output_reason"] == "no_note_vectors_available"
