import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame

from main import BounceTheChequesGame


class ControlHotkeyTests(unittest.TestCase):
    def test_f1_to_f4_do_not_grant_cash_or_unlock_rooms(self) -> None:
        game = BounceTheChequesGame.__new__(BounceTheChequesGame)
        game.show_story = False
        game.show_shop = False
        game.keep_playing = False
        game.selected_tool = 0
        game.build_dir = 1
        game.filter_color_idx = 0
        game.muted = False
        game.mouse_pos = (0, 0)
        game.world = SimpleNamespace(
            level_complete=False,
            level_failed=False,
            room_stage=1,
            cols=15,
            rows=18,
            cash=550,
            player_x=6.5,
            player_y=6.5,
            sfx_queue=[],
            popups=[],
        )
        game.renderer = Mock()

        for key in (pygame.K_F2, pygame.K_F3, pygame.K_F4):
            self.assertTrue(game._handle_key_down(key))
            self.assertEqual(game.world.room_stage, 1)
            self.assertEqual(game.world.cash, 550)

        game.renderer.center_camera_at.assert_not_called()

        self.assertTrue(game._handle_key_down(pygame.K_F1))
        self.assertEqual(game.world.room_stage, 1)
        self.assertEqual(game.world.cash, 550)
        game.renderer.center_camera_at.assert_called_once()

    def test_esc_closes_all_menus_and_clears_selected_tool(self) -> None:
        game = BounceTheChequesGame.__new__(BounceTheChequesGame)
        game.show_story = True
        game.show_shop = True
        game.keep_playing = False
        game.selected_tool = 0
        game.part_menu_tile = (3, 3)
        game.selected_part_tile = (3, 3)
        game.muted = False
        game.sfx = Mock()
        game.world = SimpleNamespace(level_complete=False, level_failed=False)

        self.assertTrue(game._handle_key_down(pygame.K_ESCAPE))
        self.assertFalse(game.show_story)
        self.assertFalse(game.show_shop)
        self.assertIsNone(game.part_menu_tile)
        self.assertIsNone(game.selected_part_tile)
        self.assertEqual(game.selected_tool, 0)

        self.assertTrue(game._handle_key_down(pygame.K_ESCAPE))
        self.assertIsNone(game.selected_tool)
        self.assertEqual(game.tool_kind, "")

        self.assertTrue(game._handle_key_down(pygame.K_1))
        self.assertEqual(game.selected_tool, 0)
        self.assertTrue(game._handle_key_down(pygame.K_1))
        self.assertIsNone(game.selected_tool)

        self.assertTrue(game._handle_key_down(pygame.K_2))
        self.assertEqual(game.selected_tool, 1)
        self.assertTrue(game._handle_key_down(pygame.K_BACKQUOTE))
        self.assertIsNone(game.selected_tool)

    def test_no_crates_and_forklift_relocates_machines_and_room_unlock_requires_quota_and_cash(self) -> None:
        from factory_sim import FORKLIFT_SPEED, FactoryWorld, Tile

        world = FactoryWorld()
        world.started = True
        self.assertLess(FORKLIFT_SPEED, 4.0)
        self.assertEqual(world.crates_remaining, 0)
        crates = [
            world.grid[r][c]
            for r in range(world.rows)
            for c in range(world.cols)
            if world.grid[r][c].kind == "crate"
        ]
        self.assertEqual(len(crates), 0)

        # Place upgraded stamper, lift with forklift, and set down elsewhere keeping level
        world.grid[11][6] = Tile(kind="stamper", dir_idx=2, machine_level=2, paid_cost=500)
        world.player_x = 5.5
        world.player_y = 11.5
        world.forklifts[0].x = 5.5
        world.forklifts[0].y = 11.5
        self.assertTrue(world.toggle_forklift())
        self.assertTrue(world.relocate_machine_with_forklift())
        self.assertEqual(world.grid[11][6].kind, "empty")
        self.assertIsNotNone(world.forklifts[0].carried_machine)
        self.assertTrue(world.relocate_machine_with_forklift())
        self.assertIsNone(world.forklifts[0].carried_machine)
        relocated = world.grid[11][6]
        self.assertEqual(relocated.kind, "stamper")
        self.assertEqual(relocated.machine_level, 2)

        # Room unlock requires BOTH rescue quota AND cash
        world.power_restored = True
        world.money_rescued = 0
        world.cash = 99999
        self.assertIsNotNone(world.room_unlock_block_reason())
        world.money_rescued = world.money_quota
        for r in range(world.rows):
            for c in range(world.cols):
                if world.grid[r][c].kind == "dest":
                    world.grid[r][c].delivered_count = world.min_dest_deliveries
        world.cash = 0
        self.assertIn("CASH", world.room_unlock_block_reason() or "")
        world.cash = world.next_room_unlock_cost()
        self.assertIsNone(world.room_unlock_block_reason())

    def test_truck_bay_cheque_types_expiration_and_machines(self) -> None:
        from factory_data import CHEQUE_TYPES
        from factory_sim import ChequeItem, FactoryWorld, Tile

        self.assertEqual(CHEQUE_TYPES["payroll"]["timeout"], 36.0)
        self.assertEqual(CHEQUE_TYPES["vip"]["timeout"], 28.0)
        self.assertEqual(CHEQUE_TYPES["rent"]["timeout"], 44.0)
        self.assertEqual(CHEQUE_TYPES["mortgage"]["timeout"], 60.0)
        self.assertEqual(CHEQUE_TYPES["void"]["timeout"], 0.0)
        self.assertEqual(CHEQUE_TYPES["fake"]["timeout"], 0.0)

        w = FactoryWorld()
        self.assertTrue(len(w.truck_bays) >= 1)
        hp = w._huge_pile_master(w.grid[5][2])
        assert hp is not None
        self.assertEqual(hp.kind, "huge_pile")
        self.assertGreater(hp.crate_stock, 0)

        # Scanner error mode diverts misprint
        w.grid[7][6] = Tile(kind="scanner", dir_idx=1, scanner_mode="error", machine_level=3)
        w.grid[7][7] = Tile(kind="belt", dir_idx=1)
        w.grid[8][6] = Tile(kind="belt", dir_idx=2)
        ch_err = ChequeItem(x=6.5, y=7.5, color_key="payroll", value=450, stamped=True, misprint=True, move_dir=1)
        w.cheques.append(ch_err)
        w._update_cheques(0.25)
        self.assertEqual(ch_err.move_dir, 2)

        # Shredder penalizes shredding a valid real cheque
        cash_pre = w.cash
        w.grid[9][6] = Tile(kind="shredder", dir_idx=1)
        ch_ok = ChequeItem(x=6.5, y=9.5, color_key="rent", value=520, stamped=True, move_dir=1)
        w.cheques.append(ch_ok)
        w._update_cheques(0.35)
        self.assertLess(w.cash, cash_pre)

        # Expired cheque delivered to dest costs money
        w.grid[11][11] = Tile(kind="dest", color_key="payroll")
        ch_exp = ChequeItem(x=11.5, y=11.5, color_key="payroll", value=450, stamped=True, age=50.0, max_age=45.0, expired=True)
        w._deliver_cheque(11, 11, w.grid[11][11], ch_exp)
        self.assertLess(w.cash, cash_pre)

    def test_setup_phase_allows_building_and_waits_for_start(self) -> None:
        from factory_sim import FactoryWorld

        w = FactoryWorld()
        self.assertFalse(w.started)
        start_cash = w.cash
        w.place_tile(6, 5, "belt", 1, "payroll")
        self.assertEqual(w.grid[5][6].kind, "belt")
        self.assertLess(w.cash, start_cash)

        w.update(2.0)
        self.assertEqual(w.elapsed_time, 0.0)
        self.assertEqual(len(w.cheques), 0)

        w.start_game()
        self.assertTrue(w.started)
        w.update(1.5)
        self.assertAlmostEqual(w.elapsed_time, 1.5)

    def test_huge_pile_does_not_shrink_or_pile_when_conveyor_full(self) -> None:
        from factory_sim import ChequeItem, FactoryWorld

        w = FactoryWorld()
        hp_edge = w.grid[4][4]
        self.assertEqual(hp_edge.kind, "huge_pile")
        master = w._huge_pile_master(hp_edge)
        assert master is not None
        master.crate_stock = 10
        hp_edge.dir_idx = 1
        hp_edge.spawn_timer = 0.0
        w.grid[4][5].kind = "belt"
        w.grid[4][5].dir_idx = 1
        # Place a cheque near the far edge of (5, 4) so tile (5, 4) is occupied
        w.cheques.append(ChequeItem(x=5.9, y=4.5, color_key="payroll", value=450, stamped=True, move_dir=1))

        w._update_sources(0.1)
        self.assertEqual(master.crate_stock, 10)
        self.assertEqual(len(w.cheques), 1)

    def test_fake_cheque_disguise_passes_sorter_but_caught_by_scanner(self) -> None:
        from factory_sim import ChequeItem, FactoryWorld, Tile

        w = FactoryWorld()
        w.grid[7][6] = Tile(kind="sorter", dir_idx=1, sorter_branch_color="payroll")
        ch_fake = ChequeItem(
            x=6.5, y=7.5, color_key="fake", value=-400, disguise_color="payroll", stamped=True, move_dir=1
        )
        w.cheques.append(ch_fake)
        w._update_cheques(0.05)
        # Passes as payroll onto sorter's payroll branch (dir 2)
        self.assertEqual(ch_fake.split_dir, 2)

        # Fraud scanner still catches fake cheque despite disguise
        w.grid[7][8] = Tile(kind="scanner", dir_idx=1, scanner_mode="fraud", machine_level=3)
        ch_fake2 = ChequeItem(
            x=8.5, y=7.5, color_key="fake", value=-400, disguise_color="payroll", stamped=True, move_dir=1
        )
        w.cheques.append(ch_fake2)
        w._update_cheques(0.6)
        self.assertTrue(ch_fake2.fraud_scanned)
        self.assertEqual(ch_fake2.move_dir, 2)

        # Fraud scanner does NOT catch real unstamped cheques
        ch_real_unstamped = ChequeItem(
            x=8.5, y=7.5, color_key="payroll", value=450, stamped=False, move_dir=1
        )
        w.cheques.append(ch_real_unstamped)
        w._update_cheques(0.6)
        self.assertTrue(ch_real_unstamped.fraud_scanned)
        self.assertEqual(ch_real_unstamped.move_dir, 1)

    def test_depot_buffers_five_and_upgrades_capacity_and_2000_starting_cash(self) -> None:
        from factory_sim import ChequeItem, FactoryWorld, Tile

        w = FactoryWorld()
        self.assertEqual(w.cash, 3500)

        w.grid[7][6] = Tile(kind="depot", dir_idx=1, machine_level=1)
        depot = w.grid[7][6]
        self.assertEqual(w.depot_capacity(depot), 5)

        # Feed 6 cheques into depot; 5 buffer, 6th is blocked because depot is full
        for _ in range(5):
            w.cheques.append(ChequeItem(x=6.5, y=7.5, color_key="payroll", value=450, stamped=True, move_dir=1))
        w._update_cheques(0.05)
        self.assertEqual(len(depot.depot_items), 5)
        self.assertTrue(w._occupied_ahead(6, 7, -1))

        # Upgrading depot increases storage capacity (MK2=10, MK3=18)
        depot.machine_level = 2
        self.assertEqual(w.depot_capacity(depot), 10)
        self.assertFalse(w._occupied_ahead(6, 7, -1))
        depot.machine_level = 3
        self.assertEqual(w.depot_capacity(depot), 18)

        # Downstream belt receives buffered cheque from depot
        w.grid[7][7] = Tile(kind="belt", dir_idx=1)
        depot.spawn_timer = 0.0
        w._update_depots(0.1)
        self.assertEqual(len(depot.depot_items), 4)
        self.assertEqual(len(w.cheques), 1)

    def test_wrong_tube_vs_unstamped_delivery_error_messages(self) -> None:
        from factory_sim import ChequeItem, FactoryWorld, Tile

        w = FactoryWorld()
        w.grid[5][11] = Tile(kind="dest", color_key="payroll")

        # Unstamped RENT cheque sent to PAYROLL tube -> WRONG TUBE (UNSTAMPED)!
        w.popups.clear()
        w._deliver_cheque(
            11, 5, w.grid[5][11],
            ChequeItem(x=11.5, y=5.5, color_key="rent", value=520, stamped=False),
        )
        self.assertIn("WRONG TUBE", w.popups[-1].text)

        # Unstamped PAYROLL cheque sent to PAYROLL tube -> UNSTAMPED!
        w.popups.clear()
        w._deliver_cheque(
            11, 5, w.grid[5][11],
            ChequeItem(x=11.5, y=5.5, color_key="payroll", value=450, stamped=False),
        )
        self.assertIn("UNSTAMPED", w.popups[-1].text)
        self.assertNotIn("WRONG TUBE", w.popups[-1].text)

    def test_upgrade_modal_shows_only_global_upgrades(self) -> None:
        from factory_data import UPGRADES
        from factory_renderer import FactoryRenderer
        from factory_sim import FactoryWorld

        pygame.init()
        renderer = FactoryRenderer(1280, 720, None, None, None)
        world = FactoryWorld()
        surf = pygame.Surface((1280, 720))
        renderer._draw_shop_modal(surf, world, 0, 1, "payroll")
        self.assertEqual(renderer.shop_card_rects, [])
        self.assertEqual(len(renderer.shop_upgrade_rects), len(UPGRADES))

    def test_place_nudges_player_clear_and_prevents_softlock(self) -> None:
        from factory_sim import FactoryWorld, Tile

        w = FactoryWorld()
        col, row = 6, 6
        w.grid[row][col] = Tile(kind="floor")
        w.player_x = col + 0.5
        w.player_y = row + 0.5
        self.assertTrue(w.place_tile(col, row, "depot", 1, "payroll", ignore_reach=True))
        self.assertEqual(w.grid[row][col].kind, "depot")
        self.assertFalse(w._player_overlaps_tile(col, row))

        # Unstuck rescue if player ever ends up inside a solid tile
        w.grid[6][6] = Tile(kind="wall")
        w.player_x = 6.5
        w.player_y = 6.5
        w._ensure_player_unstuck()
        self.assertFalse(w._is_player_blocked(w.player_x, w.player_y))

        # Negative cash recovers to at least $250 on bailout
        w.started = True
        w.paused = False
        w.cash = -300
        w.cheques.clear()
        w.carried_cheques.clear()
        w.low_cash_timer = 3.95
        w.update(0.1)
        self.assertGreaterEqual(w.cash, 250)

    def test_forklift_blocks_building_and_no_crate_emptier_and_intro_flow(self) -> None:
        from factory_sim import FactoryWorld

        w = FactoryWorld()
        w.started = True
        self.assertTrue(
            all(w.grid[r][c].loading_corner < 0 for r in range(w.rows) for c in range(w.cols))
        )
        w.player_x = w.forklifts[0].x
        w.player_y = w.forklifts[0].y
        self.assertTrue(w.toggle_forklift())
        self.assertFalse(w.place_tile(6, 11, "belt", 1, "payroll", ignore_reach=True))
        self.assertFalse(w.buy_upgrade("turbo_belts"))
        self.assertFalse(w.remove_tile(6, 11, ignore_reach=True))

    def test_mess_audit_scales_with_mess_size_and_amount(self) -> None:
        from factory_sim import FactoryWorld

        w = FactoryWorld()
        w.cheques_rescued_count = 1
        for r in range(w.rows):
            for c in range(w.cols):
                w.grid[r][c].pile_tier = 0
                w.grid[r][c].decal = ""
                if w.grid[r][c].kind == "breaker":
                    w.grid[r][c].jammed = False

        # Clean unlocked floor -> $0 fine
        w.neglect_penalties = 0
        w._apply_neglect_audit()
        self.assertEqual(w.neglect_penalties, 0)

        # Small pile (tier 1) vs giant pile (tier 3) vs multiple piles
        w.grid[6][6].pile_tier = 1
        w.grid[6][6].pile_kind = "payroll"
        w.neglect_penalties = 0
        w._apply_neglect_audit()
        small_fine = w.neglect_penalties
        self.assertGreater(small_fine, 0)

        w.grid[6][6].pile_tier = 3
        w.neglect_penalties = 0
        w._apply_neglect_audit()
        giant_fine = w.neglect_penalties
        self.assertGreater(giant_fine, small_fine * 2)

        w.grid[6][7].pile_tier = 3
        w.grid[6][7].pile_kind = "payroll"
        w.neglect_penalties = 0
        w._apply_neglect_audit()
        double_fine = w.neglect_penalties
        self.assertGreater(double_fine, giant_fine)

    def test_cleaning_requires_crowbar_selected(self) -> None:
        from factory_sim import FactoryWorld, Tile

        w = FactoryWorld()
        w.started = True
        w.cash = 1000
        w.grid[6][6] = Tile(kind="floor", decal="oil")
        w.grid[7][6] = Tile(kind="floor", pile_tier=1, pile_kind="payroll")

        # Without crowbar selected, cleaning spills or piles fails
        w.selected_tool_kind = "belt"
        self.assertFalse(w.remove_tile(6, 6, ignore_reach=True, allow_clean=False))
        self.assertEqual(w.grid[6][6].decal, "oil")
        self.assertFalse(w.interact_tile(6, 7, ignore_reach=True))
        self.assertEqual(w.grid[7][6].pile_tier, 1)

        # With crowbar selected ("demolish"), cleaning succeeds
        w.selected_tool_kind = "demolish"
        self.assertTrue(w.remove_tile(6, 6, ignore_reach=True, allow_clean=True))
        self.assertEqual(w.grid[6][6].decal, "none")
        self.assertTrue(w.interact_tile(6, 7, ignore_reach=True))
        self.assertEqual(w.grid[7][6].pile_tier, 0)

    def test_depot_cheque_timer_ticks_50_percent_slower_and_upgrades_improve_it(self) -> None:
        from factory_sim import ChequeItem, FactoryWorld, Tile

        w = FactoryWorld()
        w.grid[6][6] = Tile(kind="depot", dir_idx=1, machine_level=1)
        w.grid[6][6].spawn_timer = 10.0
        ch = ChequeItem(
            color_key="vip",
            value=850,
            x=6.5,
            y=6.5,
            move_dir=1,
            max_age=28.0,
        )
        w.grid[6][6].depot_items.append(ch)
        w._update_depots(4.0)
        self.assertAlmostEqual(ch.age, 2.0, places=5)
        self.assertFalse(ch.expired)

        # Level 3 depot ticks even slower (0.20x)
        w.grid[6][6].machine_level = 3
        w._update_depots(4.0)
        self.assertAlmostEqual(ch.age, 2.8, places=5)

    def test_fixer_scanner_shredder_accuracy_and_speed_scale_with_upgrades(self) -> None:
        from factory_sim import FactoryWorld, Tile

        w = FactoryWorld()
        t_lv1 = Tile(kind="fixer", machine_level=1)
        t_lv2 = Tile(kind="fixer", machine_level=2)
        t_lv3 = Tile(kind="fixer", machine_level=3)
        self.assertAlmostEqual(w.machine_accuracy(t_lv1), 0.80)
        self.assertAlmostEqual(w.machine_accuracy(t_lv2), 0.90)
        self.assertAlmostEqual(w.machine_accuracy(t_lv3), 1.00)
        self.assertGreater(w.fixer_cycle_time(t_lv1), w.fixer_cycle_time(t_lv2))
        self.assertGreater(w.fixer_cycle_time(t_lv2), w.fixer_cycle_time(t_lv3))
        self.assertGreater(w.scanner_cycle_time(t_lv1), w.scanner_cycle_time(t_lv2))
        self.assertGreater(w.scanner_cycle_time(t_lv2), w.scanner_cycle_time(t_lv3))
        self.assertGreater(w.shredder_cycle_time(t_lv1), w.shredder_cycle_time(t_lv2))
        self.assertGreater(w.shredder_cycle_time(t_lv2), w.shredder_cycle_time(t_lv3))

    def test_entering_new_room_grants_3k_cash_and_pauses(self) -> None:
        from factory_data import ROOM_UNLOCK_COSTS
        from factory_sim import FactoryWorld

        w = FactoryWorld()
        w.started = True
        w.power_restored = True
        w.money_rescued = w.money_quota
        for r in range(w.rows):
            for c in range(w.cols):
                if w.grid[r][c].kind == "dest":
                    w.grid[r][c].delivered_count = w.min_dest_deliveries
        cost = ROOM_UNLOCK_COSTS[1]
        w.cash = cost + 500
        self.assertTrue(w.try_unlock_next_room(14, 9))
        self.assertEqual(w.room_stage, 2)
        self.assertEqual(w.cash, 500 + 3000)
        self.assertFalse(w.started)

        # Room 3 grants scaled bonus ($5,000) and pauses again
        w.started = True
        w.power_restored = True
        w.money_rescued = w.money_quota
        for r in range(w.rows):
            for c in range(w.cols):
                if w.grid[r][c].kind == "dest":
                    w.grid[r][c].delivered_count = w.min_dest_deliveries
        cost3 = ROOM_UNLOCK_COSTS[2]
        w.cash = cost3 + 100
        self.assertTrue(w.try_unlock_next_room(29, 9))
        self.assertEqual(w.room_stage, 3)
        self.assertEqual(w.cash, 100 + 5000)
        self.assertFalse(w.started)

    def test_reset_button_requires_confirmation_before_resetting(self) -> None:
        from main import BounceTheChequesGame, ChequeSprites, ForkliftSprites, SoundBank, ThiefSprites

        pygame.init()
        app = BounceTheChequesGame(
            ThiefSprites.load(),
            ChequeSprites.load(),
            SoundBank(sounds={}),
            ForkliftSprites.load(),
        )
        app.show_story = False
        app.world.started = True
        app.world.cash = 7777
        app.world.money_rescued = 1234
        surf = pygame.Surface((1280, 720))
        app.draw(surf)

        # Clicking RESET opens confirmation modal without resetting
        app._handle_mouse_down(1, app.renderer.reset_btn_rect.center)
        self.assertTrue(app.show_reset_confirm)
        self.assertEqual(app.world.cash, 7777)

        app.draw(surf)
        # Clicking CANCEL closes modal without resetting
        app._handle_mouse_down(1, app.renderer.reset_confirm_no_rect.center)
        self.assertFalse(app.show_reset_confirm)
        self.assertEqual(app.world.cash, 7777)

        # Re-open and click YES, RESET -> resets entire game
        app._handle_mouse_down(1, app.renderer.reset_btn_rect.center)
        app.draw(surf)
        app._handle_mouse_down(1, app.renderer.reset_confirm_yes_rect.center)
        self.assertFalse(app.show_reset_confirm)
        self.assertFalse(app.world.started)
        self.assertEqual(app.world.room_stage, 1)
        self.assertEqual(app.world.cash, 3500)
        self.assertEqual(app.world.money_rescued, 0)


        pygame.init()
        app = BounceTheChequesGame(
            ThiefSprites.load(),
            ChequeSprites.load(),
            SoundBank(sounds={}),
            ForkliftSprites.load(),
        )
        app.show_story = False
        app.world.started = True
        app.world.cash = 7777
        app.world.money_rescued = 1234
        surf = pygame.Surface((1280, 720))
        app.draw(surf)

        # Clicking RESET opens confirmation modal without resetting
        app._handle_mouse_down(1, app.renderer.reset_btn_rect.center)
        self.assertTrue(app.show_reset_confirm)
        self.assertEqual(app.world.cash, 7777)

        app.draw(surf)
        # Clicking CANCEL closes modal without resetting
        app._handle_mouse_down(1, app.renderer.reset_confirm_no_rect.center)
        self.assertFalse(app.show_reset_confirm)
        self.assertEqual(app.world.cash, 7777)

        # Re-open and click YES, RESET -> resets entire game
        app._handle_mouse_down(1, app.renderer.reset_btn_rect.center)
        app.draw(surf)
        app._handle_mouse_down(1, app.renderer.reset_confirm_yes_rect.center)
        self.assertFalse(app.show_reset_confirm)
        self.assertFalse(app.world.started)
        self.assertEqual(app.world.room_stage, 1)
        self.assertEqual(app.world.cash, 3500)
        self.assertEqual(app.world.money_rescued, 0)

    def test_tab_hides_popups_and_settings_controls_popups_and_volume(self) -> None:
        from factory_renderer import ChequeSprites, ForkliftSprites, ThiefSprites
        from main import BounceTheChequesGame, SoundBank

        pygame.init()
        sfx = SoundBank(sounds={})
        app = BounceTheChequesGame(
            ThiefSprites.load(),
            ChequeSprites.load(),
            sfx,
            ForkliftSprites.load(),
        )
        app.show_story = False
        surf = pygame.Surface((1280, 720))

        self.assertFalse(app.renderer.hide_all_popups)
        app._handle_key_down(pygame.K_TAB)
        self.assertTrue(app.renderer.hide_all_popups)
        app._handle_key_down(pygame.K_TAB)
        self.assertFalse(app.renderer.hide_all_popups)

        app.draw(surf)
        app._handle_mouse_down(1, app.renderer.settings_btn_rect.center)
        self.assertTrue(app.show_settings)
        app.draw(surf)

        app._handle_mouse_down(1, app.renderer.settings_toggle_rects["floating"].center)
        app._handle_mouse_down(1, app.renderer.settings_toggle_rects["prompts"].center)
        app._handle_mouse_down(1, app.renderer.settings_toggle_rects["labels"].center)
        self.assertFalse(app.renderer.show_floating_popups)
        self.assertFalse(app.renderer.show_world_prompts)
        self.assertFalse(app.renderer.show_pile_bag_labels)

        start_music = sfx.music_volume
        app._handle_mouse_down(1, app.renderer.settings_music_plus_rect.center)
        self.assertAlmostEqual(sfx.music_volume, min(1.0, start_music + 0.10), places=2)
        app._handle_mouse_down(1, app.renderer.settings_sfx_minus_rect.center)
        self.assertAlmostEqual(sfx.sfx_volume, 0.90, places=2)
        app._handle_mouse_down(1, app.renderer.settings_mute_rect.center)
        self.assertTrue(app.muted)

        app._handle_key_down(pygame.K_ESCAPE)
        self.assertFalse(app.show_settings)


if __name__ == "__main__":
    unittest.main()
