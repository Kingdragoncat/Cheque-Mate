from __future__ import annotations

from dataclasses import dataclass

GRID_COLS = 30
GRID_ROWS = 18
TILE_SIZE = 48

BUILD_REACH = 4.5
INTERACT_REACH = 2.5

# Cardinal directions: 0=North, 1=East, 2=South, 3=West
DIRS: tuple[tuple[int, int], ...] = (
    (0, -1),
    (1, 0),
    (0, 1),
    (-1, 0),
)
DIR_NAMES: tuple[str, ...] = ("N", "E", "S", "W")

CHEQUE_ORDER: tuple[str, ...] = ("payroll", "rent", "vip", "mortgage")
BAD_CHEQUE_TYPES: tuple[str, ...] = ("void", "fake")

CHEQUE_TYPES: dict[str, dict[str, object]] = {
    "payroll": {
        "label": "PAYROLL",
        "color": (66, 206, 114),
        "bg": (206, 242, 214),
        "value": 450,
        "timeout": 36.0,
        "priority": "MEDIUM",
    },
    "rent": {
        "label": "RENT",
        "color": (244, 198, 62),
        "bg": (248, 240, 202),
        "value": 520,
        "timeout": 44.0,
        "priority": "MEDIUM",
    },
    "vip": {
        "label": "VIP",
        "color": (68, 148, 250),
        "bg": (206, 228, 250),
        "value": 850,
        "timeout": 28.0,
        "priority": "HIGH",
    },
    "mortgage": {
        "label": "MORTGAGE",
        "color": (186, 128, 244),
        "bg": (232, 218, 248),
        "value": 650,
        "timeout": 60.0,
        "priority": "LOW",
    },
    "void": {
        "label": "VOID",
        "color": (232, 62, 62),
        "bg": (248, 206, 206),
        "value": -400,
        "timeout": 0.0,
        "priority": "NONE",
    },
    "fake": {
        "label": "FAKE",
        "color": (214, 46, 68),
        "bg": (248, 202, 212),
        "value": -500,
        "timeout": 0.0,
        "priority": "NONE",
    },
}

CASH_COMMISSION_RATE = 0.11
CLEAN_DECAL_COST = 55
CLEAR_PILEUP_COST = 75
STAMPER_UPGRADE_COST = 480
STAMPER_SLOW_TIME = 1.65
STAMPER_FAST_TIME = 0.20
MACHINE_MAX_LEVEL = 3
FIXER_SLOW_TIME = 1.10
FIXER_FAST_TIME = 0.22
POLISHER_SLOW_TIME = 1.15
POLISHER_FAST_TIME = 0.22
SCANNER_SLOW_TIME = 0.22
SCANNER_FAST_TIME = 0.05
NEGLECT_INTERVAL = 6.0
UPGRADE_MAX_TIER = 3
ROOM_UNLOCK_COSTS: tuple[int, ...] = (0, 1450, 3400, 7400)

UPGRADABLE_MACHINES: tuple[str, ...] = (
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
)

MACHINE_UPGRADE_COSTS: dict[str, tuple[int, int]] = {
    "belt": (75, 165),
    "bouncer": (320, 640),
    "sorter": (390, 760),
    "scanner": (460, 880),
    "shredder": (420, 800),
    "stamper": (STAMPER_UPGRADE_COST, 940),
    "splitter": (380, 700),
    "endorser": (620, 1150),
    "fixer": (480, 900),
    "polisher": (520, 960),
    "depot": (320, 640),
}

TOOLS: list[tuple[str, str, str]] = [
    ("belt", "Conveyor Belt", "Moves cheques [R]"),
    ("bouncer", "Bounce Pad", "Hops 3 tiles"),
    ("sorter", "2-Color Sorter", "2 colors; passes VOID"),
    ("scanner", "Fraud/Err Scan", "[T] Fraud / Error mode"),
    ("shredder", "Shredder", "Deletes ANY cheque"),
    ("stamper", "Stamp Press", "Stamps unstamped"),
    ("splitter", "2-Way Splitter", "50/50 Straight / Side"),
    ("endorser", "Value Booster", "Boosts +$100 (1x)"),
    ("fixer", "Misprint Fixer", "Repairs misprints"),
    ("polisher", "Wax Polisher", "Polishes VIP cheques"),
    ("depot", "Belt Depot", "Buffers 5 cheques [U]"),
    ("demolish", "Crowbar / Mop", "Refund / Mop -$55"),
]

