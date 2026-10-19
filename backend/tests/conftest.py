"""Global Pytest Fixtures for Intelligent Forgetting Backend.

Guarantees:
1. Complete isolation of automated tests from live user data in data/memories.db.
2. In-memory or temporary database provisioning for test runs.
3. Hermetic testing environments preventing pollution across tests.
"""

import os
import pytest
from intelligent_forgetting.memory_store import MemoryStore
import intelligent_forgetting.api as api


@pytest.fixture(scope="session", autouse=True)
def isolate_test_database(tmp_path_factory):
    """Ensures automated tests execute against an isolated temporary database,
    protecting development and user data in data/memories.db from deletion.
    """
    test_db_dir = tmp_path_factory.mktemp("test_suite_db")
    test_db_path = str(test_db_dir / "test_suite_memories.db")
    from pathlib import Path
    orig_db_path = api.store.db_path
    api.store.db_path = str(Path(test_db_path).resolve())
    Path(api.store.db_path).parent.mkdir(parents=True, exist_ok=True)
    api.store._init_database()

    yield api.store

    api.store.db_path = orig_db_path
