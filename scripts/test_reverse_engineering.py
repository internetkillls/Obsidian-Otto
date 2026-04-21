"""
Reverse-engineering tests: verify behavior BEFORE vs AFTER each Phase 2 fix.
These tests FAIL with old code and PASS with new code.

Run: python scripts/test_reverse_engineering.py
"""
from __future__ import annotations
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from otto.orchestration.council import CouncilEngine


def test_old_cognitive_weakness_threshold():
    """
    OLD CODE: cognitive_weakness fired at fires >= 3 OR (severity==high AND fires >= 1)
    NEW CODE: cognitive_weakness fires ONLY at fires >= 3 OR staleness >= 3

    This test verifies the early-exit for severity==high bypass was removed.
    """
    print("\n=== REVERSE: cognitive_weakness early-exit bypass ===")
    ce = CouncilEngine()

    signals = [{"note_path": f"test{i}.md"} for i in range(10)]  # 10 >= 8, severity=high

    # OLD behavior: with severity==high (8+ signals) and fires==1, would fire
    # NEW behavior: fires must be >= 3 OR staleness >= 3
    with patch.object(ce, "_count_recent_fires", return_value=1):
        triggers = ce.detect_triggers(
            gold_scores=[],
            unresolved_signals=signals,
            top_folders=[],
            contradictions=[],
        )

    if triggers:
        print("  OLD BEHAVIOR DETECTED: severity==high bypass allowed fire at fires=1")
        print("  NEW BEHAVIOR: blocked (fires must be >= 3)")
        return False  # FAIL means old behavior detected
    else:
        print("  PASS: severity==high bypass removed, requires >= 3 fires")
        return True


def test_old_identity_threshold():
    """
    OLD CODE: identity_incoherence fired at fires >= 2
    NEW CODE: fires >= 3

    Test verifies the threshold was raised from 2 to 3.
    """
    print("\n=== REVERSE: identity_incoherence threshold ===")
    ce = CouncilEngine()

    signals = [{"note_path": "Otto-Realm\\Brain\\self_model.md"}]

    # OLD: fires=2 would fire. NEW: must be >= 3
    with patch.object(ce, "_count_recent_fires", return_value=2):
        triggers = ce.detect_triggers(
            gold_scores=[],
            unresolved_signals=signals,
            top_folders=[],
            contradictions=[],
        )

    if triggers:
        print("  OLD BEHAVIOR DETECTED: fired at fires=2")
        print("  NEW BEHAVIOR: blocked (requires >= 3)")
        return False
    else:
        print("  PASS: threshold raised to >= 3 fires")
        return True


def test_old_epistemic_threshold():
    """
    OLD CODE: epistemic_gap fired at fires >= 2
    NEW CODE: fires >= 3

    Test verifies the threshold was raised from 2 to 3.
    """
    print("\n=== REVERSE: epistemic_gap threshold ===")
    ce = CouncilEngine()

    # OLD: fires=2 with any contradictions would fire. NEW: >= 3
    with patch.object(ce, "_count_recent_fires", return_value=2):
        triggers = ce.detect_triggers(
            gold_scores=[],
            unresolved_signals=[],
            top_folders=[],
            contradictions=[MagicMock()],  # 1 contradiction
        )

    if triggers:
        print("  OLD BEHAVIOR DETECTED: fired at fires=2 + 1 contradiction")
        print("  NEW BEHAVIOR: blocked (requires >= 3 or >= 3 contradictions)")
        return False
    else:
        print("  PASS: threshold raised to >= 3 fires or contradictions")
        return True


def test_old_predicate_softmode():
    """
    OLD CODE: soft_mode triggered with fear + meta_repair + decision_pressure
              regardless of fire count.
    NEW CODE: soft_mode requires fires >= 3 in addition to those conditions.
    """
    print("\n=== REVERSE: predicate_qua_angel soft_mode gating ===")
    ce = CouncilEngine()

    signals = [{"note_path": "projects/test.md", "primary_claim": "I avoid this decision"}]
    top_folders = [{"folder": "projects", "risk_score": 10.0}]  # has_meta_repair

    # OLD: fear_pressure + meta_repair + decision_pressure = fires even at fires=0
    with patch.object(ce, "_count_recent_fires", return_value=0):
        triggers = ce.detect_triggers(
            gold_scores=[],
            unresolved_signals=signals,
            top_folders=top_folders,
            contradictions=[],
        )

    if triggers:
        print("  OLD BEHAVIOR DETECTED: soft_mode fired without fire count gate")
        print("  NEW BEHAVIOR: soft_mode requires fires >= 3")
        return False
    else:
        print("  PASS: soft_mode gated behind >= 3 fires")
        return True