TOOL_COSTS: dict[str, int] = {
    "belt": 30,
    "bouncer": 185,
    "sorter": 240,
    "scanner": 280,
    "shredder": 250,
    "stamper": 270,
    "splitter": 220,
    "endorser": 420,
    "fixer": 300,
    "polisher": 340,
    "depot": 210,
    "demolish": 0,
}

TOOL_SHOP_DETAILS: dict[str, str] = {
    "belt": "Moves cheques across bays. [E/U] MK2/MK3 boosts local belt speed.",
    "bouncer": "Launches cheques 3 tiles over grates. MK2/MK3 adds air bonus.",
    "sorter": "Sorts 2 configured colors [T/Click]. Passes VOID/FAKE randomly!",
    "scanner": "Diverts FAKE/VOID/RAW in Fraud mode or MISPRINTS in Error mode [T].",
    "shredder": "Deletes ANY cheque fed in. (+$180 on VOID/FAKE/EXPIRED!).",
    "stamper": "Stamps unstamped cheques before scanning/delivery.",
    "splitter": "Alternates 50/50 between straight & 90 deg CW outputs.",
    "endorser": "MICR print (+$100/+$155/+$220, 1x max).",
    "fixer": "Repairs misprinted (ERR) cheques & adds value.",
    "polisher": "Polishes VIP cheques (required on all VIP checks!).",
    "depot": "Temporary belt storage: holds 5 cheques (MK2: 10, MK3: 18).",
    "demolish": "Refunds 100% on machines & upgrades. Mop oil -$55 / piles -$75.",
}

UPGRADES: list[tuple[str, str, int, str]] = [
    (
        "turbo_belts",
        "Turbo Drive Servos",
        1250,
        "T1/T2/T3: +30% / +60% / +95% conveyor, stamper & machine speed.",
    ),
    (
        "long_reach",
        "Exosuit Reach & Grip",
        1100,
        "T1/T2/T3: +2/+3.5/+5 build reach, +1/+2/+3 interact reach & walk.",
    ),
    (
        "vip_endorser",
        "Precision Ink & Bounty",
        1450,
        "T1/T2/T3: Fast stamps (0.35/0.18/0.08s), +$60/+$120/+$200 ink & shred.",
    ),
    (
        "auto_drone",
        "Collector Drone",
        1850,
        "T1/T2/T3: Faster autonomous drone zaps fraud, oil & pileups free.",
    ),
    (
        "commission_boost",
        "Vault Broker Cut",
        1400,
        "T1/T2/T3: Cash cut 11%->14%->17%->21% + stronger Value Boosters.",
    ),
    (
        "fraud_shield",
        "Audit Shielding",
        1200,
        "T1/T2/T3: -35%/-65%/-85% fines & floor spills across all rooms.",
    ),
]

UPGRADE_TIER_COSTS: dict[str, tuple[int, int, int]] = {
    "turbo_belts": (1250, 3100, 6800),
    "long_reach": (1100, 2700, 5800),
    "vip_endorser": (1450, 3500, 7400),
    "auto_drone": (1850, 4200, 8800),
    "commission_boost": (1400, 3300, 7000),
    "fraud_shield": (1200, 2900, 6200),
}

STORY_LINES: tuple[str, ...] = (
    "You broke into the abandoned Central Cheque Processing Plant for easy cash.",
    "Instead, you found a decaying maze: broken lights, oil slicks, jammed vaults,",
    "and mountains of tangled, VOID, and FAKE cheques flooding the concrete floor.",
    "",
    "Grab your crowbar: WALK the bays, flip BREAKER switches, pry DOORS open,",
    "clear CHEQUE PILEUPS, shred FAKEs, and bounce every real cheque to safety!",
)


@dataclass(frozen=True)
class SourceDef:
    col: int
    row: int
    dir_idx: int
    color_key: str  # "payroll", "pension", "refund", "urgent", "mixed_pb", "urgent_fraud"
    jammed: bool = False
    require_stamp: bool = False
    require_fix: bool = False
    interval: float = 2.0
    burst_count: int = 5


@dataclass(frozen=True)
class CrateDef:
    col: int
    row: int
    dir_idx: int
    color_key: str
    stock: int = 10
    require_stamp: bool = False
    require_fix: bool = False
    interval: float = 1.35


