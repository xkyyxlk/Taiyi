from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from taiyi.storage import Database, Repository


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[Repository]:
    database = Database(tmp_path / "taiyi.sqlite3")
    database.create_schema()
    yield Repository(database)
    database.engine.dispose()
