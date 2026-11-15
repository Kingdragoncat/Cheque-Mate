import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from factory_sim import MAX_CARRIED, FactoryWorld, Tile


class BagBehaviorTests(unittest.TestCase):
    def test_movement_scales_with_bag_load(self) -> None:
        world = FactoryWorld()
        captured_velocity: list[tuple[float, float]] = []
        world._step_with_corner_slide = lambda vx, vy, allow_grate: (
            captured_velocity.append((vx, vy)) or True
        )

        world.carried_cheques = []
        world.move_player(1.0, 0.0, 1.0)
        empty_distance = captured_velocity[-1][0]

        world.carried_cheques = ["payroll"] * (MAX_CARRIED // 2)
        world.move_player(1.0, 0.0, 1.0)
        half_distance = captured_velocity[-1][0]

        world.carried_cheques = ["payroll"] * MAX_CARRIED
        world.move_player(1.0, 0.0, 1.0)
        full_distance = captured_velocity[-1][0]

        self.assertAlmostEqual(half_distance / empty_distance, 0.75)
        self.assertAlmostEqual(full_distance / empty_distance, 0.5)

    def test_full_bag_rejects_pile_pickup(self) -> None:
        world = FactoryWorld()
        col, row = 10, 10
        tile = Tile(pile_tier=1, pile_kind="payroll")
        world.grid[row][col] = tile
        world.carried_cheques = ["payroll"] * MAX_CARRIED
        original_money = world.money_rescued

        self.assertFalse(world.interact_tile(col, row, ignore_reach=True))
        self.assertEqual(tile.pile_tier, 1)
        self.assertEqual(len(world.carried_cheques), MAX_CARRIED)
        self.assertEqual(world.money_rescued, original_money)

    def test_full_bag_rejects_crate_pickup(self) -> None:
        world = FactoryWorld()
        col, row = 10, 10
        tile = Tile(
            kind="crate",
            dir_idx=1,
            color_key="payroll",
            crate_stock=1,
            crate_max=1,
        )
        world.grid[row][col] = tile
        world.carried_cheques = ["payroll"] * MAX_CARRIED
        original_money = world.money_rescued

        self.assertFalse(world.interact_tile(col, row, ignore_reach=True))
        self.assertEqual(tile.crate_stock, 1)
        self.assertEqual(len(world.carried_cheques), MAX_CARRIED)
        self.assertEqual(world.money_rescued, original_money)

    def test_jump_shortens_with_bag_load_and_is_disabled_when_full(self) -> None:
        world = FactoryWorld()
        world.trigger_jump(1.0, 0.0)
        empty_jump_speed = world.jump_vx

        world.jump_timer = 0.0
        world.carried_cheques = ["payroll"] * (MAX_CARRIED // 2)
        world.trigger_jump(1.0, 0.0)
        half_jump_speed = world.jump_vx

        world.jump_timer = 0.0
        world.carried_cheques = ["payroll"] * (MAX_CARRIED * 3 // 4)
        world.trigger_jump(1.0, 0.0)
        three_quarters_jump_speed = world.jump_vx

        world.jump_timer = 0.0
        world.carried_cheques = ["payroll"] * MAX_CARRIED
        world.trigger_jump(1.0, 0.0)

        self.assertAlmostEqual(half_jump_speed / empty_jump_speed, 0.75)
        self.assertAlmostEqual(three_quarters_jump_speed / empty_jump_speed, 0.5)
        self.assertEqual(world.jump_timer, 0.0)

    def test_splitter_routes_configured_cheque_types_to_their_outputs(self) -> None:
        world = FactoryWorld()
        tile = Tile(
            kind="splitter",
            dir_idx=1,
            splitter_straight_color="payroll",
            splitter_branch_color="refund",
        )

        self.assertEqual(world._splitter_output_dir(tile, "payroll"), 1)
        self.assertEqual(world._splitter_output_dir(tile, "refund"), 2)


if __name__ == "__main__":
    unittest.main()