@dataclass(frozen=True)
class DestDef:
    col: int
    row: int
    color_key: str
    require_boost: bool = False
    require_polish: bool = False
    require_scan: bool = False


@dataclass(frozen=True)
class BeltRun:
    x1: int
    y1: int
    x2: int
    y2: int
    dir_idx: int


@dataclass(frozen=True)
class PileupDef:
    col: int
    row: int
    tier: int  # 1=Small pile, 2=Large pileup, 3=Giant mountain
    kind: str = "payroll"  # payroll, refund, pension, urgent, void, fake, mixed
    variant: int = 0


@dataclass(frozen=True)
class LightDef:
    col: float
    row: float
    radius: float
    state: str  # "working", "flicker", "out"


@dataclass(frozen=True)
class TruckBayDef:
    col: int
    row: int
    crate_col: int
    crate_row: int
    dir_idx: int = 1
    color_key: str = "all_mixed"
    interval: float = 18.0
    dump_count: int = 14
    crate_stock: int = 8


@dataclass(frozen=True)
class LevelDef:
    title: str
    briefing: str
    quota: int
    time_limit: int
    player_start: tuple[float, float]
    sources: tuple[SourceDef, ...]
    dests: tuple[DestDef, ...]
    grates: tuple[tuple[int, int], ...]
    initial_belts: tuple[BeltRun, ...]
    starting_cash: int = 1500
    min_dest_deliveries: int = 5
    stage_goals: tuple[int, int] = (1500, 6500)
    start_col: int = 0
    room_cols: int = 13
    unlock_cost: int = 0
    crates: tuple[CrateDef, ...] = ()
    void_rects: tuple[tuple[int, int, int, int], ...] = ()
    walls: tuple[tuple[int, int], ...] = ()
    windows: tuple[tuple[int, int], ...] = ()
    doors: tuple[tuple[int, int, bool], ...] = ()
    stage_doors: tuple[tuple[int, int, int], ...] = ()
    fences: tuple[tuple[int, int], ...] = ()
    pillars: tuple[tuple[int, int], ...] = ()
    drains: tuple[tuple[int, int], ...] = ()
    breakers: tuple[tuple[int, int], ...] = ()
    oil_stains: tuple[tuple[int, int], ...] = ()
    puddles: tuple[tuple[int, int], ...] = ()
    rubbish: tuple[tuple[int, int], ...] = ()
    hazard_tiles: tuple[tuple[int, int], ...] = ()
    dirty_zones: tuple[tuple[int, int, int, int], ...] = ()
    cracked_tiles: tuple[tuple[int, int], ...] = ()
    pileups: tuple[PileupDef, ...] = ()
    lights: tuple[LightDef, ...] = ()
    loading_zones: tuple[tuple[int, int], ...] = ()
    truck_bays: tuple[TruckBayDef, ...] = ()


def _rect_coords(x1: int, y1: int, x2: int, y2: int) -> tuple[tuple[int, int], ...]:
    return tuple((x, y) for y in range(y1, y2 + 1) for x in range(x1, x2 + 1))


