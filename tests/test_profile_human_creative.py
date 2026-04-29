from __future__ import annotations

from types import SimpleNamespace

from otto.artifacts.artifact_router import triage_ideas
from otto.artifacts.idea_capture import capture_idea
from otto.artifacts.production_brief import create_production_brief
from otto.council.policy import load_council_policy, normalize_role_name
from otto.creative.song_seed import persist_song_seed
from otto.creative.songforge import build_song_skeleton
from otto.creative.vocal_chop import load_vocal_chop_policy
from otto.memento.quizworthy import ingest_gold
from otto.orchestration.creative_cron import production_cron_plan
from otto.orchestration.creative_heartbeat import run_creative_heartbeat
from otto.orchestration.daily_loop import run_daily_loop
from otto.orchestration.human_loop_closure import close_human_loop
from otto.profile.profile_policy import evaluate_profile_claim, load_profile_policy
from otto.profile.support_context import load_support_context
from otto.research.paper_onboarding import create_onboarding_pack
from otto.skills.blocker_map import load_blocker_map, skill_review
from otto.skills.skill_graph import load_skill_hierarchy


def _patch_paths(monkeypatch, tmp_path):
    paths = SimpleNamespace(state_root=tmp_path / "state", vault_path=tmp_path / "vault")
    monkeypatch.setattr("otto.governance_utils.load_paths", lambda: paths)
    return paths


def test_audhd_bd_context_is_declared_only(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    policy = load_profile_policy()
    context = load_support_context()

    assert policy["diagnostic_inference_allowed"] is False
    assert policy["clinical_labels_allowed"] == "declared_or_verified_only"
    assert context["use_as"] == "support_context_not_diagnosis"


def test_candidate_profile_claim_cannot_export(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    result = evaluate_profile_claim({"state": "PROFILE_HYPOTHESIS", "evidence_refs": ["fp_1"]})

    assert result["qmd_index_allowed"] is False
    assert result["vault_writeback_allowed"] is False


def test_council_policy_maps_therapist_and_uses_functional_boundary(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    policy = load_council_policy()

    assert normalize_role_name("therapist") == "stabilizer"
    assert policy["clinical_boundary"]["diagnosis_allowed"] is False
    assert "therapist" in policy["clinical_boundary"]["deprecated_role_names"]


def test_daily_loop_dry_run_has_no_unsafe_side_effects(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    result = run_daily_loop(dry_run=True)

    assert result["ok"] is True
    assert result["side_effects"]["vault_write"] is False
    assert result["side_effects"]["qmd_reindex"] is False
    assert result["side_effects"]["gold_promotion"] is False
    assert result["side_effects"]["telegram_enabled"] is False


def test_close_human_loop_creates_reflection_candidate(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    daily = run_daily_loop(dry_run=True)
    from otto.orchestration.action_queue import list_actions

    action_id = list_actions()[-1]["action_id"]
    result = close_human_loop(action_id, dry_run=True)

    assert daily["ok"] is True
    assert result["ok"] is True
    assert result["reflection"]["review_required"] is True
    assert result["reflection"]["qmd_index_allowed"] is False


def test_artifact_capture_router_brief_and_skill_map(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    idea = capture_idea("gateway under gateway as continuity prosthesis")["idea"]
    routes = triage_ideas(dry_run=True)["routes"]
    brief = create_production_brief(idea["idea_id"], artifact_type="song")["brief"]
    skills = load_skill_hierarchy()
    blockers = load_blocker_map()

    assert idea["qmd_index_allowed"] is False
    assert routes[0]["recommended_route"]["primary"] in {"essay", "song", "prose", "skill_drill"}
    assert "harmonic_or_midi_sketch" in brief["required_parts"]
    assert "music_production" in skills["domains"]
    assert blockers["blockers"]


def test_cron_plan_and_release_boundaries(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    plan = production_cron_plan()

    assert plan["auto_publish"] is False
    assert plan["review_required_before_publication"] is True


def test_song_seed_and_songforge_rules(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    parsed = persist_song_seed("# Cinta Fana\n@ Saya benci ketika tahu saya sungguh mencintai hidup yang fana.", dry_run=True)
    skeleton = build_song_skeleton("# Cinta Fana\n@ Saya benci ketika tahu saya sungguh mencintai hidup yang fana.", dry_run=True)

    assert parsed["seed"]["qmd_index_allowed"] is False
    assert parsed["atoms"][0]["max_chord_cycles"] == 1
    assert skeleton["skeleton"]["one_atom_max_chord_cycles"] == 1
    assert len(skeleton["rhythms"]) >= 4
    assert skeleton["lyric"]["direct_meaning_hidden"] is True
    assert skeleton["midi_spec"]["humanize"]["velocity_base"] == 82


def test_research_memento_vocal_and_heartbeat_policies(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    pack = create_onboarding_pack("interface constraints", dry_run=True)["pack"]
    rejected = ingest_gold({"state": "CANDIDATE", "title": "raw"})
    vocal = load_vocal_chop_policy()
    heartbeat = run_creative_heartbeat(dry_run=True)
    blocker = skill_review(dry_run=True)

    assert pack["state"] == "ONBOARDING_PACK_CANDIDATE"
    assert pack["qmd_index_allowed"] is False
    assert rejected["ok"] is False
    assert vocal["vocal_chop_policy"]["youtube_download_allowed"] is False
    assert heartbeat["auto_publish_blocked"] is True
    assert blocker["tasks"][0]["duration_minutes"] <= 45
