import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from wmc_helpers import Site  # noqa: E402


@pytest.fixture
def site():
    s = Site()
    yield s
    s.close()
