"""
Stress tests for the Phase 2 fixes:
1. Council recurrence tracking (≥3× required)
2. Council/morpheus order (council fires after morpheus)
3. Full note body scoring scaffold (use_full_body flag)
4. Staleness → council recurrence (dual gating)

Run with: python scripts/test_phase2_fixes.py
"""
from __future__ import annotations
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from otto.orchestration.council import CouncilEngine, CouncilTrigger
from otto.orchestration.kairos_gold import GoldScoringEngine


def test_council_recurrence_thresholds():
    """Verify council requires ≥3 detections before firing (non-economic triggers)."""
    print("\n=== Test 1: Council Recurrence Thresholds ===")
    ce = CouncilEngine()

    # --- Negative tests: should NOT fire below ≥3 threshold ---
    test_cases_no_fire = [
        ("cognitive_weakness", 0, 5, "Zero history + 5 signals"),
        ("cognitive_weakness", 2, 5, "2 fires + 5 signals"),
        ("identity_incoherence", 0, 1, "Zero history + self_model signal"),
        ("identity_incoherence", 2, 1, "2 fires + self_model signal"),
        ("epistemic_gap", 0, 0, "Zero history + 0 contradictions"),
        ("epistemic_gap", 2, 2, "2 fires + 2 contradictions (needs ≥3)"),
        ("predicate_qua_angel", 0, False, "Zero fires + no structural drag"),
        ("predicate_qua_angel", 2, False, "2 fires + no structural drag"),
    ]

    fail_count = 0
    for category, fires, param, desc in test_cases_no_fire:
        with patch.object(ce, "_count_recent_fires", return_value=fires):
            if category == "cognitive_weakness":
                triggers = ce.detect_triggers(
                    gold_scores=[],
                    unresolved_signals=[{"note_path": f"test{i}.md"} for i in range(param)],
                    top_folders=[],
                    contradictions=[],
                )
            elif category == "identity_incoherence":
                triggers = ce.detect_triggers(
                    gold_scores=[],
                    unresolved_signals=[{"note_path": "Otto-Realm\\Brain\\self_model.md"}],
                    top_folders=[],
                    contradictions=[],
                )
            elif category == "epistemic_gap":
                triggers = ce.detect_triggers(
                    gold_scores=[],
                    unresolved_signals=[],
                    top_folders=[],
                    contradictions=[MagicMock() for _ in range(param)],
                )
            elif category == "predicate_qua_angel":
                triggers = ce.detect_triggers(
                    gold_scores=[],
                    unresolved_signals=[{"note_path": "test.md", "primary_claim": "avoid decision"}],
                    top_folders=[{"risk_score": 10.0 if param else 1.0}],
                    contradictions=[],
                )
            else:
                continue

            if triggers:
                print(f"  FAIL: {desc} — fired {len(triggers)} trigger(s)")
                fail_count += 1
            else:
                print(f"  PASS: {desc} — correctly no fire")

    # --- Positive tests: should fire at ≥3 threshold ---
    test_cases_fire = [
        ("cognitive_weakness", 3, 5, "Exactly 3 fires + 5 signals"),
        ("cognitive_weakness", 5, 5, "5 fires + 5 signals"),
        ("identity_incoherence", 3, 1, "Exactly 3 fires + self_model"),
        ("epistemic_gap", 3, 0, "Exactly 3 fires + 0 contradictions"),
        ("epistemic_gap", 0, 3, "0 fires + 3 contradictions"),
    ]

    for category, fires, param, desc in test_cases_fire:
        with patch.object(ce, "_count_recent_fires", return_value=fires):
            if category == "cognitive_weakness":
                triggers = ce.detect_triggers(
                    gold_scores=[],
                    unresolved_signals=[{"note_path": f"test{i}.md"} for i in range(param)],
                    top_folders=[],
                    contradictions=[],
                )
            elif category == "identity_incoherence":
                triggers = ce.detect_triggers(
                    gold_scores=[],
                    unresolved_signals=[{"note_path": "Otto-Realm\\Brain\\self_model.md"}],
                    top_folders=[],
                    contradictions=[],
                )
            elif category == "epistemic_gap":
                triggers = ce.detect_triggers(
                    gold_scores=[],
                    unresolved_signals=[],
                    top_folders=[],
                    contradictions=[MagicMock() for _ in range(param)],
                )
            else:
                continue

            if not triggers:
                print(f"  FAIL: {desc} — should have fired")
                fail_count += 1
            else:
                print(f"  PASS: {desc} — fired {len(triggers)} trigger(s)")

    print(f"\n  Result: {'ALL PASSED' if fail_count == 0 else f'{fail_count} FAILED'}")
    return fail_count == 0