def _col_wall(col: int, *row_ranges: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    pts: list[tuple[int, int]] = []
    for y1, y2 in row_ranges:
        for y in range(y1, y2 + 1):
            pts.append((col, y))
    return tuple(pts)


LEVELS: tuple[LevelDef, ...] = (
    LevelDef(
        title="Room 1: West Intake & Stamping Hall",
        briefing=(
            "Trucks dump HUGE PILES! Clear piles [E] -> Bay, Scan/Stamp/Sort -> tubes!"
        ),
        quota=4200,
        time_limit=300,
        starting_cash=3500,
        min_dest_deliveries=4,
        stage_goals=(4200, 15000),
        start_col=0,
        room_cols=15,
        unlock_cost=ROOM_UNLOCK_COSTS[0],
        player_start=(5.5, 3.5),
        void_rects=((0, 0, 14, 1), (0, 16, 14, 17), (10, 2, 14, 2)),
        sources=(),
        truck_bays=(
            TruckBayDef(2, 5, 3, 9, 1, "room1_mixed", interval=18.0, dump_count=14, crate_stock=6),
        ),
        crates=(
            CrateDef(7, 13, 0, "payroll", stock=6, interval=1.35),
        ),
        dests=(
            DestDef(11, 5, "payroll"),
            DestDef(11, 11, "rent"),
        ),
        initial_belts=(
            BeltRun(5, 4, 7, 4, 1),
        ),
        walls=_col_wall(14, (3, 4), (6, 10), (12, 14)),
        windows=((5, 2),),
        doors=(),
        stage_doors=(
            (14, 5, 2),
            (14, 11, 2),
        ),
        breakers=((9, 8),),
        pillars=((7, 6), (8, 12)),
        fences=(),
        grates=(),
        drains=(),
        oil_stains=((8, 9),),
        puddles=((9, 14),),
        rubbish=((5, 7), (11, 8)),
        hazard_tiles=(
            _rect_coords(2, 3, 4, 5)
            + _rect_coords(2, 8, 4, 10)
            + _rect_coords(2, 12, 4, 14)
        ),
        dirty_zones=((1, 10, 13, 14),),
        cracked_tiles=((4, 3), (8, 5)),
        pileups=(
            PileupDef(9, 4, tier=1, kind="rent", variant=0),
            PileupDef(6, 14, tier=1, kind="void", variant=0),
        ),
        lights=(
            LightDef(6.0, 5.5, 5.5, "working"),
            LightDef(8.0, 11.5, 5.5, "out"),
        ),
        loading_zones=((11, 13),),
    ),
    LevelDef(
        title="Room 2: Upper Fraud & Grate Gallery",
        briefing=(
            "Unjam MIXED_RAW_FRAUD, stamp & shred fakes -> (22,4), route PENSION -> Rm1! ($15k + $3,400)"
        ),
        quota=15000,
        time_limit=420,
        starting_cash=2800,
        min_dest_deliveries=5,
        stage_goals=(15000, 42000),
        start_col=15,
        room_cols=26,
        unlock_cost=ROOM_UNLOCK_COSTS[1],
        player_start=(5.5, 3.5),
        void_rects=((15, 14, 25, 17),),
        sources=(),
        truck_bays=(
            TruckBayDef(16, 3, 16, 5, 1, "mixed_raw_fraud", interval=17.0, dump_count=16, crate_stock=8),
        ),
        dests=(
            DestDef(22, 4, "rent"),
        ),
        initial_belts=(
            BeltRun(19, 3, 20, 3, 1),
        ),
        walls=_col_wall(25, (1, 3), (5, 10), (12, 13)),
        windows=((19, 0),),
        doors=(),
        stage_doors=(
            (25, 4, 3),
            (25, 11, 3),
        ),
        breakers=(),
        pillars=((18, 4), (22, 10)),
        fences=((17, 7), (18, 7), (19, 7)),
        grates=_rect_coords(20, 7, 21, 9),
        drains=((16, 3), (22, 11)),
        oil_stains=((16, 6), (21, 11)),
        puddles=((17, 3),),
        rubbish=((23, 8),),
        crates=(
            CrateDef(18, 12, 3, "payroll", stock=8, require_stamp=True, interval=1.30),
        ),
        hazard_tiles=_rect_coords(21, 3, 23, 5),
        dirty_zones=((16, 8, 24, 12),),
        cracked_tiles=((16, 10), (23, 10)),
        pileups=(
            PileupDef(17, 12, tier=2, kind="fake", variant=1),
            PileupDef(23, 12, tier=2, kind="payroll", variant=0),
        ),
        lights=(
            LightDef(20.0, 4.5, 6.0, "working"),
            LightDef(20.0, 10.5, 5.5, "working"),
        ),
        loading_zones=((19, 10),),
    ),
    LevelDef(
        title="Room 3: L-Dock & VIP MICR Annex",
        briefing=(
            "Fix ERR & stamp REFUND -> (37,13), boost ALL_MIXED -> VIP MICR (37,4), upg [E/U]! ($42k + $7,400)"
        ),
        quota=42000,
        time_limit=520,
        starting_cash=2800,
        min_dest_deliveries=6,
        stage_goals=(42000, 110000),
        start_col=26,
        room_cols=41,
        unlock_cost=ROOM_UNLOCK_COSTS[2],
        player_start=(5.5, 3.5),
        void_rects=((27, 0, 32, 2),),
        sources=(),
        truck_bays=(
            TruckBayDef(27, 6, 27, 8, 1, "all_mixed", interval=16.0, dump_count=18, crate_stock=10),
        ),
        dests=(
            DestDef(37, 4, "vip", require_polish=True),
            DestDef(37, 13, "mortgage"),
        ),
        initial_belts=(
            BeltRun(30, 6, 31, 6, 1),
        ),
        walls=_col_wall(40, (1, 3), (5, 8), (10, 13), (15, 16)),
        windows=((35, 0),),
        doors=(),
        stage_doors=(
            (40, 4, 4),
            (40, 9, 4),
            (40, 14, 4),
        ),
        breakers=(),
        pillars=((30, 5), (35, 11)),
        fences=((31, 10), (32, 10), (33, 10)),
        grates=_rect_coords(33, 5, 34, 8),
        drains=((33, 2), (32, 16)),
        oil_stains=((29, 11), (36, 8)),
        puddles=((30, 8), (36, 15)),
        rubbish=((28, 10), (38, 6)),
        crates=(
            CrateDef(31, 15, 1, "vip_fraud", stock=10, require_stamp=True, interval=1.25),
        ),
        hazard_tiles=(
            _rect_coords(36, 3, 38, 5)
            + _rect_coords(36, 12, 38, 14)
        ),
        dirty_zones=((27, 10, 39, 16),),
        cracked_tiles=((28, 12), (38, 9)),
        pileups=(
            PileupDef(34, 11, tier=3, kind="mixed", variant=2),
            PileupDef(28, 16, tier=2, kind="void", variant=1),
        ),
        lights=(
            LightDef(34.0, 5.5, 6.0, "working"),
            LightDef(33.5, 13.5, 6.0, "working"),
        ),
        loading_zones=((32, 12),),
    ),
    LevelDef(
        title="Room 4: Twin-Chamber Executive Vault",
        briefing=(
            "Flip Breaker (42,8), Fix ERR, Stamp, Boost & Wax-Polish -> RM4 Vault ($110k) to win!"
        ),
        quota=110000,
        time_limit=640,
        starting_cash=3400,
        min_dest_deliveries=7,
        stage_goals=(42000, 110000),
        start_col=41,
        room_cols=58,
        unlock_cost=ROOM_UNLOCK_COSTS[3],
        player_start=(5.5, 3.5),
        void_rects=((41, 0, 44, 1), (41, 16, 44, 17)),
        sources=(),
        truck_bays=(
            TruckBayDef(42, 4, 42, 6, 1, "all_mixed", interval=15.0, dump_count=20, crate_stock=12),
            TruckBayDef(42, 12, 42, 14, 1, "all_mixed", interval=16.0, dump_count=18, crate_stock=10),
        ),
        dests=(
            DestDef(54, 4, "vip", require_polish=True),
            DestDef(54, 14, "mortgage"),
        ),
        initial_belts=(
            BeltRun(45, 4, 46, 4, 1),
            BeltRun(45, 12, 46, 12, 1),
        ),
        walls=(),
        windows=((50, 0),),
        doors=(),
        stage_doors=(),
        breakers=((42, 8),),
        pillars=((47, 4), (51, 12)),
        fences=((43, 8), (44, 8), (46, 8), (47, 8), (51, 8), (52, 8), (54, 8), (55, 8)),
        grates=_rect_coords(48, 7, 50, 9),
        drains=((48, 2), (49, 16)),
        oil_stains=((45, 11), (52, 5)),
        puddles=((49, 3), (52, 15)),
        rubbish=((44, 6), (55, 10)),
        crates=(
            CrateDef(46, 5, 1, "vip_fraud", stock=12, require_stamp=True, interval=1.20),
            CrateDef(46, 15, 1, "all_mixed", stock=14, require_stamp=True, interval=1.20),
        ),
        hazard_tiles=(
            _rect_coords(53, 3, 55, 5)
            + _rect_coords(53, 13, 55, 15)
        ),
        dirty_zones=((45, 9, 56, 15),),
        cracked_tiles=((46, 7), (53, 2)),
        pileups=(
            PileupDef(50, 5, tier=3, kind="fake", variant=3),
            PileupDef(49, 13, tier=3, kind="mortgage", variant=1),
        ),
        lights=(
            LightDef(49.0, 4.5, 6.5, "out"),
            LightDef(49.0, 13.0, 6.5, "flicker"),
        ),
        loading_zones=((47, 10),),
    ),
)
