import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from factory_renderer import CRATE_TEXTURE_PATH


class CrateTextureTests(unittest.TestCase):
    def test_crate_texture_uses_crate_png_asset(self) -> None:
        self.assertEqual(CRATE_TEXTURE_PATH.name, "crate.png")
        self.assertTrue(CRATE_TEXTURE_PATH.is_file())


if __name__ == "__main__":
    unittest.main()