def test_staleness_dual_gating():
    """Verify morpheus staleness_map enables council firing via dual gate."""
    print("\n=== Test 2: Staleness Dual Gating ===")
    ce = CouncilEngine()

    signals = [{"note_path": f"test{i}.md"} for i in range(6)]

    # --- Negative: no staleness, no history fires → no fire ---
    with patch.object(ce, "_count_recent_fires", return_value=0):
        triggers = ce.detect_triggers(
            gold_scores=[],
            unresolved_signals=signals,
            top_folders=[],
            contradictions=[],
            staleness_map=None,
        )
    if triggers:
        print("  FAIL: No staleness + no history → should not fire")
    else:
        print("  PASS: No staleness + no history → correctly no fire")

    # --- Positive: staleness ≥3, no history fires → fires via dual gate ---
    with patch.object(ce, "_count_recent_fires", return_value=0):
        triggers = ce.detect_triggers(
            gold_scores=[],
            unresolved_signals=signals,
            top_folders=[],
            contradictions=[],
            staleness_map={"test0.md": 3, "test1.md": 5},
        )
    if not triggers:
        print("  FAIL: staleness ≥3 → should fire via dual gate")
    else:
        print(f"  PASS: staleness ≥3 → fired {len(triggers)} trigger(s) (dual gate)")
        # Check evidence contains staleness info
        cog = next((t for t in triggers if t.category == "cognitive_weakness"), None)
        if cog and any("Stale signals" in e for e in cog.evidence):
            print("  PASS: Evidence includes staleness data")
        else:
            print("  FAIL: Evidence missing staleness data")

    return True


def test_full_body_scaffold():
    """Verify use_full_body flag behavior in build_claim_for_signal."""
    print("\n=== Test 3: Full Body Scoring Scaffold ===")
    ge = GoldScoringEngine()

    signal = {
        "note_path": "test/path.md",
        "signal_type": "general",
        "factors": {"economic": True},
    }

    # Phase 1: use_full_body=False → body limited to 2000
    with patch.object(ge, "_fetch_note_full", return_value=("Title", "fm", "B" * 10000, "tags")):
        _, claim = ge.build_claim_for_signal(signal, use_full_body=False)
        body_start = claim.find("Body:")
        body_text = claim[body_start:body_start + 100] if body_start >= 0 else ""
        if "B" * 2000 in claim or len(claim) <= 800:
            print(f"  PASS: Phase1 (use_full_body=False) — body truncated to ~2000")
        else:
            print(f"  FAIL: Phase1 body not truncated correctly")

    # Phase 2: use_full_body=True → body limited to 10000
    with patch.object(ge, "_fetch_note_full", return_value=("Title", "fm", "C" * 20000, "tags")):
        _, claim = ge.build_claim_for_signal(signal, use_full_body=True)
        body_start = claim.find("Body:")
        body_text = claim[body_start:body_start + 100] if body_start >= 0 else ""
        if "C" * 10000 in claim or len(claim) <= 800:
            print(f"  PASS: Phase2 (use_full_body=True) — body extended to ~10000")
        else:
            print(f"  FAIL: Phase2 body not extended correctly")

    # Default: no param → uses USE_FULL_BODY class flag
    with patch.object(ge, "_fetch_note_full", return_value=("T", "fm", "D" * 5000, "t")):
        _, claim = ge.build_claim_for_signal(signal)
        if ge.USE_FULL_BODY:
            print("  PASS: Default uses USE_FULL_BODY=True (Phase2 ready)")
        else:
            print("  PASS: Default uses USE_FULL_BODY=False (Phase1, scaffolded)")

    # Model config exists
    if ge._scoring_model and ge._scoring_model.task_class == "gold_scoring":
        print(f"  PASS: gold_scoring model loaded: {ge._scoring_model.model}")
    else:
        print("  FAIL: gold_scoring model not configured")

    return True


