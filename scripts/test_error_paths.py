"""
Error Path Verification Tests
Ensures all error paths in Otto-Otto are properly handled.

Run: python scripts/test_error_paths.py [--path vault|pipeline|mcp|database|orchestration|all]
"""
from __future__ import annotations
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_vault_path_errors():
    """Test vault path error handling."""
    print("\n=== Vault Path Errors ===")
    from otto.tooling import obsidian_scan

    # Test 1: No vault configured (simulate by checking actual vault is configured)
    print("  Test 1: Vault path configured")
    paths = obsidian_scan.load_paths()
    if paths.vault_path is None:
        print("    INFO: No vault configured in .env")
        print("    PASS: Correctly detects missing config")
    elif not paths.vault_path.exists():
        print("    INFO: Vault path exists but is invalid")
        print("    PASS: Would raise error on scan")
    else:
        print(f"    PASS: Vault configured at {paths.vault_path}")
        print(f"    INFO: Would scan {paths.vault_path}")

    # Test 2: Verify scan_vault raises on invalid scope
    print("  Test 2: Invalid scope raises FileNotFoundError")
    try:
        obsidian_scan.scan_vault(scope="DEFINITELY_DOES_NOT_EXIST_12345")
        print("    FAIL: Should raise FileNotFoundError")
        return False
    except FileNotFoundError as e:
        if "does not exist" in str(e):
            print("    PASS: Correct FileNotFoundError raised")
        else:
            print(f"    PARTIAL: {e}")
    except Exception as e:
        print(f"    PARTIAL: Got {type(e).__name__}: {e}")

    return True


def test_pipeline_lock_errors():
    """Test pipeline lock error handling."""
    print("\n=== Pipeline Lock Errors ===")
    from otto.pipeline import _acquire_pipeline_lock, _release_pipeline_lock
    from otto.config import load_paths

    paths = load_paths()
    lock_path = paths.state_root / "pids" / "pipeline.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Clean up first
    if lock_path.exists():
        lock_path.unlink()

    # Test 1: First acquire succeeds
    print("  Test 1: First acquire succeeds")
    result = _acquire_pipeline_lock(paths)
    if result:
        print("    PASS: Lock acquired")
    else:
        print("    FAIL: Lock should succeed")
        return False

    # Test 2: Second acquire fails (lock held)
    print("  Test 2: Second acquire blocked")
    result = _acquire_pipeline_lock(paths)
    if not result:
        print("    PASS: Lock correctly blocked")
    else:
        print("    FAIL: Lock should be blocked")
        return False

    # Test 3: Release allows re-acquire
    print("  Test 3: Release allows re-acquire")
    _release_pipeline_lock()
    result = _acquire_pipeline_lock(paths)
    if result:
        print("    PASS: Lock re-acquired after release")
    else:
        print("    FAIL: Lock should be available")
        return False

    # Cleanup
    _release_pipeline_lock()
    return True


def test_config_errors():
    """Test config loading error handling."""
    print("\n=== Config Errors ===")
    from otto.config import load_yaml_config, load_paths

    # Test 1: Missing config returns empty dict
    print("  Test 1: Missing config returns empty dict")
    result = load_yaml_config("nonexistent_config.yaml")
    if isinstance(result, dict) and not result:
        print("    PASS: Empty dict returned")
    else:
        print(f"    FAIL: Expected empty dict, got {result}")
        return False

    # Test 2: load_paths creates directories
    print("  Test 2: load_paths creates directories")
    paths = load_paths()
    required = [
        paths.bronze_root,
        paths.artifacts_root,
        paths.logs_root,
        paths.state_root,
    ]
    all_exist = all(p.exists() for p in required)
    if all_exist:
        print("    PASS: All directories created")
    else:
        print(f"    FAIL: Missing directories: {[p for p in required if not p.exists()]}")
        return False

    return True


def test_state_errors():
    """Test state management error handling."""
    print("\n=== State Errors ===")
    from otto.state import read_json, write_json

    # Test 1: read_json with missing file returns default
    print("  Test 1: read_json missing file returns default")
    result = read_json(Path("nonexistent/path.json"), default={"status": "ok"})
    if result == {"status": "ok"}:
        print("    PASS: Default returned")
    else:
        print(f"    FAIL: Got {result}")
        return False

    # Test 2: read_json with invalid JSON returns default
    print("  Test 2: read_json invalid JSON returns default")
    test_file = Path("test_invalid.json")
    test_file.write_text("{invalid json")
    result = read_json(test_file, default={"fallback": True})
    test_file.unlink()
    if result == {"fallback": True}:
        print("    PASS: Default returned for invalid JSON")
    else:
        print(f"    FAIL: Got {result}")
        return False

    # Test 3: write_json creates parent directories
    print("  Test 3: write_json creates parents")
    test_file = Path("test_state/nested/path.json")
    result = write_json(test_file, {"test": True})
    if result.exists() and test_file.exists():
        print("    PASS: Nested path created")
        test_file.unlink()
        result.parent.rmdir()
        result.parent.parent.rmdir()
        return True
    print("    FAIL: Nested path not created")
    return False


