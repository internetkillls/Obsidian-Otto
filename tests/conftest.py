from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture
def tmp_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault
