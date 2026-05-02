from __future__ import annotations

import pytest
import shutil
from pathlib import Path
from uuid import uuid4


@pytest.fixture
def scratch_path(request):
    repo = Path(__file__).resolve().parents[1]
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in request.node.name).strip("_") or "scratch"
    path = repo / ".tmp_pytest_scratch" / f"{safe_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def tmp_path(scratch_path):
    return scratch_path


@pytest.fixture
def tmp_vault(scratch_path):
    vault = scratch_path / "vault"
    vault.mkdir()
    return vault
