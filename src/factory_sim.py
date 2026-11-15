from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field

from factory_data import (
    BAD_CHEQUE_TYPES,
    BUILD_REACH,
    CASH_COMMISSION_RATE,
    CHEQUE_ORDER,
    CHEQUE_TYPES,
    CLEAN_DECAL_COST,
    CLEAR_PILEUP_COST,
    DIRS,
    FIXER_FAST_TIME,
    FIXER_SLOW_TIME,
    GRID_COLS,
    GRID_ROWS,
    INTERACT_REACH,
    LEVELS,
    MACHINE_MAX_LEVEL,
    MACHINE_UPGRADE_COSTS,
    NEGLECT_INTERVAL,
    POLISHER_FAST_TIME,
    POLISHER_SLOW_TIME,
    SCANNER_FAST_TIME,
    SCANNER_SLOW_TIME,
    STAMPER_FAST_TIME,
    STAMPER_SLOW_TIME,
    STAMPER_UPGRADE_COST,
    TOOL_COSTS,
    UPGRADABLE_MACHINES,
    UPGRADE_MAX_TIER,
    UPGRADE_TIER_COSTS,
    UPGRADES,
    CrateDef,
    LevelDef,
)

BELT_SPEED = 2.20
AIR_DURATION = 0.42
PLAYER_SPEED = 4.9
PLAYER_SPRINT_MULT = 1.65
FORKLIFT_SPEED = 3.25
FORKLIFT_MAX_CARRIED = 18
FORKLIFT_AUTOPILOT_COST = 550
MAX_CHEQUES = 80
MAX_CARRIED = 8
ROOM_FORKLIFT_SPAWNS: tuple[tuple[int, float, float], ...] = (
    (1, 5.5, 11.5),
    (2, 19.5, 11.5),
    (3, 30.5, 13.5),
    (4, 46.5, 10.5),
)


@dataclass
class Tile:
    """Single 48x48 factory tile with structural, floor wear, and machine state."""

    kind: str = "empty"
    dir_idx: int = 1
    color_key: str = "payroll"
    jammed: bool = False
    require_stamp: bool = False
    spawn_timer: float = 0.0
    spawn_interval: float = 2.0
    spawn_count: int = 0
    burst_count: int = 4
    jam_burst_queue: int = 0
    delivered_count: int = 0
    bounce_anim: float = 0.0
    stamp_anim: float = 0.0

    floor_variant: str = "clean"  # "clean", "dirty", "cracked", "hazard"
    decal: str = "none"  # "none", "oil", "puddle", "rubbish", "drain"
    is_doorway: bool = False
    pile_tier: int = 0  # 0=none, 1=small, 2=large, 3=giant mountain
    pile_kind: str = "payroll"
    pile_variant: int = 0
    paid_cost: int = 0
    toggle_state: int = 0
    splitter_straight_color: str = "payroll"
    splitter_branch_color: str = "vip"
    sorter_branch_color: str = "vip"
    scanner_mode: str = "fraud"
    truck_bay_idx: int = -1
    overclocked: bool = False
    machine_level: int = 1
    door_stage: int = 1
    crate_stock: int = 0
    crate_max: int = 0
    require_boost: bool = False
    require_fix: bool = False
    require_polish: bool = False
    require_scan: bool = False
    loading_corner: int = -1
    pile_master: bool = False
    depot_items: list["ChequeItem"] = field(default_factory=list)


@dataclass
class ChequeItem:
    """Moving or bouncing cheque item on the factory floor."""

    x: float
    y: float
    color_key: str
    value: int
    disguise_color: str = ""
    stamped: bool = True
    misprint: bool = False
    polished: bool = False
    fraud_scanned: bool = False
    move_dir: int = 1
    airborne: bool = False
    start_x: float = 0.0
    start_y: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    air_progress: float = 0.0
    stamped_by: tuple[int, int] | None = None
    fixed_by: tuple[int, int] | None = None
    polished_by: tuple[int, int] | None = None
    scanned_by: tuple[int, int] | None = None
    boosted_by: set[tuple[int, int]] = field(default_factory=set)

    @property
    def apparent_color(self) -> str:
        """Visible/routing color: fake cheques disguise themselves as a real cheque type."""
        if self.color_key == "fake" and self.disguise_color:
            return self.disguise_color
        return self.color_key

    sorted_by: set[tuple[int, int]] = field(default_factory=set)
    last_split_tile: tuple[int, int] | None = None
    split_dir: int = -1
    stamp_hold: float = 0.0
    process_hold: float = 0.0
    age: float = 0.0
    max_age: float = 0.0
    expired: bool = False


@dataclass
class FloatingText:
    """World-space popup feedback text."""

    x: float
    y: float
    text: str
    color: tuple[int, int, int]
    ttl: float = 1.25


@dataclass
class Particle:
    """Short-lived world-space visual effect particle."""

    x: float
    y: float
    vx: float
    vy: float
    color: tuple[int, int, int]
    size: float = 4.0
    ttl: float = 0.5
    max_ttl: float = 0.5


@dataclass
class ForkliftUnit:
    """Drivable factory forklift for lifting and relocating conveyors & machines."""

    x: float
    y: float
    facing_left: bool = False
    moving: bool = False
    autopilot: bool = False
    cooldown: float = 0.0
    room_stage: int = 1
    carried_machine: dict[str, object] | None = None


