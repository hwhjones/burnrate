import importlib
import unittest
from importlib import metadata
from unittest.mock import patch

import burnrate


class TestVersion(unittest.TestCase):
    def test_installed_version_comes_from_distribution_metadata(self):
        self.assertEqual(burnrate.__version__, metadata.version("burnrate"))

    def test_uninstalled_source_tree_uses_safe_fallback(self):
        try:
            with patch(
                "importlib.metadata.version",
                side_effect=metadata.PackageNotFoundError,
            ):
                reloaded = importlib.reload(burnrate)
                self.assertEqual(reloaded.__version__, "0+unknown")
        finally:
            importlib.reload(burnrate)


if __name__ == "__main__":
    unittest.main()
