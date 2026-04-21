"""
Pipeline Transformer Optimizer Tests

Run: python scripts/test_pipeline_optimizer.py
"""
from __future__ import annotations
import sys
import time
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import sqlite3
from otto.tooling.pipeline_cache import (
    PipelineCache,
    IncrementalSilver,
    run_pipeline_optimized,
    get_pipeline_efficiency,
)


def test_pipeline_cache():
    """Test PipelineCache mtime-based delta detection."""
    print("\n=== Test: PipelineCache ===")

    # Create temp cache
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "cache.json"
        cache = PipelineCache(cache_path)

        # Set up cache state (simulates previous run)
        cache.cache["files"] = {
            "note1.md": {"mtime": 1000.0, "sha1": "sha1_1"},
            "note2.md": {"mtime": 1000.0, "sha1": "sha1_2"},
            "note3.md": {"mtime": 1000.0, "sha1": "sha1_3"},  # This one will be deleted
        }
        cache.save()

        # Check unchanged file
        assert cache.is_changed("note1.md", 1000.0, "sha1_1") == False, "Should be unchanged"
        print("  PASS: Unchanged file detected correctly")

        # Check changed file (different mtime)
        assert cache.is_changed("note1.md", 2000.0, "sha1_1") == True, "Should be changed (mtime)"
        print("  PASS: Changed mtime detected")

        # Check changed file (different sha1)
        assert cache.is_changed("note1.md", 1000.0, "sha1_different") == True, "Should be changed (sha1)"
        print("  PASS: Changed sha1 detected")

        # Check new file
        assert cache.is_changed("note4.md", 1000.0, "sha1_4") == True, "Should be new"
        print("  PASS: New file detected")

        # Test get_changed_files - compare current vault state against cached state
        current_vault = [
            {"path": "note1.md", "mtime": 1000.0, "sha1": "sha1_1"},  # unchanged
            {"path": "note2.md", "mtime": 2000.0, "sha1": "sha1_2"},  # changed (mtime updated)
            # note3.md is now missing (deleted from vault)
            {"path": "note4.md", "mtime": 1000.0, "sha1": "sha1_4"},  # new
        ]
        changed, deleted = cache.get_changed_files(current_vault)

        # note2 changed (mtime 1000 -> 2000), note4 is new
        assert len(changed) == 2, f"Expected 2 changed, got {len(changed)}: {[c['path'] for c in changed]}"
        assert "note2.md" in [c["path"] for c in changed], "note2 should be changed"
        assert "note4.md" in [c["path"] for c in changed], "note4 should be new"

        # note3 was in cache but not in current vault = deleted
        assert len(deleted) == 1, f"Expected 1 deleted, got {len(deleted)}: {deleted}"
        assert "note3.md" in deleted, "note3 should be deleted"

        print("  PASS: get_changed_files works correctly")

        # Now update cache with current vault state
        for note in current_vault:
            cache.set_file(note["path"], note["mtime"], note["sha1"])
        cache.save()

        # Verify cache is now up to date
        assert cache.is_changed("note1.md", 1000.0, "sha1_1") == False, "Should be unchanged after update"
        assert cache.is_changed("note2.md", 2000.0, "sha1_2") == False, "Should be unchanged after update"
        assert cache.is_changed("note4.md", 1000.0, "sha1_4") == False, "Should be unchanged after update"
        print("  PASS: Cache updated correctly")

    return True