class FactoryWorld:
    """Simulates the multi-bay factory, player movement/reach, and cheque automation."""

    def __init__(self, level_idx: int = 0) -> None:
        self.cols = GRID_COLS
        self.rows = GRID_ROWS
        self.level_idx = 0
        self.current_level: LevelDef = LEVELS[0]
        self.grid: list[list[Tile]] = []
        self.cheques: list[ChequeItem] = []
        self.popups: list[FloatingText] = []
        self.particles: list[Particle] = []
        self.lights: list[dict[str, object]] = []
        self.forklifts: list[ForkliftUnit] = []
        self.player_forklift_idx: int | None = None
        self.sfx_queue: list[str] = []

        self.player_x = 6.5
        self.player_y = 6.5
        self.facing_left = False
        self.player_anim = "idle"
        self.anim_time = 0.0
        self.action_timer = 0.0
        self.jump_timer = 0.0
        self.jump_vx = 0.0
        self.jump_vy = 0.0

        self.carried_cheques: list[str] = []
        self.walk_target: tuple[float, float] | None = None
        self.walk_path: list[tuple[float, float]] = []
        self.pending_action: tuple[str, int, int, str, int, str] | None = None
        self.selected_tool_kind: str = ""
        self._walk_stall_timer = 0.0
        self.power_restored = False
        self.on_oil = False

        self.upgrades: dict[str, int] = {}
        self.truck_bays: list[dict[str, object]] = []
        self.room_stage = 1
        self.low_cash_timer = 0.0
        self.room_open_anim: float = 0.0
        self.room_open_col: int = -1
        self.room_open_stage: int = 1
        self.bulkhead_ready_stage: int = 1
        self.streak = 0
        self.max_streak = 0
        self.streak_timer = 0.0
        self.neglect_timer = 10.0
        self.neglect_penalties = 0
        self.recent_earnings: deque[tuple[float, int]] = deque()
        self.screen_shake = 0.0
        self.drone_x = 6.5
        self.drone_y = 5.7
        self.drone_laser_target: tuple[float, float] | None = None
        self.drone_laser_timer = 0.0
        self.drone_cooldown = 0.0

        self.cash = 1500
        self.money_rescued = 0
        self.money_quota = 5000
        self.wrong_deliveries = 0
        self.cheques_rescued_count = 0
        self.lost_cheques_count = 0
        self.lost_cheques_value = 0
        self.elapsed_time = 0.0
        self.started = False
        self.paused = False
        self.sim_speed = 1.0
        self.level_complete = False
        self.level_failed = False

        self.load_level(level_idx)

    def _populate_room_segment(self, lvl: LevelDef) -> None:
        """Populate floor zones, decals, walls, machines, crates, and lights for a room segment."""
        for x1, y1, x2, y2 in lvl.dirty_zones:
            for r in range(max(1, y1), min(self.rows - 1, y2 + 1)):
                for c in range(max(1, x1), min(self.cols - 1, x2 + 1)):
                    self.grid[r][c].floor_variant = "dirty"
        for c, r in lvl.cracked_tiles:
            if self.in_bounds(c, r):
                self.grid[r][c].floor_variant = "cracked"
        for c, r in lvl.hazard_tiles:
            if self.in_bounds(c, r):
                self.grid[r][c].floor_variant = "hazard"

        for c, r in lvl.oil_stains:
            if self.in_bounds(c, r):
                self.grid[r][c].decal = "oil"
        for c, r in lvl.puddles:
            if self.in_bounds(c, r):
                self.grid[r][c].decal = "puddle"
        for c, r in lvl.rubbish:
            if self.in_bounds(c, r):
                self.grid[r][c].decal = "rubbish"
        for c, r in lvl.drains:
            if self.in_bounds(c, r):
                self.grid[r][c].decal = "drain"

        for x1, y1, x2, y2 in lvl.void_rects:
            for r in range(max(0, y1), min(self.rows, y2 + 1)):
                for c in range(max(lvl.start_col, x1), min(self.cols, x2 + 1)):
                    vt = self.grid[r][c]
                    vt.kind = "void"
                    vt.decal = "none"
                    vt.floor_variant = "clean"

        seg_end = min(self.cols, lvl.room_cols)
        wall_ring: list[tuple[int, int]] = []
        for r in range(self.rows):
            for c in range(lvl.start_col, seg_end):
                if self.grid[r][c].kind == "void":
                    continue
                touches_void = False
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dc == 0 and dr == 0:
                            continue
                        nc, nr = c + dc, r + dr
                        if not self.in_bounds(nc, nr):
                            continue
                        if nc < lvl.start_col and (dc != 0 and dr != 0):
                            continue
                        if self.grid[nr][nc].kind == "void":
                            touches_void = True
                            break
                    if touches_void:
                        break
                if touches_void:
                    wall_ring.append((c, r))
        for c, r in wall_ring:
            self.grid[r][c].kind = "wall"

        for c, r in lvl.windows:
            if self.in_bounds(c, r):
                self.grid[r][c].kind = "window"
        for c, r in lvl.walls:
            if self.in_bounds(c, r):
                self.grid[r][c].kind = "wall"
        for c, r in lvl.pillars:
            if self.in_bounds(c, r):
                self.grid[r][c].kind = "pillar"
        for c, r in lvl.fences:
            if self.in_bounds(c, r):
                self.grid[r][c].kind = "fence"
        for c, r in lvl.grates:
            if self.in_bounds(c, r):
                self.grid[r][c].kind = "grate"
        for c, r, is_open in lvl.doors:
            if self.in_bounds(c, r):
                self.grid[r][c].kind = "door_open" if is_open else "door_closed"
                self.grid[r][c].is_doorway = True
        for c, r, req_stage in lvl.stage_doors:
            if self.in_bounds(c, r):
                t = self.grid[r][c]
                t.kind = "door_open" if req_stage <= self.room_stage else "door_closed"
                t.door_stage = req_stage
                t.is_doorway = True
        for c, r in lvl.breakers:
            if self.in_bounds(c, r):
                self.grid[r][c].kind = "breaker"
                self.grid[r][c].jammed = True

        for run in lvl.initial_belts:
            step_x = 0 if run.x1 == run.x2 else (1 if run.x2 > run.x1 else -1)
            step_y = 0 if run.y1 == run.y2 else (1 if run.y2 > run.y1 else -1)
            cx, cy = run.x1, run.y1
            while True:
                if self.in_bounds(cx, cy):
                    t = self.grid[cy][cx]
                    if t.kind in ("empty", "door_open"):
                        t.kind = "belt"
                        t.dir_idx = run.dir_idx
                if cx == run.x2 and cy == run.y2:
                    break
                cx += step_x
                cy += step_y

        for src in lvl.sources:
            t = self.grid[src.row][src.col]
            t.kind = "jammed_source" if src.jammed else "source"
            t.dir_idx = src.dir_idx
            t.color_key = src.color_key
            t.jammed = src.jammed
            t.require_stamp = src.require_stamp
            t.require_fix = src.require_fix
            t.spawn_interval = src.interval
            t.burst_count = src.burst_count
            t.spawn_timer = 0.65 if src.jammed else 10.0

        for dst in lvl.dests:
            t = self.grid[dst.row][dst.col]
            t.kind = "dest"
            t.color_key = dst.color_key
            t.require_boost = dst.require_boost
            t.require_polish = dst.require_polish
            t.require_scan = dst.require_scan

        for p in lvl.pileups:
            if self.in_bounds(p.col, p.row):
                t = self.grid[p.row][p.col]
                t.pile_tier = p.tier
                t.pile_kind = p.kind
                t.pile_variant = p.variant

        for tb in lvl.truck_bays:
            bay_idx = len(self.truck_bays)
            mc = min(self.cols - 1, max(0, tb.col + 1))
            mr = min(self.rows - 1, max(0, tb.row - 1))
            for pr in range(tb.row - 2, tb.row + 1):
                for pc in range(tb.col, tb.col + 3):
                    if not self.in_bounds(pc, pr):
                        continue
                    hp = self.grid[pr][pc]
                    if hp.kind in ("void", "wall", "window", "door_closed"):
                        continue
                    hp.kind = "huge_pile"
                    hp.hazard = True
                    hp.dir_idx = tb.dir_idx
                    hp.color_key = tb.color_key
                    hp.spawn_interval = 1.25
                    hp.spawn_timer = 0.85
                    hp.truck_bay_idx = bay_idx
                    hp.pile_master = pc == mc and pr == mr
                    if hp.pile_master:
                        hp.crate_stock = tb.dump_count
                        hp.crate_max = max(24, tb.dump_count * 2)
            self.truck_bays.append(
                {
                    "col": tb.col,
                    "row": tb.row,
                    "master_col": mc,
                    "master_row": mr,
                    "crate_col": tb.crate_col,
                    "crate_row": tb.crate_row,
                    "dir_idx": tb.dir_idx,
                    "color_key": tb.color_key,
                    "interval": tb.interval,
                    "timer": tb.interval * 0.75,
                    "dump_count": tb.dump_count,
                    "crate_stock": tb.crate_stock,
                    "truck_anim": 0.0,
                }
            )

        for lgt in lvl.lights:
            self.lights.append(
                {
                    "col": lgt.col,
                    "row": lgt.row,
                    "radius": lgt.radius,
                    "state": lgt.state,
                }
            )

        for st_num, fx, fy in ROOM_FORKLIFT_SPAWNS:
            if lvl.start_col <= fx < seg_end and not any(
                fl.room_stage == st_num for fl in self.forklifts
            ):
                self.forklifts.append(ForkliftUnit(x=fx, y=fy, room_stage=st_num))

    def next_room_unlock_cost(self) -> int:
        if self.room_stage >= len(LEVELS):
            return 0
        return LEVELS[self.room_stage].unlock_cost

    def room_unlock_block_reason(self, target_stage: int | None = None) -> str | None:
        if self.room_stage >= len(LEVELS):
            return "MAX ROOM"
        if target_stage is not None and target_stage > self.room_stage + 1:
            return f"OPEN RM{self.room_stage + 1} FIRST!"
        if not self.power_restored:
            return "FLIP BREAKER FIRST!"
        if self.money_rescued < self.money_quota:
            return f"NEED ${self.money_quota:,} QUOTA!"
        satisfied, total = self.dest_tubes_status()
        if total > 0 and satisfied < total:
            return f"FILL TUBES ({satisfied}/{total})!"
        cost = self.next_room_unlock_cost()
        if self.cash < cost:
            return f"NEED ${cost:,} CASH!"
        return None

    def can_unlock_next_room(self) -> bool:
        return self.room_unlock_block_reason() is None

    def try_unlock_next_room(self, col: int, row: int) -> bool:
        reason = self.room_unlock_block_reason()
        if reason is not None:
            self._emit_sfx("error")
            self.popups.append(
                FloatingText(col + 0.5, row - 0.1, reason, (255, 188, 86))
            )
            return False
        cost = self.next_room_unlock_cost()
        self.cash -= cost
        self._append_room_wing(self.room_stage, silent=False, paid_cost=cost)
        self.player_anim = "crowbar"
        self.action_timer = 0.45
        self._check_quota()
        return True

    def _append_room_wing(
        self, stage_idx: int, silent: bool = False, paid_cost: int = 0
    ) -> None:
        """Physically append the next contiguous room onto the live factory without resetting existing rooms."""
        if stage_idx <= 0 or stage_idx >= len(LEVELS):
            return
        lvl = LEVELS[stage_idx]
        old_cols = self.cols
        new_cols = lvl.room_cols
        if new_cols > old_cols:
            extra = new_cols - old_cols
            for r in range(self.rows):
                self.grid[r].extend(Tile() for _ in range(extra))
            self.cols = new_cols
            for c in range(old_cols, new_cols):
                self.grid[0][c].kind = "wall"
                self.grid[self.rows - 1][c].kind = "wall"
            for r in range(self.rows):
                self.grid[r][new_cols - 1].kind = "wall"

        self.room_stage = stage_idx + 1
        self.level_idx = stage_idx
        self.current_level = lvl
        self.money_quota = lvl.quota

        for r in range(self.rows):
            for c in range(old_cols):
                t = self.grid[r][c]
                if t.kind == "door_closed" and t.door_stage <= self.room_stage:
                    t.kind = "door_open"
                    t.is_doorway = True
                    if not silent:
                        self._spawn_particles(
                            c + 0.5, r + 0.5, (120, 232, 255), count=10, speed=2.8
                        )

        self._populate_room_segment(lvl)
        if lvl.breakers:
            self.power_restored = False

        if not silent:
            room_bonus = (0, 3000, 5000, 7500)[min(3, max(0, stage_idx))]
            self.cash += room_bonus
            self.started = False
            for r in range(self.rows):
                for c in range(self.cols):
                    st = self.grid[r][c]
                    if st.kind in ("source", "jammed_source", "crate"):
                        st.spawn_interval = max(0.55, st.spawn_interval * 0.85)
            self.room_open_anim = 1.65
            self.room_open_col = old_cols - 1
            self.room_open_stage = self.room_stage
            for r in range(self.rows):
                if (
                    0 <= old_cols - 1 < self.cols
                    and self.grid[r][old_cols - 1].kind == "door_open"
                ):
                    self._spawn_particles(
                        old_cols - 0.5,
                        r + 0.5,
                        (255, 224, 96),
                        count=18,
                        speed=3.6,
                        ttl=0.75,
                        size=5.0,
                    )
            if paid_cost > 0:
                msg = f"ROOM {self.room_stage} ONLINE! (-${paid_cost:,} | +${room_bonus:,} SETUP)"
            else:
                msg = f"ROOM {self.room_stage} ONLINE! (+${room_bonus:,} SETUP)"
            self.screen_shake = max(self.screen_shake, 0.38)
            self._emit_sfx("upgrade")
            self.popups.append(
                FloatingText(
                    self.player_x,
                    self.player_y - 0.7,
                    msg,
                    (110, 248, 255),
                    ttl=2.8,
                )
            )

    def expand_to_stage(self, target_stage: int) -> None:
        """Expand the continuous factory in place up to target_stage without clearing Room 1."""
        clamped = max(1, min(len(LEVELS), target_stage))
        while self.room_stage < clamped:
            self._append_room_wing(self.room_stage, silent=False)

    def load_level(self, level_idx: int) -> None:
        """Reset world state starting in Room 1, optionally expanding in place up to level_idx."""
        target_idx = level_idx % len(LEVELS)
        lvl0 = LEVELS[0]
        self.level_idx = 0
        self.current_level = lvl0
        self.cols = lvl0.room_cols
        self.room_stage = 1

        self.grid = [[Tile() for _ in range(self.cols)] for _ in range(self.rows)]
        for c in range(self.cols):
            self.grid[0][c].kind = "wall"
            self.grid[self.rows - 1][c].kind = "wall"
        for r in range(self.rows):
            self.grid[r][0].kind = "wall"
            self.grid[r][self.cols - 1].kind = "wall"

        self.lights = []
        self.truck_bays = []
        self.forklifts = []
        self.player_forklift_idx = None
        self.cheques = []
        self.popups = []
        self.particles = []
        self.sfx_queue = []
        self._populate_room_segment(lvl0)
        self.power_restored = len(lvl0.breakers) == 0

        for s in range(1, target_idx + 1):
            self._append_room_wing(s, silent=True)

        self.player_x, self.player_y = LEVELS[target_idx].player_start
        self.facing_left = False
        self.player_anim = "idle"
        self.action_timer = 0.0
        self.jump_timer = 0.0
        self.carried_cheques = []
        self.walk_target = None
        self.walk_path = []
        self.pending_action = None
        self._walk_stall_timer = 0.0
        self.on_oil = False

        self.upgrades = {}
        self.low_cash_timer = 0.0
        self.room_open_anim = 0.0
        self.room_open_col = -1
        self.room_open_stage = 1
        self.bulkhead_ready_stage = 1
        self.streak = 0
        self.max_streak = 0
        self.streak_timer = 0.0
        self.neglect_timer = 10.0
        self.neglect_penalties = 0
        self.recent_earnings.clear()
        self.screen_shake = 0.0
        self.drone_x = self.player_x
        self.drone_y = self.player_y - 0.8
        self.drone_laser_target = None
        self.drone_laser_timer = 0.0
        self.drone_cooldown = 0.0

        self.cash = LEVELS[target_idx].starting_cash
        self.money_rescued = 0
        self.money_quota = LEVELS[target_idx].quota
        self.wrong_deliveries = 0
        self.cheques_rescued_count = 0
        self.lost_cheques_count = 0
        self.lost_cheques_value = 0
        self.elapsed_time = 0.0
        self.started = False
        self.paused = False
        self.sim_speed = 1.0
        self.level_complete = False
        self.level_failed = False

    def in_bounds(self, col: int, row: int) -> bool:
        return 0 <= col < self.cols and 0 <= row < self.rows

    def player_dist(self, col: int, row: int) -> float:
        return math.hypot((col + 0.5) - self.player_x, (row + 0.5) - self.player_y)

    def upgrade_tier(self, key: str) -> int:
        return self.upgrades.get(key, 0)

    def upgrade_next_cost(self, key: str) -> int | None:
        tier = self.upgrade_tier(key)
        if tier >= UPGRADE_MAX_TIER:
            return None
        costs = UPGRADE_TIER_COSTS.get(key)
        if costs is None:
            return None
        return costs[tier]

    @property
    def build_reach(self) -> float:
        return BUILD_REACH + (0.0, 2.0, 3.5, 5.0)[self.upgrade_tier("long_reach")]

    @property
    def interact_reach(self) -> float:
        return INTERACT_REACH + (0.0, 1.0, 2.0, 3.0)[self.upgrade_tier("long_reach")]

    @property
    def in_forklift(self) -> bool:
        return (
            self.player_forklift_idx is not None
            and 0 <= self.player_forklift_idx < len(self.forklifts)
        )

    @property
    def active_forklift(self) -> ForkliftUnit | None:
        if not self.in_forklift or self.player_forklift_idx is None:
            return None
        return self.forklifts[self.player_forklift_idx]

    @property
    def max_carry_capacity(self) -> int:
        return FORKLIFT_MAX_CARRIED if self.in_forklift else MAX_CARRIED

    @property
    def belt_speed(self) -> float:
        return BELT_SPEED * (1.0, 1.30, 1.60, 1.95)[self.upgrade_tier("turbo_belts")]

    @property
    def commission_rate(self) -> float:
        return (CASH_COMMISSION_RATE, 0.14, 0.17, 0.21)[
            self.upgrade_tier("commission_boost")
        ]

    @property
    def fine_multiplier(self) -> float:
        return (1.0, 0.65, 0.35, 0.15)[self.upgrade_tier("fraud_shield")]

    def effective_machine_level(self, tile: Tile) -> int:
        return min(
            MACHINE_MAX_LEVEL, max(tile.machine_level, 2 if tile.overclocked else 1)
        )

    def machine_upgrade_cost(self, tile: Tile) -> int | None:
        if tile.kind not in UPGRADABLE_MACHINES:
            return None
        lvl = self.effective_machine_level(tile)
        if lvl >= MACHINE_MAX_LEVEL:
            return None
        costs = MACHINE_UPGRADE_COSTS.get(tile.kind)
        if costs is None:
            return None
        idx = lvl - 1
        return costs[idx] if 0 <= idx < len(costs) else None

    def stamper_cycle_time(self, tile: Tile) -> float:
        base = (STAMPER_SLOW_TIME, 0.35, 0.18, 0.08)[self.upgrade_tier("vip_endorser")]
        lvl = self.effective_machine_level(tile)
        if lvl >= 3:
            return min(base, 0.08)
        if lvl == 2:
            return min(base, STAMPER_FAST_TIME)
        return base

    def fixer_cycle_time(self, tile: Tile) -> float:
        lvl = self.effective_machine_level(tile)
        base = (FIXER_SLOW_TIME, FIXER_FAST_TIME * 0.75, 0.04)[lvl - 1]
        turbo_mult = (1.0, 0.85, 0.72, 0.60)[self.upgrade_tier("turbo_belts")]
        return base * turbo_mult

    def polisher_cycle_time(self, tile: Tile) -> float:
        lvl = self.effective_machine_level(tile)
        base = (POLISHER_SLOW_TIME, POLISHER_FAST_TIME, 0.08)[lvl - 1]
        turbo_mult = (1.0, 0.85, 0.72, 0.60)[self.upgrade_tier("turbo_belts")]
        return base * turbo_mult

    def scanner_cycle_time(self, tile: Tile) -> float:
        lvl = self.effective_machine_level(tile)
        base = (SCANNER_SLOW_TIME, SCANNER_FAST_TIME * 0.70, 0.0)[lvl - 1]
        turbo_mult = (1.0, 0.85, 0.70, 0.55)[self.upgrade_tier("turbo_belts")]
        return base * turbo_mult

    def shredder_cycle_time(self, tile: Tile) -> float:
        lvl = self.effective_machine_level(tile)
        base = (0.30, 0.14, 0.0)[lvl - 1]
        turbo_mult = (1.0, 0.85, 0.70, 0.55)[self.upgrade_tier("turbo_belts")]
        return base * turbo_mult

    def machine_accuracy(self, tile: Tile) -> float:
        lvl = self.effective_machine_level(tile)
        return (0.80, 0.90, 1.00)[min(2, max(0, lvl - 1))]

    def tile_belt_speed(self, tile: Tile) -> float:
        lvl = self.effective_machine_level(tile)
        mult = (
            (1.0, 1.32, 1.68)[lvl - 1]
            if tile.kind == "belt"
            else (1.0, 1.15, 1.30)[lvl - 1]
        )
        return self.belt_speed * mult

    def _splitter_output_dir(self, tile: Tile, color_key: str) -> int:
        out_dir = tile.dir_idx if tile.toggle_state % 2 == 0 else (tile.dir_idx + 1) % 4
        tile.toggle_state = (tile.toggle_state + 1) % 2
        return out_dir

    def next_stage_goal(self) -> int | None:
        if self.room_stage >= len(LEVELS):
            return None
        return self.money_quota

    @property
    def combo_multiplier(self) -> float:
        if self.streak >= 22:
            return 1.75
        if self.streak >= 14:
            return 1.50
        if self.streak >= 8:
            return 1.30
        if self.streak >= 4:
            return 1.15
        return 1.0

    @property
    def throughput_per_min(self) -> int:
        if self.elapsed_time <= 0.01:
            return 0
        cutoff = self.elapsed_time - 15.0
        while self.recent_earnings and self.recent_earnings[0][0] < cutoff:
            self.recent_earnings.popleft()
        total = sum(amt for _, amt in self.recent_earnings)
        window = max(5.0, min(15.0, self.elapsed_time))
        return int(round(total * 60.0 / window))

    @property
    def star_rating(self) -> int:
        if not self.level_complete:
            return 0
        stars = 1
        if self.wrong_deliveries == 0:
            stars += 1
        if (
            self.elapsed_time <= self.current_level.time_limit * 0.75
            or self.max_streak >= 6
        ):
            stars += 1
        return stars

    def in_build_reach(self, col: int, row: int) -> bool:
        return self.player_dist(col, row) <= self.build_reach

    def in_interact_reach(self, col: int, row: int) -> bool:
        return self.player_dist(col, row) <= self.interact_reach

    def _emit_sfx(self, name: str) -> None:
        if len(self.sfx_queue) < 16:
            self.sfx_queue.append(name)

    def _spawn_particles(
        self,
        x: float,
        y: float,
        color: tuple[int, int, int],
        count: int = 8,
        speed: float = 2.2,
        ttl: float = 0.45,
        size: float = 4.0,
    ) -> None:
        if len(self.particles) >= 160:
            self.particles = self.particles[-(160 - count) :]
        for i in range(count):
            ang = i * 2.399963 + (self.anim_time * 3.1)
            mag = speed * (0.55 + 0.45 * ((i % 3) / 2.0))
            self.particles.append(
                Particle(
                    x=x,
                    y=y,
                    vx=math.cos(ang) * mag,
                    vy=math.sin(ang) * mag,
                    color=color,
                    size=size,
                    ttl=ttl,
                    max_ttl=ttl,
                )
            )

    @property
    def jammed_remaining(self) -> int:
        count = 0
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c].kind == "jammed_source" and self.grid[r][c].jammed:
                    count += 1
        return count

    @property
    def pileups_remaining(self) -> int:
        count = 0
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c].pile_tier > 0:
                    count += 1
        return count

    @property
    def crates_remaining(self) -> int:
        count = 0
        for r in range(self.rows):
            for c in range(self.cols):
                t = self.grid[r][c]
                if t.kind == "crate" and t.crate_stock > 0:
                    count += 1
        return count
        return 0

    @property
    def min_dest_deliveries(self) -> int:
        return self.current_level.min_dest_deliveries

    def dest_tubes_status(self) -> tuple[int, int]:
        target = self.min_dest_deliveries
        satisfied = 0
        total = 0
        for r in range(self.rows):
            for c in range(self.cols):
                t = self.grid[r][c]
                if t.kind == "dest":
                    total += 1
                    if t.delivered_count >= target:
                        satisfied += 1
        return satisfied, total

    def _is_player_blocked(
        self, px: float, py: float, allow_grate: bool = False
    ) -> bool:
        r = 0.27
        for ox in (-r, r):
            for oy in (-r, r):
                tc = int(math.floor(px + ox))
                tr = int(math.floor(py + oy))
                if not self.in_bounds(tc, tr):
                    return True
                t = self.grid[tr][tc]
                if t.kind in (
                    "void",
                    "wall",
                    "window",
                    "pillar",
                    "fence",
                    "door_closed",
                    "source",
                    "jammed_source",
                    "huge_pile",
                    "crate",
                    "dest",
                    "breaker",
                ):
                    return True
                if t.kind == "grate" and not allow_grate:
                    return True
                if t.pile_tier >= 2:
                    return True
        return False

    def _is_tile_walkable(self, col: int, row: int) -> bool:
        if not self.in_bounds(col, row):
            return False
        t = self.grid[row][col]
        if t.kind in (
            "void",
            "wall",
            "window",
            "pillar",
            "fence",
            "door_closed",
            "source",
            "jammed_source",
            "huge_pile",
            "crate",
            "dest",
            "breaker",
            "grate",
        ):
            return False
        return t.pile_tier < 2

    def _player_overlaps_tile(self, col: int, row: int) -> bool:
        return (
            abs(self.player_x - (col + 0.5)) < 0.77
            and abs(self.player_y - (row + 0.5)) < 0.77
        )

    def _nudge_player_out_of_tile(self, col: int, row: int) -> bool:
        """Move player to the closest clear adjacent tile so they never stand inside a placed machine."""
        if not self._player_overlaps_tile(col, row):
            return True
        candidates: list[tuple[float, float, float]] = []
        for dc, dr in (
            (1, 0),
            (-1, 0),
            (0, 1),
            (0, -1),
            (1, 1),
            (-1, 1),
            (1, -1),
            (-1, -1),
        ):
            nc, nr = col + dc, row + dr
            cx, cy = nc + 0.5, nr + 0.5
            if (
                self.in_bounds(nc, nr)
                and not self._is_player_blocked(cx, cy, allow_grate=False)
                and self.grid[nr][nc].kind == "floor"
            ):
                dist2 = (cx - self.player_x) ** 2 + (cy - self.player_y) ** 2
                candidates.append((dist2, cx, cy))
        if not candidates:
            for dc, dr in (
                (1, 0),
                (-1, 0),
                (0, 1),
                (0, -1),
                (1, 1),
                (-1, 1),
                (1, -1),
                (-1, -1),
            ):
                nc, nr = col + dc, row + dr
                cx, cy = nc + 0.5, nr + 0.5
                if self.in_bounds(nc, nr) and not self._is_player_blocked(
                    cx, cy, allow_grate=False
                ):
                    dist2 = (cx - self.player_x) ** 2 + (cy - self.player_y) ** 2
                    candidates.append((dist2, cx, cy))
        if not candidates:
            return False
        candidates.sort(key=lambda item: item[0])
        self.player_x = candidates[0][1]
        self.player_y = candidates[0][2]
        return True

    def _ensure_player_unstuck(self) -> None:
        """Prevent softlocks by rescuing the player if ever inside a blocking tile."""
        if not self._is_player_blocked(
            self.player_x, self.player_y, allow_grate=self.jump_timer > 0.0
        ):
            return
        start_c = max(0, min(self.cols - 1, int(math.floor(self.player_x))))
        start_r = max(0, min(self.rows - 1, int(math.floor(self.player_y))))
        visited: set[tuple[int, int]] = {(start_c, start_r)}
        queue: list[tuple[int, int]] = [(start_c, start_r)]
        while queue:
            c, r = queue.pop(0)
            cx, cy = c + 0.5, r + 0.5
            if (c, r) != (start_c, start_r) and not self._is_player_blocked(
                cx, cy, allow_grate=False
            ):
                self.player_x = cx
                self.player_y = cy
                return
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nc, nr = c + dc, r + dr
                if self.in_bounds(nc, nr) and (nc, nr) not in visited:
                    visited.add((nc, nr))
                    queue.append((nc, nr))

    def _queue_walk(
        self,
        act: str,
        col: int,
        row: int,
        tool_kind: str,
        dir_idx: int,
        filter_color: str,
    ) -> None:
        """Compute shortest walkable path through doorways to within reach of target tile."""
        self.pending_action = (act, col, row, tool_kind, dir_idx, filter_color)
        req = self.interact_reach if act == "interact" else self.build_reach
        sx, sy = int(math.floor(self.player_x)), int(math.floor(self.player_y))
        start = (sx, sy)
        parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        q: deque[tuple[int, int]] = deque([start])
        goal_node: tuple[int, int] | None = None

        while q:
            cx, cy = q.popleft()
            if (cx, cy) != start and math.hypot(cx - col, cy - row) <= req - 0.35:
                goal_node = (cx, cy)
                break
            for dc, dr in DIRS:
                nx, ny = cx + dc, cy + dr
                nxt = (nx, ny)
                if nxt not in parent and self._is_tile_walkable(nx, ny):
                    parent[nxt] = (cx, cy)
                    q.append(nxt)

        if goal_node is not None:
            path: list[tuple[float, float]] = []
            cur: tuple[int, int] | None = goal_node
            while cur is not None and cur != start:
                path.append((cur[0] + 0.5, cur[1] + 0.5))
                cur = parent[cur]
            path.reverse()
            self.walk_path = path
            self.walk_target = path[0] if path else None
            self._walk_stall_timer = 0.0
        else:
            self.walk_path = []
            self.walk_target = (col + 0.5, row + 0.5)
            self._walk_stall_timer = 0.0

    def trigger_jump(self, move_dx: float, move_dy: float) -> None:
        """Jump over maintenance grates and oil slicks."""
        if self.jump_timer > 0.0 or self.in_forklift:
            return
        bag_load = min(1.0, len(self.carried_cheques) / MAX_CARRIED)
        if bag_load >= 1.0:
            return
        self.walk_target = None
        self.walk_path = []
        self.pending_action = None
        self.jump_timer = 0.36
        self.player_anim = "jump"
        if abs(move_dx) < 0.05 and abs(move_dy) < 0.05:
            move_dx = -1.0 if self.facing_left else 1.0
            move_dy = 0.0
        mag = max(0.01, math.hypot(move_dx, move_dy))
        if bag_load <= 0.5:
            jump_mult = 1.0 - (0.5 * bag_load)
        else:
            jump_mult = 2.0 - (2.0 * bag_load)
        jump_speed = PLAYER_SPEED * 1.48 * jump_mult
        self.jump_vx = (move_dx / mag) * jump_speed
        self.jump_vy = (move_dy / mag) * jump_speed

    def _step_with_corner_slide(self, vx: float, vy: float, allow_grate: bool) -> bool:
        """Move horizontally & vertically with smooth corner nudging around pillars/walls."""
        moved = False
        if abs(vx) > 1e-5:
            if not self._is_player_blocked(
                self.player_x + vx, self.player_y, allow_grate
            ):
                self.player_x += vx
                moved = True
            else:
                for nudge in (-0.22, 0.22):
                    if not self._is_player_blocked(
                        self.player_x + vx, self.player_y + nudge, allow_grate
                    ):
                        slide = math.copysign(min(abs(vx) * 0.75, 0.22), nudge)
                        if not self._is_player_blocked(
                            self.player_x, self.player_y + slide, allow_grate
                        ):
                            self.player_y += slide
                            moved = True
                            break

        if abs(vy) > 1e-5:
            if not self._is_player_blocked(
                self.player_x, self.player_y + vy, allow_grate
            ):
                self.player_y += vy
                moved = True
            else:
                for nudge in (-0.22, 0.22):
                    if not self._is_player_blocked(
                        self.player_x + nudge, self.player_y + vy, allow_grate
                    ):
                        slide = math.copysign(min(abs(vy) * 0.75, 0.22), nudge)
                        if not self._is_player_blocked(
                            self.player_x + slide, self.player_y, allow_grate
                        ):
                            self.player_x += slide
                            moved = True
                            break
        return moved

    def move_player(
        self, dx: float, dy: float, dt: float, sprinting: bool = False
    ) -> None:
        """Move the player manually or follow an auto-walk build/interact target."""
        pc = int(math.floor(self.player_x))
        pr = int(math.floor(self.player_y))
        self.on_oil = (
            self.in_bounds(pc, pr)
            and self.grid[pr][pc].decal == "oil"
            and self.jump_timer <= 0.0
        )

        manual_moving = abs(dx) > 0.01 or abs(dy) > 0.01
        if manual_moving:
            self.walk_target = None
            self.walk_path = []
            self.pending_action = None
            self._walk_stall_timer = 0.0

        if self.jump_timer > 0.0:
            self.jump_timer = max(0.0, self.jump_timer - dt)
            self._step_with_corner_slide(
                self.jump_vx * dt, self.jump_vy * dt, allow_grate=True
            )
            self.player_anim = "jump"
            if self.jump_timer == 0.0 and self._is_player_blocked(
                self.player_x, self.player_y, allow_grate=False
            ):
                self._nudge_off_grate()
            return

        auto_walking = False
        if not manual_moving and self.walk_target is not None:
            if self._try_finish_pending():
                return
            while (
                self.walk_path
                and math.hypot(
                    self.walk_path[0][0] - self.player_x,
                    self.walk_path[0][1] - self.player_y,
                )
                <= 0.25
            ):
                self.walk_path.pop(0)
            self.walk_target = self.walk_path[0] if self.walk_path else self.walk_target
            tx, ty = self.walk_target
            dx = tx - self.player_x
            dy = ty - self.player_y
            dist = math.hypot(dx, dy)
            if dist <= 0.25 and not self.walk_path:
                self.walk_target = None
                self.pending_action = None
                dx, dy = 0.0, 0.0
            else:
                auto_walking = True

        moving = manual_moving or auto_walking
        if moving:
            if dx < -0.04:
                self.facing_left = True
            elif dx > 0.04:
                self.facing_left = False

            mag = max(1e-5, math.hypot(dx, dy))
            lr_tier = self.upgrade_tier("long_reach")
            exo_mult = (1.0, 1.15, 1.30, 1.48)[lr_tier]
            if self.in_forklift:
                speed = (
                    FORKLIFT_SPEED
                    * exo_mult
                    * (PLAYER_SPRINT_MULT if sprinting else 1.0)
                )
            else:
                oil_mult = (0.62, 0.78, 0.90, 1.0)[lr_tier] if self.on_oil else 1.0
                bag_load = min(1.0, len(self.carried_cheques) / MAX_CARRIED)
                bag_mult = 1.0 - (0.5 * bag_load)
                speed = (
                    PLAYER_SPEED
                    * exo_mult
                    * (PLAYER_SPRINT_MULT if sprinting else 1.0)
                    * oil_mult
                    * bag_mult
                )
            did_move = self._step_with_corner_slide(
                (dx / mag) * speed * dt,
                (dy / mag) * speed * dt,
                allow_grate=False,
            )
            if auto_walking:
                if self._try_finish_pending():
                    return
                if not did_move:
                    self._walk_stall_timer += dt
                    if self._walk_stall_timer >= 0.45:
                        self.walk_target = None
                        self.walk_path = []
                        self.pending_action = None
                        self._walk_stall_timer = 0.0
                else:
                    self._walk_stall_timer = 0.0

        fl = self.active_forklift
        if fl is not None:
            fl.x = self.player_x
            fl.y = self.player_y
            fl.facing_left = self.facing_left
            fl.moving = moving

        if self.action_timer > 0.0:
            return
        if moving:
            self.player_anim = "sprint" if sprinting else "walk"
        else:
            self.player_anim = "idle"

    def _try_finish_pending(self) -> bool:
        if self.pending_action is None:
            return False
        act, col, row, tool_kind, dir_idx, filter_color = self.pending_action
        in_reach = (
            self.in_interact_reach(col, row)
            if act == "interact"
            else self.in_build_reach(col, row)
        )
        if not in_reach:
            return False
        self.walk_target = None
        self.walk_path = []
        self.pending_action = None
        if act == "interact":
            self.interact_tile(col, row, ignore_reach=True)
        elif act == "remove":
            self.remove_tile(col, row, ignore_reach=True)
        else:
            self.place_tile(
                col, row, tool_kind, dir_idx, filter_color, ignore_reach=True
            )
        return True

    def _nudge_off_grate(self) -> None:
        cx, cy = int(math.floor(self.player_x)), int(math.floor(self.player_y))
        for radius in range(1, 5):
            for dc in (-radius, radius, 0):
                for dr in (0, -radius, radius):
                    nc, nr = cx + dc, cy + dr
                    if self.in_bounds(nc, nr) and not self._is_player_blocked(
                        nc + 0.5, nr + 0.5, allow_grate=False
                    ):
                        self.player_x = nc + 0.5
                        self.player_y = nr + 0.5
                        return

    def _adjust_money(self, rescued_delta: int, cash_delta: int | None = None) -> None:
        if cash_delta is None:
            cash_delta = (
                int(round(rescued_delta * self.commission_rate))
                if rescued_delta > 0
                else rescued_delta
            )
        self.money_rescued += rescued_delta
        self.cash += cash_delta
        if rescued_delta > 0:
            self.recent_earnings.append((self.elapsed_time, rescued_delta))

    def _blocked_if_in_forklift(self) -> bool:
        if not self.in_forklift:
            return False
        if not self.popups or self.popups[-1].text != "EXIT FORKLIFT [G] TO BUILD/BUY!":
            self._emit_sfx("error")
            self.popups.append(
                FloatingText(
                    self.player_x,
                    self.player_y - 0.6,
                    "EXIT FORKLIFT [G] TO BUILD/BUY!",
                    (255, 190, 68),
                )
            )
        return True

    def buy_upgrade(self, key: str) -> bool:
        """Purchase the next tier of a multi-tier wing upgrade with spendable cash."""
        if self._blocked_if_in_forklift():
            return False
        spec = next((u for u in UPGRADES if u[0] == key), None)
        if spec is None:
            return False
        _, name, _, _ = spec
        cur_tier = self.upgrade_tier(key)
        cost = self.upgrade_next_cost(key)
        if cost is None or cur_tier >= UPGRADE_MAX_TIER:
            self.popups.append(
                FloatingText(
                    self.player_x, self.player_y - 0.5, "MAX TIER!", (160, 224, 255)
                )
            )
            self._emit_sfx("error")
            return False
        if self.cash < cost:
            self.popups.append(
                FloatingText(
                    self.player_x, self.player_y - 0.5, f"NEED ${cost}!", (255, 86, 86)
                )
            )
            self._emit_sfx("error")
            return False

        self.cash -= cost
        new_tier = cur_tier + 1
        self.upgrades[key] = new_tier
        if key == "auto_drone" and new_tier == 1:
            self.drone_x = self.player_x
            self.drone_y = self.player_y - 0.8
            self.drone_cooldown = 0.15
        self._spawn_particles(
            self.player_x, self.player_y, (255, 222, 86), count=14, speed=3.0, size=5.0
        )
        self._emit_sfx("upgrade")
        self.popups.append(
            FloatingText(
                self.player_x,
                self.player_y - 0.6,
                f"UPGRADED: {name.upper()} T{new_tier}!",
                (255, 228, 96),
            )
        )
        return True

    def _blocked_if_paused(self) -> bool:
        if not self.paused:
            return False
        if not self.popups or self.popups[-1].text != "PAUSED! [F] RESUME":
            self.popups.append(
                FloatingText(
                    self.player_x,
                    self.player_y - 0.5,
                    "PAUSED! [F] RESUME",
                    (255, 210, 92),
                )
            )
            self._emit_sfx("error")
        return True

    def upgrade_machine_tile(
        self, col: int, row: int, ignore_reach: bool = False
    ) -> bool:
        """Upgrade an individual placed machine tile (MK1 -> MK2 -> MK3) using cash."""
        if self._blocked_if_paused() or self._blocked_if_in_forklift():
            return False
        if not self.in_bounds(col, row):
            return False
        if not ignore_reach and not self.in_build_reach(col, row):
            return False
        tile = self.grid[row][col]
        if tile.kind not in UPGRADABLE_MACHINES:
            return False
        cur_lvl = self.effective_machine_level(tile)
        cost = self.machine_upgrade_cost(tile)
        if cost is None or cur_lvl >= MACHINE_MAX_LEVEL:
            self._emit_sfx("error")
            self.popups.append(
                FloatingText(col + 0.5, row - 0.1, "MACHINE MAX MK3!", (160, 224, 255))
            )
            return False
        if self.cash < cost:
            self._emit_sfx("error")
            self.popups.append(
                FloatingText(
                    col + 0.5, row - 0.1, f"NEED ${cost} TO UPG!", (255, 86, 86)
                )
            )
            return False

        self.cash -= cost
        new_lvl = cur_lvl + 1
        tile.machine_level = new_lvl
        tile.overclocked = new_lvl >= 2
        tile.paid_cost += cost
        tile.stamp_anim = 1.0
        self.facing_left = (col + 0.5) < self.player_x
        self.player_anim = "place"
        self.action_timer = 0.28
        self._spawn_particles(
            col + 0.5, row + 0.5, (110, 232, 255), count=12, speed=2.6
        )
        self._emit_sfx("upgrade")
        msg = (
            f"TURBO STAMP! -${cost}"
            if tile.kind == "stamper" and new_lvl == 2
            else f"{tile.kind.upper()} MK{new_lvl}! -${cost}"
        )
        self.popups.append(FloatingText(col + 0.5, row - 0.1, msg, (110, 238, 255)))
        return True

    def upgrade_nearest_machine(
        self, hover_tile: tuple[int, int] | None = None
    ) -> bool:
        """Upgrade the hovered machine (within build reach) or nearest upgradable machine."""
        if self._blocked_if_paused():
            return False
        if hover_tile is not None:
            hc, hr = hover_tile
            if self.in_bounds(hc, hr) and self.in_build_reach(hc, hr):
                ht = self.grid[hr][hc]
                if ht.kind in UPGRADABLE_MACHINES:
                    return self.upgrade_machine_tile(hc, hr, ignore_reach=True)

        best: tuple[float, int, int] | None = None
        for r in range(self.rows):
            for c in range(self.cols):
                t = self.grid[r][c]
                if (
                    t.kind not in UPGRADABLE_MACHINES
                    or self.machine_upgrade_cost(t) is None
                ):
                    continue
                d = self.player_dist(c, r)
                if d <= self.interact_reach and (best is None or d < best[0]):
                    best = (d, c, r)
        best_fl: tuple[float, int] | None = None
        if not self.in_forklift:
            for idx, fl in enumerate(self.forklifts):
                if fl.autopilot:
                    continue
                d = math.hypot(fl.x - self.player_x, fl.y - self.player_y)
                if d <= self.interact_reach + 0.5 and (
                    best_fl is None or d < best_fl[0]
                ):
                    best_fl = (d, idx)

        if best_fl is not None and (best is None or best_fl[0] <= best[0]):
            fl = self.forklifts[best_fl[1]]
            if self.cash < FORKLIFT_AUTOPILOT_COST:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        fl.x,
                        fl.y - 0.5,
                        f"NEED ${FORKLIFT_AUTOPILOT_COST} FOR AUTO-HAUL!",
                        (255, 86, 86),
                    )
                )
                return False
            self.cash -= FORKLIFT_AUTOPILOT_COST
            fl.autopilot = True
            fl.cooldown = 0.15
            self._spawn_particles(fl.x, fl.y, (110, 238, 255), count=12, speed=2.6)
            self._emit_sfx("upgrade")
            self.popups.append(
                FloatingText(
                    fl.x,
                    fl.y - 0.6,
                    f"FORKLIFT AUTO-HAUL ON! -${FORKLIFT_AUTOPILOT_COST}",
                    (110, 238, 255),
                )
            )
            return True

        if best is not None:
            return self.upgrade_machine_tile(best[1], best[2], ignore_reach=True)
        return False

    def toggle_forklift(self) -> bool:
        """Mount the nearest parked forklift or dismount the currently driven forklift."""
        if self._blocked_if_paused():
            return False
        if self.in_forklift:
            fl = self.active_forklift
            if fl is not None:
                fl.x = self.player_x
                fl.y = self.player_y
                fl.facing_left = self.facing_left
                fl.moving = False
            self.player_forklift_idx = None
            self._emit_sfx("interact")
            self.popups.append(
                FloatingText(
                    self.player_x,
                    self.player_y - 0.5,
                    "EXITED FORKLIFT",
                    (255, 212, 96),
                )
            )
            return True

        best: tuple[float, int] | None = None
        for idx, fl in enumerate(self.forklifts):
            d = math.hypot(fl.x - self.player_x, fl.y - self.player_y)
            if d <= self.interact_reach + 0.6 and (best is None or d < best[0]):
                best = (d, idx)
        if best is None:
            return False
        idx = best[1]
        fl = self.forklifts[idx]
        fl.moving = False
        self.player_forklift_idx = idx
        self.walk_target = None
        self.walk_path = []
        self.pending_action = None
        self.jump_timer = 0.0
        self.player_x = fl.x
        self.player_y = fl.y
        self.facing_left = fl.facing_left
        self._spawn_particles(fl.x, fl.y, (255, 206, 82), count=10, speed=2.4)
        self._emit_sfx("upgrade")
        self.popups.append(
            FloatingText(
                fl.x, fl.y - 0.6, "FORKLIFT! [G] EXIT [X] LIFT MACHINE", (255, 224, 96)
            )
        )
        return True

    def relocate_machine_with_forklift(self) -> bool:
        """Lift a placed conveyor or machine onto the forklift forks, or set it down."""
        if self._blocked_if_paused() or not self.in_forklift:
            return False
        fl = self.active_forklift
        if fl is None:
            return False

        if fl.carried_machine is None:
            best: tuple[float, int, int] | None = None
            for r in range(self.rows):
                for c in range(self.cols):
                    t = self.grid[r][c]
                    if t.kind in UPGRADABLE_MACHINES:
                        d = self.player_dist(c, r)
                        if d <= self.interact_reach + 0.4 and (
                            best is None or d < best[0]
                        ):
                            best = (d, c, r)
            if best is None:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        self.player_x,
                        self.player_y - 0.5,
                        "NO MACHINE IN REACH TO LIFT!",
                        (255, 180, 82),
                    )
                )
                return False
            _, c, r = best
            t = self.grid[r][c]
            fl.carried_machine = {
                "kind": t.kind,
                "dir_idx": t.dir_idx,
                "color_key": t.color_key,
                "sorter_branch_color": t.sorter_branch_color,
                "splitter_straight_color": t.splitter_straight_color,
                "splitter_branch_color": t.splitter_branch_color,
                "scanner_mode": t.scanner_mode,
                "machine_level": t.machine_level,
                "paid_cost": t.paid_cost,
                "toggle_state": t.toggle_state,
                "depot_items": list(t.depot_items),
            }
            self.grid[r][c] = Tile(
                kind="door_open" if t.is_doorway else "empty",
                floor_variant=t.floor_variant,
                decal=t.decal,
                is_doorway=t.is_doorway,
                loading_corner=t.loading_corner,
            )
            self._spawn_particles(c + 0.5, r + 0.5, (255, 212, 96), count=10, speed=2.4)
            self._emit_sfx("interact")
            self.popups.append(
                FloatingText(
                    fl.x,
                    fl.y - 0.6,
                    f"LIFTED {str(fl.carried_machine['kind']).upper()}! [X] PLACE",
                    (255, 224, 96),
                )
            )
            return True

        pcol = int(math.floor(self.player_x))
        prow = int(math.floor(self.player_y))
        front_dc = -1 if self.facing_left else 1
        ordered_candidates: list[tuple[int, int]] = [(pcol + front_dc, prow)]
        other_spots: list[tuple[float, int, int]] = []
        for r in range(self.rows):
            for c in range(self.cols):
                if (c, r) in ((pcol, prow), (pcol + front_dc, prow)):
                    continue
                d = self.player_dist(c, r)
                if d <= self.interact_reach:
                    other_spots.append((d, c, r))
        other_spots.sort()
        ordered_candidates.extend((c, r) for _, c, r in other_spots)

        for tc, tr in ordered_candidates:
            if not self.in_bounds(tc, tr):
                continue
            dest_t = self.grid[tr][tc]
            if dest_t.kind != "empty" or dest_t.pile_tier > 0 or dest_t.is_doorway:
                continue
            data = fl.carried_machine
            m_kind = str(data["kind"])
            self.grid[tr][tc] = Tile(
                kind=m_kind,
                dir_idx=int(data["dir_idx"]),  # type: ignore[arg-type]
                color_key=str(data.get("color_key", "payroll")),
                sorter_branch_color=str(data.get("sorter_branch_color", "rent")),
                splitter_straight_color=str(
                    data.get("splitter_straight_color", "payroll")
                ),
                splitter_branch_color=str(data.get("splitter_branch_color", "rent")),
                scanner_mode=str(data.get("scanner_mode", "fraud")),
                machine_level=int(data.get("machine_level", 1)),  # type: ignore[arg-type]
                paid_cost=int(data.get("paid_cost", 0)),  # type: ignore[arg-type]
                toggle_state=int(data.get("toggle_state", 0)),  # type: ignore[arg-type]
                depot_items=list(data.get("depot_items", [])),  # type: ignore[arg-type]
                floor_variant=dest_t.floor_variant,
                decal=dest_t.decal,
                is_doorway=dest_t.is_doorway,
                loading_corner=dest_t.loading_corner,
            )
            fl.carried_machine = None
            self._spawn_particles(
                tc + 0.5, tr + 0.5, (110, 248, 138), count=10, speed=2.4
            )
            self._emit_sfx("place")
            self.popups.append(
                FloatingText(
                    tc + 0.5, tr - 0.1, f"PLACED {m_kind.upper()}!", (110, 248, 138)
                )
            )
            return True

        self._emit_sfx("error")
        self.popups.append(
            FloatingText(
                self.player_x,
                self.player_y - 0.5,
                "CLEAR FLOOR TILE TO PLACE CRATE!",
                (255, 86, 86),
            )
        )
        return False

    def interact_tile(self, col: int, row: int, ignore_reach: bool = False) -> bool:
        """Hands-on interaction: unjam vaults, open doors, flip breakers, haul crates, upgrade stamps, or deliver."""
        if self._blocked_if_paused():
            return False
        if not self.in_bounds(col, row):
            return False
        if not ignore_reach and not self.in_interact_reach(col, row):
            self._queue_walk("interact", col, row, "demolish", 0, "payroll")
            return False

        tile = self.grid[row][col]
        self.facing_left = (col + 0.5) < self.player_x

        if tile.kind == "jammed_source" and tile.jammed:
            tile.jammed = False
            tile.jam_burst_queue = max(2, tile.burst_count)
            tile.spawn_timer = 0.05
            self._adjust_money(60, 10)
            self.player_anim = "crowbar"
            self.action_timer = 0.45
            self._spawn_particles(
                col + 0.5, row + 0.5, (108, 246, 138), count=10, speed=2.6
            )
            self._emit_sfx("interact")
            self.popups.append(
                FloatingText(
                    col + 0.5, row - 0.1, "UNJAMMED! +$60 (+$10)", (100, 245, 130)
                )
            )
            self._check_quota()
            return True

        if tile.kind == "door_closed":
            if tile.door_stage > self.room_stage:
                return self.try_unlock_next_room(col, row)
            tile.kind = "door_open"
            tile.is_doorway = True
            self.player_anim = "crowbar"
            self.action_timer = 0.40
            self._spawn_particles(
                col + 0.5, row + 0.5, (120, 224, 255), count=8, speed=2.2
            )
            self._emit_sfx("interact")
            self.popups.append(
                FloatingText(col + 0.5, row - 0.1, "DOOR OPENED!", (120, 224, 255))
            )
            return True

        if tile.kind == "breaker" and tile.jammed:
            tile.jammed = False
            remaining_breakers = any(
                self.grid[rr][cc].kind == "breaker" and self.grid[rr][cc].jammed
                for rr in range(self.rows)
                for cc in range(self.cols)
            )
            if not remaining_breakers:
                self.power_restored = True
                for lgt in self.lights:
                    lgt["state"] = "working"
            else:
                for lgt in self.lights:
                    if (
                        math.hypot(
                            float(lgt["col"]) - (col + 0.5),
                            float(lgt["row"]) - (row + 0.5),
                        )
                        <= 12.5
                    ):  # type: ignore[arg-type]
                        lgt["state"] = "working"
            self._adjust_money(80, 12)
            self.player_anim = "crowbar"
            self.action_timer = 0.42
            self._spawn_particles(
                col + 0.5, row + 0.5, (255, 228, 96), count=12, speed=2.8
            )
            self._emit_sfx("upgrade")
            self.popups.append(
                FloatingText(
                    col + 0.5, row - 0.1, "LIGHTS ON! +$80 (+$12)", (255, 228, 96)
                )
            )
            self._check_quota()
            return True

        if tile.pile_tier > 0:
            if not self.in_forklift and self.selected_tool_kind != "demolish":
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5,
                        row - 0.1,
                        "SELECT CROWBAR TO CLEAN!",
                        (255, 196, 86),
                    )
                )
                return False
            c_key = (
                tile.pile_kind
                if tile.pile_kind in CHEQUE_ORDER
                else CHEQUE_ORDER[
                    (tile.pile_variant + tile.pile_tier) % len(CHEQUE_ORDER)
                ]
            )
            cap = self.max_carry_capacity
            if c_key not in BAD_CHEQUE_TYPES and len(self.carried_cheques) >= cap:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5, row - 0.1, "BAG FULL! DELIVER/BELT!", (255, 180, 82)
                    )
                )
                return False
            clear_cost = 0 if self.in_forklift else CLEAR_PILEUP_COST
            if clear_cost > 0 and self.cash < clear_cost:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5,
                        row - 0.1,
                        f"NEED ${CLEAR_PILEUP_COST} TO CLEAR!",
                        (255, 86, 86),
                    )
                )
                return False
            self.cash -= clear_cost
            tiers_to_clear = min(2, tile.pile_tier) if self.in_forklift else 1
            cleared = 0
            for _ in range(tiers_to_clear):
                if tile.pile_tier <= 0:
                    break
                if (
                    tile.pile_kind not in BAD_CHEQUE_TYPES
                    and len(self.carried_cheques) >= cap
                ):
                    break
                tile.pile_tier -= 1
                cleared += 1
                if tile.pile_kind not in BAD_CHEQUE_TYPES:
                    t_key = (
                        tile.pile_kind
                        if tile.pile_kind in CHEQUE_ORDER
                        else CHEQUE_ORDER[
                            (tile.pile_variant + tile.pile_tier + 1) % len(CHEQUE_ORDER)
                        ]
                    )
                    self.carried_cheques.append(t_key)
                    self.cheques_rescued_count += 1
            if cleared <= 0:
                return False
            self.player_anim = "place"
            self.action_timer = 0.30
            quota_gain = 75 * cleared
            self._adjust_money(quota_gain, 0)
            if tile.pile_kind in BAD_CHEQUE_TYPES:
                self._spawn_particles(col + 0.5, row + 0.5, (255, 130, 86), count=8)
                self._emit_sfx("shred")
                cost_tag = "FORKS FREE!" if clear_cost == 0 else f"-${clear_cost}"
                self.popups.append(
                    FloatingText(
                        col + 0.5,
                        row - 0.1,
                        f"SHREDDED {tile.pile_kind.upper()} +${quota_gain} ({cost_tag})",
                        (255, 180, 82),
                    )
                )
            else:
                self._spawn_particles(col + 0.5, row + 0.5, (108, 244, 136), count=8)
                self._emit_sfx("interact")
                cost_tag = "FORKS FREE!" if clear_cost == 0 else f"-${clear_cost}"
                self.popups.append(
                    FloatingText(
                        col + 0.5,
                        row - 0.1,
                        f"CLEARED +${quota_gain} ({cost_tag})",
                        (108, 244, 136),
                    )
                )
            self._check_quota()
            return True

        if tile.kind == "dest" and self.carried_cheques:
            if tile.require_boost:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5, row - 0.1, "NEEDS [8] BOOSTER LINE!", (255, 196, 86)
                    )
                )
                return False
            if tile.require_polish:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5, row - 0.1, "NEEDS [0] POLISH LINE!", (255, 196, 86)
                    )
                )
                return False
            if tile.require_scan:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5, row - 0.1, "NEEDS [4] SCAN LINE!", (255, 196, 86)
                    )
                )
                return False
            matching = [c for c in self.carried_cheques if c == tile.color_key]
            if matching:
                self.carried_cheques = [
                    c for c in self.carried_cheques if c != tile.color_key
                ]
                gained = 0
                for c in matching:
                    val = max(100, int(CHEQUE_TYPES[c]["value"]) // 2)  # type: ignore[arg-type]
                    gained += val
                    tile.delivered_count += 1
                    self.cheques_rescued_count += 1
                self._adjust_money(gained)
                tile.bounce_anim = 1.0
                self.player_anim = "place"
                self.action_timer = 0.32
                c_rgb = tuple(CHEQUE_TYPES[tile.color_key]["color"])  # type: ignore[arg-type]
                self._spawn_particles(col + 0.5, row + 0.5, c_rgb, count=10, speed=2.5)
                self._emit_sfx("deliver")
                self.popups.append(
                    FloatingText(
                        col + 0.5,
                        row - 0.1,
                        f"BAG DELIVERED +${gained}!",
                        (110, 248, 138),
                    )
                )
                self._check_quota()
                return True
            lbl = str(CHEQUE_TYPES[tile.color_key]["label"])
            self._emit_sfx("error")
            self.popups.append(
                FloatingText(col + 0.5, row - 0.1, f"NEEDS {lbl}!", (255, 196, 86))
            )
            return False

        if (
            tile.kind == "crate"
            and self.carried_cheques
            and tile.crate_stock < tile.crate_max
        ):
            room = tile.crate_max - tile.crate_stock
            packed = min(room, len(self.carried_cheques))
            tile.crate_stock += packed
            del self.carried_cheques[:packed]
            tile.bounce_anim = 1.0
            self.player_anim = "place"
            self.action_timer = 0.25
            self._spawn_particles(
                col + 0.5, row + 0.5, (255, 212, 118), count=8, speed=2.2
            )
            self._emit_sfx("interact")
            self.popups.append(
                FloatingText(
                    col + 0.5, row - 0.1, f"PACKED +{packed} IN CRATE!", (255, 224, 110)
                )
            )
            return True

        if tile.kind == "scanner":
            tile.scanner_mode = "error" if tile.scanner_mode == "fraud" else "fraud"
            tile.bounce_anim = 1.0
            self._emit_sfx("interact")
            mode_lbl = (
                "SCANNER: FRAUD MODE"
                if tile.scanner_mode == "fraud"
                else "SCANNER: ERROR MODE"
            )
            self.popups.append(
                FloatingText(col + 0.5, row - 0.1, mode_lbl, (120, 232, 255))
            )
            return True

        if tile.kind == "crate" and tile.crate_stock > 0:
            if not self.in_forklift:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5,
                        row - 0.1,
                        "CRATES NEED FORKLIFT! [G]",
                        (255, 186, 86),
                    )
                )
                return False
            fl = self.active_forklift
            if fl is not None and fl.carried_crate is None and tile.loading_corner < 0:
                return self.relocate_crate_with_forklift()
            dx, dy = DIRS[tile.dir_idx]
            sc, sr = col + dx, row + dy
            can_belt_spawn = (
                self.in_bounds(sc, sr)
                and self._tile_accepts_cheque(sc, sr)
                and len(self.cheques) < MAX_CHEQUES
                and not self._occupied_ahead(sc, sr, -1)
            )
            cap = self.max_carry_capacity
            bag_room = cap - len(self.carried_cheques)
            if not can_belt_spawn and bag_room <= 0:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5, row - 0.1, "BAG FULL! DELIVER/BELT!", (255, 180, 82)
                    )
                )
                return False

            unloaded = 0
            belt_spawned = False
            quota_gain = 0
            cash_gain = 0
            max_take = min(6 if self.in_forklift else 3, tile.crate_stock)
            for _ in range(max_take):
                c_key = self._resolve_cheque_key(tile)
                if not belt_spawned and can_belt_spawn:
                    val = int(CHEQUE_TYPES[c_key]["value"])  # type: ignore[arg-type]
                    stamped = (
                        True if c_key in BAD_CHEQUE_TYPES else (not tile.require_stamp)
                    )
                    misprint = (c_key not in BAD_CHEQUE_TYPES) and tile.require_fix
                    self.cheques.append(
                        ChequeItem(
                            x=sc + 0.5,
                            y=sr + 0.5,
                            color_key=c_key,
                            value=val,
                            stamped=stamped,
                            misprint=misprint,
                            move_dir=tile.dir_idx,
                        )
                    )
                    belt_spawned = True
                    tile.crate_stock -= 1
                    unloaded += 1
                    continue

                if c_key in BAD_CHEQUE_TYPES:
                    tile.crate_stock -= 1
                    unloaded += 1
                    quota_gain += 60
                    cash_gain += 12
                elif len(self.carried_cheques) < cap:
                    self.carried_cheques.append(c_key)
                    tile.crate_stock -= 1
                    unloaded += 1
                    quota_gain += 50
                    cash_gain += 10
                else:
                    break

            if unloaded <= 0:
                return False

            tile.bounce_anim = 1.0
            self.player_anim = "place"
            self.action_timer = 0.28
            self._spawn_particles(
                col + 0.5, row + 0.5, (255, 212, 118), count=8, speed=2.3
            )
            if tile.crate_stock <= 0:
                quota_gain += 400
                cash_gain += 120
                self._emit_sfx("upgrade")
                self.popups.append(
                    FloatingText(
                        col + 0.5, row - 0.15, "CRATE CLEARED! +$400!", (110, 248, 138)
                    )
                )
            else:
                self._emit_sfx("interact")
                self.popups.append(
                    FloatingText(
                        col + 0.5,
                        row - 0.1,
                        f"HAULED x{unloaded} (+${quota_gain}) [{tile.crate_stock} left]",
                        (255, 224, 110),
                    )
                )
            if quota_gain > 0 or cash_gain > 0:
                self._adjust_money(quota_gain, cash_gain)
            self._check_quota()
            return True

        if (
            self.carried_cheques
            and tile.kind
            in (
                "belt",
                "endorser",
                "splitter",
                "scanner",
                "stamper",
                "fixer",
                "polisher",
            )
            and len(self.cheques) < MAX_CHEQUES
            and not self._occupied_ahead(col, row, -1)
        ):
            c_key = self.carried_cheques.pop(0)
            val = int(CHEQUE_TYPES[c_key]["value"])  # type: ignore[arg-type]
            self.cheques.append(
                ChequeItem(
                    x=col + 0.5,
                    y=row + 0.5,
                    color_key=c_key,
                    value=val,
                    stamped=True,
                    move_dir=tile.dir_idx,
                )
            )
            self.player_anim = "place"
            self.action_timer = 0.20
            self._emit_sfx("interact")
            self.popups.append(
                FloatingText(col + 0.5, row - 0.1, "FED TO BELT!", (120, 240, 255))
            )
            return True

        if (
            tile.kind in UPGRADABLE_MACHINES
            and self.machine_upgrade_cost(tile) is not None
        ):
            return self.upgrade_machine_tile(col, row, ignore_reach=True)

        if tile.kind == "sorter":
            idx = (
                CHEQUE_ORDER.index(tile.color_key)
                if tile.color_key in CHEQUE_ORDER
                else 0
            )
            tile.color_key = CHEQUE_ORDER[(idx + 1) % len(CHEQUE_ORDER)]
            lbl = str(CHEQUE_TYPES[tile.color_key]["label"])
            col_rgb = tuple(CHEQUE_TYPES[tile.color_key]["color"])  # type: ignore[arg-type]
            self.player_anim = "place"
            self.action_timer = 0.25
            self._emit_sfx("interact")
            self.popups.append(
                FloatingText(col + 0.5, row - 0.1, f"SORT: {lbl}", col_rgb)
            )
            return True

        return False

    def interact_nearest(self) -> bool:
        """Interact with the nearest jammed machine, breaker, door, crate, pileup, bad cheque, or machine upgrade."""
        if self._blocked_if_paused():
            return False
        candidates: list[tuple[int, float, int, int]] = []
        reach = self.interact_reach
        for r in range(self.rows):
            for c in range(self.cols):
                dist = self.player_dist(c, r)
                if dist > reach:
                    continue
                t = self.grid[r][c]
                if t.kind == "jammed_source" and t.jammed:
                    candidates.append((0, dist, c, r))
                elif t.kind == "breaker" and t.jammed:
                    candidates.append((1, dist, c, r))
                elif t.kind == "door_closed":
                    candidates.append((2, dist, c, r))
                elif t.kind == "dest" and any(
                    ch == t.color_key for ch in self.carried_cheques
                ):
                    candidates.append((3, dist, c, r))
                elif t.kind == "crate" and t.crate_stock > 0:
                    candidates.append((3, dist, c, r))
                elif t.pile_tier > 0:
                    candidates.append((4, dist, c, r))
                elif (
                    t.kind in ("stamper", "fixer", "polisher")
                    and self.machine_upgrade_cost(t) is not None
                ):
                    candidates.append((5, dist, c, r))
                elif (
                    self.carried_cheques
                    and t.kind == "belt"
                    and not self._occupied_ahead(c, r, -1)
                ):
                    candidates.append((6, dist, c, r))
                elif (
                    t.kind in UPGRADABLE_MACHINES
                    and self.machine_upgrade_cost(t) is not None
                ):
                    candidates.append((7, dist, c, r))
                elif t.kind == "sorter":
                    candidates.append((8, dist, c, r))

        # Check loose bad cheques on nearby conveyors before falling back to sorters.
        for idx, ch in enumerate(self.cheques):
            if ch.color_key not in BAD_CHEQUE_TYPES:
                continue
            dist = math.hypot(ch.x - self.player_x, ch.y - self.player_y)
            if dist <= reach:
                self._pop_cheque(idx)
                self._adjust_money(60, 12)
                self.player_anim = "crowbar"
                self.action_timer = 0.30
                self._spawn_particles(ch.x, ch.y, (255, 160, 84), count=8)
                self._emit_sfx("shred")
                self.popups.append(
                    FloatingText(
                        ch.x,
                        ch.y - 0.1,
                        f"SNATCHED {ch.color_key.upper()}! +$60 (+$12)",
                        (255, 178, 84),
                    )
                )
                self._check_quota()
                return True

        if not candidates:
            if not self.in_forklift:
                return self.toggle_forklift()
            return False
        candidates.sort()
        _, _, col, row = candidates[0]
        return self.interact_tile(col, row, ignore_reach=True)

    def place_tile(
        self,
        col: int,
        row: int,
        tool_kind: str,
        dir_idx: int,
        filter_color: str,
        ignore_reach: bool = False,
    ) -> bool:
        """Build/orient a machine within reach, interact, or auto-walk closer if out of range."""
        if self._blocked_if_paused() or self._blocked_if_in_forklift():
            return False
        if not self.in_bounds(col, row):
            return False
        tile = self.grid[row][col]

        if (
            (tile.kind == "jammed_source" and tile.jammed)
            or tile.kind == "door_closed"
            or (tile.kind == "breaker" and tile.jammed)
            or (tile.kind == "crate" and tile.crate_stock > 0)
            or (
                tile.kind == "dest"
                and any(c == tile.color_key for c in self.carried_cheques)
            )
            or tile.pile_tier > 0
        ):
            if tile.pile_tier > 0 and tool_kind != "demolish" and not self.in_forklift:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5,
                        row - 0.1,
                        "SELECT CROWBAR TO CLEAN!",
                        (255, 196, 86),
                    )
                )
                return False
            return self.interact_tile(col, row, ignore_reach=ignore_reach)

        if tool_kind == "demolish":
            return self.remove_tile(col, row, ignore_reach=ignore_reach, allow_clean=True)

        if tile.kind in (
            "void",
            "wall",
            "window",
            "pillar",
            "fence",
            "door_closed",
            "source",
            "jammed_source",
            "huge_pile",
            "crate",
            "dest",
            "breaker",
            "grate",
        ):
            return False

        if not ignore_reach and not self.in_build_reach(col, row):
            self._queue_walk("place", col, row, tool_kind, dir_idx, filter_color)
            return False

        if (
            tile.kind == "sorter"
            and tool_kind == "sorter"
            and tile.dir_idx == dir_idx % 4
        ):
            if tile.color_key != filter_color:
                tile.color_key = filter_color
                lbl = str(CHEQUE_TYPES[filter_color]["label"])
                col_rgb = tuple(CHEQUE_TYPES[filter_color]["color"])  # type: ignore[arg-type]
                self.facing_left = (col + 0.5) < self.player_x
                self.player_anim = "place"
                self.action_timer = 0.25
                self._emit_sfx("interact")
                self.popups.append(
                    FloatingText(col + 0.5, row - 0.1, f"SORT: {lbl}", col_rgb)
                )
                return True
            return self.interact_tile(col, row, ignore_reach=True)

        if (
            tile.kind == tool_kind
            and tile.kind in UPGRADABLE_MACHINES
            and tile.dir_idx == dir_idx % 4
            and (tool_kind != "sorter" or tile.color_key == filter_color)
            and self.machine_upgrade_cost(tile) is not None
        ):
            return self.upgrade_machine_tile(col, row, ignore_reach=True)

        if tile.kind == tool_kind:
            tile.dir_idx = dir_idx % 4
            tile.toggle_state = max(tile.toggle_state, 1)
            if tool_kind == "sorter":
                tile.color_key = filter_color
            self.facing_left = (col + 0.5) < self.player_x
            self.player_anim = "place"
            self.action_timer = 0.25
            self._emit_sfx("place")
            return True

        cost = TOOL_COSTS.get(tool_kind, 0)
        net_cost = max(0, cost - tile.paid_cost)
        if net_cost > 0 and self.cash < net_cost:
            self._emit_sfx("error")
            self.popups.append(
                FloatingText(col + 0.5, row - 0.1, f"NEED ${net_cost}!", (255, 86, 86))
            )
            return False

        if not self._nudge_player_out_of_tile(col, row):
            self._emit_sfx("error")
            self.popups.append(
                FloatingText(col + 0.5, row - 0.1, "STEP CLEAR!", (255, 190, 68))
            )
            return False

        self.cash -= net_cost
        if tile.paid_cost > cost:
            self.cash += tile.paid_cost - cost

        self.grid[row][col] = Tile(
            kind=tool_kind,
            dir_idx=dir_idx % 4,
            color_key=filter_color if tool_kind == "sorter" else "payroll",
            floor_variant=tile.floor_variant,
            decal=tile.decal,
            is_doorway=tile.is_doorway,
            paid_cost=cost,
        )
        self.facing_left = (col + 0.5) < self.player_x
        self.player_anim = "place"
        self.action_timer = 0.25
        self._spawn_particles(
            col + 0.5,
            row + 0.5,
            (140, 208, 255),
            count=6,
            speed=1.8,
            ttl=0.35,
            size=3.0,
        )
        self._emit_sfx("place")
        if net_cost > 0:
            self.popups.append(
                FloatingText(col + 0.5, row - 0.1, f"-${net_cost}", (255, 224, 96))
            )
        return True

    def remove_tile(
        self,
        col: int,
        row: int,
        ignore_reach: bool = False,
        allow_clean: bool = True,
    ) -> bool:
        """Remove a player-built machine, clear a pileup, or mop an oil/rubbish decal."""
        if self._blocked_if_paused() or self._blocked_if_in_forklift():
            return False
        if not self.in_bounds(col, row):
            return False
        if not ignore_reach and not self.in_build_reach(col, row):
            self._queue_walk("remove", col, row, "demolish", 0, "payroll")
            return False

        tile = self.grid[row][col]
        if tile.kind in UPGRADABLE_MACHINES:
            refund = tile.paid_cost
            if refund > 0:
                self.cash += refund
            self.grid[row][col] = Tile(
                kind="door_open" if tile.is_doorway else "empty",
                floor_variant=tile.floor_variant,
                decal=tile.decal,
                is_doorway=tile.is_doorway,
            )
            self.facing_left = (col + 0.5) < self.player_x
            self.player_anim = "crowbar"
            self.action_timer = 0.25
            self._spawn_particles(
                col + 0.5,
                row + 0.5,
                (186, 204, 228),
                count=6,
                speed=1.8,
                ttl=0.35,
                size=3.0,
            )
            self._emit_sfx("remove")
            if refund > 0:
                self.popups.append(
                    FloatingText(
                        col + 0.5, row - 0.1, f"REFUND +${refund}", (160, 224, 255)
                    )
                )
            return True

        if tile.pile_tier > 0:
            if not allow_clean and not self.in_forklift:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5, row - 0.1, "SELECT CROWBAR TO CLEAN!", (255, 196, 86)
                    )
                )
                return False
            return self.interact_tile(col, row, ignore_reach=True)

        if tile.decal in ("oil", "puddle", "rubbish"):
            if not allow_clean:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5, row - 0.1, "SELECT CROWBAR TO CLEAN!", (255, 196, 86)
                    )
                )
                return False
            if self.cash < CLEAN_DECAL_COST:
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5,
                        row - 0.1,
                        f"NEED ${CLEAN_DECAL_COST} TO MOP!",
                        (255, 86, 86),
                    )
                )
                return False
            self.cash -= CLEAN_DECAL_COST
            tile.decal = "none"
            self.facing_left = (col + 0.5) < self.player_x
            self.player_anim = "crowbar"
            self.action_timer = 0.26
            self._spawn_particles(
                col + 0.5, row + 0.5, (160, 224, 255), count=6, speed=1.6, ttl=0.35
            )
            self._emit_sfx("remove")
            self.popups.append(
                FloatingText(
                    col + 0.5,
                    row - 0.1,
                    f"CLEANED! -${CLEAN_DECAL_COST}",
                    (160, 224, 255),
                )
            )
            return True

        return False

    def _check_room_progression(self) -> None:
        if (
            self.room_stage < len(LEVELS)
            and self.bulkhead_ready_stage <= self.room_stage
            and self.power_restored
            and self.money_rescued >= self.money_quota
        ):
            satisfied, total = self.dest_tubes_status()
            if total > 0 and satisfied >= total:
                self.bulkhead_ready_stage = self.room_stage + 1
                self._emit_sfx("upgrade")
                self.popups.append(
                    FloatingText(
                        self.player_x,
                        self.player_y - 0.7,
                        f"RM{self.room_stage + 1} BULKHEAD READY! PAY ${self.next_room_unlock_cost():,} AT EAST GATE [E]!",
                        (110, 248, 255),
                        ttl=3.0,
                    )
                )

    def _check_quota(self) -> None:
        self._check_room_progression()
        satisfied, total = self.dest_tubes_status()
        if (
            self.room_stage >= len(LEVELS)
            and self.money_rescued >= self.money_quota
            and self.jammed_remaining == 0
            and self.crates_remaining == 0
            and self.power_restored
            and total > 0
            and satisfied >= total
        ):
            if not self.level_complete:
                self._emit_sfx("win")
            self.level_complete = True

    def start_game(self) -> None:
        """Leave setup phase and begin active shift simulation."""
        if self.started:
            return
        self.started = True
        self.paused = False
        self._emit_sfx("upgrade")
        self.popups.append(
            FloatingText(
                self.player_x, self.player_y - 0.6, "SHIFT STARTED!", (110, 248, 138)
            )
        )

    def update(self, raw_dt: float, keep_playing: bool = False) -> None:
        """Advance clocks, machines, particles, collector drone, cheques, and win/loss state."""
        self.anim_time += raw_dt
        if self.room_open_anim > 0.0:
            self.room_open_anim = max(0.0, self.room_open_anim - raw_dt)
        if self.action_timer > 0.0:
            self.action_timer = max(0.0, self.action_timer - raw_dt)
        if self.screen_shake > 0.0:
            self.screen_shake = max(0.0, self.screen_shake - raw_dt * 1.4)
        if self.drone_laser_timer > 0.0:
            self.drone_laser_timer = max(0.0, self.drone_laser_timer - raw_dt)
            if self.drone_laser_timer == 0.0:
                self.drone_laser_target = None

        for p in self.popups:
            p.y -= 0.45 * raw_dt
            p.ttl -= raw_dt
        self.popups = [p for p in self.popups if p.ttl > 0.0]

        for pt in self.particles:
            pt.x += pt.vx * raw_dt
            pt.y += pt.vy * raw_dt
            pt.vx *= 0.90
            pt.vy *= 0.90
            pt.ttl -= raw_dt
        self.particles = [pt for pt in self.particles if pt.ttl > 0.0]

        if (
            not self.started
            or self.paused
            or ((self.level_complete or self.level_failed) and not keep_playing)
        ):
            return

        sim_dt = raw_dt * self.sim_speed
        self.elapsed_time += sim_dt
        if self.streak > 0:
            self.streak_timer -= sim_dt
            if self.streak_timer <= 0.0:
                self.streak = max(0, self.streak - 1)
                self.streak_timer = 3.0 if self.streak > 0 else 0.0

        self._ensure_player_unstuck()
        if self.cash < 30:
            bail_wait = (
                4.0
                if (len(self.cheques) == 0 and len(self.carried_cheques) == 0)
                else 15.0
            )
            self.low_cash_timer += sim_dt
            if self.low_cash_timer >= bail_wait:
                self.low_cash_timer = 0.0
                self.cash = max(self.cash + 250, 250)
                self._emit_sfx("upgrade")
                self.popups.append(
                    FloatingText(
                        self.player_x,
                        self.player_y - 0.6,
                        "PETTY CASH BAILOUT +$250!",
                        (110, 248, 160),
                    )
                )
        else:
            self.low_cash_timer = 0.0

        self.neglect_timer -= sim_dt
        if self.neglect_timer <= 0.0:
            audit_mult = (1.0, 1.35, 1.75, 2.25)[self.upgrade_tier("fraud_shield")]
            self.neglect_timer += NEGLECT_INTERVAL * audit_mult
            self._apply_neglect_audit()

        self._update_truck_bays(sim_dt)
        self._update_sources(sim_dt)
        self._update_depots(sim_dt)
        self._update_cheques(sim_dt)
        self._update_drone(sim_dt)
        self._update_forklifts(sim_dt)

        self._check_quota()

    def _record_lost_cheque(self, ch: ChequeItem) -> None:
        base_val = abs(int(CHEQUE_TYPES.get(ch.color_key, {}).get("value", 400)))  # type: ignore[arg-type]
        val = max(base_val, abs(int(ch.value)))
        self.lost_cheques_count += 1
        self.lost_cheques_value += val

    def _apply_neglect_audit(self) -> None:
        if (
            self.cheques_rescued_count == 0
            and self.lost_cheques_count == 0
            and len(self.cheques) == 0
        ):
            return
        pile_count = 0
        pile_weight = 0
        pile_value = 0
        mess_count = 0
        unfixed_breakers = 0
        focus_pos: tuple[float, float] | None = None
        cur_lvl = LEVELS[min(len(LEVELS) - 1, max(0, self.room_stage - 1))]
        scan_cols = min(self.cols, cur_lvl.start_col + cur_lvl.room_cols)
        for r in range(self.rows):
            for c in range(scan_cols):
                t = self.grid[r][c]
                if t.pile_tier > 0:
                    tier_w = (0, 1, 3, 6)[min(3, t.pile_tier)]
                    pile_count += 1
                    pile_weight += tier_w
                    p_info = CHEQUE_TYPES.get(t.pile_kind, CHEQUE_TYPES["payroll"])
                    pile_value += tier_w * abs(int(p_info["value"]))  # type: ignore[arg-type]
                    if focus_pos is None:
                        focus_pos = (c + 0.5, r + 0.5)
                if t.decal in ("oil", "puddle", "rubbish") and t.kind in (
                    "empty",
                    "door_open",
                ):
                    mess_count += 1
                    if focus_pos is None:
                        focus_pos = (c + 0.5, r + 0.5)
                if t.kind == "breaker" and t.jammed:
                    unfixed_breakers += 1
                    if focus_pos is None:
                        focus_pos = (c + 0.5, r + 0.5)

        if pile_weight == 0 and mess_count == 0 and unfixed_breakers == 0:
            return

        mult = self.fine_multiplier
        raw_quota = (
            pile_weight * 35
            + int(pile_value * 0.04)
            + mess_count * 20
            + unfixed_breakers * 55
        )
        raw_cash = (
            pile_weight * 8
            + int(pile_value * 0.01)
            + mess_count * 5
            + unfixed_breakers * 12
        )
        quota_fine = int(round(raw_quota * mult)) if raw_quota > 0 else 0
        cash_fine = int(round(raw_cash * mult)) if raw_cash > 0 else 0
        if quota_fine <= 0 and cash_fine <= 0:
            return
        self._adjust_money(-quota_fine, -cash_fine)
        self.neglect_penalties += quota_fine
        px, py = focus_pos if focus_pos is not None else (self.player_x, self.player_y)
        parts: list[str] = []
        if pile_count > 0:
            parts.append(f"{pile_count} pile{'s' if pile_count != 1 else ''}")
        if mess_count > 0:
            parts.append(f"{mess_count} spill{'s' if mess_count != 1 else ''}")
        detail = f" ({', '.join(parts)})" if parts else ""
        audit_msg = f"MESS AUDIT{detail}! -${quota_fine} (-${cash_fine} CASH)"
        self.popups.append(FloatingText(px, py - 0.15, audit_msg, (255, 118, 86)))
        self._emit_sfx("error")

    def _update_drone(self, dt: float) -> None:
        drone_tier = self.upgrade_tier("auto_drone")
        if drone_tier <= 0:
            return
        if self.drone_cooldown > 0.0:
            self.drone_cooldown = max(0.0, self.drone_cooldown - dt)

        drone_speed = (5.2, 6.8, 8.8)[drone_tier - 1]
        cd_time = (1.6, 1.0, 0.55)[drone_tier - 1]
        reward_mult = (1.0, 1.25, 1.55)[drone_tier - 1]

        # Pick nearest target: loose VOID/FAKE cheque first, then floor pileup, then crate (T2+).
        best_dist = 1e9
        best_kind = "idle"
        best_pos = (
            self.player_x + math.cos(self.anim_time * 2.0) * 1.1,
            self.player_y - 0.8 + math.sin(self.anim_time * 2.0) * 0.5,
        )
        best_cheque_idx = -1
        best_tile_rc: tuple[int, int] | None = None

        for i, ch in enumerate(self.cheques):
            if ch.color_key in BAD_CHEQUE_TYPES and not ch.airborne:
                d = math.hypot(ch.x - self.drone_x, ch.y - self.drone_y)
                if d < best_dist:
                    best_dist = d
                    best_kind = "cheque"
                    best_pos = (ch.x, ch.y)
                    best_cheque_idx = i

        if best_kind == "idle":
            for r in range(self.rows):
                for c in range(self.cols):
                    if self.grid[r][c].pile_tier > 0:
                        d = math.hypot(
                            (c + 0.5) - self.drone_x, (r + 0.5) - self.drone_y
                        )
                        if d < best_dist:
                            best_dist = d
                            best_kind = "pile"
                            best_pos = (c + 0.5, r + 0.5)
                            best_tile_rc = (c, r)

        if best_kind == "idle" and drone_tier >= 2:
            for r in range(self.rows):
                for c in range(self.cols):
                    t = self.grid[r][c]
                    if t.kind == "crate" and t.crate_stock > 0:
                        d = math.hypot(
                            (c + 0.5) - self.drone_x, (r + 0.5) - self.drone_y
                        )
                        if d < best_dist:
                            best_dist = d
                            best_kind = "crate"
                            best_pos = (c + 0.5, r + 0.5)
                            best_tile_rc = (c, r)

        dx = best_pos[0] - self.drone_x
        dy = best_pos[1] - self.drone_y
        dist = math.hypot(dx, dy)
        if dist > 0.08:
            step = min(dist, drone_speed * dt)
            self.drone_x += (dx / dist) * step
            self.drone_y += (dy / dist) * step

        if self.drone_cooldown <= 0.0 and dist <= 1.35:
            if best_kind == "cheque" and 0 <= best_cheque_idx < len(self.cheques):
                ch = self.cheques[best_cheque_idx]
                tx, ty = ch.x, ch.y
                self._pop_cheque(best_cheque_idx)
                rw = int(round(120 * reward_mult))
                crw = int(round(20 * reward_mult))
                self._adjust_money(rw, crw)
                self.drone_laser_target = (tx, ty)
                self.drone_laser_timer = 0.22
                self.drone_cooldown = cd_time
                self._spawn_particles(tx, ty, (112, 240, 255), count=8)
                self._emit_sfx("shred")
                self.popups.append(
                    FloatingText(
                        tx, ty - 0.15, f"BOT ZAP +${rw} (+${crw})", (112, 240, 255)
                    )
                )
                self._check_quota()
            elif best_kind == "pile" and best_tile_rc is not None:
                c, r = best_tile_rc
                t = self.grid[r][c]
                if t.pile_tier > 0:
                    t.pile_tier -= 1
                    is_bad = t.pile_kind in BAD_CHEQUE_TYPES
                    reward = int(round((120 if is_bad else 150) * reward_mult))
                    cash_reward = int(round((20 if is_bad else 25) * reward_mult))
                    self._adjust_money(reward, cash_reward)
                    if not is_bad:
                        self.cheques_rescued_count += 1
                    self.drone_laser_target = (c + 0.5, r + 0.5)
                    self.drone_laser_timer = 0.22
                    self.drone_cooldown = cd_time
                    self._spawn_particles(c + 0.5, r + 0.5, (112, 240, 255), count=8)
                    self._emit_sfx("interact")
                    self.popups.append(
                        FloatingText(
                            c + 0.5,
                            r - 0.15,
                            f"BOT CLEAR +${reward} (+${cash_reward})",
                            (112, 240, 255),
                        )
                    )
                    self._check_quota()
            elif best_kind == "crate" and best_tile_rc is not None:
                c, r = best_tile_rc
                t = self.grid[r][c]
                if t.kind == "crate" and t.crate_stock > 0:
                    t.crate_stock -= 1
                    reward = int(round(120 * reward_mult))
                    cash_reward = int(round(20 * reward_mult))
                    if t.crate_stock <= 0:
                        reward += 400
                        cash_reward += 120
                    self._adjust_money(reward, cash_reward)
                    self.drone_laser_target = (c + 0.5, r + 0.5)
                    self.drone_laser_timer = 0.22
                    self.drone_cooldown = cd_time
                    self._spawn_particles(c + 0.5, r + 0.5, (112, 240, 255), count=8)
                    self._emit_sfx("interact")
                    self.popups.append(
                        FloatingText(
                            c + 0.5,
                            r - 0.15,
                            f"BOT CRATE +${reward}",
                            (112, 240, 255),
                        )
                    )
                    self._check_quota()

    def _forklift_bfs_step(
        self, start_c: int, start_r: int, target_c: int, target_r: int
    ) -> tuple[float, float] | None:
        if not self.in_bounds(start_c, start_r):
            return None
        q: deque[tuple[int, int]] = deque([(start_c, start_r)])
        parent: dict[tuple[int, int], tuple[int, int] | None] = {
            (start_c, start_r): None
        }
        goal: tuple[int, int] | None = None
        while q:
            cc, cr = q.popleft()
            if math.hypot(cc - target_c, cr - target_r) <= 1.25:
                goal = (cc, cr)
                break
            for dx, dy in DIRS:
                nc, nr = cc + dx, cr + dy
                if (nc, nr) in parent or not self.in_bounds(nc, nr):
                    continue
                if self._is_player_blocked(nc + 0.5, nr + 0.5, allow_grate=False):
                    continue
                parent[(nc, nr)] = (cc, cr)
                q.append((nc, nr))
        if goal is None or goal == (start_c, start_r):
            return None
        cur = goal
        while parent[cur] is not None and parent[cur] != (start_c, start_r):
            cur = parent[cur]  # type: ignore[assignment]
        return (cur[0] + 0.5, cur[1] + 0.5)

    def _update_forklifts(self, dt: float) -> None:
        drone_tier = self.upgrade_tier("auto_drone")
        for idx, fl in enumerate(self.forklifts):
            if idx == self.player_forklift_idx:
                continue
            if not fl.autopilot and drone_tier <= 0:
                fl.moving = False
                continue
            if fl.cooldown > 0.0:
                fl.cooldown = max(0.0, fl.cooldown - dt)
            fl.moving = False

            cd_time = 0.85 if drone_tier >= 2 else 1.15
            best_dist = 1e9
            best_kind = ""
            best_rc: tuple[int, int] | None = None

            if fl.carried_crate is not None:
                for r in range(self.rows):
                    for c in range(self.cols):
                        t = self.grid[r][c]
                        if (
                            t.loading_corner >= 0
                            and t.kind == "empty"
                            and t.pile_tier == 0
                            and not t.is_doorway
                        ):
                            d = math.hypot((c + 0.5) - fl.x, (r + 0.5) - fl.y)
                            if d < best_dist:
                                best_dist = d
                                best_kind = "drop_crate"
                                best_rc = (c, r)
            else:
                has_loading_slot = any(
                    self.grid[r][c].loading_corner >= 0
                    and self.grid[r][c].kind == "empty"
                    and self.grid[r][c].pile_tier == 0
                    and not self.grid[r][c].is_doorway
                    for r in range(self.rows)
                    for c in range(self.cols)
                )
                for r in range(self.rows):
                    for c in range(self.cols):
                        t = self.grid[r][c]
                        if (
                            has_loading_slot
                            and t.kind == "crate"
                            and t.crate_stock > 0
                            and t.loading_corner < 0
                        ):
                            d = math.hypot((c + 0.5) - fl.x, (r + 0.5) - fl.y)
                            if best_kind != "pickup_crate" or d < best_dist:
                                best_dist = d
                                best_kind = "pickup_crate"
                                best_rc = (c, r)
                        elif best_kind != "pickup_crate" and t.pile_tier > 0:
                            d = math.hypot((c + 0.5) - fl.x, (r + 0.5) - fl.y)
                            if best_kind != "pile" or d < best_dist:
                                best_dist = d
                                best_kind = "pile"
                                best_rc = (c, r)
                        elif (
                            best_kind not in ("pickup_crate", "pile")
                            and t.kind == "crate"
                            and t.crate_stock > 0
                        ):
                            d = math.hypot((c + 0.5) - fl.x, (r + 0.5) - fl.y)
                            if d < best_dist:
                                best_dist = d
                                best_kind = "crate"
                                best_rc = (c, r)

            if best_rc is None:
                fl.moving = False
                continue

            tx, ty = best_rc[0] + 0.5, best_rc[1] + 0.5
            dx, dy = tx - fl.x, ty - fl.y
            dist = math.hypot(dx, dy)

            if dist > 1.15:
                wp = self._forklift_bfs_step(
                    int(math.floor(fl.x)), int(math.floor(fl.y)), best_rc[0], best_rc[1]
                )
                wx, wy = wp if wp is not None else (tx, ty)
                wdx, wdy = wx - fl.x, wy - fl.y
                wdist = math.hypot(wdx, wdy)
                if abs(wdx) > 0.04:
                    fl.facing_left = wdx < 0.0
                fl.moving = True
                step = min(max(0.05, dist - 0.8), 3.8 * dt)
                vx = (wdx / max(1e-5, wdist)) * step
                vy = (wdy / max(1e-5, wdist)) * step
                if abs(vx) > 1e-5 and not self._is_player_blocked(
                    fl.x + vx, fl.y, allow_grate=False
                ):
                    fl.x += vx
                if abs(vy) > 1e-5 and not self._is_player_blocked(
                    fl.x, fl.y + vy, allow_grate=False
                ):
                    fl.y += vy
            else:
                if abs(dx) > 0.04:
                    fl.facing_left = dx < 0.0
                fl.moving = False

            if fl.cooldown <= 0.0 and dist <= 1.35:
                c, r = best_rc
                t = self.grid[r][c]
                if (
                    best_kind == "pickup_crate"
                    and t.kind == "crate"
                    and t.crate_stock > 0
                ):
                    fl.carried_crate = {
                        "color_key": t.color_key,
                        "stock": t.crate_stock,
                        "max_stock": t.crate_max,
                        "dir_idx": t.dir_idx,
                        "require_stamp": t.require_stamp,
                        "require_fix": t.require_fix,
                        "interval": t.spawn_interval,
                        "splitter_straight_color": t.splitter_straight_color,
                        "splitter_branch_color": t.splitter_branch_color,
                    }
                    self.grid[r][c] = Tile(
                        kind="door_open" if t.is_doorway else "empty",
                        floor_variant=t.floor_variant,
                        decal=t.decal,
                        is_doorway=t.is_doorway,
                        loading_corner=t.loading_corner,
                    )
                    fl.cooldown = cd_time
                    self._spawn_particles(c + 0.5, r + 0.5, (255, 212, 96), count=8)
                    self._emit_sfx("interact")
                    self.popups.append(
                        FloatingText(
                            fl.x, fl.y - 0.55, "FORK LIFTED CRATE!", (255, 224, 96)
                        )
                    )
                elif (
                    best_kind == "drop_crate"
                    and fl.carried_crate is not None
                    and t.kind == "empty"
                ):
                    data = fl.carried_crate
                    t.kind = "crate"
                    t.color_key = str(data["color_key"])
                    t.crate_stock = int(data["stock"])  # type: ignore[arg-type]
                    t.crate_max = int(data["max_stock"])  # type: ignore[arg-type]
                    t.dir_idx = int(data["dir_idx"])  # type: ignore[arg-type]
                    t.require_stamp = bool(data["require_stamp"])
                    t.require_fix = bool(data["require_fix"])
                    t.spawn_interval = float(data["interval"])  # type: ignore[arg-type]
                    t.splitter_straight_color = str(data["splitter_straight_color"])
                    t.splitter_branch_color = str(data["splitter_branch_color"])
                    t.spawn_timer = 0.8
                    t.bounce_anim = 1.0
                    fl.carried_crate = None
                    fl.cooldown = cd_time
                    self._spawn_particles(c + 0.5, r + 0.5, (110, 248, 138), count=10)
                    self._emit_sfx("interact")
                    self.popups.append(
                        FloatingText(
                            c + 0.5, r - 0.15, "CRATE -> LOADING BAY!", (110, 248, 138)
                        )
                    )
                elif best_kind == "pile" and t.pile_tier > 0:
                    t.pile_tier -= 1
                    is_bad = t.pile_kind in BAD_CHEQUE_TYPES
                    rw = 120 if is_bad else 150
                    crw = 15 if is_bad else 20
                    self._adjust_money(rw, crw)
                    if not is_bad:
                        self.cheques_rescued_count += 1
                    fl.cooldown = cd_time
                    self._spawn_particles(c + 0.5, r + 0.5, (255, 206, 82), count=8)
                    self._emit_sfx("interact")
                    self.popups.append(
                        FloatingText(
                            c + 0.5, r - 0.15, f"FORK CLEAR +${rw}", (255, 212, 96)
                        )
                    )
                    self._check_quota()
                elif best_kind == "crate" and t.kind == "crate" and t.crate_stock > 0:
                    t.crate_stock -= 1
                    rw = 100
                    crw = 15
                    if t.crate_stock <= 0:
                        rw += 400
                        crw += 120
                    self._adjust_money(rw, crw)
                    fl.cooldown = cd_time
                    self._spawn_particles(c + 0.5, r + 0.5, (255, 206, 82), count=8)
                    self._emit_sfx("interact")
                    self.popups.append(
                        FloatingText(
                            c + 0.5, r - 0.15, f"FORK HAUL +${rw}", (255, 212, 96)
                        )
                    )
                    self._check_quota()

    def _resolve_cheque_key(self, t: Tile) -> str:
        if t.color_key == "room1_mixed":
            seq = ("payroll", "rent", "void", "payroll", "fake", "rent")
            c_key = seq[t.spawn_count % len(seq)]
        elif t.color_key == "vip_fraud":
            seq = ("vip", "vip", "fake", "vip", "void")
            c_key = seq[t.spawn_count % len(seq)]
        elif t.color_key == "mixed_raw_fraud":
            seq = ("rent", "vip", "fake", "payroll", "void", "vip", "mortgage")
            c_key = seq[t.spawn_count % len(seq)]
        elif t.color_key == "all_mixed":
            seq = ("payroll", "vip", "rent", "fake", "vip", "mortgage", "void")
            c_key = seq[t.spawn_count % len(seq)]
        else:
            c_key = t.color_key if t.color_key in CHEQUE_TYPES else "payroll"
        t.spawn_count += 1
        return c_key

    def _source_line_extended(self, col: int, row: int) -> bool:
        """Return True once the player extends or modifies a source's starter belt stub."""
        src = self.grid[row][col]
        if src.kind == "jammed_source" and not src.jammed:
            return True
        dx, dy = DIRS[src.dir_idx]
        cur_c, cur_r = col + dx, row + dy
        visited: set[tuple[int, int]] = set()
        hops = 0
        while (
            self.in_bounds(cur_c, cur_r) and (cur_c, cur_r) not in visited and hops < 7
        ):
            visited.add((cur_c, cur_r))
            t = self.grid[cur_r][cur_c]
            if (
                t.paid_cost > 0
                or t.toggle_state > 0
                or t.kind
                in (
                    "bouncer",
                    "sorter",
                    "scanner",
                    "shredder",
                    "stamper",
                    "splitter",
                    "endorser",
                    "fixer",
                    "polisher",
                    "dest",
                )
            ):
                return True
            if t.kind != "belt":
                return hops >= 4
            hops += 1
            if hops >= 4:
                return True
            ndx, ndy = DIRS[t.dir_idx]
            cur_c += ndx
            cur_r += ndy
        return False

    def _huge_pile_master(self, tile: Tile) -> Tile | None:
        if 0 <= tile.truck_bay_idx < len(self.truck_bays):
            bay = self.truck_bays[tile.truck_bay_idx]
            mc = int(bay.get("master_col", bay["col"]))  # type: ignore[arg-type]
            mr = int(bay.get("master_row", bay["row"]))  # type: ignore[arg-type]
            if self.in_bounds(mc, mr):
                return self.grid[mr][mc]
        return tile if tile.kind == "huge_pile" else None

    def _update_truck_bays(self, dt: float) -> None:
        for bay in self.truck_bays:
            anim = float(bay.get("truck_anim", 0.0))  # type: ignore[arg-type]
            if anim > 0.0:
                bay["truck_anim"] = max(0.0, anim - dt)
            timer = float(bay.get("timer", 0.0)) - dt  # type: ignore[arg-type]
            if timer > 0.0:
                bay["timer"] = timer
                continue
            bay["timer"] = float(bay.get("interval", 18.0))  # type: ignore[arg-type]
            bay["truck_anim"] = 2.4
            hc = int(bay.get("master_col", bay["col"]))  # type: ignore[arg-type]
            hr = int(bay.get("master_row", bay["row"]))  # type: ignore[arg-type]
            cc = int(bay["crate_col"])  # type: ignore[arg-type]
            cr = int(bay["crate_row"])  # type: ignore[arg-type]
            dump_count = int(bay.get("dump_count", 12))  # type: ignore[arg-type]
            crate_stock = int(bay.get("crate_stock", 8))  # type: ignore[arg-type]
            if self.in_bounds(hc, hr):
                hp = self.grid[hr][hc]
                hp.kind = "huge_pile"
                cap = max(36, hp.crate_max)
                new_stock = hp.crate_stock + dump_count
                overflow = max(0, new_stock - cap)
                hp.crate_stock = min(cap, new_stock)
                hp.crate_max = cap
                hp.bounce_anim = 1.0
                if overflow > 0:
                    spill_spots = max(1, min(4, (overflow + 2) // 3))
                    spilled = 0
                    for dist_r in (1, 2, 3):
                        for dr in range(-dist_r, dist_r + 1):
                            for dc in range(-dist_r, dist_r + 1):
                                if spilled >= spill_spots:
                                    break
                                sc, sr = hc + dc, hr + dr
                                if self.in_bounds(sc, sr):
                                    st = self.grid[sr][sc]
                                    if (
                                        st.kind == "empty"
                                        and st.pile_tier < 3
                                        and not st.is_doorway
                                    ):
                                        st.pile_tier += 1
                                        st.pile_kind = "mixed"
                                        spilled += 1
                    if spilled > 0:
                        self.popups.append(
                            FloatingText(
                                hc + 0.5, hr - 0.55, "PILE OVERFLOW!", (255, 128, 92)
                            )
                        )
            self._spawn_particles(
                hc + 0.5, hr + 0.5, (255, 214, 108), count=12, speed=2.4
            )
            self._emit_sfx("interact")
            self.popups.append(
                FloatingText(
                    hc + 0.5, hr - 0.25, "TRUCK DUMPED CHEQUE PILE!", (255, 224, 110)
                )
            )

    def _update_sources(self, dt: float) -> None:
        for r in range(self.rows):
            for c in range(self.cols):
                t = self.grid[r][c]
                if t.bounce_anim > 0.0:
                    t.bounce_anim = max(0.0, t.bounce_anim - dt * 4.0)
                if t.stamp_anim > 0.0:
                    t.stamp_anim = max(0.0, t.stamp_anim - dt * 4.0)

                is_source = t.kind in ("source", "jammed_source") and not t.jammed
                pile_master = (
                    self._huge_pile_master(t) if t.kind == "huge_pile" else None
                )
                is_huge_pile = pile_master is not None and pile_master.crate_stock > 0
                is_crate = (
                    t.kind == "crate" and t.crate_stock > 0 and t.loading_corner >= 0
                )
                if not is_source and not is_huge_pile and not is_crate:
                    continue

                if is_source and not self._source_line_extended(c, r):
                    t.spawn_timer = max(t.spawn_timer, 0.9)
                    continue

                dx, dy = DIRS[t.dir_idx]
                spawn_c, spawn_r = c + dx, r + dy
                if (is_huge_pile or is_crate) and not (
                    self.in_bounds(spawn_c, spawn_r)
                    and self._tile_accepts_cheque(spawn_c, spawn_r)
                    and not (
                        self.grid[spawn_r][spawn_c].kind == "belt"
                        and self.grid[spawn_r][spawn_c].dir_idx == (t.dir_idx + 2) % 4
                    )
                ):
                    for alt_dir in range(4):
                        adx, ady = DIRS[alt_dir]
                        ac, ar = c + adx, r + ady
                        if not self.in_bounds(ac, ar) or not self._tile_accepts_cheque(
                            ac, ar
                        ):
                            continue
                        nb = self.grid[ar][ac]
                        if nb.kind == "belt" and nb.dir_idx == (alt_dir + 2) % 4:
                            continue
                        t.dir_idx = alt_dir
                        spawn_c, spawn_r = ac, ar
                        break
                if not self.in_bounds(spawn_c, spawn_r):
                    continue
                if (is_crate or is_huge_pile) and not self._tile_accepts_cheque(
                    spawn_c, spawn_r
                ):
                    continue

                t.spawn_timer -= dt
                if t.spawn_timer > 0.0:
                    continue

                if (
                    len(self.cheques) >= MAX_CHEQUES
                    or (
                        (is_crate or is_huge_pile)
                        and self._occupied_ahead(spawn_c, spawn_r, -1)
                    )
                    or any(
                        not ch.airborne
                        and math.hypot(ch.x - (spawn_c + 0.5), ch.y - (spawn_r + 0.5))
                        < 0.34
                        for ch in self.cheques
                    )
                ):
                    t.spawn_timer = 0.25
                    continue

                if t.jam_burst_queue > 0:
                    t.jam_burst_queue -= 1
                    t.spawn_timer = 0.42 if t.jam_burst_queue > 0 else t.spawn_interval
                elif is_source and t.burst_count > 1:
                    t.jam_burst_queue = t.burst_count - 1
                    t.spawn_timer = 0.42
                else:
                    t.spawn_timer = t.spawn_interval

                c_key = self._resolve_cheque_key(t)
                val = int(CHEQUE_TYPES[c_key]["value"])  # type: ignore[arg-type]
                max_age = float(CHEQUE_TYPES[c_key].get("timeout", 0.0))  # type: ignore[arg-type]
                if is_huge_pile or is_crate:
                    stamped = (
                        True if c_key in BAD_CHEQUE_TYPES else (t.spawn_count % 2 == 0)
                    )
                    misprint = (c_key not in BAD_CHEQUE_TYPES) and (
                        t.spawn_count % 4 == 1
                    )
                else:
                    stamped = (
                        True if c_key in BAD_CHEQUE_TYPES else (not t.require_stamp)
                    )
                    misprint = (c_key not in BAD_CHEQUE_TYPES) and t.require_fix
                disguise = (
                    ("payroll", "rent", "vip", "mortgage")[(t.spawn_count + c + r) % 4]
                    if c_key == "fake"
                    else ""
                )
                self.cheques.append(
                    ChequeItem(
                        x=spawn_c + 0.5,
                        y=spawn_r + 0.5,
                        color_key=c_key,
                        value=val,
                        disguise_color=disguise,
                        stamped=stamped,
                        misprint=misprint,
                        move_dir=t.dir_idx,
                        max_age=max_age,
                    )
                )
                if is_huge_pile and pile_master is not None:
                    pile_master.crate_stock = max(0, pile_master.crate_stock - 1)
                elif is_crate:
                    t.crate_stock -= 1
                    if t.crate_stock <= 0:
                        self._adjust_money(400, 120)
                        self._spawn_particles(
                            c + 0.5, r + 0.5, (110, 248, 138), count=12
                        )
                        self._emit_sfx("upgrade")
                        self.popups.append(
                            FloatingText(
                                c + 0.5,
                                r - 0.15,
                                "CRATE CLEARED! +$400!",
                                (110, 248, 138),
                            )
                        )
                        self.grid[r][c] = Tile(
                            kind="door_open" if t.is_doorway else "empty",
                            floor_variant=t.floor_variant,
                            decal=t.decal,
                            hazard=t.hazard,
                            oil_stain=t.oil_stain,
                            puddle=t.puddle,
                            cracked=t.cracked,
                            is_doorway=t.is_doorway,
                            loading_corner=t.loading_corner,
                        )
                        self._check_quota()

    def depot_capacity(self, tile: Tile) -> int:
        return (5, 10, 18)[self.effective_machine_level(tile) - 1]

    def _update_depots(self, dt: float) -> None:
        for r in range(self.rows):
            for c in range(self.cols):
                t = self.grid[r][c]
                if t.kind != "depot" or not t.depot_items:
                    continue
                depot_lvl = self.effective_machine_level(t)
                age_mult = (0.50, 0.35, 0.20)[min(2, max(0, depot_lvl - 1))]
                for ch in t.depot_items:
                    if ch.max_age > 0.0 and not ch.expired:
                        ch.age += dt * age_mult
                        if ch.age >= ch.max_age:
                            ch.expired = True
                t.spawn_timer = max(0.0, t.spawn_timer - dt)
                if t.spawn_timer > 0.0:
                    continue
                dx, dy = DIRS[t.dir_idx]
                out_c, out_r = c + dx, r + dy
                if (
                    not self.in_bounds(out_c, out_r)
                    or not self._tile_accepts_cheque(out_c, out_r)
                    or self._occupied_ahead(out_c, out_r, -1)
                    or len(self.cheques) >= MAX_CHEQUES
                ):
                    t.spawn_timer = 0.2
                    continue
                ch = t.depot_items.pop(0)
                ch.x = out_c + 0.5
                ch.y = out_r + 0.5
                ch.move_dir = t.dir_idx
                ch.airborne = False
                ch.process_hold = 0.0
                self.cheques.append(ch)
                t.bounce_anim = 0.6
                t.spawn_timer = 0.35

    def _update_cheques(self, dt: float) -> None:
        idx = 0
        while idx < len(self.cheques):
            ch = self.cheques[idx]
            if ch.max_age > 0.0 and not ch.expired:
                ch.age += dt
                if ch.age >= ch.max_age:
                    ch.expired = True
            if ch.airborne:
                ch.air_progress += dt / AIR_DURATION
                if ch.air_progress >= 1.0:
                    ch.airborne = False
                    ch.air_progress = 0.0
                    ch.x = ch.target_x
                    ch.y = ch.target_y
                    col = int(math.floor(ch.x))
                    row = int(math.floor(ch.y))
                    if not self._tile_accepts_cheque(col, row):
                        self._spill_to_floor(col, row, ch, popup="DROPPED!")
                        self._pop_cheque(idx)
                        continue
                else:
                    p = ch.air_progress
                    ch.x = ch.start_x + (ch.target_x - ch.start_x) * p
                    ch.y = ch.start_y + (ch.target_y - ch.start_y) * p
                idx += 1
                continue

            col = int(math.floor(ch.x))
            row = int(math.floor(ch.y))
            if not self.in_bounds(col, row):
                self._pop_cheque(idx)
                continue

            tile = self.grid[row][col]
            if tile.kind == "dest":
                self._deliver_cheque(col, row, tile, ch)
                self._pop_cheque(idx)
                continue

            if tile.kind == "grate":
                self._pop_cheque(idx)
                self._record_lost_cheque(ch)
                self.streak = 0
                self.streak_timer = 0.0
                fine = int(round(250 * self.fine_multiplier))
                cash_fine = int(round(50 * self.fine_multiplier))
                self._adjust_money(-fine, -cash_fine)
                self.neglect_penalties += fine
                self._emit_sfx("error")
                self.popups.append(
                    FloatingText(
                        col + 0.5, row + 0.2, f"FELL IN GRATE! -${fine}", (255, 96, 86)
                    )
                )
                continue

            if (
                tile.kind in ("empty", "door_open")
                or tile.pile_tier > 0
                or tile.kind
                in (
                    "void",
                    "wall",
                    "window",
                    "pillar",
                    "fence",
                    "door_closed",
                    "breaker",
                    "crate",
                )
            ):
                if tile.kind in ("empty", "door_open") and tile.pile_tier < 3:
                    self._spill_to_floor(col, row, ch, popup="PILEUP!")
                    self._pop_cheque(idx)
                    continue
                idx += 1
                continue

            if tile.kind == "huge_pile":
                master = self._huge_pile_master(tile) or tile
                cap = max(36, master.crate_max)
                master.crate_stock = min(cap, master.crate_stock + 1)
                master.bounce_anim = 0.6
                self._pop_cheque(idx)
                self._emit_sfx("interact")
                continue

            if tile.kind == "depot":
                if len(tile.depot_items) < self.depot_capacity(tile):
                    tile.depot_items.append(ch)
                    tile.bounce_anim = 0.6
                    self._pop_cheque(idx)
                    self._emit_sfx("interact")
                    continue

            if tile.kind == "bouncer":
                dx, dy = DIRS[tile.dir_idx]
                cx, cy = col + 0.5, row + 0.5
                center_dist = math.hypot(ch.x - cx, ch.y - cy)
                along_diff = (ch.x - cx) * dx + (ch.y - cy) * dy
                perp_dist = abs((ch.x - cx) * dy - (ch.y - cy) * dx)
                if center_dist < 0.30 or (along_diff >= -0.04 and perp_dist < 0.26):
                    lvl = self.effective_machine_level(tile)
                    if (
                        lvl >= 2
                        and not ch.sorted_by
                        and ch.color_key not in BAD_CHEQUE_TYPES
                    ):
                        ch.sorted_by.add((col, row))
                        ch.value += (0, 20, 45)[lvl - 1]
                    ch.airborne = True
                    ch.air_progress = 0.0
                    ch.start_x = cx
                    ch.start_y = cy
                    ch.target_x = cx + dx * 3.0
                    ch.target_y = cy + dy * 3.0
                    ch.move_dir = tile.dir_idx
                    tile.bounce_anim = 1.0
                    self._spawn_particles(cx, cy, (255, 196, 72), count=7, speed=2.4)
                    self._emit_sfx("bounce")
                    idx += 1
                    continue

            if tile.kind == "shredder":
                shred_cycle = self.shredder_cycle_time(tile)
                if shred_cycle > 0.0:
                    ch.x = col + 0.5
                    ch.y = row + 0.5
                    ch.process_hold += dt
                    if ch.process_hold < shred_cycle:
                        idx += 1
                        continue
                    ch.process_hold = 0.0
                if (ch.color_key in BAD_CHEQUE_TYPES or ch.expired) and random.random() > self.machine_accuracy(tile):
                    tile.bounce_anim = 0.6
                    self._emit_sfx("error")
                    self.popups.append(
                        FloatingText(col + 0.5, row - 0.1, "SHRED MISSED!", (255, 186, 86))
                    )
                    dx, dy = DIRS[tile.dir_idx]
                    out_c, out_r = col + dx, row + dy
                    if self.in_bounds(out_c, out_r) and self._tile_accepts_cheque(out_c, out_r):
                        ch.x = out_c + 0.5
                        ch.y = out_r + 0.5
                        ch.move_dir = tile.dir_idx
                    else:
                        self._spill_to_floor(col, row, ch, popup="SHRED JAM!")
                        self._pop_cheque(idx)
                        continue
                    idx += 1
                    continue
                tile.bounce_anim = 1.0
                self._pop_cheque(idx)
                if ch.color_key in BAD_CHEQUE_TYPES or ch.expired:
                    self.streak += 1
                    self.streak_timer = 7.0
                    self.max_streak = max(self.max_streak, self.streak)
                    vip_tier = self.upgrade_tier("vip_endorser")
                    lvl = self.effective_machine_level(tile)
                    base_bounty = (
                        180 + (0, 50, 100, 160)[vip_tier] + (0, 50, 120)[lvl - 1]
                    )
                    base_cash = 45 + (0, 15, 30, 50)[vip_tier] + (0, 15, 35)[lvl - 1]
                    mult = self.combo_multiplier
                    award = int(round(base_bounty * mult))
                    cash_award = int(round(base_cash * mult))
                    self._adjust_money(award, cash_award)
                    self._spawn_particles(
                        col + 0.5, row + 0.5, (255, 118, 128), count=10, speed=2.5
                    )
                    self._emit_sfx("shred")
                    combo_tag = (
                        f" ({self.combo_multiplier:.2g}x)"
                        if self.combo_multiplier > 1.0
                        else ""
                    )
                    self.popups.append(
                        FloatingText(
                            col + 0.5,
                            row - 0.1,
                            f"SHRED! +${award}{combo_tag}",
                            (110, 248, 138),
                        )
                    )
                    self._check_quota()
                else:
                    self._record_lost_cheque(ch)
                    self.streak = 0
                    self.streak_timer = 0.0
                    fine = int(
                        round(max(150, abs(ch.value) * 0.5) * self.fine_multiplier)
                    )
                    cash_fine = int(round(40 * self.fine_multiplier))
                    self._adjust_money(-fine, -cash_fine)
                    self.neglect_penalties += fine
                    self._spawn_particles(
                        col + 0.5, row + 0.5, (255, 96, 96), count=10, speed=2.4
                    )
                    self._emit_sfx("error")
                    self.popups.append(
                        FloatingText(
                            col + 0.5,
                            row - 0.1,
                            f"SHREDDED REAL CHEQUE! -${fine}",
                            (255, 108, 108),
                        )
                    )
                continue

            if tile.kind == "stamper" and ch.stamped_by != (col, row):
                cx, cy = col + 0.5, row + 0.5
                center_dist = math.hypot(ch.x - cx, ch.y - cy)
                if center_dist < 0.32:
                    ch.x = cx
                    ch.y = cy
                    ch.stamp_hold += dt
                    if ch.stamp_hold < self.stamper_cycle_time(tile):
                        idx += 1
                        continue
                    ch.stamp_hold = 0.0
                    ch.stamped_by = (col, row)
                    tile.stamp_anim = 1.0
                    if ch.color_key in BAD_CHEQUE_TYPES:
                        self._emit_sfx("stamp")
                    elif not ch.stamped:
                        ch.stamped = True
                        lvl = self.effective_machine_level(tile)
                        vip_ink = (0, 60, 120, 200)[
                            self.upgrade_tier("vip_endorser")
                        ] + (45 if lvl >= 3 else 0)
                        if vip_ink > 0:
                            ch.value += vip_ink
                        self._spawn_particles(
                            cx, cy, (120, 244, 198), count=7, speed=2.0
                        )
                        self._emit_sfx("stamp")
                        self.popups.append(
                            FloatingText(
                                cx,
                                row - 0.1,
                                f"VIP STAMP +${vip_ink}!"
                                if vip_ink > 0
                                else "STAMPED!",
                                (120, 240, 255),
                            )
                        )
                    else:
                        self._emit_sfx("stamp")

            if tile.kind == "fixer" and ch.fixed_by != (col, row):
                cx, cy = col + 0.5, row + 0.5
                center_dist = math.hypot(ch.x - cx, ch.y - cy)
                if center_dist < 0.32:
                    ch.x = cx
                    ch.y = cy
                    ch.process_hold += dt
                    if ch.process_hold < self.fixer_cycle_time(tile):
                        idx += 1
                        continue
                    ch.process_hold = 0.0
                    ch.fixed_by = (col, row)
                    tile.stamp_anim = 1.0
                    lvl = self.effective_machine_level(tile)
                    if ch.color_key in BAD_CHEQUE_TYPES:
                        self._emit_sfx("interact")
                    elif ch.misprint:
                        if random.random() <= self.machine_accuracy(tile):
                            ch.misprint = False
                            fix_bonus = (75, 115, 165)[lvl - 1]
                            ch.value += fix_bonus
                            self._spawn_particles(
                                cx, cy, (242, 134, 255), count=8, speed=2.2
                            )
                            self._emit_sfx("stamp")
                            self.popups.append(
                                FloatingText(
                                    cx, row - 0.1, f"FIXED! +${fix_bonus}", (242, 144, 255)
                                )
                            )
                        else:
                            self._emit_sfx("error")
                            self.popups.append(
                                FloatingText(cx, row - 0.1, "FIX MISSED!", (255, 186, 86))
                            )
                    elif lvl >= 3:
                        ch.value += 35
                        self._spawn_particles(
                            cx, cy, (200, 160, 255), count=5, speed=1.8
                        )
                        self._emit_sfx("interact")
                        self.popups.append(
                            FloatingText(
                                cx, row - 0.1, "RE-ALIGNED +$35", (200, 178, 255)
                            )
                        )

            if tile.kind == "polisher" and ch.polished_by != (col, row):
                cx, cy = col + 0.5, row + 0.5
                center_dist = math.hypot(ch.x - cx, ch.y - cy)
                if center_dist < 0.32:
                    ch.x = cx
                    ch.y = cy
                    ch.process_hold += dt
                    if ch.process_hold < self.polisher_cycle_time(tile):
                        idx += 1
                        continue
                    ch.process_hold = 0.0
                    ch.polished_by = (col, row)
                    tile.stamp_anim = 1.0
                    lvl = self.effective_machine_level(tile)
                    if ch.color_key in BAD_CHEQUE_TYPES:
                        self._emit_sfx("interact")
                    elif (not ch.stamped or ch.misprint) and lvl < 3:
                        ch.misprint = True
                        self._spawn_particles(
                            cx, cy, (255, 118, 92), count=8, speed=2.4
                        )
                        self._emit_sfx("error")
                        self.popups.append(
                            FloatingText(
                                cx, row - 0.1, "SMEARED! -> MISPRINT!", (255, 118, 92)
                            )
                        )
                    else:
                        if lvl >= 3:
                            ch.stamped = True
                            ch.misprint = False
                        if not ch.polished:
                            ch.polished = True
                            pol_bonus = (90, 140, 200)[lvl - 1]
                            ch.value += pol_bonus
                            self._spawn_particles(
                                cx, cy, (255, 218, 92), count=9, speed=2.3
                            )
                            self._emit_sfx("stamp")
                            self.popups.append(
                                FloatingText(
                                    cx,
                                    row - 0.1,
                                    f"POLISHED! +${pol_bonus}",
                                    (255, 224, 108),
                                )
                            )

            if tile.kind == "endorser":
                center_dist = math.hypot(ch.x - (col + 0.5), ch.y - (row + 0.5))
                if (
                    center_dist < 0.28
                    and ch.color_key not in BAD_CHEQUE_TYPES
                    and not ch.boosted_by
                ):
                    ch.boosted_by.add((col, row))
                    lvl = self.effective_machine_level(tile)
                    lvl_bonus = (0, 55, 120)[lvl - 1]
                    boost_amt = (
                        100
                        + (0, 40, 85, 140)[self.upgrade_tier("commission_boost")]
                        + lvl_bonus
                    )
                    ch.value += boost_amt
                    tile.stamp_anim = 1.0
                    self._spawn_particles(
                        col + 0.5, row + 0.5, (255, 224, 96), count=7, speed=2.0
                    )
                    self._emit_sfx("stamp")
                    self.popups.append(
                        FloatingText(
                            col + 0.5,
                            row - 0.1,
                            f"+${boost_amt}",
                            (255, 224, 96),
                        )
                    )

            if tile.kind == "scanner":
                center_dist = math.hypot(ch.x - (col + 0.5), ch.y - (row + 0.5))
                if ch.scanned_by != (col, row) and center_dist < 0.28:
                    cycle = self.scanner_cycle_time(tile)
                    if cycle > 0.0:
                        ch.x = col + 0.5
                        ch.y = row + 0.5
                        ch.process_hold += dt
                        if ch.process_hold < cycle:
                            idx += 1
                            continue
                        ch.process_hold = 0.0
                    already_scanned = ch.fraud_scanned
                    ch.scanned_by = (col, row)
                    tile.stamp_anim = 1.0
                    lvl = self.effective_machine_level(tile)
                    accurate = random.random() <= self.machine_accuracy(tile)
                    if accurate:
                        ch.fraud_scanned = True
                    divert_hit = accurate and (
                        (ch.color_key in BAD_CHEQUE_TYPES or ch.expired)
                        if tile.scanner_mode == "fraud"
                        else (ch.misprint or ch.expired or not ch.stamped)
                    )
                    if not accurate:
                        self._emit_sfx("error")
                        self.popups.append(
                            FloatingText(
                                col + 0.5, row - 0.1, "SCAN MISSED!", (255, 186, 86)
                            )
                        )
                    elif divert_hit:
                        tile.bounce_anim = 1.0
                    elif lvl >= 2 and not already_scanned:
                        uv_bonus = 35 if lvl == 2 else 75
                        ch.value += uv_bonus
                        self._spawn_particles(
                            col + 0.5, row + 0.5, (112, 236, 255), count=6, speed=1.9
                        )
                        self.popups.append(
                            FloatingText(
                                col + 0.5,
                                row - 0.1,
                                f"UV OK +${uv_bonus}",
                                (120, 244, 255),
                            )
                        )

            if tile.kind == "sorter":
                center_dist = math.hypot(ch.x - (col + 0.5), ch.y - (row + 0.5))
                if center_dist < 0.28 and (col, row) not in ch.sorted_by:
                    ch.sorted_by.add((col, row))
                    if ch.apparent_color in BAD_CHEQUE_TYPES:
                        ch.split_dir = (
                            (tile.dir_idx + 1) % 4
                            if (tile.spawn_count % 2 == 1)
                            else tile.dir_idx
                        )
                        tile.spawn_count += 1
                    elif ch.apparent_color == tile.sorter_branch_color:
                        ch.split_dir = (tile.dir_idx + 1) % 4
                    else:
                        ch.split_dir = tile.dir_idx
                    lvl = self.effective_machine_level(tile)
                    if lvl >= 2 and ch.color_key not in BAD_CHEQUE_TYPES:
                        ch.value += 25 if lvl == 2 else 55

            if tile.kind == "splitter":
                center_dist = math.hypot(ch.x - (col + 0.5), ch.y - (row + 0.5))
                if ch.last_split_tile != (col, row) and center_dist < 0.28:
                    out_dir = self._splitter_output_dir(tile, ch.apparent_color)
                    tile.stamp_anim = 1.0
                    ch.last_split_tile = (col, row)
                    ch.split_dir = out_dir
                    lvl = self.effective_machine_level(tile)
                    if (
                        lvl >= 2
                        and ch.color_key not in BAD_CHEQUE_TYPES
                        and not ch.sorted_by
                    ):
                        ch.sorted_by.add((col, row))
                        ch.value += 15 if lvl == 2 else 35
            elif tile.kind != "sorter":
                ch.last_split_tile = (-1, -1)

            desired_dir = tile.dir_idx
            if tile.kind == "sorter":
                if (col, row) in ch.sorted_by and ch.split_dir >= 0:
                    desired_dir = ch.split_dir
                elif ch.apparent_color == tile.sorter_branch_color:
                    desired_dir = (tile.dir_idx + 1) % 4
            elif tile.kind == "scanner" and ch.scanned_by == (col, row):
                divert_hit = (
                    (ch.color_key in BAD_CHEQUE_TYPES or ch.expired)
                    if tile.scanner_mode == "fraud"
                    else (ch.misprint or ch.expired or not ch.stamped)
                )
                if divert_hit:
                    desired_dir = (tile.dir_idx + 1) % 4
            elif (
                tile.kind == "splitter"
                and ch.last_split_tile == (col, row)
                and ch.split_dir >= 0
            ):
                desired_dir = ch.split_dir
            ch.move_dir = desired_dir

            dx, dy = DIRS[desired_dir]
            cx, cy = col + 0.5, row + 0.5
            step = self.tile_belt_speed(tile) * dt
            perp_diff = (cy - ch.y) if dx != 0 else (cx - ch.x)
            if abs(perp_diff) > 0.04:
                move_p = max(-step, min(step, perp_diff))
                if dx != 0:
                    ch.y += move_p
                else:
                    ch.x += move_p
                fwd_step = max(0.0, step - abs(move_p))
            else:
                if dx != 0:
                    ch.y = cy
                else:
                    ch.x = cx
                fwd_step = step

            nx = ch.x + dx * fwd_step
            ny = ch.y + dy * fwd_step
            nc, nr = int(math.floor(nx)), int(math.floor(ny))

            # Stop on tile exit boundary if destination tile cannot accept yet.
            if (nc, nr) != (col, row):
                dest_is_pile = (
                    self.in_bounds(nc, nr) and self.grid[nr][nc].kind == "huge_pile"
                )
                if not dest_is_pile and not self._tile_accepts_cheque(nc, nr):
                    ch.x = max(col + 0.25, min(col + 0.75, cx + dx * 0.25))
                    ch.y = max(row + 0.25, min(row + 0.75, cy + dy * 0.25))
                    idx += 1
                    continue
                if not dest_is_pile and self._occupied_ahead(nc, nr, idx):
                    idx += 1
                    continue

            ch.x = nx
            ch.y = ny
            idx += 1

    def _spill_to_floor(self, col: int, row: int, ch: ChequeItem, popup: str) -> None:
        self._record_lost_cheque(ch)
        if not self.in_bounds(col, row):
            return
        t = self.grid[row][col]
        if t.kind not in ("empty", "door_open"):
            return
        if t.pile_tier < 3:
            t.pile_tier += 1
            t.pile_kind = ch.color_key
        self.streak = 0
        self.streak_timer = 0.0
        fine = int(round(120 * self.fine_multiplier))
        cash_fine = int(round(25 * self.fine_multiplier))
        self._adjust_money(-fine, -cash_fine)
        self.neglect_penalties += fine
        self._emit_sfx("error")
        self.popups.append(
            FloatingText(col + 0.5, row - 0.1, f"{popup} -${fine}", (255, 160, 82))
        )

    def _tile_accepts_cheque(self, col: int, row: int) -> bool:
        if not self.in_bounds(col, row):
            return False
        t = self.grid[row][col]
        if t.pile_tier >= 2:
            return False
        return t.kind in (
            "belt",
            "bouncer",
            "sorter",
            "scanner",
            "shredder",
            "stamper",
            "splitter",
            "endorser",
            "fixer",
            "polisher",
            "depot",
            "dest",
            "grate",
        )

    def _occupied_ahead(self, nc: int, nr: int, self_idx: int) -> bool:
        dest_t = self.grid[nr][nc]
        if dest_t.kind in ("dest", "grate", "shredder"):
            return False
        if dest_t.kind == "depot":
            return len(dest_t.depot_items) >= self.depot_capacity(dest_t)
        for i, other in enumerate(self.cheques):
            if i == self_idx or other.airborne:
                continue
            if int(math.floor(other.x)) == nc and int(math.floor(other.y)) == nr:
                return True
        return False

    def _reject_delivery(
        self,
        col: int,
        row: int,
        ch: ChequeItem,
        raw_fine: int,
        raw_cash: int,
        label: str,
        rgb: tuple[int, int, int],
        *,
        shake: float = 0.20,
        particle_count: int = 8,
        particle_speed: float | None = None,
    ) -> None:
        self._record_lost_cheque(ch)
        self.streak = 0
        self.streak_timer = 0.0
        self.wrong_deliveries += 1
        self.screen_shake = shake
        fine = int(round(raw_fine * self.fine_multiplier))
        cash_fine = int(round(raw_cash * self.fine_multiplier))
        self._adjust_money(-fine, -cash_fine)
        self.neglect_penalties += fine
        if particle_speed is not None:
            self._spawn_particles(
                col + 0.5, row + 0.5, rgb, count=particle_count, speed=particle_speed
            )
        else:
            self._spawn_particles(col + 0.5, row + 0.5, rgb, count=particle_count)
        self._emit_sfx("error")
        self.popups.append(
            FloatingText(col + 0.5, row - 0.15, f"{label} -${fine}", rgb)
        )

    def _deliver_cheque(self, col: int, row: int, tile: Tile, ch: ChequeItem) -> None:
        if ch.expired:
            fine = max(150, abs(ch.value) // 2)
            self._reject_delivery(
                col,
                row,
                ch,
                fine,
                max(50, fine // 3),
                "EXPIRED!",
                (255, 92, 92),
                shake=0.22,
                particle_count=10,
            )
        elif ch.color_key in BAD_CHEQUE_TYPES:
            self._reject_delivery(
                col,
                row,
                ch,
                400,
                100,
                f"{ch.color_key.upper()}!",
                (255, 78, 78),
                shake=0.25,
                particle_count=12,
                particle_speed=2.8,
            )
        elif ch.color_key != tile.color_key:
            wrong_lbl = "WRONG TUBE (UNSTAMPED)!" if not ch.stamped else "WRONG TUBE!"
            self._reject_delivery(col, row, ch, 220, 60, wrong_lbl, (255, 118, 92))
        elif not ch.stamped:
            self._reject_delivery(col, row, ch, 150, 45, "UNSTAMPED!", (255, 190, 68))
        elif ch.misprint:
            self._reject_delivery(col, row, ch, 150, 45, "MISPRINT!", (242, 134, 255))
        elif tile.require_scan and not ch.fraud_scanned:
            self._reject_delivery(col, row, ch, 140, 40, "UNSCANNED!", (120, 224, 255))
        elif tile.require_boost and not ch.boosted_by:
            self._reject_delivery(
                col, row, ch, 160, 45, "UNBOOSTED!", (255, 204, 76), particle_count=9
            )
        elif (tile.require_polish or ch.color_key == "vip") and not ch.polished:
            self._reject_delivery(
                col,
                row,
                ch,
                160,
                45,
                "VIP NEEDS POLISH!",
                (255, 218, 108),
                particle_count=9,
            )
        elif ch.color_key == tile.color_key:
            self.streak += 1
            self.streak_timer = 7.0
            self.max_streak = max(self.max_streak, self.streak)
            base_val = (
                ch.value
                + (80 if tile.require_boost else 0)
                + (90 if tile.require_polish else 0)
                + (50 if tile.require_scan else 0)
            )
            award = int(round(base_val * self.combo_multiplier))
            self._adjust_money(award)
            self.cheques_rescued_count += 1
            tile.delivered_count += 1
            tile.bounce_anim = 1.0
            c_rgb = tuple(CHEQUE_TYPES[tile.color_key]["color"])  # type: ignore[arg-type]
            self._spawn_particles(col + 0.5, row + 0.5, c_rgb, count=10, speed=2.5)
            self._emit_sfx("deliver")
            combo_tag = (
                f" ({self.combo_multiplier:.2g}x!)"
                if self.combo_multiplier > 1.0
                else ""
            )
            self.popups.append(
                FloatingText(
                    col + 0.5, row - 0.15, f"+${award}!{combo_tag}", (98, 248, 128)
                )
            )
        else:
            self._reject_delivery(
                col, row, ch, 200, 60, "WRONG TUBE!", (255, 92, 92), particle_count=10
            )

    def _pop_cheque(self, idx: int) -> None:
        self.cheques[idx] = self.cheques[-1]
        self.cheques.pop()