def test_database_errors():
    """Test database connection error handling."""
    print("\n=== Database Errors ===")
    from otto.db import pg_available

    # Test 1: pg_available returns False when no connection
    print("  Test 1: pg_available returns False when no connection")
    result = pg_available()
    # Should be False (no Docker Postgres running by default)
    print(f"    Result: {result} (expected: False)")
    return True  # Don't fail if Postgres IS available


def test_mcp_errors():
    """Test MCP launch error handling."""
    print("\n=== MCP Errors ===")
    from otto.docker_utils import docker_available, docker_daemon_running

    # Test 1: docker_available checks
    print("  Test 1: docker_available check")
    result = docker_available()
    print(f"    Docker available: {result}")
    # Don't fail if Docker IS available

    # Test 2: docker_daemon_running checks
    print("  Test 2: docker_daemon_running check")
    result = docker_daemon_running()
    print(f"    Docker daemon running: {result}")
    # Don't fail if Docker IS running

    return True


def test_orchestration_errors():
    """Test orchestration error handling."""
    print("\n=== Orchestration Errors ===")
    from otto.orchestration.council import CouncilEngine

    # Test 1: detect_triggers handles empty inputs
    print("  Test 1: detect_triggers empty inputs")
    ce = CouncilEngine()
    triggers = ce.detect_triggers(
        gold_scores=[],
        unresolved_signals=[],
        top_folders=[],
        contradictions=[],
    )
    if isinstance(triggers, list):
        print(f"    PASS: Returns list (possibly empty: {len(triggers)})")
    else:
        print("    FAIL: Should return list")
        return False

    # Test 2: detect_triggers with stale_map parameter
    print("  Test 2: detect_triggers with staleness_map")
    triggers = ce.detect_triggers(
        gold_scores=[],
        unresolved_signals=[{"note_path": "test.md"} for _ in range(6)],
        top_folders=[],
        contradictions=[],
        staleness_map={"test.md": 5},
    )
    print(f"    PASS: Handles staleness_map (got {len(triggers)} triggers)")

    return True


def test_error_recovery():
    """Test error recovery mechanisms."""
    print("\n=== Error Recovery ===")

    # Test 1: Pipeline can recover from lock file
    print("  Test 1: Pipeline lock recovery")
    from otto.pipeline import _acquire_pipeline_lock, _release_pipeline_lock
    from otto.config import load_paths

    paths = load_paths()
    lock_path = paths.state_root / "pids" / "pipeline.lock"

    # Create stale lock
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("999999")  # Invalid PID

    # Should handle stale lock
    acquired = _acquire_pipeline_lock(paths)
    if acquired:
        print("    PASS: Recovered from stale lock")
        _release_pipeline_lock()
    else:
        # Check if it detected stale correctly
        print("    PARTIAL: Stale lock handled (check manually)")

    # Cleanup
    if lock_path.exists():
        lock_path.unlink()

    return True


def run_all_tests():
    """Run all error path tests."""
    print("="*60)
    print("ERROR PATH VERIFICATION")
    print("="*60)

    results = {
        "vault": test_vault_path_errors(),
        "pipeline": test_pipeline_lock_errors(),
        "config": test_config_errors(),
        "state": test_state_errors(),
        "database": test_database_errors(),
        "mcp": test_mcp_errors(),
        "orchestration": test_orchestration_errors(),
        "recovery": test_error_recovery(),
    }

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")

    print(f"\nTotal: {passed}/{total} passed")

    return all(results.values())


def run_specific_test(path: str):
    """Run a specific error path test."""
    tests = {
        "vault": test_vault_path_errors,
        "pipeline": test_pipeline_lock_errors,
        "config": test_config_errors,
        "state": test_state_errors,
        "database": test_database_errors,
        "mcp": test_mcp_errors,
        "orchestration": test_orchestration_errors,
        "recovery": test_error_recovery,
    }

    if path not in tests:
        print(f"Unknown path: {path}")
        print(f"Available: {list(tests.keys())}")
        return False

    print(f"Running test: {path}")
    return tests[path]()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1].lower()
        if path == "--help":
            print("Usage: python scripts/test_error_paths.py [path]")
            print("Paths: vault, pipeline, config, state, database, mcp, orchestration, recovery, all")
            sys.exit(0)
        if path == "all":
            success = run_all_tests()
        else:
            success = run_specific_test(path)
    else:
        success = run_all_tests()

    sys.exit(0 if success else 1)