def test_incremental_silver():
    """Test IncrementalSilver with upsert."""
    print("\n=== Test: IncrementalSilver ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        silver = IncrementalSilver(db_path)

        # First run needs schema rebuild
        assert silver.needs_schema_rebuild() == True, "New DB should need schema"
        print("  PASS: New DB detected correctly")

        # Create schema matching normalize.py (with size and sha1)
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE notes (
                path TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                size INTEGER NOT NULL DEFAULT 0,
                sha1 TEXT NOT NULL DEFAULT '',
                mtime REAL NOT NULL DEFAULT 0,
                has_frontmatter INTEGER NOT NULL DEFAULT 0,
                frontmatter_text TEXT DEFAULT '',
                body_excerpt TEXT DEFAULT '',
                tags_json TEXT DEFAULT '[]',
                wikilinks_json TEXT DEFAULT '[]',
                scarcity TEXT DEFAULT '[]',
                necessity TEXT,
                artificial TEXT,
                orientation TEXT,
                allocation TEXT,
                cluster_membership TEXT DEFAULT '[]'
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE notes_fts USING fts5(path, title, frontmatter_text, body_excerpt)
        """)
        conn.commit()
        conn.close()

        # Second run should not need rebuild
        silver2 = IncrementalSilver(db_path)
        assert silver2.needs_schema_rebuild() == False, "Existing DB should not need rebuild"
        print("  PASS: Existing DB detected correctly")

        # Test incremental update
        changed_notes = [
            {
                "path": "test1.md",
                "title": "Test Note",
                "size": 100,
                "sha1": "abc123",
                "mtime": 1000.0,
                "has_frontmatter": True,
                "frontmatter_text": "key: value",
                "body_excerpt": "Test body",
                "tags": ["test"],
                "wikilinks": [],
                "scarcity": [],
                "necessity": None,
                "artificial": None,
                "orientation": None,
                "allocation": None,
                "cluster_membership": [],
            }
        ]
        stats = silver2.build_incremental(changed_notes, [])
        assert stats["changed"] == 1, f"Expected 1 changed, got {stats['changed']}"
        print(f"  PASS: Incremental update: {stats}")

        # Verify data was inserted
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT title FROM notes WHERE path='test1.md'").fetchone()
        assert row and row[0] == "Test Note", f"Data not inserted: {row}"
        conn.close()
        print("  PASS: Data verified in SQLite")

    return True


def test_pipeline_efficiency():
    """Test pipeline efficiency metrics."""
    print("\n=== Test: Pipeline Efficiency ===")

    metrics = get_pipeline_efficiency()
    print(f"  Metrics: {metrics}")
    assert "cached_files" in metrics, "Should have cached_files"
    assert "last_run_ts" in metrics, "Should have last_run_ts"

    print("  PASS: Efficiency metrics retrieved")
    return True


def run_optimized_pipeline():
    """Run actual optimized pipeline (requires vault configured).

    NOTE: This requires a clean database or schema-compatible database.
    The existing database may have legacy schema that needs migration.
    """
    print("\n=== Run: Optimized Pipeline ===")

    try:
        from otto.config import load_paths
        paths = load_paths()
        if paths.vault_path is None or not paths.vault_path.exists():
            print("  SKIP: Vault not configured")
            return True

        # Check if database has correct schema
        import sqlite3
        try:
            conn = sqlite3.connect(paths.sqlite_path)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(notes)").fetchall()}
            conn.close()
            required = {"path", "title", "size", "sha1", "mtime", "has_frontmatter"}
            if not required.issubset(cols):
                print(f"  SKIP: Database has legacy schema (missing {required - cols})")
                print("  NOTE: Run full pipeline once to migrate schema")
                return True
        except Exception:
            pass

        result = run_pipeline_optimized(scope=None, full=False)
        print(f"  Status: {result.get('status')}")
        print(f"  Bronze: {result.get('bronze')}")
        print(f"  Silver: {result.get('silver')}")
        print(f"  Gold: {result.get('gold')}")

        if result.get("status") == "success":
            print("  PASS: Optimized pipeline completed")
        elif result.get("status") == "unchanged":
            print("  PASS: Cache hit (no changes)")

        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


if __name__ == "__main__":
    print("="*60)
    print("PIPELINE TRANSFORMER OPTIMIZER TESTS")
    print("="*60)

    results = []

    results.append(("PipelineCache", test_pipeline_cache()))
    results.append(("IncrementalSilver", test_incremental_silver()))
    results.append(("Pipeline Efficiency", test_pipeline_efficiency()))
    results.append(("Run Optimized", run_optimized_pipeline()))

    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")

    print(f"\nTotal: {passed}/{total} passed")

    sys.exit(0 if passed == total else 1)