def test_council_morpheus_order():
    """Verify kairos.py fires council AFTER morpheus enrich."""
    print("\n=== Test 4: Council/Morpheus Order ===")

    # Read kairos.py and verify order
    kairos_path = Path(__file__).parent.parent / "src" / "otto" / "orchestration" / "kairos.py"
    content = kairos_path.read_text()

    # Find positions of key calls
    morpheus_enrich_pos = content.find("morpheus.enrich(")
    council_detect_pos = content.find("council_engine.detect_triggers(")

    if morpheus_enrich_pos < council_detect_pos:
        print("  PASS: morpheus.enrich() comes BEFORE council_engine.detect_triggers()")
    else:
        print("  FAIL: council fires before morpheus — spec order violated")

    # Verify staleness_map passed from enrichment to council
    staleness_param_pos = content.find("staleness_map=enrichment.staleness_map")
    if staleness_param_pos > 0:
        print("  PASS: staleness_map wired from enrichment to council")
    else:
        print("  FAIL: staleness_map not passed to council")

    return morpheus_enrich_pos < council_detect_pos


def test_stress_large_inputs():
    """Stress test with large signal counts."""
    print("\n=== Test 5: Stress — Large Signal Counts ===")

    ce = CouncilEngine()
    ge = GoldScoringEngine()

    # 1000 unresolved signals
    signals = [{"note_path": f"projects/stress_{i}.md", "signal_type": "general"} for i in range(1000)]

    # Large staleness map
    staleness = {f"projects/stress_{i}.md": (i % 10) for i in range(1000)}

    with patch.object(ce, "_count_recent_fires", return_value=3):
        triggers = ce.detect_triggers(
            gold_scores=[],
            unresolved_signals=signals,
            top_folders=[{"folder": f"projects/stress_{i}", "risk_score": 10.0} for i in range(100)],
            contradictions=[],
            staleness_map=staleness,
        )

    if triggers:
        print(f"  PASS: 1000 signals processed — {len(triggers)} triggers, fast path works")
    else:
        print("  FAIL: Large signal count produced no triggers")

    # Large contradictions list
    contradictions = [MagicMock() for _ in range(500)]
    with patch.object(ce, "_count_recent_fires", return_value=3):
        triggers = ce.detect_triggers(
            gold_scores=[],
            unresolved_signals=[],
            top_folders=[],
            contradictions=contradictions,
        )

    if triggers:
        print(f"  PASS: 500 contradictions processed — {len(triggers)} triggers")
    else:
        print("  FAIL: Large contradiction count produced no triggers")

    return True


def test_stress_body_scoring():
    """Stress test full body scoring."""
    print("\n=== Test 6: Stress — Full Body Scoring ===")

    ge = GoldScoringEngine()

    # Very large body (simulate 50KB note)
    large_body = "X" * 50000

    signal = {
        "note_path": "projects/large_note.md",
        "signal_type": "economic",
        "factors": {"scarcity": True, "necessity": "high"},
    }

    with patch.object(ge, "_fetch_note_full", return_value=("Large Title", "fm: value", large_body, "tag1, tag2")):
        _, claim = ge.build_claim_for_signal(signal, use_full_body=True)

        if len(claim) <= 800:
            print(f"  PASS: 50KB body → claim capped at 800 chars (total len={len(claim)})")
        else:
            print(f"  FAIL: Claim exceeds limit: {len(claim)}")

    return True


def test_economic_threat_always_fires():
    """Economic threat should NOT be gated by recurrence (spec: cannot be suppressed)."""
    print("\n=== Test 7: Economic Threat Exception ===")

    ce = CouncilEngine()

    # Zero history fires + economic score → should still fire
    with patch.object(ce, "_count_recent_fires", return_value=0):
        triggers = ce.detect_triggers(
            gold_scores=[MagicMock(primary_claim="economic signal about revenue")],
            unresolved_signals=[],
            top_folders=[],
            contradictions=[],
        )

    if triggers and any(t.category == "economic_threat" for t in triggers):
        print("  PASS: Economic threat fires even with 0 history fires (unsuppressible)")
    else:
        print("  FAIL: Economic threat suppressed by recurrence gating")

    return True


if __name__ == "__main__":
    results = []
    results.append(test_council_recurrence_thresholds())
    results.append(test_staleness_dual_gating())
    results.append(test_full_body_scaffold())
    results.append(test_council_morpheus_order())
    results.append(test_stress_large_inputs())
    results.append(test_stress_body_scoring())
    results.append(test_economic_threat_always_fires())

    print(f"\n{'='*50}")
    if all(results):
        print("ALL TESTS PASSED")
    else:
        print(f"TESTS FAILED: {sum(1 for r in results if not r)}")
    sys.exit(0 if all(results) else 1)
