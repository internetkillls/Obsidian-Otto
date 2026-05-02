from __future__ import annotations

from otto.repo_surface import classify_repo_surface
from otto.schema_registry import schema_fingerprint, schema_registry


def test_schema_registry_has_single_fingerprint():
    registry = schema_registry()
    assert any(item["backend"] == "sqlite" for item in registry)
    assert any(item["backend"] == "postgres" for item in registry)
    assert len(schema_fingerprint()) == 64


def test_repo_surface_classification():
    assert classify_repo_surface("src/otto/cli.py").status == "canonical"
    assert classify_repo_surface("src/app/cli.py").status == "compatibility"
    assert classify_repo_surface(".Otto-Realm/Scripts/run.py").status == "governance"
