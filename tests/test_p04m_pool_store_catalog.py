"""CAT-01 mode of the retained P04M pool store tests: same SQLite writer, with
seat roles and shell rows read from the single catalog (CREW-ANY server path)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from tests.test_p04m_pool_store import PoolStoreTests
import catalog_v1
import catalog_v1_data


class CatalogModePoolStoreTests(PoolStoreTests):
    def setUp(self):
        catalog_v1.activate(catalog_v1_data.CATALOG_SHA256)
        self.addCleanup(catalog_v1.deactivate_for_tests)
        super().setUp()


del PoolStoreTests  # the legacy-mode run belongs to tests/test_p04m_pool_store.py
