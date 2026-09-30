import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from fortuna.rules import load_regimes  # noqa: E402


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def regimes():
    return load_regimes(REPO_ROOT / "metadata" / "game_regimes.csv")
