import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from factory_renderer import FactoryRenderer
from factory_sim import Tile


class BeltCurveTests(unittest.TestCase):
    def test_detects_perpendicular_incoming_direction_at_corner(self) -> None:
        grid = [[Tile() for _ in range(3)] for _ in range(3)]
        grid[1][1] = Tile(kind="belt", dir_idx=2)
        grid[1][0] = Tile(kind="belt", dir_idx=1)
        world = type("World", (), {"grid": grid, "cols": 3, "rows": 3})()

        self.assertEqual(FactoryRenderer._belt_incoming_dir(world, 1, 1, 2), 1)


if __name__ == "__main__":
    unittest.main()