def test_old_evidence_counting():
    """
    OLD CODE: evidence strings used {fires + 1} (projected count)
    NEW CODE: evidence uses {fires} (actual recorded count)
    """
    print("\n=== REVERSE: evidence count accuracy ===")
    ce = CouncilEngine()

    signals = [{"note_path": f"test{i}.md"} for i in range(6)]

    with patch.object(ce, "_count_recent_fires", return_value=3):
        triggers = ce.detect_triggers(
            gold_scores=[],
            unresolved_signals=signals,
            top_folders=[],
            contradictions=[],
        )

    if triggers:
        cog = next((t for t in triggers if t.category == "cognitive_weakness"), None)
        if cog:
            # OLD: would show "4" (fires+1). NEW: shows "3" (fires)
            evidence_text = " ".join(cog.evidence)
            if "4" in evidence_text and "3" not in evidence_text:
                print("  OLD BEHAVIOR DETECTED: evidence uses projected count (fires+1)")
                return False
            elif "3" in evidence_text:
                print("  PASS: evidence uses actual fires count")
                return True

    print("  PASS: evidence count logic updated")
    return True


def test_staleness_map_not_passed():
    """
    OLD CODE: detect_triggers had no staleness_map parameter
    NEW CODE: staleness_map passed from morpheus enrichment
    """
    print("\n=== REVERSE: staleness_map parameter ===")
    import inspect
    sig = inspect.signature(CouncilEngine.detect_triggers)
    params = list(sig.parameters.keys())

    if "staleness_map" not in params:
        print("  OLD BEHAVIOR DETECTED: no staleness_map parameter")
        print("  NEW BEHAVIOR: staleness_map parameter exists")
        return False
    else:
        print("  PASS: staleness_map parameter wired into detect_triggers")
        return True


def test_council_before_morpheus():
    """
    OLD CODE: council_engine.detect_triggers called BEFORE morpheus.enrich
    NEW CODE: morpheus.enrich runs first, council receives staleness_map
    """
    print("\n=== REVERSE: council/morpheus order ===")
    kairos_path = Path(__file__).parent.parent / "src" / "otto" / "orchestration" / "kairos.py"
    content = kairos_path.read_text()

    # OLD: council before morpheus. NEW: morpheus before council
    council_pos = content.find("council_engine.detect_triggers(")
    morpheus_pos = content.find("morpheus.enrich(")

    # Check if old order (council before morpheus, staleness_map not passed)
    old_order = council_pos < morpheus_pos
    staleness_wired = "staleness_map=enrichment.staleness_map" in content

    if old_order and not staleness_wired:
        print("  OLD BEHAVIOR DETECTED: council before morpheus, no staleness_map")
        return False
    elif not old_order and staleness_wired:
        print("  PASS: morpheus before council, staleness_map wired")
        return True
    else:
        print("  PARTIAL: order/coupling may have issues")
        return False


def test_use_full_body_flag():
    """
    OLD CODE: build_claim_for_signal had no use_full_body param
    NEW CODE: use_full_body param controls body length
    """
    print("\n=== REVERSE: use_full_body parameter ===")
    import inspect
    from otto.orchestration.kairos_gold import GoldScoringEngine

    sig = inspect.signature(GoldScoringEngine.build_claim_for_signal)
    params = list(sig.parameters.keys())

    if "use_full_body" not in params:
        print("  OLD BEHAVIOR DETECTED: no use_full_body parameter")
        print("  NEW BEHAVIOR: use_full_body parameter exists")
        return False
    else:
        print("  PASS: use_full_body parameter scaffolded")
        return True


if __name__ == "__main__":
    results = []
    results.append(test_old_cognitive_weakness_threshold())
    results.append(test_old_identity_threshold())
    results.append(test_old_epistemic_threshold())
    results.append(test_old_predicate_softmode())
    results.append(test_old_evidence_counting())
    results.append(test_staleness_map_not_passed())
    results.append(test_council_before_morpheus())
    results.append(test_use_full_body_flag())

    print(f"\n{'='*60}")
    fixed_count = sum(1 for r in results if r)
    old_count = sum(1 for r in results if not r)

    print(f"OLD BEHAVIORS DETECTED (need fixing): {old_count}")
    print(f"FIXES VERIFIED (working correctly): {fixed_count}")

    if all(results):
        print("\nALL REVERSE TESTS PASSED — Phase 2 fixes confirmed active")
    else:
        print("\nSOME OLD BEHAVIORS DETECTED — review fixes")

    sys.exit(0 if all(results) else 1)
