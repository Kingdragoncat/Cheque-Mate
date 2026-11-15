from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import pygame

from factory_data import (
    BAD_CHEQUE_TYPES,
    CASH_COMMISSION_RATE,
    CHEQUE_TYPES,
    CLEAN_DECAL_COST,
    CLEAR_PILEUP_COST,
    DIR_NAMES,
    DIRS,
    LEVELS,
    MACHINE_MAX_LEVEL,
    STAMPER_UPGRADE_COST,
    STORY_LINES,
    TILE_SIZE,
    TOOL_COSTS,
    TOOL_SHOP_DETAILS,
    TOOLS,
    UPGRADABLE_MACHINES,
    UPGRADE_MAX_TIER,
    UPGRADES,
)
from factory_sim import (
    FORKLIFT_MAX_CARRIED,
    MAX_CARRIED,
    ChequeItem,
    FactoryWorld,
    ForkliftUnit,
    Tile,
)

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
SPRITESHEET_PATH = ASSETS_DIR / "Player" / "thief_spritesheet.jpg"
CHEQUESHEET_PATH = ASSETS_DIR / "Cheques" / "cheque_variations.jpg"
FORKLIFT_SHEET_PATH = ASSETS_DIR / "forklift" / "spritesheet.png"
CRATE_TEXTURE_PATH = ASSETS_DIR / "forklift" / "crate.png"
LOADING_CORNER_PATH = ASSETS_DIR / "forklift" / "loading_corner.png"
FUNNEL_TEXTURE_PATH = ASSETS_DIR / "forklift" / "funnel.png"
FONT_PATH = ASSETS_DIR / "fonts" / "ui_bold.ttf"


def _load_ui_font(size: int) -> pygame.font.Font:
    """Load the bundled TrueType bold UI font (consistent across WebAssembly and desktop)."""
    if FONT_PATH.is_file():
        return pygame.font.Font(str(FONT_PATH), size)
    return pygame.font.SysFont("segoeui,consolas,arial", size, bold=True)


def _fmt_money(val: int) -> str:
    return f"-${abs(val):,}" if val < 0 else f"${val:,}"


def _extract_clean_frame(
    sheet: pygame.Surface,
    rect: tuple[int, int, int, int],
    clear_top_left: tuple[int, int] | None = None,
) -> pygame.Surface:
    """Crop one frame and flood-fill exterior near-white background to alpha=0."""
    x0, y0, w, h = rect
    sub = pygame.Surface((w, h), pygame.SRCALPHA)
    sub.blit(sheet, (0, 0), rect)

    if clear_top_left is not None:
        cw, ch = clear_top_left
        pygame.draw.rect(sub, (255, 255, 255, 255), (0, 0, min(cw, w), min(ch, h)))

    visited = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()

    def is_bg_white(px: int, py: int) -> bool:
        r, g, b, _ = sub.get_at((px, py))
        return r >= 218 and g >= 218 and b >= 218

    for x in range(w):
        for y in (0, h - 1):
            idx = y * w + x
            if not visited[idx] and is_bg_white(x, y):
                visited[idx] = 1
                q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            idx = y * w + x
            if not visited[idx] and is_bg_white(x, y):
                visited[idx] = 1
                q.append((x, y))

    while q:
        cx, cy = q.popleft()
        sub.set_at((cx, cy), (0, 0, 0, 0))
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                nidx = ny * w + nx
                if not visited[nidx] and is_bg_white(nx, ny):
                    visited[nidx] = 1
                    q.append((nx, ny))

    bbox = sub.get_bounding_rect(min_alpha=12)
    if bbox.width == 0 or bbox.height == 0:
        return sub
    return sub.subsurface(bbox).copy()


def _extract_cheque_cell(
    sheet: pygame.Surface, rect: tuple[int, int, int, int]
) -> pygame.Surface:
    """Strip the neutral grey checkerboard around one cheque or pileup sprite."""
    x0, y0, w, h = rect
    sub = pygame.Surface((w, h), pygame.SRCALPHA)
    sub.blit(sheet, (0, 0), rect)
    visited = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()

    def is_bg(px: int, py: int) -> bool:
        r, g, b, _ = sub.get_at((px, py))
        return (
            95 <= min(r, g, b)
            and max(r, g, b) <= 225
            and (max(r, g, b) - min(r, g, b)) <= 24
        )

    for x in range(w):
        for y in (0, 1, h - 2, h - 1):
            idx = y * w + x
            if not visited[idx] and is_bg(x, y):
                visited[idx] = 1
                q.append((x, y))
    for y in range(h):
        for x in (0, 1, w - 2, w - 1):
            idx = y * w + x
            if not visited[idx] and is_bg(x, y):
                visited[idx] = 1
                q.append((x, y))

    while q:
        cx, cy = q.popleft()
        sub.set_at((cx, cy), (0, 0, 0, 0))
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                nidx = ny * w + nx
                if not visited[nidx] and is_bg(nx, ny):
                    visited[nidx] = 1
                    q.append((nx, ny))

    bbox = sub.get_bounding_rect(min_alpha=10)
    return sub.subsurface(bbox).copy() if bbox.width > 0 else sub


def _scale_to_height(surf: pygame.Surface, target_h: int) -> pygame.Surface:
    w, h = surf.get_size()
    new_w = max(6, int(round(w * (target_h / max(1, h)))))
    return pygame.transform.scale(surf, (new_w, max(6, target_h)))


def _scale_to_width(surf: pygame.Surface, target_w: int) -> pygame.Surface:
    w, h = surf.get_size()
    new_h = max(6, int(round(h * (target_w / max(1, w)))))
    return pygame.transform.scale(surf, (max(6, target_w), new_h))


@dataclass
class ThiefSprites:
    """Animated right/left character sprites sliced from thief_spritesheet.jpg."""

    anims_right: dict[str, list[pygame.Surface]]
    anims_left: dict[str, list[pygame.Surface]]
    portrait_hud: pygame.Surface
    portrait_story: pygame.Surface

    @classmethod
    def load(cls, path: Path | None = None, sprite_height: int = 58) -> ThiefSprites:
        sheet = pygame.image.load(str(path or SPRITESHEET_PATH))
        specs: dict[
            str, list[tuple[tuple[int, int, int, int], tuple[int, int] | None]]
        ] = {
            "idle": [
                ((85, 44, 160, 266), (70, 25)),
                ((318, 44, 174, 266), None),
                ((552, 44, 170, 266), None),
                ((785, 44, 172, 266), None),
            ],
            "walk": [
                ((18, 338, 164, 206), (115, 8)),
                ((186, 334, 164, 209), None),
                ((352, 334, 162, 209), None),
                ((518, 334, 162, 209), None),
                ((680, 334, 162, 209), None),
                ((842, 334, 162, 209), None),
            ],
            "jump": [
                ((185, 546, 158, 236), None),
                ((370, 546, 182, 236), None),
                ((558, 546, 184, 236), None),
                ((748, 546, 158, 236), None),
            ],
            "action": [
                ((80, 780, 234, 242), (85, 32)),
                ((315, 782, 176, 240), None),
                ((538, 782, 202, 240), None),
                ((780, 782, 198, 240), None),
            ],
        }

        raw_frames: dict[str, list[pygame.Surface]] = {}
        anims_right: dict[str, list[pygame.Surface]] = {}
        anims_left: dict[str, list[pygame.Surface]] = {}

        for name, frame_list in specs.items():
            raw_frames[name] = []
            anims_right[name] = []
            anims_left[name] = []
            for rect, clear_tl in frame_list:
                clean = _extract_clean_frame(sheet, rect, clear_tl)
                raw_frames[name].append(clean)
                scaled = _scale_to_height(clean, sprite_height)
                anims_right[name].append(scaled)
                anims_left[name].append(pygame.transform.flip(scaled, True, False))

        portrait_hud = _scale_to_height(raw_frames["idle"][0], 48)
        portrait_story = _scale_to_height(raw_frames["action"][0], 132)
        return cls(
            anims_right=anims_right,
            anims_left=anims_left,
            portrait_hud=portrait_hud,
            portrait_story=portrait_story,
        )

    def get_frame(
        self, anim_state: str, anim_time: float, facing_left: bool
    ) -> pygame.Surface:
        bank = self.anims_left if facing_left else self.anims_right
        if anim_state == "crowbar":
            return bank["action"][0]
        if anim_state == "shock":
            return bank["action"][1]
        if anim_state == "place":
            return bank["action"][2]
        if anim_state == "sprint":
            seq = [bank["action"][3], bank["walk"][1], bank["walk"][3], bank["walk"][5]]
            return seq[int(anim_time * 12) % len(seq)]
        if anim_state == "walk":
            frames = bank["walk"]
            return frames[int(anim_time * 10) % len(frames)]
        if anim_state == "jump":
            frames = bank["jump"]
            return frames[int(anim_time * 9) % len(frames)]
        frames = bank["idle"]
        return frames[int(anim_time * 3.5) % len(frames)]


@dataclass
class ForkliftSprites:
    """Right/left animated forklift frames sliced from assets/forklift/spritesheet.png."""

    frames_right: list[pygame.Surface]
    frames_left: list[pygame.Surface]

    @classmethod
    def load(cls, path: Path | None = None, sprite_height: int = 68) -> ForkliftSprites:
        sheet = pygame.image.load(str(path or FORKLIFT_SHEET_PATH))
        cells = ((0, 0), (1, 0), (2, 0), (3, 0), (0, 1), (1, 1))
        frames_right: list[pygame.Surface] = []
        frames_left: list[pygame.Surface] = []
        for col_idx, row_idx in cells:
            crop = pygame.Surface((204, 124), pygame.SRCALPHA)
            crop.blit(sheet, (0, 0), (col_idx * 256 + 32, row_idx * 256 + 59, 204, 124))
            scaled = _scale_to_height(crop, sprite_height)
            frames_right.append(scaled)
            frames_left.append(pygame.transform.flip(scaled, True, False))
        return cls(frames_right=frames_right, frames_left=frames_left)

    def get_frame(
        self, anim_time: float, facing_left: bool, moving: bool, load_state: int = 0
    ) -> pygame.Surface:
        bank = self.frames_left if facing_left else self.frames_right
        base = 4 if load_state >= 2 else (2 if load_state == 1 else 0)
        offset = (int(anim_time * 10) % 2) if moving else 0
        idx = min(len(bank) - 1, base + offset)
        return bank[idx]


@dataclass
class ChequeSprites:
    """Single, stacked, pileup, VOID/FAKE, and giant mountain sprites from cheque_variations.jpg."""

    singles: dict[str, pygame.Surface]
    stacks: list[pygame.Surface]
    small_piles: list[pygame.Surface]
    large_piles: list[pygame.Surface]
    void_piles: list[pygame.Surface]
    fake_piles: list[pygame.Surface]
    mountains: list[pygame.Surface]
    _scaled_cache: dict[tuple[int, int], pygame.Surface]

    @classmethod
    def load(cls, path: Path | None = None) -> ChequeSprites:
        sheet = pygame.image.load(str(path or CHEQUESHEET_PATH))
        cols = [
            (139, 258),
            (262, 383),
            (388, 509),
            (514, 635),
            (640, 759),
            (763, 888),
            (892, 1020),
        ]
        rows = [(55, 118), (122, 186), (191, 276), (281, 355)]
        mountains_rects = [
            (18, 362, 262, 194),
            (302, 362, 256, 194),
            (576, 362, 204, 194),
            (804, 362, 206, 194),
        ]

        grid: list[list[pygame.Surface]] = []
        for y0, y1 in rows:
            row_surfs = [
                _extract_cheque_cell(sheet, (x0, y0, x1 - x0, y1 - y0))
                for x0, x1 in cols
            ]
            grid.append(row_surfs)

        singles = {
            "payroll": grid[0][2],
            "rent": grid[0][1],
            "vip": grid[0][0],
            "mortgage": grid[0][3],
            "void": grid[3][0],
            "fake": grid[3][4],
        }
        stacks = [grid[0][5], grid[0][6]]
        small_piles = [grid[1][4], grid[1][5], grid[1][6], grid[1][0], grid[1][2]]
        large_piles = list(grid[2])
        void_piles = [grid[3][2], grid[3][3]]
        fake_piles = [grid[3][5], grid[3][6]]
        mountains = [_extract_cheque_cell(sheet, r) for r in mountains_rects]

        return cls(
            singles=singles,
            stacks=stacks,
            small_piles=small_piles,
            large_piles=large_piles,
            void_piles=void_piles,
            fake_piles=fake_piles,
            mountains=mountains,
            _scaled_cache={},
        )

    def get_scaled(self, raw: pygame.Surface, width: int) -> pygame.Surface:
        w = max(8, width)
        key = (id(raw), w)
        if key not in self._scaled_cache:
            self._scaled_cache[key] = _scale_to_width(raw, w)
        return self._scaled_cache[key]

    def pick_pile_surface(
        self, tier: int, kind: str, variant: int, width: int
    ) -> pygame.Surface:
        if tier >= 3:
            if kind == "void":
                raw = self.mountains[1]
            elif kind == "fake":
                raw = self.mountains[3]
            elif kind == "mixed":
                raw = self.mountains[2]
            else:
                raw = self.mountains[0]
        elif tier == 2:
            if kind == "void":
                raw = self.void_piles[variant % len(self.void_piles)]
            elif kind == "fake":
                raw = self.fake_piles[variant % len(self.fake_piles)]
            else:
                raw = self.large_piles[variant % len(self.large_piles)]
        else:
            if kind == "void":
                raw = self.void_piles[0]
            elif kind == "fake":
                raw = self.fake_piles[0]
            else:
                raw = self.small_piles[variant % len(self.small_piles)]
        return self.get_scaled(raw, width)


class IndustrialTileSet:
    """Procedural 90-degree top-down industrial factory textures at 48x48 base resolution."""

    def __init__(self, size: int = TILE_SIZE) -> None:
        self.s = size
        self.floors: dict[tuple[str, int], pygame.Surface] = {}
        self.decals: dict[str, pygame.Surface] = {}
        self.walls: dict[int, pygame.Surface] = {}
        self.fences: dict[int, pygame.Surface] = {}
        self.pillar = self._make_pillar()
        self.grate = self._make_grate()
        self.window = self._make_window()
        self.door_open = self._make_door(is_open=True)
        self.door_closed = self._make_door(is_open=False)
        self.door_frame_overlay = self._make_door_frame_overlay()
        self._scaled_cache: dict[tuple[int, int], pygame.Surface] = {}

        self._build_floors()
        self._build_decals()
        for mask in range(16):
            self.walls[mask] = self._make_wall(mask)
            self.fences[mask] = self._make_fence(mask)

    def scaled(self, surf: pygame.Surface, ts: int) -> pygame.Surface:
        if ts == self.s:
            return surf
        key = (id(surf), ts)
        if key not in self._scaled_cache:
            self._scaled_cache[key] = pygame.transform.scale(surf, (ts, ts))
        return self._scaled_cache[key]

    def _base_concrete(
        self, base_rgb: tuple[int, int, int], seed: int
    ) -> pygame.Surface:
        s = self.s
        surf = pygame.Surface((s, s))
        surf.fill(base_rgb)
        r, g, b = base_rgb
        # Concrete micro-grain & subtle slab bevel seams.
        for i in range(44):
            px = ((i * 37 + seed * 17) % (s - 4)) + 2
            py = ((i * 53 + seed * 29) % (s - 4)) + 2
            delta = -8 if (i + seed) % 3 == 0 else 7
            col = (
                max(0, min(255, r + delta)),
                max(0, min(255, g + delta)),
                max(0, min(255, b + delta)),
            )
            surf.fill(col, (px, py, 2, 2))
        pygame.draw.line(surf, (r + 14, g + 14, b + 14), (0, 0), (s - 1, 0), 1)
        pygame.draw.line(surf, (r + 14, g + 14, b + 14), (0, 0), (0, s - 1), 1)
        pygame.draw.line(surf, (r - 24, g - 24, b - 24), (0, s - 1), (s - 1, s - 1), 1)
        pygame.draw.line(surf, (r - 24, g - 24, b - 24), (s - 1, 0), (s - 1, s - 1), 1)
        # Corner expansion pin dots
        for rx, ry in ((4, 4), (s - 6, 4), (4, s - 6), (s - 6, s - 6)):
            surf.fill((r - 20, g - 20, b - 18), (rx, ry, 2, 2))
        return surf

    def _build_floors(self) -> None:
        s = self.s
        for idx in range(4):
            tint = ((132, 138, 145), (128, 134, 142), (136, 141, 148), (125, 132, 139))[
                idx
            ]
            self.floors[("clean", idx)] = self._base_concrete(tint, idx + 1)

        for idx in range(4):
            dirty = self._base_concrete((98, 103, 110), idx + 10)
            # Sooty industrial grime smudges + scuff tracks
            grime = pygame.Surface((s, s), pygame.SRCALPHA)
            pygame.draw.ellipse(
                grime, (48, 50, 56, 72), (6 + (idx * 5) % 14, 10, 26, 18)
            )
            pygame.draw.ellipse(
                grime, (64, 60, 52, 56), (14, 24 - (idx * 3) % 10, 24, 14)
            )
            dirty.blit(grime, (0, 0))
            self.floors[("dirty", idx)] = dirty

        for idx in range(4):
            crk = self._base_concrete((118, 124, 131), idx + 20)
            pts = (
                [(6, 8), (16, 15), (24, 14), (35, 25), (42, 28)]
                if idx % 2 == 0
                else [(40, 8), (30, 18), (22, 22), (18, 34), (10, 42)]
            )
            pygame.draw.lines(
                crk, (150, 156, 162), False, [(p[0] + 1, p[1] + 1) for p in pts], 2
            )
            pygame.draw.lines(crk, (46, 50, 56), False, pts, 2)
            pygame.draw.line(
                crk, (46, 50, 56), pts[2], (pts[2][0] + 6, pts[2][1] - 9), 1
            )
            self.floors[("cracked", idx)] = crk

        for idx in range(4):
            haz = self._base_concrete((112, 116, 122), idx + 30)
            # Crisp yellow/black safety caution stripes along border.
            stripe_surf = pygame.Surface((s, s), pygame.SRCALPHA)
            for offset in range(-s, s * 2, 12):
                pygame.draw.polygon(
                    stripe_surf,
                    (226, 178, 42, 210),
                    [
                        (offset, 0),
                        (offset + 6, 0),
                        (offset + 6 - s, s),
                        (offset - s, s),
                    ],
                )
            # Keep center readable so belts stand out clearly over hazard tiles.
            inner = pygame.Rect(6, 6, s - 12, s - 12)
            pygame.draw.rect(haz, (40, 44, 52), (0, 0, s, s))
            haz.blit(stripe_surf, (0, 0))
            center_tile = self._base_concrete((114, 119, 126), idx + 40)
            haz.blit(center_tile, inner.topleft, inner)
            pygame.draw.rect(haz, (40, 44, 52), inner, 1)
            self.floors[("hazard", idx)] = haz

    def _build_decals(self) -> None:
        s = self.s
        # Oil stain (glossy dark slick with sheen)
        oil = pygame.Surface((s, s), pygame.SRCALPHA)
        pygame.draw.ellipse(oil, (20, 22, 28, 220), (6, 12, 34, 24))
        pygame.draw.ellipse(oil, (26, 28, 34, 210), (14, 8, 22, 28))
        pygame.draw.arc(oil, (82, 108, 134, 170), (12, 14, 18, 12), 0.2, 2.2, 2)
        pygame.draw.circle(oil, (112, 82, 136, 140), (26, 24), 4)
        self.decals["oil"] = oil

        # Water puddle (translucent pooling water)
        pud = pygame.Surface((s, s), pygame.SRCALPHA)
        pygame.draw.ellipse(pud, (66, 118, 166, 145), (8, 10, 32, 24))
        pygame.draw.ellipse(pud, (94, 148, 198, 120), (12, 13, 22, 16))
        pygame.draw.line(pud, (186, 224, 250, 185), (15, 16), (25, 16), 2)
        self.decals["puddle"] = pud

        # Scattered paper & rubbish
        rub = pygame.Surface((s, s), pygame.SRCALPHA)
        for rx, ry, col in (
            (8, 10, (226, 224, 210)),
            (26, 18, (196, 218, 232)),
            (14, 30, (216, 228, 198)),
            (31, 32, (208, 194, 172)),
        ):
            pygame.draw.rect(rub, (36, 40, 48, 220), (rx - 1, ry - 1, 10, 7))
            pygame.draw.rect(rub, col, (rx, ry, 8, 5))
            pygame.draw.line(
                rub, (110, 114, 122), (rx + 2, ry + 2), (rx + 6, ry + 2), 1
            )
        pygame.draw.circle(rub, (164, 72, 68, 225), (22, 11), 3)
        self.decals["rubbish"] = rub

        # Recessed floor drain
        drn = pygame.Surface((s, s), pygame.SRCALPHA)
        box = pygame.Rect(10, 10, s - 20, s - 20)
        pygame.draw.rect(drn, (58, 64, 74), box, border_radius=4)
        pygame.draw.rect(drn, (108, 116, 128), box, width=2, border_radius=4)
        for sx in range(14, s - 13, 4):
            pygame.draw.line(drn, (22, 26, 32), (sx, 14), (sx, s - 15), 2)
        self.decals["drain"] = drn

    def _make_wall(self, mask: int) -> pygame.Surface:
        s = self.s
        surf = pygame.Surface((s, s))
        # Cast concrete wall top cap (90 deg top-down).
        surf.fill((68, 74, 86))
        top_n, east, south, west = mask & 1, mask & 2, mask & 4, mask & 8
        # Inner concrete surface
        pygame.draw.rect(surf, (86, 94, 108), (4, 4, s - 8, s - 8))
        # Dark outer bevels only on exposed faces
        if not top_n:
            pygame.draw.rect(surf, (32, 36, 44), (0, 0, s, 4))
            pygame.draw.line(surf, (124, 134, 150), (3, 4), (s - 4, 4), 2)
        if not south:
            pygame.draw.rect(surf, (28, 32, 40), (0, s - 5, s, 5))
        if not west:
            pygame.draw.rect(surf, (32, 36, 44), (0, 0, 4, s))
            pygame.draw.line(surf, (124, 134, 150), (4, 3), (4, s - 5), 2)
        if not east:
            pygame.draw.rect(surf, (28, 32, 40), (s - 5, 0, 5, s))
        # Structural corner/T-junction steel plate cap if intersection or corner
        neighbors = sum(bool(mask & b) for b in (1, 2, 4, 8))
        if neighbors != 2 or (
            (top_n and east) or (top_n and west) or (south and east) or (south and west)
        ):
            cap = pygame.Rect(s // 2 - 7, s // 2 - 7, 14, 14)
            pygame.draw.rect(surf, (62, 68, 80), cap, border_radius=2)
            pygame.draw.rect(surf, (112, 122, 138), cap, width=1, border_radius=2)
        return surf

    def _make_fence(self, mask: int) -> pygame.Surface:
        s = self.s
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        cx, cy = s // 2, s // 2
        # Soft ground shadow under rail
        if mask & 2 or mask & 8 or mask == 0:
            x0 = 0 if (mask & 8) else cx - 8
            x1 = s if (mask & 2) else cx + 8
            pygame.draw.line(surf, (20, 24, 32, 110), (x0, cy + 4), (x1, cy + 4), 7)
            pygame.draw.line(surf, (40, 44, 52), (x0, cy), (x1, cy), 7)
            pygame.draw.line(surf, (232, 186, 46), (x0, cy), (x1, cy), 3)
        if mask & 1 or mask & 4:
            y0 = 0 if (mask & 1) else cy - 8
            y1 = s if (mask & 4) else cy + 8
            pygame.draw.line(surf, (20, 24, 32, 110), (cx + 4, y0), (cx + 4, y1), 7)
            pygame.draw.line(surf, (40, 44, 52), (cx, y0), (cx, y1), 7)
            pygame.draw.line(surf, (232, 186, 46), (cx, y0), (cx, y1), 3)
        # Center stanchion bracket
        pygame.draw.circle(surf, (44, 48, 56), (cx, cy), 6)
        pygame.draw.circle(surf, (156, 166, 182), (cx, cy), 4)
        return surf

    def _make_pillar(self) -> pygame.Surface:
        s = self.s
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        # Drop shadow
        pygame.draw.rect(
            surf, (18, 22, 30, 120), (8, 8, s - 10, s - 10), border_radius=4
        )
        base = pygame.Rect(4, 4, s - 8, s - 8)
        pygame.draw.rect(surf, (62, 68, 80), base, border_radius=4)
        pygame.draw.rect(surf, (32, 36, 44), base, width=2, border_radius=4)
        # Yellow safety bumper corners
        for bx, by in (
            (5, 5),
            (s - 12, 5),
            (5, s - 12),
            (s - 12, s - 12),
        ):
            pygame.draw.rect(surf, (226, 182, 46), (bx, by, 7, 7))
        # Steel H-beam cap in center
        beam = pygame.Rect(11, 11, s - 22, s - 22)
        pygame.draw.rect(surf, (108, 118, 134), beam, border_radius=2)
        pygame.draw.rect(surf, (156, 168, 186), beam, width=2, border_radius=2)
        pygame.draw.line(
            surf,
            (48, 54, 66),
            (beam.centerx, beam.top + 3),
            (beam.centerx, beam.bottom - 4),
            4,
        )
        return surf

    def _make_grate(self) -> pygame.Surface:
        s = self.s
        surf = pygame.Surface((s, s))
        surf.fill((16, 20, 26))
        pygame.draw.rect(surf, (198, 152, 40), (0, 0, s, s), 3)
        for p in range(6, s - 4, 7):
            pygame.draw.line(surf, (84, 94, 108), (p, 4), (p, s - 5), 2)
            pygame.draw.line(surf, (118, 130, 146), (p, 4), (p, s - 5), 1)
            pygame.draw.line(surf, (66, 74, 86), (4, p), (s - 5, p), 2)
        return surf

    def _make_window(self) -> pygame.Surface:
        s = self.s
        surf = self._make_wall(2 | 8)
        # Recessed sky-blue window glass in the center of the exterior wall
        glass = pygame.Rect(5, 10, s - 10, s - 20)
        pygame.draw.rect(surf, (36, 44, 56), glass.inflate(4, 4))
        pygame.draw.rect(surf, (156, 212, 246), glass)
        pygame.draw.line(
            surf,
            (218, 244, 255),
            (glass.left + 3, glass.top + 3),
            (glass.right - 4, glass.top + 3),
            2,
        )
        pygame.draw.line(
            surf,
            (56, 66, 80),
            (glass.centerx, glass.top),
            (glass.centerx, glass.bottom),
            3,
        )
        return surf

    def _make_door(self, is_open: bool) -> pygame.Surface:
        s = self.s
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        # Concrete threshold frame N & S
        pygame.draw.rect(surf, (78, 86, 98), (0, 0, s, 8))
        pygame.draw.rect(surf, (78, 86, 98), (0, s - 8, s, 8))
        if is_open:
            pygame.draw.rect(surf, (46, 52, 62), (0, 2, s, 8))
            pygame.draw.rect(surf, (46, 52, 62), (0, s - 10, s, 8))
            pygame.draw.circle(surf, (82, 236, 128), (s // 2, 5), 3)
        else:
            slab = pygame.Rect(6, 7, s - 12, s - 14)
            pygame.draw.rect(surf, (92, 100, 114), slab, border_radius=3)
            pygame.draw.rect(surf, (32, 36, 44), slab, width=2, border_radius=3)
            # Warning stripe down center + red locked LED
            pygame.draw.line(
                surf,
                (230, 182, 42),
                (slab.centerx, slab.top + 4),
                (slab.centerx, slab.bottom - 4),
                4,
            )
            pygame.draw.circle(surf, (242, 72, 72), (slab.centerx, 5), 3)
        return surf

    def _make_door_frame_overlay(self) -> pygame.Surface:
        s = self.s
        surf = pygame.Surface((s, s), pygame.SRCALPHA)
        pygame.draw.rect(surf, (48, 54, 64), (0, 0, s, 6))
        pygame.draw.rect(surf, (48, 54, 64), (0, s - 6, s, 6))
        pygame.draw.circle(surf, (82, 236, 128), (s // 2, 3), 2)
        return surf


class FactoryRenderer:
    """Renders the neglected industrial factory, lighting, real cheques, thief, and HUD."""

    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        sprites: ThiefSprites,
        cheque_sprites: ChequeSprites,
        forklift_sprites: ForkliftSprites | None = None,
    ) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.sprites = sprites
        self.cheque_sprites = cheque_sprites
        self.forklift_sprites = (
            forklift_sprites if forklift_sprites is not None else ForkliftSprites.load()
        )
        raw_crate = pygame.image.load(str(CRATE_TEXTURE_PATH))
        crate_bbox = raw_crate.get_bounding_rect(min_alpha=12)
        self.crate_texture = (
            raw_crate.subsurface(crate_bbox).copy()
            if crate_bbox.width > 0 and crate_bbox.height > 0
            else raw_crate
        )
        self._crate_scaled_cache: dict[tuple[int, int], pygame.Surface] = {}
        self.loading_corner_textures: list[pygame.Surface] = []
        self._loading_corner_cache: dict[tuple[int, int], pygame.Surface] = {}
        if LOADING_CORNER_PATH.is_file():
            base_lc = pygame.image.load(str(LOADING_CORNER_PATH))
            for deg in (0, -90, 180, 90):
                self.loading_corner_textures.append(
                    pygame.transform.rotate(base_lc, deg)
                )
        self.funnel_textures: list[pygame.Surface] = []
        self._funnel_cache: dict[tuple[int, int, int], pygame.Surface] = {}
        if FUNNEL_TEXTURE_PATH.is_file():
            base_fn = pygame.image.load(str(FUNNEL_TEXTURE_PATH))
            for deg in (90, 0, -90, 180):
                self.funnel_textures.append(pygame.transform.rotate(base_fn, deg))
        self.tileset = IndustrialTileSet(TILE_SIZE)

        self.zoom = 1.0
        self.follow_player = True
        self.cam_offset_x = 0.0
        self.cam_offset_y = 0.0
        self.reset_camera(30, 18, 6.5, 6.5)

        self.title_font = _load_ui_font(21)
        self.label_font = _load_ui_font(17)
        self.slot_font = _load_ui_font(16)
        self.small_font = _load_ui_font(15)
        self.mini_font = _load_ui_font(13)
        self.big_font = _load_ui_font(30)

        self.hotbar_rects: list[pygame.Rect] = []
        self.hotbar_tool_indices: list[int] = []
        self.hotbar_prev_rect = pygame.Rect(0, 0, 0, 0)
        self.hotbar_next_rect = pygame.Rect(0, 0, 0, 0)
        self.shop_card_rects: list[pygame.Rect] = []
        self.shop_upgrade_rects: list[pygame.Rect] = []
        self.shop_btn_rect = pygame.Rect(0, 0, 0, 0)
        self.shop_close_rect = pygame.Rect(0, 0, 0, 0)
        self.modal_btn_rect = pygame.Rect(0, 0, 0, 0)
        self.speed_btn_rect = pygame.Rect(0, 0, 0, 0)
        self.reset_btn_rect = pygame.Rect(0, 0, 0, 0)
        self.reset_confirm_yes_rect = pygame.Rect(0, 0, 0, 0)
        self.reset_confirm_no_rect = pygame.Rect(0, 0, 0, 0)
        self.hide_all_popups = False
        self.show_floating_popups = True
        self.show_world_prompts = True
        self.show_pile_bag_labels = True
        self.settings_btn_rect = pygame.Rect(0, 0, 0, 0)
        self.settings_close_rect = pygame.Rect(0, 0, 0, 0)
        self.settings_toggle_rects: dict[str, pygame.Rect] = {}
        self.settings_music_minus_rect = pygame.Rect(0, 0, 0, 0)
        self.settings_music_plus_rect = pygame.Rect(0, 0, 0, 0)
        self.settings_sfx_minus_rect = pygame.Rect(0, 0, 0, 0)
        self.settings_sfx_plus_rect = pygame.Rect(0, 0, 0, 0)
        self.settings_mute_rect = pygame.Rect(0, 0, 0, 0)
        self.part_menu_upgrade_rect = pygame.Rect(0, 0, 0, 0)
        self.part_menu_straight_rect = pygame.Rect(0, 0, 0, 0)
        self.part_menu_branch_rect = pygame.Rect(0, 0, 0, 0)
        self.part_menu_rotate_rect = pygame.Rect(0, 0, 0, 0)
        self.part_menu_delete_rect = pygame.Rect(0, 0, 0, 0)
        self.show_minimap = True
        self.minimap_rect = pygame.Rect(screen_width - 190, 114, 178, 108)
        self._shake_px: tuple[int, int] = (0, 0)
        self._light_surf = pygame.Surface((screen_width // 4, screen_height // 4))

    def reset_camera(
        self,
        cols: int,
        rows: int,
        player_x: float | None = None,
        player_y: float | None = None,
    ) -> None:
        """Center camera on the player (or grid center) and re-enable smooth follow."""
        self.zoom = 1.0
        self.follow_player = True
        play_top = 92
        play_h = self.screen_height - play_top - 84
        tx = player_x if player_x is not None else cols * 0.5
        ty = player_y if player_y is not None else rows * 0.5
        self.cam_offset_x = self.screen_width * 0.5 - tx * TILE_SIZE * self.zoom
        self.cam_offset_y = (play_top + play_h * 0.5) - ty * TILE_SIZE * self.zoom
        self._clamp_camera(cols, rows)

    def _clamp_camera(self, cols: int, rows: int) -> None:
        play_top = 92
        play_h = self.screen_height - play_top - 84
        world_w = cols * TILE_SIZE * self.zoom
        world_h = rows * TILE_SIZE * self.zoom
        margin = 64
        if world_w + margin * 2 <= self.screen_width:
            self.cam_offset_x = (self.screen_width - world_w) * 0.5
        else:
            min_x = self.screen_width - world_w - margin
            max_x = margin
            self.cam_offset_x = max(min_x, min(max_x, self.cam_offset_x))
        if world_h + margin * 2 <= play_h:
            self.cam_offset_y = play_top + (play_h - world_h) * 0.5
        else:
            min_y = (play_top + play_h) - world_h - margin
            max_y = play_top + margin
            self.cam_offset_y = max(min_y, min(max_y, self.cam_offset_y))

    def update_camera(self, world: FactoryWorld, dt: float) -> None:
        if not self.follow_player:
            return
        play_top = 92
        play_h = self.screen_height - play_top - 84
        target_x = self.screen_width * 0.5 - world.player_x * TILE_SIZE * self.zoom
        target_y = (play_top + play_h * 0.5) - world.player_y * TILE_SIZE * self.zoom
        blend = min(1.0, dt * 7.5)
        self.cam_offset_x += (target_x - self.cam_offset_x) * blend
        self.cam_offset_y += (target_y - self.cam_offset_y) * blend
        self._clamp_camera(world.cols, world.rows)

    def pan(self, dx: float, dy: float) -> None:
        self.follow_player = False
        self.cam_offset_x += dx
        self.cam_offset_y += dy

    def zoom_at(self, factor: float, anchor: tuple[int, int]) -> None:
        old_zoom = self.zoom
        new_zoom = max(0.38, min(1.85, old_zoom * factor))
        if abs(new_zoom - old_zoom) < 1e-4:
            return
        wx = (anchor[0] - self.cam_offset_x) / old_zoom
        wy = (anchor[1] - self.cam_offset_y) / old_zoom
        self.zoom = new_zoom
        self.cam_offset_x = anchor[0] - wx * new_zoom
        self.cam_offset_y = anchor[1] - wy * new_zoom

    def tile_to_screen(self, tx: float, ty: float) -> tuple[int, int]:
        sx = (
            int(round(self.cam_offset_x + tx * TILE_SIZE * self.zoom))
            + self._shake_px[0]
        )
        sy = (
            int(round(self.cam_offset_y + ty * TILE_SIZE * self.zoom))
            + self._shake_px[1]
        )
        return sx, sy

    def screen_to_tile(self, sx: int, sy: int) -> tuple[int, int]:
        tx = (sx - self.cam_offset_x) / (TILE_SIZE * self.zoom)
        ty = (sy - self.cam_offset_y) / (TILE_SIZE * self.zoom)
        return int(math.floor(tx)), int(math.floor(ty))

    def minimap_to_world(
        self, sx: int, sy: int, cols: int, rows: int
    ) -> tuple[float, float] | None:
        if not self.show_minimap or not self.minimap_rect.collidepoint((sx, sy)):
            return None
        wx = ((sx - self.minimap_rect.left) / max(1, self.minimap_rect.width)) * cols
        wy = ((sy - self.minimap_rect.top) / max(1, self.minimap_rect.height)) * rows
        return max(0.0, min(float(cols), wx)), max(0.0, min(float(rows), wy))

    def center_camera_at(self, wx: float, wy: float, cols: int, rows: int) -> None:
        self.follow_player = False
        play_top = 92
        play_h = self.screen_height - play_top - 84
        self.cam_offset_x = self.screen_width * 0.5 - wx * TILE_SIZE * self.zoom
        self.cam_offset_y = (play_top + play_h * 0.5) - wy * TILE_SIZE * self.zoom
        self._clamp_camera(cols, rows)

    def draw(
        self,
        screen: pygame.Surface,
        world: FactoryWorld,
        selected_tool: int | None,
        build_dir: int,
        filter_color: str,
        hover_tile: tuple[int, int] | None,
        show_story: bool,
        keep_playing: bool = False,
        show_shop: bool = False,
        muted: bool = False,
        part_menu_tile: tuple[int, int] | None = None,
        part_menu_pos: tuple[int, int] = (0, 0),
        hotbar_page: int = 0,
    ) -> None:
        if world.screen_shake > 0.0:
            self._shake_px = (
                int(round(math.sin(world.anim_time * 58.0) * 7.0 * world.screen_shake)),
                int(round(math.cos(world.anim_time * 47.0) * 6.0 * world.screen_shake)),
            )
        else:
            self._shake_px = (0, 0)

        screen.fill((20, 24, 32))
        self._draw_floor_and_structures(screen, world)
        self._draw_cheques(screen, world)
        self._draw_pileups(screen, world)
        self._draw_window_beams(screen, world)
        self._draw_forklifts(screen, world)
        self._draw_player(screen, world)
        self._draw_lighting(screen, world)
        self._draw_particles(screen, world)
        self._draw_drone(screen, world)

        show_end = (world.level_complete or world.level_failed) and not keep_playing
        if not show_story and not show_end and not show_shop:
            self._draw_hover_preview(
                screen, world, hover_tile, selected_tool, build_dir, filter_color
            )
            if not getattr(self, "hide_all_popups", False) and getattr(
                self, "show_world_prompts", True
            ):
                self._draw_interact_prompts(screen, world)
        if not getattr(self, "hide_all_popups", False) and getattr(
            self, "show_floating_popups", True
        ):
            self._draw_popups(screen, world)
        self._shake_px = (0, 0)

        if world.room_open_anim > 0.0:
            prog = 1.0 - max(0.0, min(1.0, world.room_open_anim / 1.65))
            cx, cy = self.tile_to_screen(world.room_open_col + 0.5, world.rows * 0.5)
            ring_r = max(12, int(24 + prog * 540 * self.zoom))
            pygame.draw.circle(
                screen,
                (96, 232, 255),
                (cx, cy),
                ring_r,
                width=max(2, int(5 * (1.0 - prog))),
            )
            if ring_r > 36:
                pygame.draw.circle(
                    screen, (255, 218, 92), (cx, cy), max(8, ring_r - 24), width=2
                )
            banner_txt = f"BULKHEAD BREACHED - ROOM {world.room_open_stage} ONLINE!"
            b_surf = self.title_font.render(banner_txt, True, (255, 234, 118))
            b_rect = b_surf.get_rect(center=(self.screen_width // 2, 116))
            pygame.draw.rect(
                screen, (16, 28, 44), b_rect.inflate(26, 12), border_radius=8
            )
            pygame.draw.rect(
                screen,
                (108, 236, 255),
                b_rect.inflate(26, 12),
                width=2,
                border_radius=8,
            )
            screen.blit(b_surf, b_rect.topleft)

        if not show_story and not show_shop and not show_end:
            self._draw_offscreen_indicators(screen, world)
            if self.show_minimap:
                self._draw_minimap(screen, world)

        self._draw_top_hud(screen, world)
        self._draw_mission_strip(screen, world)
        self._draw_hotbar(
            screen,
            world,
            selected_tool,
            build_dir,
            filter_color,
            show_shop=show_shop,
            muted=muted,
            hotbar_page=hotbar_page,
        )
        self._draw_part_menu(screen, world, part_menu_tile, part_menu_pos)

        if show_story:
            self._draw_story_modal(screen)
        elif show_shop:
            self._draw_shop_modal(screen, world, selected_tool, build_dir, filter_color)
        elif show_end:
            self._draw_end_modal(screen, world)

    def _draw_part_menu(
        self,
        screen: pygame.Surface,
        world: FactoryWorld,
        part_menu_tile: tuple[int, int] | None,
        part_menu_pos: tuple[int, int],
    ) -> None:
        self.part_menu_upgrade_rect = pygame.Rect(0, 0, 0, 0)
        self.part_menu_straight_rect = pygame.Rect(0, 0, 0, 0)
        self.part_menu_branch_rect = pygame.Rect(0, 0, 0, 0)
        self.part_menu_rotate_rect = pygame.Rect(0, 0, 0, 0)
        self.part_menu_delete_rect = pygame.Rect(0, 0, 0, 0)
        if part_menu_tile is None or not world.in_bounds(*part_menu_tile):
            return

        col, row = part_menu_tile
        tile = world.grid[row][col]
        panel = pygame.Rect(part_menu_pos[0] + 12, part_menu_pos[1] + 12, 210, 180)
        play_top = 90
        panel.clamp_ip(
            pygame.Rect(
                4,
                play_top + 4,
                self.screen_width - 8,
                self.screen_height - play_top - 8,
            )
        )
        pygame.draw.rect(screen, (18, 26, 40), panel, border_radius=7)
        pygame.draw.rect(screen, (104, 214, 242), panel, width=2, border_radius=7)
        title = self.small_font.render(tile.kind.upper(), True, (232, 248, 255))
        screen.blit(title, (panel.left + 10, panel.top + 8))

        self.part_menu_upgrade_rect = pygame.Rect(
            panel.left + 10, panel.top + 34, 190, 28
        )
        self.part_menu_rotate_rect = pygame.Rect(
            panel.left + 10, panel.top + 68, 92, 28
        )
        self.part_menu_delete_rect = pygame.Rect(
            panel.left + 108, panel.top + 68, 92, 28
        )
        upgrade_cost = world.machine_upgrade_cost(tile)
        upgrade_label = (
            f"UPGRADE ${upgrade_cost}"
            if upgrade_cost is not None
            else "MAX / NO UPGRADE"
        )
        self._draw_menu_button(
            screen, self.part_menu_upgrade_rect, upgrade_label, upgrade_cost is not None
        )

        if tile.kind == "splitter":
            straight = str(
                CHEQUE_TYPES.get(tile.splitter_straight_color, CHEQUE_TYPES["payroll"])[
                    "label"
                ]
            )
            branch = str(
                CHEQUE_TYPES.get(tile.splitter_branch_color, CHEQUE_TYPES["vip"])[
                    "label"
                ]
            )
            self.part_menu_straight_rect = pygame.Rect(
                panel.left + 10, panel.top + 68, 92, 28
            )
            self.part_menu_branch_rect = pygame.Rect(
                panel.left + 108, panel.top + 68, 92, 28
            )
            self._draw_menu_button(
                screen, self.part_menu_straight_rect, f"STRAIGHT {straight[:5]}", True
            )
            self._draw_menu_button(
                screen, self.part_menu_branch_rect, f"SIDE {branch[:5]}", True
            )
            rotate_y = panel.top + 102
        elif tile.kind == "sorter":
            branch = str(
                CHEQUE_TYPES.get(tile.sorter_branch_color, CHEQUE_TYPES["vip"])["label"]
            )
            self.part_menu_straight_rect = pygame.Rect(
                panel.left + 10, panel.top + 68, 92, 28
            )
            self.part_menu_branch_rect = pygame.Rect(
                panel.left + 108, panel.top + 68, 92, 28
            )
            self._draw_menu_button(
                screen, self.part_menu_straight_rect, "STRT: OTHER", False
            )
            self._draw_menu_button(
                screen, self.part_menu_branch_rect, f"SIDE: {branch[:5]}", True
            )
            rotate_y = panel.top + 102
        else:
            rotate_y = panel.top + 68

        self.part_menu_rotate_rect = pygame.Rect(panel.left + 10, rotate_y, 92, 28)
        self.part_menu_delete_rect = pygame.Rect(panel.left + 108, rotate_y, 92, 28)
        self._draw_menu_button(screen, self.part_menu_rotate_rect, "ROTATE", True)
        self._draw_menu_button(
            screen, self.part_menu_delete_rect, "DELETE", True, danger=True
        )

    def _draw_menu_button(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        enabled: bool,
        danger: bool = False,
    ) -> None:
        fill = (80, 46, 52) if danger else ((40, 82, 102) if enabled else (42, 48, 60))
        edge = (
            (226, 126, 132)
            if danger
            else ((112, 228, 250) if enabled else (90, 100, 116))
        )
        pygame.draw.rect(screen, fill, rect, border_radius=4)
        pygame.draw.rect(screen, edge, rect, width=1, border_radius=4)
        text = self.mini_font.render(label, True, (240, 246, 255))
        screen.blit(text, text.get_rect(center=rect.center).topleft)

    def _neighbor_mask(
        self, world: FactoryWorld, c: int, r: int, kinds: tuple[str, ...]
    ) -> int:
        mask = 0
        for bit, (dc, dr) in ((1, (0, -1)), (2, (1, 0)), (4, (0, 1)), (8, (-1, 0))):
            nc, nr = c + dc, r + dr
            if world.in_bounds(nc, nr) and world.grid[nr][nc].kind in kinds:
                mask |= bit
        return mask

    def _draw_floor_and_structures(
        self, screen: pygame.Surface, world: FactoryWorld
    ) -> None:
        ts = max(16, int(round(TILE_SIZE * self.zoom)))
        belt_rate = 32.0 * (1.0, 1.30, 1.60, 1.95)[world.upgrade_tier("turbo_belts")]
        anim_shift = (world.anim_time * belt_rate) % 16.0

        # Pass 1: concrete floor variants + decals + grates
        for row in range(world.rows):
            for col in range(world.cols):
                tile = world.grid[row][col]
                sx, sy = self.tile_to_screen(col, row)
                if (
                    sx + ts < 0
                    or sy + ts < 0
                    or sx > self.screen_width
                    or sy > self.screen_height
                ):
                    continue
                rect = pygame.Rect(sx, sy, ts, ts)

                if tile.kind == "void":
                    continue

                if tile.kind == "grate":
                    screen.blit(
                        self.tileset.scaled(self.tileset.grate, ts), rect.topleft
                    )
                else:
                    var_idx = (col * 5 + row * 11) % 4
                    floor_surf = self.tileset.floors.get(
                        (tile.floor_variant, var_idx), self.tileset.floors[("clean", 0)]
                    )
                    screen.blit(self.tileset.scaled(floor_surf, ts), rect.topleft)
                    if tile.decal != "none" and tile.decal in self.tileset.decals:
                        screen.blit(
                            self.tileset.scaled(self.tileset.decals[tile.decal], ts),
                            rect.topleft,
                        )
                    if tile.loading_corner >= 0 and tile.loading_corner < len(
                        self.loading_corner_textures
                    ):
                        lc_key = (tile.loading_corner, ts)
                        if lc_key not in self._loading_corner_cache:
                            self._loading_corner_cache[lc_key] = (
                                pygame.transform.smoothscale(
                                    self.loading_corner_textures[tile.loading_corner],
                                    (ts, ts),
                                )
                            )
                        screen.blit(self._loading_corner_cache[lc_key], rect.topleft)
                        if tile.loading_corner == 0:
                            emp_lbl = self.mini_font.render(
                                "CRATE EMPTIER", True, (255, 226, 128)
                            )
                            er = emp_lbl.get_rect(midbottom=(rect.right, rect.top - 2))
                            pygame.draw.rect(
                                screen, (22, 24, 30), er.inflate(6, 2), border_radius=3
                            )
                            screen.blit(emp_lbl, er.topleft)

        # Pass 2: belts, machines, walls, doors, fences, pillars, breakers, tubes
        wall_group = ("wall", "window", "door_closed", "door_open", "breaker")
        for row in range(world.rows):
            for col in range(world.cols):
                tile = world.grid[row][col]
                sx, sy = self.tile_to_screen(col, row)
                if (
                    sx + ts < -20
                    or sy + ts < -20
                    or sx > self.screen_width + 20
                    or sy > self.screen_height + 20
                ):
                    continue
                rect = pygame.Rect(sx, sy, ts, ts)

                if tile.kind == "void":
                    continue
                if tile.kind == "wall":
                    mask = self._neighbor_mask(world, col, row, wall_group)
                    screen.blit(
                        self.tileset.scaled(self.tileset.walls[mask], ts), rect.topleft
                    )
                elif tile.kind == "window":
                    screen.blit(
                        self.tileset.scaled(self.tileset.window, ts), rect.topleft
                    )
                elif tile.kind == "pillar":
                    screen.blit(
                        self.tileset.scaled(self.tileset.pillar, ts), rect.topleft
                    )
                elif tile.kind == "fence":
                    mask = self._neighbor_mask(
                        world, col, row, ("fence", "wall", "pillar")
                    )
                    screen.blit(
                        self.tileset.scaled(self.tileset.fences[mask], ts), rect.topleft
                    )
                elif tile.kind == "door_closed":
                    screen.blit(
                        self.tileset.scaled(self.tileset.door_closed, ts), rect.topleft
                    )
                    frame = rect.inflate(-3, -3)
                    pygame.draw.rect(
                        screen, (255, 194, 72), (frame.left, frame.top, frame.width, 3)
                    )
                    pygame.draw.rect(
                        screen,
                        (255, 194, 72),
                        (frame.left, frame.bottom - 3, frame.width, 3),
                    )
                    pygame.draw.rect(
                        screen, (72, 84, 102), frame, width=2, border_radius=3
                    )
                    reason = world.room_unlock_block_reason(tile.door_stage)
                    led_col = (
                        (88, 246, 138)
                        if reason is None
                        else ((255, 206, 82) if "CASH" in reason else (246, 82, 82))
                    )
                    pygame.draw.circle(
                        screen, (16, 20, 28), (frame.right - 6, frame.top + 8), 5
                    )
                    pygame.draw.circle(
                        screen, led_col, (frame.right - 6, frame.top + 8), 3
                    )
                    if tile.door_stage >= 2:
                        cost = (
                            LEVELS[tile.door_stage - 1].unlock_cost
                            if 1 <= tile.door_stage <= len(LEVELS)
                            else world.next_room_unlock_cost()
                        )
                        rm_s = self.mini_font.render(
                            f"RM{tile.door_stage}", True, led_col
                        )
                        cs_s = self.mini_font.render(
                            f"${cost:,}", True, (255, 228, 128)
                        )
                        bw = max(rm_s.get_width(), cs_s.get_width()) + 8
                        bh = rm_s.get_height() + cs_s.get_height() + 4
                        box_r = pygame.Rect(0, 0, bw, bh)
                        box_r.center = rect.center
                        pygame.draw.rect(screen, (18, 22, 30), box_r, border_radius=4)
                        pygame.draw.rect(
                            screen, led_col, box_r, width=1, border_radius=4
                        )
                        screen.blit(
                            rm_s,
                            rm_s.get_rect(
                                midtop=(box_r.centerx, box_r.top + 2)
                            ).topleft,
                        )
                        screen.blit(
                            cs_s,
                            cs_s.get_rect(
                                midbottom=(box_r.centerx, box_r.bottom - 2)
                            ).topleft,
                        )
                elif tile.kind == "door_open":
                    screen.blit(
                        self.tileset.scaled(self.tileset.door_open, ts), rect.topleft
                    )
                    if world.room_open_anim > 0.0 and col == world.room_open_col:
                        shut_frac = max(0.0, min(1.0, world.room_open_anim / 1.35))
                        half_h = max(2, int(round((ts * 0.45) * shut_frac)))
                        top_sh = pygame.Rect(
                            rect.left + 3, rect.top + 2, rect.width - 6, half_h
                        )
                        bot_sh = pygame.Rect(
                            rect.left + 3,
                            rect.bottom - 2 - half_h,
                            rect.width - 6,
                            half_h,
                        )
                        pygame.draw.rect(screen, (52, 66, 86), top_sh, border_radius=2)
                        pygame.draw.rect(
                            screen, (110, 232, 255), top_sh, width=1, border_radius=2
                        )
                        pygame.draw.rect(screen, (52, 66, 86), bot_sh, border_radius=2)
                        pygame.draw.rect(
                            screen, (110, 232, 255), bot_sh, width=1, border_radius=2
                        )
                elif tile.kind == "breaker":
                    mask = self._neighbor_mask(world, col, row, wall_group)
                    screen.blit(
                        self.tileset.scaled(self.tileset.walls[mask], ts), rect.topleft
                    )
                    self._draw_breaker_panel(screen, rect, tile, world.anim_time)
                elif tile.kind == "crate":
                    self._draw_crate_tile(screen, rect, tile, ts)
                elif tile.kind == "huge_pile":
                    self._draw_huge_pile_tile(screen, rect, tile, ts, world, col, row)
                elif tile.kind == "belt":
                    for side_delta in (1, 3):
                        sdir = (tile.dir_idx + side_delta) % 4
                        nc, nr = col + DIRS[sdir][0], row + DIRS[sdir][1]
                        if world.in_bounds(nc, nr):
                            nb = world.grid[nr][nc]
                            expected = (sdir + 2) % 4
                            feeds_in = (
                                (
                                    nb.kind
                                    in (
                                        "belt",
                                        "source",
                                        "crate",
                                        "huge_pile",
                                        "stamper",
                                        "endorser",
                                        "splitter",
                                        "fixer",
                                        "polisher",
                                        "depot",
                                    )
                                    and nb.dir_idx == expected
                                )
                                or (
                                    nb.kind in ("sorter", "scanner")
                                    and nb.dir_idx == expected
                                )
                                or (
                                    nb.kind in ("sorter", "scanner", "splitter")
                                    and (nb.dir_idx + 1) % 4 == expected
                                )
                            )
                            if feeds_in:
                                port = pygame.Rect(
                                    rect.centerx
                                    + DIRS[sdir][0] * (ts // 2 - 4)
                                    - ts // 5,
                                    rect.centery
                                    + DIRS[sdir][1] * (ts // 2 - 4)
                                    - ts // 5,
                                    (ts * 2) // 5,
                                    (ts * 2) // 5,
                                )
                                pygame.draw.rect(
                                    screen, (36, 42, 52), port, border_radius=2
                                )
                                pygame.draw.rect(
                                    screen,
                                    (92, 102, 118),
                                    port,
                                    width=1,
                                    border_radius=2,
                                )
                    incoming_dir = self._belt_incoming_dir(
                        world, col, row, tile.dir_idx
                    )
                    self._draw_belt_tile(
                        screen, rect, tile.dir_idx, anim_shift, ts, incoming_dir
                    )
                elif tile.kind == "bouncer":
                    self._draw_bouncer_tile(screen, rect, tile, ts)
                elif tile.kind == "sorter":
                    self._draw_sorter_tile(screen, rect, tile, anim_shift, ts)
                elif tile.kind == "scanner":
                    self._draw_scanner_tile(screen, rect, tile, anim_shift, ts)
                elif tile.kind == "shredder":
                    self._draw_shredder_tile(screen, rect, tile, world.anim_time, ts)
                elif tile.kind == "stamper":
                    self._draw_stamper_tile(
                        screen, rect, tile, anim_shift, ts, col, row, world
                    )
                elif tile.kind == "splitter":
                    self._draw_splitter_tile(screen, rect, tile, anim_shift, ts)
                elif tile.kind == "endorser":
                    self._draw_endorser_tile(screen, rect, tile, anim_shift, ts, world)
                elif tile.kind == "fixer":
                    self._draw_fixer_tile(
                        screen, rect, tile, anim_shift, ts, col, row, world
                    )
                elif tile.kind == "polisher":
                    self._draw_polisher_tile(
                        screen, rect, tile, anim_shift, ts, col, row, world
                    )
                elif tile.kind == "depot":
                    self._draw_depot_tile(screen, rect, tile, ts, world)
                elif tile.kind in ("source", "jammed_source"):
                    standby = not tile.jammed and not world._source_line_extended(
                        col, row
                    )
                    self._draw_source_tile(
                        screen, rect, tile, world.anim_time, ts, standby=standby
                    )
                elif tile.kind == "dest":
                    self._draw_dest_tile(screen, rect, tile, ts, world)

                if tile.kind in UPGRADABLE_MACHINES:
                    self._draw_machine_level_badge(screen, rect, tile, world)

                if tile.is_doorway and tile.kind in (
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
                ):
                    screen.blit(
                        self.tileset.scaled(self.tileset.door_frame_overlay, ts),
                        rect.topleft,
                    )

    def _draw_breaker_panel(
        self, screen: pygame.Surface, rect: pygame.Rect, tile: Tile, anim_time: float
    ) -> None:
        box = rect.inflate(-10, -10)
        pygame.draw.rect(screen, (52, 58, 70), box, border_radius=4)
        pygame.draw.rect(screen, (150, 162, 178), box, width=2, border_radius=4)
        led_on = not tile.jammed
        flash = (int(anim_time * 5) % 2) == 0
        led_col = (
            (74, 240, 122) if led_on else ((255, 76, 76) if flash else (140, 38, 38))
        )
        pygame.draw.circle(screen, led_col, (box.centerx, box.top + 8), 4)
        bolt_txt = self.small_font.render(
            "PWR" if led_on else "OFF", True, (240, 244, 250)
        )
        screen.blit(
            bolt_txt, bolt_txt.get_rect(center=(box.centerx, box.bottom - 10)).topleft
        )

    def _draw_bouncer_tile(
        self, screen: pygame.Surface, rect: pygame.Rect, tile: Tile, ts: int
    ) -> None:
        inset = rect.inflate(-4, -4)
        pulse = int(round(tile.bounce_anim * 5))
        pad_rect = inset.inflate(pulse, pulse)
        pygame.draw.rect(screen, (194, 114, 34), pad_rect, border_radius=6)
        pygame.draw.rect(screen, (255, 220, 112), pad_rect, width=2, border_radius=6)
        self._draw_arrow_triangle(
            screen, pad_rect.center, tile.dir_idx, max(7, ts // 4), (255, 248, 210)
        )

    def _draw_crate_tile(
        self, screen: pygame.Surface, rect: pygame.Rect, tile: Tile, ts: int
    ) -> None:
        pad = max(4, ts // 7)
        box = rect.inflate(pad, pad)
        empty = tile.crate_stock <= 0
        texture_size = (box.width, box.height)
        if texture_size not in self._crate_scaled_cache:
            self._crate_scaled_cache[texture_size] = pygame.transform.smoothscale(
                self.crate_texture, texture_size
            )
        crate_surf = self._crate_scaled_cache[texture_size]

        layers = (
            1
            if empty
            else (1 if tile.crate_stock <= 2 else (2 if tile.crate_stock <= 5 else 3))
        )
        step_y = max(6, ts // 6)
        top_box = box
        for li in range(layers):
            ox = (li % 2) * 3 - (1 if li > 0 else 0)
            oy = -li * step_y
            layer_box = box.move(ox, oy)
            top_box = layer_box
            sh = layer_box.move(2, 3)
            pygame.draw.rect(screen, (14, 16, 22), sh, border_radius=5)
            screen.blit(crate_surf, layer_box.topleft)

        if empty:
            pygame.draw.rect(screen, (24, 30, 28, 120), top_box, border_radius=5)

        if tile.color_key == "mixed_pb":
            accent = (108, 212, 232)
        elif tile.color_key in ("urgent_fraud", "vip_fraud"):
            accent = (238, 118, 92)
        elif tile.color_key in ("mixed_raw_fraud", "room1_mixed"):
            accent = (176, 152, 236)
        elif tile.color_key == "all_mixed":
            accent = (255, 214, 108)
        else:
            accent = tuple(
                CHEQUE_TYPES.get(tile.color_key, CHEQUE_TYPES["payroll"])["color"]
            )  # type: ignore[arg-type]

        pygame.draw.rect(
            screen,
            accent,
            (top_box.left + 4, top_box.bottom - 7, top_box.width - 8, 4),
            border_radius=2,
        )

        dx, dy = DIRS[tile.dir_idx]
        self._draw_arrow_triangle(
            screen,
            (top_box.centerx + dx * (ts // 3), top_box.centery + dy * (ts // 3)),
            tile.dir_idx,
            max(4, ts // 7),
            (255, 240, 178),
        )
        badge_txt = "DONE" if empty else f"CRATE x{tile.crate_stock}"
        b_col = (110, 248, 142) if empty else (255, 224, 118)
        lbl = self.mini_font.render(badge_txt, True, b_col)
        lr = lbl.get_rect(midbottom=(rect.centerx, top_box.top - 1))
        pygame.draw.rect(screen, (22, 24, 30), lr.inflate(6, 2), border_radius=3)
        screen.blit(lbl, lr.topleft)
        if not empty and (tile.require_stamp or tile.require_fix):
            req_tag = (
                "RAW+ERR"
                if (tile.require_stamp and tile.require_fix)
                else ("ERR" if tile.require_fix else "RAW")
            )
            req_col = (242, 144, 255) if tile.require_fix else (255, 198, 86)
            raw_lbl = self.mini_font.render(req_tag, True, req_col)
            rr = raw_lbl.get_rect(midbottom=(top_box.centerx, top_box.bottom - 8))
            pygame.draw.rect(screen, (22, 24, 30), rr.inflate(4, 1), border_radius=2)
            screen.blit(raw_lbl, rr.topleft)

    def _draw_huge_pile_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        ts: int,
        world: FactoryWorld,
        col: int,
        row: int,
    ) -> None:
        cx, cy = rect.center
        master = world._huge_pile_master(tile) or tile
        stock = master.crate_stock
        max_stock = max(1, master.crate_max)
        fill = max(0.0, min(1.0, stock / float(max_stock)))
        bay_cx = cx
        bay_cy = cy

        conn_dir = tile.dir_idx
        dx, dy = DIRS[conn_dir]
        nc, nr = col + dx, row + dy
        connected = (
            world.in_bounds(nc, nr)
            and world._tile_accepts_cheque(nc, nr)
            and not (
                world.grid[nr][nc].kind == "belt"
                and world.grid[nr][nc].dir_idx == (conn_dir + 2) % 4
            )
        )
        if not connected:
            for alt_dir in range(4):
                adx, ady = DIRS[alt_dir]
                ac, ar = col + adx, row + ady
                if world.in_bounds(ac, ar) and world._tile_accepts_cheque(ac, ar):
                    nb = world.grid[ar][ac]
                    if nb.kind == "belt" and nb.dir_idx == (alt_dir + 2) % 4:
                        continue
                    conn_dir = alt_dir
                    dx, dy = adx, ady
                    connected = True
                    break

        if not tile.pile_master:
            if connected and self.funnel_textures:
                self._draw_pile_funnel(screen, cx, cy, ts, conn_dir)
            return

        if stock <= 0:
            if connected and self.funnel_textures:
                self._draw_pile_funnel(screen, cx, cy, ts, conn_dir)
            lbl = self.mini_font.render("PILE EMPTY", True, (152, 166, 188))
            lr = lbl.get_rect(midbottom=(cx, rect.top - 2))
            pygame.draw.rect(screen, (22, 24, 30), lr.inflate(6, 2), border_radius=3)
            screen.blit(lbl, lr.topleft)
            return

        sh_scale = 0.40 + 0.60 * fill
        shadow_w = max(24, int(round(ts * 3.1 * sh_scale)))
        shadow_h = max(20, int(round(ts * 2.7 * sh_scale)))
        shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (12, 16, 24, 115), (0, 0, shadow_w, shadow_h))
        screen.blit(
            shadow, shadow.get_rect(center=(bay_cx, bay_cy + int(ts * 0.10))).topleft
        )

        # 1. Base giant cheque mountains filling the 3x3 pile zone (no crates)
        if self.cheque_sprites.mountains:
            m_spots = (
                (0.0, 0.0, 1.65),
                (-0.78, -0.72, 1.40),
                (0.75, -0.72, 1.35),
                (-0.75, 0.72, 1.35),
                (0.75, 0.72, 1.35),
            )
            m_count = max(1 if fill > 0.20 else 0, int(round(len(m_spots) * fill)))
            for mi, (ox, oy, sc) in enumerate(m_spots[:m_count]):
                m_src = self.cheque_sprites.mountains[
                    mi % len(self.cheque_sprites.mountains)
                ]
                m_surf = self.tileset.scaled(m_src, max(20, int(round(ts * sc))))
                screen.blit(
                    m_surf,
                    m_surf.get_rect(
                        center=(bay_cx + int(ox * ts), bay_cy + int(oy * ts))
                    ).topleft,
                )

        # 2. Mixed large piles and void/fake piles across the 3x3 zone (no crates)
        lp_spots = (
            (0.0, -0.45, 1.05),
            (-0.48, 0.35, 1.00),
            (0.48, -0.35, 0.98),
            (-0.95, -0.10, 0.95),
            (0.95, 0.10, 0.95),
            (-0.15, -0.95, 0.95),
            (0.15, 0.92, 0.92),
        )
        mixed_piles = (
            self.cheque_sprites.large_piles
            + self.cheque_sprites.void_piles
            + self.cheque_sprites.fake_piles
        )
        if mixed_piles:
            lp_count = max(1 if fill > 0.12 else 0, int(round(len(lp_spots) * fill)))
            for li, (ox, oy, sc) in enumerate(lp_spots[:lp_count]):
                lp_src = mixed_piles[(li * 3) % len(mixed_piles)]
                lp_surf = self.tileset.scaled(lp_src, max(16, int(round(ts * sc))))
                screen.blit(
                    lp_surf,
                    lp_surf.get_rect(
                        center=(bay_cx + int(ox * ts), bay_cy + int(oy * ts))
                    ).topleft,
                )

        if self.cheque_sprites.small_piles:
            sp_spots = (
                (-0.35, -0.50),
                (0.35, 0.25),
                (0.05, 0.10),
                (-0.65, -0.35),
                (-1.00, -0.80),
                (0.95, -0.82),
                (-0.95, 0.70),
                (0.90, 0.68),
            )
            sp_count = max(1, int(round(len(sp_spots) * fill)))
            for si, (ox, oy) in enumerate(sp_spots[:sp_count]):
                sp_src = self.cheque_sprites.small_piles[
                    si % len(self.cheque_sprites.small_piles)
                ]
                sp_surf = self.tileset.scaled(sp_src, max(12, int(round(ts * 0.68))))
                screen.blit(
                    sp_surf,
                    sp_surf.get_rect(
                        center=(bay_cx + int(ox * ts), bay_cy + int(oy * ts))
                    ).topleft,
                )

        # 3. Scattered colored single cheques
        scatter_keys = ("payroll", "rent", "vip", "mortgage", "void", "fake")
        scatter_spots = (
            (-0.45, -0.20, 8),
            (0.25, -0.35, -14),
            (-0.10, 0.35, 31),
            (0.60, -0.05, -8),
            (-1.05, -0.45, -24),
            (-0.75, -0.95, 15),
            (0.20, -1.00, -12),
            (0.85, -0.55, 28),
            (-0.90, 0.30, 19),
            (-0.25, 0.75, -17),
            (0.55, 0.70, 22),
            (1.00, 0.20, -29),
        )
        s_count = max(1, int(round(len(scatter_spots) * fill)))
        for ci, (ox, oy, ang) in enumerate(scatter_spots[:s_count]):
            ck = scatter_keys[ci % len(scatter_keys)]
            base_s = self.cheque_sprites.singles.get(ck)
            if base_s is not None:
                small_s = _scale_to_width(base_s, max(12, int(round(ts * 0.46))))
                rot_s = pygame.transform.rotate(small_s, ang)
                screen.blit(
                    rot_s,
                    rot_s.get_rect(
                        center=(bay_cx + int(ox * ts), bay_cy + int(oy * ts))
                    ).topleft,
                )

        if connected and self.funnel_textures:
            self._draw_pile_funnel(screen, cx, cy, ts, conn_dir)
        else:
            self._draw_arrow_triangle(
                screen,
                (cx + dx * (ts // 2 - 1), cy + dy * (ts // 2 - 1)),
                conn_dir,
                max(5, ts // 6),
                (255, 240, 178),
            )
        if not getattr(self, "hide_all_popups", False) and getattr(
            self, "show_pile_bag_labels", True
        ):
            lbl = self.mini_font.render(f"HUGE PILE x{stock}", True, (255, 228, 120))
            lr = lbl.get_rect(
                midbottom=(bay_cx, bay_cy - int(ts * (0.60 + 0.75 * fill)))
            )
            pygame.draw.rect(screen, (22, 24, 30), lr.inflate(8, 3), border_radius=3)
            screen.blit(lbl, lr.topleft)

    def _draw_pile_funnel(
        self,
        screen: pygame.Surface,
        cx: int,
        cy: int,
        ts: int,
        dir_idx: int,
    ) -> None:
        base_fn = self.funnel_textures[dir_idx % 4]
        bw, bh = base_fn.get_size()
        if dir_idx in (1, 3):
            fw = max(20, int(round(ts * 1.15)))
            fh = max(16, int(round(fw * (bh / max(1, bw)))))
        else:
            fh = max(20, int(round(ts * 1.15)))
            fw = max(16, int(round(fh * (bw / max(1, bh)))))
        key = (dir_idx % 4, fw, fh)
        if key not in self._funnel_cache:
            self._funnel_cache[key] = pygame.transform.smoothscale(base_fn, (fw, fh))
        fn_surf = self._funnel_cache[key]
        dx, dy = DIRS[dir_idx]
        fn_cx = cx + int(round(dx * ts * 0.42))
        fn_cy = cy + int(round(dy * ts * 0.42))
        screen.blit(fn_surf, fn_surf.get_rect(center=(fn_cx, fn_cy)).topleft)

    def _draw_depot_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        ts: int,
        world: FactoryWorld,
    ) -> None:
        cap = world.depot_capacity(tile)
        count = len(tile.depot_items)
        pad = max(3, ts // 10)
        box = rect.inflate(-pad, -pad)
        pygame.draw.rect(screen, (36, 44, 60), box, border_radius=6)
        pygame.draw.rect(screen, (118, 176, 228), box, width=2, border_radius=6)

        # Inner storage bay with stacked fill bars
        inner = box.inflate(-max(6, ts // 6), -max(8, ts // 5))
        pygame.draw.rect(screen, (20, 24, 34), inner, border_radius=4)
        fill_ratio = min(1.0, count / max(1, cap))
        if fill_ratio > 0.0:
            fill_h = max(3, int(round(inner.height * fill_ratio)))
            fill_rect = pygame.Rect(
                inner.left + 2,
                inner.bottom - fill_h + 1,
                max(2, inner.width - 4),
                max(2, fill_h - 2),
            )
            bar_col = (255, 198, 76) if count >= cap else (110, 232, 168)
            pygame.draw.rect(screen, bar_col, fill_rect, border_radius=2)

        dx, dy = DIRS[tile.dir_idx]
        self._draw_arrow_triangle(
            screen,
            (rect.centerx + dx * (ts // 2 - 4), rect.centery + dy * (ts // 2 - 4)),
            tile.dir_idx,
            max(4, ts // 7),
            (255, 240, 178),
        )
        lbl = self.mini_font.render(f"DEPOT {count}/{cap}", True, (210, 236, 255))
        lr = lbl.get_rect(midbottom=(rect.centerx, rect.top - 1))
        pygame.draw.rect(screen, (22, 24, 30), lr.inflate(6, 2), border_radius=3)
        screen.blit(lbl, lr.topleft)
        self._draw_machine_level_badge(screen, rect, tile, world)

    def _draw_sorter_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        anim_shift: float,
        ts: int,
    ) -> None:
        info = CHEQUE_TYPES[tile.color_key]
        c_rgb = tuple(info["color"])  # type: ignore[arg-type]
        short_lbl = str(info["label"])[:3]
        branch_dir = (tile.dir_idx + 1) % 4
        sdx, sdy = DIRS[tile.dir_idx]
        bdx, bdy = DIRS[branch_dir]
        # Perpendicular half-width unit
        spx, spy = -sdy, sdx

        # 1. Animated main conveyor underneath
        self._draw_belt_tile(screen, rect, tile.dir_idx, anim_shift, ts)

        # 2. 90 deg CW coloured discharge chute from tile center to branch edge
        chute_half = max(5, ts // 5)
        edge_cx = rect.centerx + bdx * (ts // 2 - 2)
        edge_cy = rect.centery + bdy * (ts // 2 - 2)
        c_poly = [
            (rect.centerx + sdx * chute_half, rect.centery + sdy * chute_half),
            (edge_cx + sdx * chute_half, edge_cy + sdy * chute_half),
            (edge_cx - sdx * chute_half, edge_cy - sdy * chute_half),
            (rect.centerx - sdx * chute_half, rect.centery - sdy * chute_half),
        ]
        pygame.draw.polygon(screen, (34, 42, 58), c_poly)
        pygame.draw.line(screen, c_rgb, c_poly[0], c_poly[1], 2)
        pygame.draw.line(screen, c_rgb, c_poly[3], c_poly[2], 2)
        lip_r = pygame.Rect(
            edge_cx - abs(sdx) * chute_half - 2,
            edge_cy - abs(sdy) * chute_half - 2,
            max(5, abs(sdx) * chute_half * 2 + 4),
            max(5, abs(sdy) * chute_half * 2 + 4),
        )
        pygame.draw.rect(screen, c_rgb, lip_r, border_radius=2)

        # 3. Overhead steel scanner bridge & pivoting diverter arm
        bridge_len = max(14, int(ts * 0.44))
        bridge_w = max(8, int(ts * 0.24))
        bw = bridge_w if sdx != 0 else bridge_len
        bh = bridge_len if sdx != 0 else bridge_w
        bridge = pygame.Rect(rect.centerx - bw // 2, rect.centery - bh // 2, bw, bh)
        pygame.draw.rect(screen, (42, 50, 68), bridge, border_radius=4)
        pygame.draw.rect(screen, c_rgb, bridge, width=2, border_radius=4)

        # Optical sensor lens + glowing core
        lens_r = max(4, ts // 8)
        pygame.draw.circle(screen, (18, 22, 32), bridge.center, lens_r + 2)
        pygame.draw.circle(screen, c_rgb, bridge.center, lens_r)
        pygame.draw.circle(screen, (255, 255, 255), bridge.center, max(2, lens_r // 2))

        # Directional chevrons (white straight pass-through, colored 90 deg CW divert)
        self._draw_arrow_triangle(
            screen,
            (
                rect.centerx + sdx * max(6, ts // 3 - 2),
                rect.centery + sdy * max(6, ts // 3 - 2),
            ),
            tile.dir_idx,
            max(4, ts // 8),
            (226, 236, 252),
        )
        self._draw_arrow_triangle(
            screen,
            (
                rect.centerx + bdx * max(6, ts // 3 - 2),
                rect.centery + bdy * max(6, ts // 3 - 2),
            ),
            branch_dir,
            max(5, ts // 7),
            c_rgb,
        )

        # 4. Crisp colour tag anchored in opposing straight quadrant so arrows stay clear
        tag_x = rect.centerx - bdx * max(6, ts // 4) - spx * 0
        tag_y = rect.centery - bdy * max(6, ts // 4) - spy * 0
        tag = self.mini_font.render(short_lbl, True, (255, 255, 255))
        tr = tag.get_rect(center=(tag_x, tag_y)).clamp(rect.inflate(-4, -4))
        pygame.draw.rect(screen, (20, 24, 34), tr.inflate(5, 2), border_radius=3)
        pygame.draw.rect(screen, c_rgb, tr.inflate(5, 2), width=1, border_radius=3)
        screen.blit(tag, tr.topleft)

    def _draw_scanner_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        anim_shift: float,
        ts: int,
    ) -> None:
        self._draw_belt_tile(screen, rect, tile.dir_idx, anim_shift, ts)
        arch = rect.inflate(-6, -8)
        pygame.draw.rect(screen, (36, 48, 72), arch, border_radius=5)
        scan_glow = (
            (255, 92, 128)
            if tile.bounce_anim > 0
            else ((120, 246, 255) if tile.stamp_anim > 0 else (68, 178, 224))
        )
        pygame.draw.rect(screen, scan_glow, arch, width=2, border_radius=5)
        # UV laser beam across belt + straight pass / 90 deg CW fraud reject indicator.
        pygame.draw.line(
            screen,
            (255, 76, 132) if tile.stamp_anim > 0 else (72, 224, 248),
            (arch.left + 4, arch.centery),
            (arch.right - 5, arch.centery),
            2,
        )
        branch_dir = (tile.dir_idx + 1) % 4
        dx, dy = DIRS[branch_dir]
        self._draw_arrow_triangle(
            screen,
            (arch.centerx + dx * (ts // 5), arch.centery + dy * (ts // 5)),
            branch_dir,
            max(5, ts // 6),
            (255, 78, 118),
        )
        mode_tag = "FRD" if tile.scanner_mode == "fraud" else "ERR"
        mode_col = (120, 244, 255) if tile.scanner_mode == "fraud" else (242, 144, 255)
        lbl = self.small_font.render(mode_tag, True, mode_col)
        screen.blit(lbl, lbl.get_rect(center=(arch.centerx, arch.top + 8)).topleft)

    def _draw_shredder_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        anim_time: float,
        ts: int,
    ) -> None:
        inset = rect.inflate(-4, -4)
        pygame.draw.rect(screen, (96, 28, 36), inset, border_radius=5)
        pygame.draw.rect(
            screen,
            (238, 148, 52) if tile.bounce_anim > 0 else (214, 72, 72),
            inset,
            width=2,
            border_radius=5,
        )
        pit = inset.inflate(-10, -10)
        pygame.draw.rect(screen, (22, 24, 30), pit, border_radius=3)
        # Spinning silver sawtooth bars inside shredder chute.
        offset = int((anim_time * (28.0 if tile.bounce_anim > 0 else 10.0)) % 6)
        for bx in range(pit.left + 2 + offset, pit.right - 2, 6):
            pygame.draw.line(
                screen, (172, 182, 198), (bx, pit.top + 2), (bx, pit.bottom - 3), 2
            )
        lbl = self.small_font.render("SHRD", True, (255, 226, 214))
        screen.blit(lbl, lbl.get_rect(center=pit.center).topleft)

    def _draw_stamper_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        anim_shift: float,
        ts: int,
        col: int = -1,
        row: int = -1,
        world: FactoryWorld | None = None,
    ) -> None:
        self._draw_belt_tile(screen, rect, tile.dir_idx, anim_shift, ts)
        press = rect.inflate(-10, -14)
        turbo = tile.overclocked or (
            world is not None and world.upgrade_tier("vip_endorser") > 0
        )
        if tile.stamp_anim > 0:
            press_col = (74, 232, 168)
        elif tile.overclocked:
            press_col = (44, 138, 186)
        else:
            press_col = (34, 146, 98)
        rim_col = (
            (118, 240, 255)
            if tile.overclocked
            else ((255, 224, 96) if turbo else (196, 255, 220))
        )
        pygame.draw.rect(screen, press_col, press, border_radius=4)
        pygame.draw.rect(screen, rim_col, press, width=2, border_radius=4)
        lbl_str = "TURBO" if tile.overclocked else ("VIP" if turbo else "SLOW")
        lbl = self.mini_font.render(lbl_str, True, (255, 255, 255))
        screen.blit(lbl, lbl.get_rect(center=press.center).topleft)

        # Draw active dwell progress bar if a cheque is currently pressed
        if world is not None and col >= 0 and row >= 0:
            hold_pct = 0.0
            cycle = max(0.05, world.stamper_cycle_time(tile))
            for ch in world.cheques:
                if (
                    not ch.airborne
                    and ch.stamp_hold > 0.0
                    and int(math.floor(ch.x)) == col
                    and int(math.floor(ch.y)) == row
                ):
                    hold_pct = min(1.0, ch.stamp_hold / cycle)
                    break
            if hold_pct > 0.0:
                p_bar = pygame.Rect(
                    press.left + 2, press.bottom - 5, max(4, press.width - 4), 4
                )
                pygame.draw.rect(screen, (18, 22, 30), p_bar)
                pygame.draw.rect(
                    screen,
                    (255, 224, 88),
                    (p_bar.left, p_bar.top, int(p_bar.width * hold_pct), p_bar.height),
                )

    def _draw_splitter_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        anim_shift: float,
        ts: int,
    ) -> None:
        self._draw_belt_tile(screen, rect, tile.dir_idx, anim_shift, ts)
        s_dir = tile.dir_idx
        b_dir = (tile.dir_idx + 1) % 4
        sdx, sdy = DIRS[s_dir]
        bdx, bdy = DIRS[b_dir]
        straight_col = tuple(
            CHEQUE_TYPES.get(tile.splitter_straight_color, CHEQUE_TYPES["payroll"])[
                "color"
            ]
        )
        branch_col = tuple(
            CHEQUE_TYPES.get(tile.splitter_branch_color, CHEQUE_TYPES["vip"])["color"]
        )

        branch_start = rect.center
        branch_end = (
            rect.centerx + bdx * (ts // 2 - 3),
            rect.centery + bdy * (ts // 2 - 3),
        )
        pygame.draw.line(
            screen, (82, 90, 106), branch_start, branch_end, max(8, int(ts * 0.52))
        )
        pygame.draw.line(
            screen, (20, 24, 31), branch_start, branch_end, max(6, int(ts * 0.40))
        )
        pygame.draw.line(
            screen, (48, 54, 65), branch_start, branch_end, max(4, int(ts * 0.26))
        )

        for output_dir, color in ((s_dir, straight_col), (b_dir, branch_col)):
            ox = rect.centerx + DIRS[output_dir][0] * (ts // 2 - 5)
            oy = rect.centery + DIRS[output_dir][1] * (ts // 2 - 5)
            pygame.draw.circle(screen, color, (ox, oy), max(5, ts // 8))
            pygame.draw.circle(screen, (255, 255, 255), (ox, oy), max(2, ts // 16))
            self._draw_arrow_triangle(
                screen,
                (
                    rect.centerx + DIRS[output_dir][0] * max(6, ts // 4),
                    rect.centery + DIRS[output_dir][1] * max(6, ts // 4),
                ),
                output_dir,
                max(4, ts // 8),
                color,
            )

        label = self.mini_font.render("50/50", True, (232, 248, 255))
        screen.blit(label, label.get_rect(center=(rect.centerx, rect.centery)).topleft)

    def _draw_machine_level_badge(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        world: FactoryWorld | None = None,
    ) -> None:
        lvl = (
            world.effective_machine_level(tile)
            if world is not None
            else min(
                MACHINE_MAX_LEVEL, max(tile.machine_level, 2 if tile.overclocked else 1)
            )
        )
        if lvl < 2:
            return
        fg = (255, 224, 96) if lvl >= 3 else (118, 240, 255)
        lbl = self.mini_font.render(f"MK{lvl}", True, fg)
        lr = lbl.get_rect(topright=(rect.right - 2, rect.top + 1))
        pygame.draw.rect(screen, (16, 20, 30), lr.inflate(4, 1), border_radius=2)
        pygame.draw.rect(screen, fg, lr.inflate(4, 1), width=1, border_radius=2)
        screen.blit(lbl, lr.topleft)

    def _draw_fixer_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        anim_shift: float,
        ts: int,
        col: int = -1,
        row: int = -1,
        world: FactoryWorld | None = None,
    ) -> None:
        self._draw_belt_tile(screen, rect, tile.dir_idx, anim_shift, ts)
        arch = rect.inflate(-9, -11)
        lvl = world.effective_machine_level(tile) if world is not None else 1
        fill_col = (146, 56, 178) if tile.stamp_anim > 0 else (92, 38, 124)
        rim_col = (
            (255, 224, 112)
            if lvl >= 3
            else ((128, 240, 255) if lvl == 2 else (232, 134, 255))
        )
        pygame.draw.rect(screen, fill_col, arch, border_radius=4)
        pygame.draw.rect(screen, rim_col, arch, width=2, border_radius=4)
        pygame.draw.line(
            screen,
            (255, 186, 255),
            (arch.left + 4, arch.top + 4),
            (arch.right - 5, arch.bottom - 5),
            2,
        )
        lbl = self.mini_font.render("FIX", True, (255, 244, 255))
        screen.blit(lbl, lbl.get_rect(center=arch.center).topleft)
        if world is not None and col >= 0 and row >= 0:
            hold_pct = 0.0
            cycle = max(0.04, world.fixer_cycle_time(tile))
            for ch in world.cheques:
                if (
                    not ch.airborne
                    and ch.process_hold > 0.0
                    and ch.fixed_by != (col, row)
                    and int(math.floor(ch.x)) == col
                    and int(math.floor(ch.y)) == row
                ):
                    hold_pct = min(1.0, ch.process_hold / cycle)
                    break
            if hold_pct > 0.0:
                p_bar = pygame.Rect(
                    arch.left + 2, arch.bottom - 5, max(4, arch.width - 4), 4
                )
                pygame.draw.rect(screen, (18, 22, 30), p_bar)
                pygame.draw.rect(
                    screen,
                    (242, 144, 255),
                    (p_bar.left, p_bar.top, int(p_bar.width * hold_pct), p_bar.height),
                )

    def _draw_polisher_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        anim_shift: float,
        ts: int,
        col: int = -1,
        row: int = -1,
        world: FactoryWorld | None = None,
    ) -> None:
        self._draw_belt_tile(screen, rect, tile.dir_idx, anim_shift, ts)
        press = rect.inflate(-9, -11)
        lvl = world.effective_machine_level(tile) if world is not None else 1
        fill_col = (196, 134, 34) if tile.stamp_anim > 0 else (128, 82, 24)
        rim_col = (132, 248, 255) if lvl >= 3 else (255, 220, 96)
        pygame.draw.rect(screen, fill_col, press, border_radius=5)
        pygame.draw.rect(screen, rim_col, press, width=2, border_radius=5)
        pygame.draw.circle(
            screen, (255, 232, 138), press.center, max(4, ts // 6), width=2
        )
        lbl_str = "CURE" if lvl >= 3 else "WAX"
        lbl = self.mini_font.render(lbl_str, True, (255, 252, 236))
        screen.blit(lbl, lbl.get_rect(center=press.center).topleft)
        if world is not None and col >= 0 and row >= 0:
            hold_pct = 0.0
            cycle = max(0.04, world.polisher_cycle_time(tile))
            for ch in world.cheques:
                if (
                    not ch.airborne
                    and ch.process_hold > 0.0
                    and ch.polished_by != (col, row)
                    and int(math.floor(ch.x)) == col
                    and int(math.floor(ch.y)) == row
                ):
                    hold_pct = min(1.0, ch.process_hold / cycle)
                    break
            if hold_pct > 0.0:
                p_bar = pygame.Rect(
                    press.left + 2, press.bottom - 5, max(4, press.width - 4), 4
                )
                pygame.draw.rect(screen, (18, 22, 30), p_bar)
                pygame.draw.rect(
                    screen,
                    (255, 224, 96),
                    (p_bar.left, p_bar.top, int(p_bar.width * hold_pct), p_bar.height),
                )

    def _draw_endorser_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        anim_shift: float,
        ts: int,
        world: FactoryWorld | None = None,
    ) -> None:
        self._draw_belt_tile(screen, rect, tile.dir_idx, anim_shift, ts)
        arch = rect.inflate(-8, -12)
        fill_col = (224, 168, 42) if tile.stamp_anim > 0 else (156, 112, 28)
        pygame.draw.rect(screen, fill_col, arch, border_radius=4)
        pygame.draw.rect(screen, (255, 232, 128), arch, width=2, border_radius=4)
        tier = world.upgrade_tier("commission_boost") if world is not None else 0
        lvl = world.effective_machine_level(tile) if world is not None else 1
        lvl_bonus = (0, 55, 120)[lvl - 1]
        boost_amt = 100 + (0, 40, 85, 140)[tier] + lvl_bonus
        lbl = self.small_font.render(f"+${boost_amt}", True, (255, 252, 224))
        screen.blit(lbl, lbl.get_rect(center=arch.center).topleft)

    @staticmethod
    def _belt_incoming_dir(
        world: FactoryWorld, col: int, row: int, out_dir: int
    ) -> int | None:
        """Find a perpendicular belt input so corners can be rendered as turns."""
        flow_tiles = {
            "belt",
            "source",
            "crate",
            "stamper",
            "endorser",
            "splitter",
            "fixer",
            "polisher",
            "sorter",
            "scanner",
        }
        for neighbor_dir, (dc, dr) in enumerate(DIRS):
            nc, nr = col + dc, row + dr
            if not (0 <= nc < world.cols and 0 <= nr < world.rows):
                continue
            neighbor = world.grid[nr][nc]
            expected_output = (neighbor_dir + 2) % 4
            if neighbor.kind in flow_tiles and neighbor.dir_idx == expected_output:
                incoming_dir = neighbor.dir_idx
                if incoming_dir not in (out_dir, (out_dir + 2) % 4):
                    return incoming_dir
        return None

    def _draw_belt_corner(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        incoming_dir: int,
        out_dir: int,
        anim_shift: float,
        ts: int,
    ) -> None:
        in_dx, in_dy = DIRS[incoming_dir]
        out_dx, out_dy = DIRS[out_dir]
        half_t = ts * 0.5
        piv_x = rect.centerx + (-in_dx + out_dx) * half_t
        piv_y = rect.centery + (-in_dy + out_dy) * half_t
        u0x, u0y = float(-out_dx), float(-out_dy)
        u1x, u1y = float(in_dx), float(in_dy)

        def _arc_ring(r_in: float, r_out: float, color: tuple[int, int, int]) -> None:
            steps = 16
            outer_pts: list[tuple[int, int]] = []
            inner_pts: list[tuple[int, int]] = []
            for i in range(steps + 1):
                theta = (i / steps) * (math.pi * 0.5)
                ct, st = math.cos(theta), math.sin(theta)
                vx = ct * u0x + st * u1x
                vy = ct * u0y + st * u1y
                outer_pts.append(
                    (int(round(piv_x + vx * r_out)), int(round(piv_y + vy * r_out)))
                )
                inner_pts.append(
                    (int(round(piv_x + vx * r_in)), int(round(piv_y + vy * r_in)))
                )
            poly = outer_pts + list(reversed(inner_pts))
            pygame.draw.polygon(screen, color, poly)

        old_clip = screen.get_clip()
        screen.set_clip(rect)
        pad_outer = max(2.0, min(4.0, ts * 0.08))
        pad_groove = max(4.0, min(7.0, ts * 0.14))
        pad_bed = max(5.5, min(9.0, ts * 0.19))

        _arc_ring(pad_outer, ts - pad_outer, (82, 90, 106))
        _arc_ring(pad_groove, ts - pad_groove, (20, 24, 31))
        _arc_ring(pad_bed, ts - pad_bed, (48, 54, 65))

        phase = (anim_shift / 16.0) % 1.0
        r_bed_in = pad_bed + 1.0
        r_bed_out = ts - pad_bed - 1.0
        for i in range(3):
            u = (phase + i / 3.0) % 1.0
            theta = u * (math.pi * 0.5)
            ct, st = math.cos(theta), math.sin(theta)
            vx = ct * u0x + st * u1x
            vy = ct * u0y + st * u1y
            pygame.draw.line(
                screen,
                (38, 44, 54),
                (int(round(piv_x + vx * r_bed_in)), int(round(piv_y + vy * r_bed_in))),
                (
                    int(round(piv_x + vx * r_bed_out)),
                    int(round(piv_y + vy * r_bed_out)),
                ),
                max(1, int(ts * 0.04)),
            )

        chev_half = max(3.0, ts * 0.11)
        chev_len = max(3.0, ts * 0.10)
        for i in range(3):
            u = (phase + (i + 0.5) / 3.0) % 1.0
            theta = u * (math.pi * 0.5)
            ct, st = math.cos(theta), math.sin(theta)
            vx = ct * u0x + st * u1x
            vy = ct * u0y + st * u1y
            tx = -st * u0x + ct * u1x
            ty = -st * u0y + ct * u1y
            cx_m = piv_x + vx * half_t
            cy_m = piv_y + vy * half_t
            tip = (int(round(cx_m + tx * chev_len)), int(round(cy_m + ty * chev_len)))
            wing1 = (
                int(round(cx_m - tx * (chev_len * 0.7) + vx * chev_half)),
                int(round(cy_m - ty * (chev_len * 0.7) + vy * chev_half)),
            )
            wing2 = (
                int(round(cx_m - tx * (chev_len * 0.7) - vx * chev_half)),
                int(round(cy_m - ty * (chev_len * 0.7) - vy * chev_half)),
            )
            pygame.draw.polygon(screen, (236, 188, 66), [tip, wing1, wing2])

        screen.set_clip(old_clip)

    def _draw_belt_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        dir_idx: int,
        anim_shift: float,
        ts: int,
        incoming_dir: int | None = None,
    ) -> None:
        if incoming_dir is not None:
            self._draw_belt_corner(screen, rect, incoming_dir, dir_idx, anim_shift, ts)
            return

        inset = rect.inflate(-6, -6)
        dx, dy = DIRS[dir_idx]
        px, py = -dy, dx
        cx, cy = inset.center
        half_len = (abs(dx) * inset.width + abs(dy) * inset.height) * 0.5
        half_w = (abs(dy) * inset.width + abs(dx) * inset.height) * 0.5

        def to_pt(along_px: float, across_px: float) -> tuple[int, int]:
            return (
                int(round(cx + dx * along_px + px * across_px)),
                int(round(cy + dy * along_px + py * across_px)),
            )

        def fill_quad(
            a0: float, a1: float, w0: float, w1: float, color: tuple[int, int, int]
        ) -> None:
            pts = [to_pt(a0, w0), to_pt(a1, w0), to_pt(a1, w1), to_pt(a0, w1)]
            pygame.draw.polygon(screen, color, pts)

        rail_w = max(2.0, half_w * 0.16)
        inner_w = max(3.0, half_w - rail_w)
        roller_r = max(2.0, half_len * 0.13)
        belt_span = max(3.0, half_len - roller_r * 0.55)
        travel_amp = max(2.5, min(0.35 * ts, belt_span - 0.5))

        # Metallic end rollers peeking out at tail (u=0) and head (u=1)
        for sign in (-1.0, 1.0):
            r_a0 = min(sign * half_len, sign * (half_len - roller_r))
            r_a1 = max(sign * half_len, sign * (half_len - roller_r))
            fill_quad(r_a0, r_a1, -half_w + 1.0, half_w - 1.0, (112, 122, 138))
            rim_a0 = min(sign * half_len, sign * (half_len - roller_r * 0.45))
            rim_a1 = max(sign * half_len, sign * (half_len - roller_r * 0.45))
            fill_quad(rim_a0, rim_a1, -inner_w, inner_w, (148, 158, 176))

        # Main conveyor belt surface with subtle cylindrical top highlight
        fill_quad(-belt_span, belt_span, -inner_w, inner_w, (34, 39, 48))
        fill_quad(-belt_span * 0.78, belt_span * 0.78, -inner_w, inner_w, (48, 54, 65))

        # Dark seams where the rubber belt wraps underneath each roller
        seam_h = max(1.5, roller_r * 0.55)
        fill_quad(-belt_span, -belt_span + seam_h, -inner_w, inner_w, (20, 24, 31))
        fill_quad(belt_span - seam_h, belt_span, -inner_w, inner_w, (20, 24, 31))

        # Steel side rails framing the belt
        fill_quad(-half_len, half_len, -half_w, -inner_w, (82, 90, 106))
        fill_quad(-half_len, half_len, inner_w, half_w, (82, 90, 106))
        pygame.draw.rect(screen, (60, 67, 80), inset, width=1, border_radius=3)

        phase = (anim_shift / 16.0) % 1.0

        # Moving belt slats using the same cylindrical projection as the arrows
        for s in range(3):
            u_s = (phase + (s + 0.5) / 3.0) % 1.0
            theta_s = (u_s - 0.5) * math.pi
            wrap_s = max(0.0, math.cos(theta_s))
            along_s = math.sin(theta_s) * travel_amp
            slat_half_t = max(0.6, 1.3 * max(0.25, wrap_s))
            slat_col = (
                int(26 + 34 * wrap_s),
                int(30 + 38 * wrap_s),
                int(38 + 44 * wrap_s),
            )
            fill_quad(
                along_s - slat_half_t,
                along_s + slat_half_t,
                -inner_w + 1.0,
                inner_w - 1.0,
                slat_col,
            )

        # Three evenly spaced chevron arrows curling smoothly around the rollers
        base_len = max(2.8, ts * 0.10)
        base_hw = max(3.0, inner_w * 0.56)
        for i in range(3):
            u = (phase + i / 3.0) % 1.0
            theta = (u - 0.5) * math.pi
            along = math.sin(theta) * travel_amp
            wrap = max(0.0, math.cos(theta))

            len_scale = max(0.18, wrap)
            wid_scale = 0.55 + 0.45 * wrap
            tip_l = base_len * len_scale
            tail_l = base_len * len_scale
            notch_l = tail_l * 0.28
            hw = base_hw * wid_scale

            color = (
                int(78 + (242 - 78) * wrap),
                int(66 + (204 - 66) * wrap),
                int(34 + (78 - 34) * wrap),
            )
            pts = [
                to_pt(along + tip_l, 0.0),
                to_pt(along - tail_l, hw),
                to_pt(along - notch_l, 0.0),
                to_pt(along - tail_l, -hw),
            ]
            pygame.draw.polygon(screen, color, pts)

    def _draw_source_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        anim_time: float,
        ts: int,
        standby: bool = False,
    ) -> None:
        shake_x = int(round(math.sin(anim_time * 32.0) * 2)) if tile.jammed else 0
        box = rect.inflate(-4, -4).move(shake_x, 0)
        pygame.draw.rect(screen, (62, 68, 82), box, border_radius=5)

        if tile.color_key == "mixed_pb":
            pygame.draw.rect(
                screen,
                (68, 152, 255),
                (box.left + 4, box.top + 4, box.width // 2 - 4, 8),
            )
            pygame.draw.rect(
                screen,
                (72, 212, 112),
                (box.centerx, box.top + 4, box.width // 2 - 4, 8),
            )
            rim_col = (140, 210, 255)
        elif tile.color_key == "urgent_fraud":
            pygame.draw.rect(
                screen,
                (212, 148, 86),
                (box.left + 4, box.top + 4, box.width // 2 - 4, 8),
            )
            pygame.draw.rect(
                screen,
                (224, 68, 116),
                (box.centerx, box.top + 4, box.width // 2 - 4, 8),
            )
            rim_col = (232, 118, 92)
        elif tile.color_key == "mixed_raw_fraud":
            seg_w = max(4, (box.width - 8) // 4)
            for si, scol in enumerate(
                ((212, 148, 86), (72, 212, 112), (224, 68, 116), (68, 152, 255))
            ):
                pygame.draw.rect(
                    screen,
                    scol,
                    (box.left + 4 + si * seg_w, box.top + 4, seg_w, 8),
                )
            rim_col = (186, 158, 244)
        elif tile.color_key == "all_mixed":
            seg_w = max(4, (box.width - 8) // 4)
            for si, scol in enumerate(
                ((68, 152, 255), (212, 148, 86), (72, 212, 112), (236, 198, 72))
            ):
                pygame.draw.rect(
                    screen,
                    scol,
                    (box.left + 4 + si * seg_w, box.top + 4, seg_w, 8),
                )
            rim_col = (255, 218, 108)
        else:
            rim_col = tuple(CHEQUE_TYPES[tile.color_key]["color"])  # type: ignore[arg-type]
            pygame.draw.rect(
                screen, rim_col, (box.left + 4, box.top + 4, box.width - 8, 8)
            )

        pygame.draw.rect(
            screen,
            (255, 88, 72) if tile.jammed else rim_col,
            box,
            width=2,
            border_radius=5,
        )
        dx, dy = DIRS[tile.dir_idx]
        self._draw_arrow_triangle(
            screen,
            (box.centerx + dx * (ts // 5), box.centery + dy * (ts // 5)),
            tile.dir_idx,
            max(5, ts // 6),
            (255, 255, 255),
        )

        if not tile.jammed and tile.burst_count > 1:
            b_surf = self.mini_font.render(
                f"x{tile.burst_count}", True, (118, 238, 255)
            )
            br = b_surf.get_rect(topright=(box.right - 2, box.top + 2))
            pygame.draw.rect(screen, (18, 24, 34), br.inflate(4, 1), border_radius=2)
            screen.blit(b_surf, br.topleft)

        if tile.jammed:
            for ox, oy in ((-8, 2), (4, 0), (-1, 6)):
                scrap = pygame.Rect(box.centerx + ox, box.centery + oy, 11, 7)
                pygame.draw.rect(screen, (244, 240, 224), scrap)
                pygame.draw.rect(screen, rim_col, scrap, width=1)
        elif standby:
            tag = self.mini_font.render("WAIT", True, (152, 226, 255))
            tr = tag.get_rect(center=(box.centerx, box.bottom - 9))
            pygame.draw.rect(screen, (22, 28, 40), tr.inflate(4, 1), border_radius=2)
            screen.blit(tag, tr.topleft)
        elif tile.require_stamp or tile.require_fix:
            req_txt = (
                "RAW+ERR"
                if (tile.require_stamp and tile.require_fix)
                else ("ERR" if tile.require_fix else "RAW")
            )
            req_col = (242, 144, 255) if tile.require_fix else (255, 206, 92)
            tag = self.small_font.render(req_txt, True, req_col)
            screen.blit(tag, tag.get_rect(center=(box.centerx, box.bottom - 9)).topleft)

    def _draw_dest_tile(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tile: Tile,
        ts: int,
        world: FactoryWorld,
    ) -> None:
        info = CHEQUE_TYPES[tile.color_key]
        c_rgb = tuple(info["color"])  # type: ignore[arg-type]
        target = world.min_dest_deliveries
        done = tile.delivered_count >= target
        pulse = int(round(tile.bounce_anim * 4))
        box = rect.inflate(-2 + pulse, -2 + pulse)
        pygame.draw.rect(
            screen,
            (28, 52, 42) if done else ((34, 48, 64) if pulse > 0 else (26, 32, 46)),
            box,
            border_radius=6,
        )
        pygame.draw.rect(
            screen,
            (80, 235, 135)
            if done
            else ((255, 255, 255) if tile.bounce_anim > 0.5 else c_rgb),
            box,
            width=3,
            border_radius=6,
        )
        if tile.require_boost and not done:
            pygame.draw.rect(
                screen, (255, 214, 78), box.inflate(-5, -5), width=2, border_radius=4
            )
        pygame.draw.circle(
            screen, c_rgb, box.center, max(8, ts // 4 + pulse // 2), width=3
        )

        short_lbl = str(info["label"])
        lbl = self.small_font.render(short_lbl, True, c_rgb)
        l_rect = lbl.get_rect(midbottom=(box.centerx, box.top - 1))
        pygame.draw.rect(screen, (18, 22, 32), l_rect.inflate(6, 2), border_radius=3)
        screen.blit(lbl, l_rect.topleft)

        prog_col = (80, 235, 135) if done else (255, 210, 90)
        cnt = self.mini_font.render(f"{tile.delivered_count}/{target}", True, prog_col)
        cnt_cy = box.centery - 4 if tile.require_boost else box.centery
        c_rect = cnt.get_rect(center=(box.centerx, cnt_cy))
        pygame.draw.rect(screen, (16, 20, 30), c_rect.inflate(6, 2), border_radius=4)
        pygame.draw.rect(
            screen, prog_col, c_rect.inflate(6, 2), width=1, border_radius=4
        )
        screen.blit(cnt, c_rect.topleft)

        if tile.require_boost or tile.require_polish or tile.require_scan:
            if tile.require_boost and tile.require_polish:
                req_tag = "VIP+WAX"
                req_col = (255, 224, 96)
            elif tile.require_polish:
                req_tag = "WAX SEAL"
                req_col = (255, 214, 92)
            elif tile.require_scan and not tile.require_boost:
                req_tag = "UV SCAN"
                req_col = (120, 236, 255)
            else:
                req_tag = "VIP MICR"
                req_col = (255, 222, 92)
            vip_lbl = self.mini_font.render(req_tag, True, req_col)
            vr = vip_lbl.get_rect(midbottom=(box.centerx, box.bottom - 1))
            pygame.draw.rect(screen, (36, 28, 12), vr.inflate(4, 1), border_radius=2)
            pygame.draw.rect(
                screen, req_col, vr.inflate(4, 1), width=1, border_radius=2
            )
            screen.blit(vip_lbl, vr.topleft)

    def _draw_cheques(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        item_w = max(20, int(round(TILE_SIZE * 0.72 * self.zoom)))
        for ch in world.cheques:
            sx, sy = self.tile_to_screen(ch.x, ch.y)
            lift = 0
            w_draw = item_w
            if ch.airborne:
                arc = 4.0 * ch.air_progress * (1.0 - ch.air_progress)
                lift = int(round(arc * 36.0 * self.zoom))
                w_draw = int(round(item_w * (1.0 + 0.32 * arc)))
                sw = max(8, int(round(22 * self.zoom)))
                sh = max(4, int(round(11 * self.zoom)))
                pygame.draw.ellipse(
                    screen, (14, 16, 24), (sx - sw // 2, sy - sh // 2, sw, sh)
                )

            draw_key = (
                ch.color_key
                if (ch.fraud_scanned and ch.color_key in BAD_CHEQUE_TYPES)
                else ch.apparent_color
            )
            raw = self.cheque_sprites.singles.get(
                draw_key, self.cheque_sprites.singles["payroll"]
            )
            spr = self.cheque_sprites.get_scaled(raw, w_draw)
            pos = (sx - spr.get_width() // 2, sy - lift - spr.get_height() // 2)
            if draw_key == "vip":
                pulse = 0.5 + 0.5 * math.sin(world.anim_time * 6.0 + (id(ch) % 17))
                gw = spr.get_width() + 14
                gh = spr.get_height() + 12
                glow = pygame.Surface((gw, gh), pygame.SRCALPHA)
                pygame.draw.ellipse(
                    glow,
                    (96, 184, 255, int(70 + 55 * pulse)),
                    (0, 0, gw, gh),
                )
                pygame.draw.ellipse(
                    glow,
                    (255, 224, 108, int(48 + 42 * pulse)),
                    (3, 3, max(2, gw - 6), max(2, gh - 6)),
                )
                screen.blit(glow, (pos[0] - 7, pos[1] - 6))
            screen.blit(spr, pos)
            if draw_key == "vip":
                for sp_i in range(3):
                    ph = world.anim_time * 5.2 + sp_i * 2.1 + (id(ch) % 11)
                    tw = max(0.0, math.sin(ph))
                    if tw > 0.25:
                        sp_x = pos[0] + int(spr.get_width() * (0.2 + 0.3 * sp_i))
                        sp_y = pos[1] + int(
                            spr.get_height() * (0.25 + 0.25 * ((sp_i + 1) % 2))
                        )
                        arm = max(2, int(round((3 + 3 * tw) * self.zoom)))
                        pygame.draw.line(
                            screen,
                            (255, 248, 178),
                            (sp_x - arm, sp_y),
                            (sp_x + arm, sp_y),
                            1,
                        )
                        pygame.draw.line(
                            screen,
                            (255, 248, 178),
                            (sp_x, sp_y - arm),
                            (sp_x, sp_y + arm),
                            1,
                        )

            if not ch.stamped and ch.color_key not in BAD_CHEQUE_TYPES:
                tag_rect = pygame.Rect(pos[0] + spr.get_width() - 8, pos[1] - 2, 10, 8)
                pygame.draw.rect(screen, (255, 196, 56), tag_rect)
                pygame.draw.rect(screen, (24, 24, 28), tag_rect, 1)
            if ch.misprint and ch.color_key not in BAD_CHEQUE_TYPES:
                err_rect = pygame.Rect(pos[0] - 2, pos[1] - 2, 10, 8)
                pygame.draw.rect(screen, (236, 88, 255), err_rect)
                pygame.draw.rect(screen, (24, 24, 28), err_rect, 1)
            if ch.polished:
                pygame.draw.circle(
                    screen,
                    (255, 218, 86),
                    (pos[0] + spr.get_width() - 3, pos[1] + spr.get_height() - 2),
                    4,
                )
            if ch.fraud_scanned and ch.color_key not in BAD_CHEQUE_TYPES:
                pygame.draw.circle(
                    screen,
                    (108, 240, 255),
                    (pos[0] + 3, pos[1] + spr.get_height() - 2),
                    3,
                )

    def _draw_pileups(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        for row in range(world.rows):
            for col in range(world.cols):
                tile = world.grid[row][col]
                if tile.pile_tier <= 0:
                    continue
                sx, sy = self.tile_to_screen(col + 0.5, row + 0.55)
                base_w = (
                    40 if tile.pile_tier == 1 else (56 if tile.pile_tier == 2 else 94)
                )
                draw_w = max(18, int(round(base_w * self.zoom)))
                spr = self.cheque_sprites.pick_pile_surface(
                    tile.pile_tier, tile.pile_kind, tile.pile_variant, draw_w
                )
                shadow_w = int(round(spr.get_width() * 0.85))
                shadow_h = max(6, int(round(spr.get_height() * 0.25)))
                shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
                pygame.draw.ellipse(
                    shadow, (12, 14, 20, 115), (0, 0, shadow_w, shadow_h)
                )
                screen.blit(
                    shadow, (sx - shadow_w // 2, sy + spr.get_height() // 2 - shadow_h)
                )
                screen.blit(
                    spr, (sx - spr.get_width() // 2, sy - spr.get_height() // 2)
                )

    def _draw_window_beams(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        ts = TILE_SIZE * self.zoom
        for r in range(world.rows):
            for c in range(world.cols):
                if world.grid[r][c].kind != "window":
                    continue
                sx, sy = self.tile_to_screen(c, r + 1)
                beam = pygame.Surface((int(ts * 2.2), int(ts * 3.2)), pygame.SRCALPHA)
                pts = [
                    (4, 0),
                    (int(ts) - 4, 0),
                    (int(ts * 1.9), int(ts * 3.1)),
                    (int(ts * 0.2), int(ts * 3.1)),
                ]
                pygame.draw.polygon(beam, (176, 218, 252, 34), pts)
                screen.blit(beam, (sx, sy))

    def _draw_fork_machine_icon(
        self,
        screen: pygame.Surface,
        fx: int,
        fy: int,
        facing_left: bool,
        machine_data: dict[str, object],
        load_state: int,
        world: FactoryWorld,
    ) -> None:
        m_kind = str(machine_data.get("kind", "belt"))
        m_dir = int(machine_data.get("dir_idx", 1))  # type: ignore[arg-type]
        m_col = str(machine_data.get("color_key", "payroll"))
        side = -1 if facing_left else 1
        cw = max(26, int(round(36 * self.zoom)))
        ch = max(26, int(round(36 * self.zoom)))
        lift_px = int(round((16 if load_state >= 2 else 6) * self.zoom))
        cx = fx + side * int(round(34 * self.zoom))
        cy = fy + int(round(4 * self.zoom)) - lift_px
        cr = pygame.Rect(cx - cw // 2, cy - ch // 2, cw, ch)
        self._draw_tool_preview_icon(screen, cr, m_kind, m_dir, m_col, world)
        pygame.draw.rect(screen, (255, 224, 96), cr, width=1, border_radius=4)

    def _draw_forklifts(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        for idx, fl in enumerate(world.forklifts):
            if idx == world.player_forklift_idx:
                continue
            fx, fy = self.tile_to_screen(fl.x, fl.y)
            sw = max(22, int(round(56 * self.zoom)))
            sh = max(8, int(round(14 * self.zoom)))
            pygame.draw.ellipse(
                screen, (14, 18, 24), (fx - sw // 2, fy + int(9 * self.zoom), sw, sh)
            )

            load_state = 2 if fl.carried_machine is not None else 0
            frame = self.forklift_sprites.get_frame(
                world.anim_time, fl.facing_left, fl.moving, load_state
            )
            if abs(self.zoom - 1.0) > 0.02:
                fw = max(24, int(round(frame.get_width() * self.zoom)))
                fh = max(16, int(round(frame.get_height() * self.zoom)))
                frame = pygame.transform.scale(frame, (fw, fh))
            rect = frame.get_rect(midbottom=(fx, fy + int(16 * self.zoom)))
            screen.blit(frame, rect.topleft)

            if fl.carried_machine is not None:
                self._draw_fork_machine_icon(
                    screen,
                    fx,
                    fy,
                    fl.facing_left,
                    fl.carried_machine,
                    load_state,
                    world,
                )

            auto_on = fl.autopilot or world.upgrade_tier("auto_drone") > 0
            dist = math.hypot(fl.x - world.player_x, fl.y - world.player_y)
            tag: str | None = None
            tag_col = (255, 218, 92)
            if auto_on:
                tag = "AUTO [G]" if dist <= world.interact_reach + 0.6 else "AUTO"
                tag_col = (112, 240, 255)
            elif dist <= world.interact_reach + 0.6:
                tag = "DRIVE [G/E] | AUTO [U]"
            if tag is not None:
                b_surf = self.mini_font.render(tag, True, tag_col)
                br = b_surf.get_rect(midbottom=(rect.centerx, rect.top - 2))
                pygame.draw.rect(
                    screen, (20, 24, 34), br.inflate(6, 2), border_radius=3
                )
                screen.blit(b_surf, br.topleft)

    def _draw_player(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        px, py = self.tile_to_screen(world.player_x, world.player_y)
        # Subtle work-reach ring around player so proximity matters visually.
        reach_r = int(round(world.build_reach * TILE_SIZE * self.zoom))
        ring = pygame.Surface((reach_r * 2 + 4, reach_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(
            ring, (112, 198, 246, 36), (reach_r + 2, reach_r + 2), reach_r, width=2
        )
        screen.blit(ring, (px - reach_r - 2, py - reach_r - 2))

        if world.walk_target is not None:
            wx, wy = self.tile_to_screen(*world.walk_target)
            pygame.draw.circle(
                screen, (116, 232, 152), (wx, wy), max(5, int(7 * self.zoom)), width=2
            )

        fl = world.active_forklift
        if fl is not None:
            sw = max(24, int(round(58 * self.zoom)))
            sh = max(8, int(round(14 * self.zoom)))
            pygame.draw.ellipse(
                screen, (14, 18, 24), (px - sw // 2, py + int(10 * self.zoom), sw, sh)
            )

            # Draw thief slightly tucked into cab before drawing forklift cage overlay
            seat_shift = (
                -int(round(6 * self.zoom))
                if not world.facing_left
                else int(round(6 * self.zoom))
            )
            driver = self.sprites.get_frame("idle", world.anim_time, world.facing_left)
            dw = max(12, int(round(driver.get_width() * 0.68 * self.zoom)))
            dh = max(12, int(round(driver.get_height() * 0.68 * self.zoom)))
            driver_scaled = pygame.transform.scale(driver, (dw, dh))
            screen.blit(
                driver_scaled,
                driver_scaled.get_rect(
                    midbottom=(px + seat_shift, py + int(2 * self.zoom))
                ).topleft,
            )

            load_state = (
                2
                if (fl.carried_machine is not None or len(world.carried_cheques) >= 8)
                else (1 if world.carried_cheques else 0)
            )
            f_frame = self.forklift_sprites.get_frame(
                world.anim_time, fl.facing_left, fl.moving, load_state
            )
            if abs(self.zoom - 1.0) > 0.02:
                fw = max(24, int(round(f_frame.get_width() * self.zoom)))
                fh = max(16, int(round(f_frame.get_height() * self.zoom)))
                f_frame = pygame.transform.scale(f_frame, (fw, fh))
            rect = f_frame.get_rect(midbottom=(px, py + int(16 * self.zoom)))
            screen.blit(f_frame, rect.topleft)

            if fl.carried_machine is not None:
                self._draw_fork_machine_icon(
                    screen,
                    px,
                    py,
                    fl.facing_left,
                    fl.carried_machine,
                    load_state,
                    world,
                )

            if fl.carried_machine is not None:
                m_lbl = str(fl.carried_machine.get("kind", "PART")).upper()
                b_txt = f"{m_lbl} ON FORKS [X] PLACE | [R] ROT | [G] EXIT"
            else:
                b_txt = f"FORKS {len(world.carried_cheques)}/{FORKLIFT_MAX_CARRIED} | [X] LIFT | [G] EXIT"
            badge = self.small_font.render(b_txt, True, (255, 228, 96))
            br = badge.get_rect(midbottom=(rect.centerx, rect.top - 2))
            pygame.draw.rect(screen, (20, 24, 34), br.inflate(6, 2), border_radius=3)
            screen.blit(badge, br.topleft)
            return

        lift = 0
        if world.jump_timer > 0.0:
            p = 1.0 - (world.jump_timer / 0.36)
            lift = int(round(4.0 * p * (1.0 - p) * 28.0 * self.zoom))

        sw, sh = max(14, int(round(28 * self.zoom))), max(6, int(round(11 * self.zoom)))
        pygame.draw.ellipse(
            screen, (14, 18, 24), (px - sw // 2, py + int(10 * self.zoom), sw, sh)
        )

        frame = self.sprites.get_frame(
            world.player_anim, world.anim_time, world.facing_left
        )
        if abs(self.zoom - 1.0) > 0.02:
            fw = max(12, int(round(frame.get_width() * self.zoom)))
            fh = max(12, int(round(frame.get_height() * self.zoom)))
            frame = pygame.transform.scale(frame, (fw, fh))
        rect = frame.get_rect(midbottom=(px, py + int(14 * self.zoom) - lift))
        screen.blit(frame, rect.topleft)

        if (
            world.carried_cheques
            and not getattr(self, "hide_all_popups", False)
            and getattr(self, "show_pile_bag_labels", True)
        ):
            badge = self.small_font.render(
                f"BAG {len(world.carried_cheques)}/{MAX_CARRIED}", True, (255, 228, 96)
            )
            br = badge.get_rect(midbottom=(rect.centerx, rect.top - 2))
            pygame.draw.rect(screen, (20, 24, 34), br.inflate(6, 2), border_radius=3)
            screen.blit(badge, br.topleft)

    def _draw_lighting(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        lw, lh = self._light_surf.get_size()
        scale_x = lw / self.screen_width
        scale_y = lh / self.screen_height
        # Bright enough to inspect everything cleanly even in darkened bays.
        self._light_surf.fill((174, 184, 202))

        for lgt in world.lights:
            lx, ly = self.tile_to_screen(float(lgt["col"]), float(lgt["row"]))  # type: ignore[arg-type]
            radius_px = max(
                8, int(round(float(lgt["radius"]) * TILE_SIZE * self.zoom * scale_x))
            )  # type: ignore[arg-type]
            state = str(lgt["state"])
            if state == "out":
                continue
            if state == "flicker":
                wave = math.sin(world.anim_time * 23.0) + 0.5 * math.sin(
                    world.anim_time * 47.0
                )
                if wave < -0.35:
                    continue
                boost = (228, 226, 204)
            else:
                boost = (255, 248, 224)
            cx = int(lx * scale_x)
            cy = int(ly * scale_y)
            pygame.draw.circle(self._light_surf, (218, 218, 212), (cx, cy), radius_px)
            pygame.draw.circle(
                self._light_surf, boost, (cx, cy), max(4, int(radius_px * 0.62))
            )

        # Keep player's flashlamp halo bright so work area is always crisp.
        px, py = self.tile_to_screen(world.player_x, world.player_y)
        pr = max(12, int(round(3.6 * TILE_SIZE * self.zoom * scale_x)))
        pygame.draw.circle(
            self._light_surf,
            (238, 242, 248),
            (int(px * scale_x), int(py * scale_y)),
            pr,
        )

        scaled_light = pygame.transform.smoothscale(
            self._light_surf, (self.screen_width, self.screen_height)
        )
        screen.blit(scaled_light, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    def _draw_particles(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        for pt in world.particles:
            sx, sy = self.tile_to_screen(pt.x, pt.y)
            life = max(0.0, min(1.0, pt.ttl / max(0.01, pt.max_ttl)))
            rad = max(1, int(round(pt.size * life * self.zoom)))
            pygame.draw.circle(screen, pt.color, (sx, sy), rad)

    def _draw_drone(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        if "auto_drone" not in world.upgrades:
            return
        dx, dy = self.tile_to_screen(world.drone_x, world.drone_y)
        hover = int(round(math.sin(world.anim_time * 6.0) * 3.0 * self.zoom))
        if world.drone_laser_target is not None and world.drone_laser_timer > 0.0:
            tx, ty = self.tile_to_screen(*world.drone_laser_target)
            pygame.draw.line(screen, (92, 242, 255), (dx, dy - 6 + hover), (tx, ty), 3)
            pygame.draw.circle(
                screen, (255, 255, 255), (tx, ty), max(4, int(6 * self.zoom))
            )

        # Ground shadow
        sw = max(10, int(18 * self.zoom))
        sh = max(4, int(7 * self.zoom))
        pygame.draw.ellipse(
            screen, (14, 18, 26), (dx - sw // 2, dy + int(10 * self.zoom), sw, sh)
        )

        # Drone body + twin rotors
        by = dy - int(8 * self.zoom) + hover
        r_body = max(6, int(10 * self.zoom))
        span = max(8, int(13 * self.zoom))
        pygame.draw.line(screen, (154, 174, 206), (dx - span, by), (dx + span, by), 2)
        spin = (
            int(abs(math.cos(world.anim_time * 28.0)) * max(4, int(7 * self.zoom))) + 2
        )
        for rx in (dx - span, dx + span):
            pygame.draw.line(
                screen, (190, 232, 255), (rx - spin, by - 4), (rx + spin, by - 4), 2
            )
        pygame.draw.circle(screen, (36, 48, 72), (dx, by), r_body)
        pygame.draw.circle(screen, (112, 236, 255), (dx, by), r_body, width=2)
        pygame.draw.circle(screen, (255, 224, 96), (dx, by), max(2, r_body // 3))

    def _draw_offscreen_indicators(
        self, screen: pygame.Surface, world: FactoryWorld
    ) -> None:
        play_top = 96
        play_bottom = self.screen_height - 92
        pulse = (int(world.anim_time * 5.0) % 2) == 0
        for row in range(world.rows):
            for col in range(world.cols):
                t = world.grid[row][col]
                if t.kind == "jammed_source" and t.jammed:
                    col_rgb = (255, 92, 82)
                    tag = "JAM"
                elif t.kind == "breaker" and t.jammed:
                    col_rgb = (255, 206, 72)
                    tag = "PWR"
                else:
                    continue
                sx, sy = self.tile_to_screen(col + 0.5, row + 0.5)
                if 16 <= sx <= self.screen_width - 16 and play_top <= sy <= play_bottom:
                    continue
                if not pulse:
                    continue
                ix = max(34, min(self.screen_width - 34, sx))
                iy = max(play_top + 14, min(play_bottom - 14, sy))
                box = pygame.Rect(ix - 20, iy - 10, 40, 20)
                pygame.draw.rect(screen, (22, 26, 38), box, border_radius=4)
                pygame.draw.rect(screen, col_rgb, box, width=2, border_radius=4)
                lbl = self.small_font.render(tag, True, col_rgb)
                screen.blit(lbl, lbl.get_rect(center=box.center).topleft)

    def _draw_minimap(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        r = self.minimap_rect
        panel = pygame.Rect(r.left - 6, r.top - 24, r.width + 12, r.height + 30)
        pygame.draw.rect(screen, (14, 18, 28), panel, border_radius=6)
        pygame.draw.rect(screen, (88, 114, 158), panel, width=1, border_radius=6)
        hdr = self.small_font.render("PLANT RADAR [M]", True, (176, 208, 244))
        screen.blit(hdr, (r.left, panel.top + 2))

        pygame.draw.rect(screen, (28, 34, 44), r)
        cw = r.width / world.cols
        rh = r.height / world.rows
        for row in range(world.rows):
            for col in range(world.cols):
                t = world.grid[row][col]
                px = int(r.left + col * cw)
                py = int(r.top + row * rh)
                pw = max(2, int(math.ceil(cw)))
                ph = max(2, int(math.ceil(rh)))
                col_rgb: tuple[int, int, int] | None = None
                if t.kind == "void":
                    col_rgb = (10, 13, 20)
                elif t.kind in ("wall", "window", "pillar", "fence"):
                    col_rgb = (68, 76, 92)
                elif t.kind == "door_closed":
                    col_rgb = (242, 166, 62)
                elif t.kind == "grate":
                    col_rgb = (18, 22, 28)
                elif t.kind in UPGRADABLE_MACHINES:
                    col_rgb = (108, 146, 198)
                elif t.kind in ("source", "jammed_source"):
                    col_rgb = (255, 76, 76) if t.jammed else (120, 220, 255)
                elif t.kind == "crate":
                    col_rgb = (218, 172, 82) if t.crate_stock > 0 else (84, 168, 110)
                elif t.kind == "dest":
                    col_rgb = tuple(CHEQUE_TYPES[t.color_key]["color"])  # type: ignore[arg-type]
                elif t.kind == "breaker":
                    col_rgb = (255, 212, 68) if t.jammed else (84, 240, 128)
                if col_rgb is not None:
                    pygame.draw.rect(screen, col_rgb, (px, py, pw, ph))
                if t.pile_tier > 0:
                    pygame.draw.rect(
                        screen,
                        (240, 186, 82),
                        (px + 1, py + 1, max(2, pw - 1), max(2, ph - 1)),
                    )

        for ch in world.cheques:
            cx = int(r.left + (ch.x / world.cols) * r.width)
            cy = int(r.top + (ch.y / world.rows) * r.height)
            c_rgb = tuple(CHEQUE_TYPES[ch.color_key]["color"])  # type: ignore[arg-type]
            pygame.draw.circle(screen, c_rgb, (cx, cy), 2)

        for fl in world.forklifts:
            fx = int(r.left + (fl.x / world.cols) * r.width)
            fy = int(r.top + (fl.y / world.rows) * r.height)
            pygame.draw.circle(screen, (255, 198, 72), (fx, fy), 2)

        px = int(r.left + (world.player_x / world.cols) * r.width)
        py = int(r.top + (world.player_y / world.rows) * r.height)
        pygame.draw.circle(screen, (255, 255, 255), (px, py), 3)
        if "auto_drone" in world.upgrades:
            dx = int(r.left + (world.drone_x / world.cols) * r.width)
            dy = int(r.top + (world.drone_y / world.rows) * r.height)
            pygame.draw.circle(screen, (96, 240, 255), (dx, dy), 2)

        # Current camera viewport box
        vx0 = (-self.cam_offset_x) / (TILE_SIZE * self.zoom)
        vy0 = (90 - self.cam_offset_y) / (TILE_SIZE * self.zoom)
        vx1 = (self.screen_width - self.cam_offset_x) / (TILE_SIZE * self.zoom)
        vy1 = (self.screen_height - 84 - self.cam_offset_y) / (TILE_SIZE * self.zoom)
        vr = pygame.Rect(
            int(r.left + (vx0 / world.cols) * r.width),
            int(r.top + (vy0 / world.rows) * r.height),
            max(8, int(((vx1 - vx0) / world.cols) * r.width)),
            max(8, int(((vy1 - vy0) / world.rows) * r.height)),
        ).clip(r)
        pygame.draw.rect(screen, (255, 232, 128), vr, width=1)

    def _draw_interact_prompts(
        self, screen: pygame.Surface, world: FactoryWorld
    ) -> None:
        for row in range(world.rows):
            for col in range(world.cols):
                t = world.grid[row][col]
                label: str | None = None
                col_rgb = (255, 220, 88)
                near = world.in_interact_reach(col, row)

                if t.kind == "jammed_source" and t.jammed:
                    label = "JAM! [E]" if near else "JAM!"
                    col_rgb = (255, 112, 92)
                elif t.kind == "breaker" and t.jammed:
                    label = "BREAKER [E]" if near else "OFF"
                    col_rgb = (255, 206, 82)
                elif t.kind == "crate" and t.crate_stock > 0 and near:
                    label = f"HAUL [E] x{t.crate_stock}"
                    col_rgb = (255, 224, 112)
                elif t.kind == "door_closed":
                    if t.door_stage > world.room_stage:
                        cost = world.next_room_unlock_cost()
                        reason = world.room_unlock_block_reason(t.door_stage)
                        if reason is None:
                            label = (
                                f"[E] UNLOCK RM{t.door_stage} (-${cost:,})"
                                if near
                                else f"RM{t.door_stage} READY (-${cost:,})"
                            )
                            col_rgb = (88, 246, 138)
                        elif near:
                            label = reason
                            col_rgb = (255, 206, 82)
                    elif near:
                        label = "OPEN [E]"
                        col_rgb = (120, 226, 255)
                elif t.pile_tier > 0 and near:
                    label = (
                        f"SHRED -${CLEAR_PILEUP_COST} [E]"
                        if t.pile_kind in BAD_CHEQUE_TYPES
                        else f"CLEAR -${CLEAR_PILEUP_COST} [E]"
                    )
                    col_rgb = (255, 214, 92)
                elif (
                    t.kind == "stamper"
                    and world.machine_upgrade_cost(t) is not None
                    and near
                ):
                    upg_c = world.machine_upgrade_cost(t)
                    lvl = world.effective_machine_level(t)
                    label = f"UPG ${upg_c} [E]" if lvl == 1 else f"MK3 ${upg_c} [E/U]"
                    col_rgb = (118, 238, 255)
                elif (
                    t.kind == "dest"
                    and near
                    and any(c == t.color_key for c in world.carried_cheques)
                ):
                    label = "DELIVER [E]"
                    col_rgb = (112, 246, 138)
                elif t.kind == "belt" and near and world.carried_cheques:
                    label = "FEED [E]"
                    col_rgb = (120, 240, 255)
                elif t.kind in UPGRADABLE_MACHINES and near:
                    upg_c = world.machine_upgrade_cost(t)
                    if upg_c is not None:
                        lvl = world.effective_machine_level(t)
                        key_tag = "[U]" if t.kind in ("belt", "sorter") else "[E/U]"
                        label = f"MK{lvl + 1} ${upg_c} {key_tag}"
                        col_rgb = (118, 238, 255)

                if label is not None:
                    sx, sy = self.tile_to_screen(col + 0.5, row - 0.05)
                    txt = self.small_font.render(label, True, (255, 255, 255))
                    box = txt.get_rect(midbottom=(sx, sy))
                    pygame.draw.rect(
                        screen, (24, 28, 40), box.inflate(8, 3), border_radius=4
                    )
                    pygame.draw.rect(
                        screen, col_rgb, box.inflate(8, 3), width=1, border_radius=4
                    )
                    screen.blit(txt, box.topleft)

    def _draw_hover_preview(
        self,
        screen: pygame.Surface,
        world: FactoryWorld,
        hover_tile: tuple[int, int] | None,
        selected_tool: int | None,
        build_dir: int,
        filter_color: str,
    ) -> None:
        if hover_tile is None or world.in_forklift:
            return
        col, row = hover_tile
        if not world.in_bounds(col, row):
            return
        if world.grid[row][col].kind == "void":
            return
        sx, sy = self.tile_to_screen(col, row)
        ts = max(16, int(round(TILE_SIZE * self.zoom)))
        rect = pygame.Rect(sx, sy, ts, ts)
        if selected_tool is None:
            in_reach = world.in_build_reach(col, row)
            outline = (110, 214, 255) if in_reach else (255, 202, 82)
            pygame.draw.rect(screen, outline, rect, width=2, border_radius=4)
            return
        tool_kind = TOOLS[selected_tool][0]
        in_reach = world.in_build_reach(col, row)
        tile = world.grid[row][col]
        base_cost = TOOL_COSTS.get(tool_kind, 0)
        net_cost = 0 if tile.kind == tool_kind else max(0, base_cost - tile.paid_cost)
        demolish_fee = 0
        if tool_kind == "demolish":
            if tile.kind in UPGRADABLE_MACHINES:
                demolish_fee = 0
            elif tile.pile_tier > 0:
                demolish_fee = CLEAR_PILEUP_COST
            elif tile.decal in ("oil", "puddle", "rubbish"):
                demolish_fee = CLEAN_DECAL_COST
            affordable = demolish_fee == 0 or world.cash >= demolish_fee
        elif (
            tile.kind == tool_kind
            and tile.kind in UPGRADABLE_MACHINES
            and tile.dir_idx == build_dir % 4
            and (tool_kind != "sorter" or tile.color_key == filter_color)
        ):
            upg_c = world.machine_upgrade_cost(tile)
            net_cost = upg_c if upg_c is not None else 0
            affordable = upg_c is None or world.cash >= upg_c
        else:
            affordable = net_cost == 0 or world.cash >= net_cost

        if not affordable:
            outline = (255, 86, 86)
        else:
            outline = (104, 242, 136) if in_reach else (255, 202, 82)
            if tool_kind == "demolish":
                outline = (255, 110, 96) if in_reach else (255, 178, 86)

        if tool_kind != "demolish" and tile.kind not in (
            "void",
            "wall",
            "window",
            "pillar",
            "fence",
            "door_closed",
            "source",
            "jammed_source",
            "crate",
            "dest",
            "breaker",
            "grate",
        ):
            ghost = pygame.Surface((ts, ts))
            ghost.fill((12, 16, 24))
            ghost.set_colorkey((12, 16, 24))
            self._draw_tool_preview_icon(
                ghost, ghost.get_rect(), tool_kind, build_dir, filter_color, world
            )
            ghost.set_alpha(65 if world.paused else (135 if affordable else 85))
            screen.blit(ghost, rect.topleft)

        if world.paused:
            outline = (255, 198, 72)

        pygame.draw.rect(screen, outline, rect, width=2, border_radius=4)
        if tool_kind in (
            "belt",
            "bouncer",
            "sorter",
            "scanner",
            "stamper",
            "splitter",
            "endorser",
            "fixer",
            "polisher",
            "depot",
        ):
            sdx, sdy = DIRS[build_dir]
            arrow_sz = max(4, ts // 8)
            arrow_off = ts // 3
            self._draw_arrow_triangle(
                screen,
                (rect.centerx + sdx * arrow_off, rect.centery + sdy * arrow_off),
                build_dir,
                arrow_sz,
                outline,
            )
            if tool_kind == "sorter":
                branch = (build_dir + 1) % 4
                dx, dy = DIRS[branch]
                c_rgb = tuple(CHEQUE_TYPES[filter_color]["color"])  # type: ignore[arg-type]
                self._draw_arrow_triangle(
                    screen,
                    (rect.centerx + dx * arrow_off, rect.centery + dy * arrow_off),
                    branch,
                    arrow_sz,
                    c_rgb,
                )
            elif tool_kind == "scanner":
                branch = (build_dir + 1) % 4
                dx, dy = DIRS[branch]
                self._draw_arrow_triangle(
                    screen,
                    (rect.centerx + dx * arrow_off, rect.centery + dy * arrow_off),
                    branch,
                    arrow_sz,
                    (255, 78, 118),
                )
            elif tool_kind == "splitter":
                branch = (build_dir + 1) % 4
                dx, dy = DIRS[branch]
                self._draw_arrow_triangle(
                    screen,
                    (rect.centerx + dx * arrow_off, rect.centery + dy * arrow_off),
                    branch,
                    arrow_sz,
                    (92, 224, 248),
                )
            elif tool_kind == "bouncer":
                dx, dy = DIRS[build_dir]
                tx, ty = self.tile_to_screen(col + dx * 3 + 0.5, row + dy * 3 + 0.5)
                for seg in range(1, 9):
                    p = seg / 9.0
                    arc_lift = 4.0 * p * (1.0 - p) * 28.0 * self.zoom
                    wx = int(round(rect.centerx + (tx - rect.centerx) * p))
                    wy = int(round(rect.centery + (ty - rect.centery) * p - arc_lift))
                    pygame.draw.circle(screen, outline, (wx, wy), max(2, ts // 14))
                pygame.draw.circle(screen, outline, (tx, ty), max(5, ts // 6), width=2)
        elif tool_kind == "shredder":
            inner = rect.inflate(-8, -8)
            pygame.draw.rect(
                screen,
                (255, 96, 96) if affordable else outline,
                inner,
                width=2,
                border_radius=3,
            )

        cost_txt: str | None = None
        cost_col = (255, 224, 96)
        if world.paused:
            cost_txt = "PAUSED [F]"
            cost_col = (255, 198, 92)
        elif tool_kind == "demolish":
            if tile.kind in UPGRADABLE_MACHINES and tile.paid_cost > 0:
                cost_txt = f"+${tile.paid_cost}"
                cost_col = (160, 224, 255)
            elif demolish_fee > 0:
                verb = "CLEAR" if tile.pile_tier > 0 else "MOP"
                cost_txt = (
                    f"-${demolish_fee} {verb}"
                    if affordable
                    else f"NEED ${demolish_fee}"
                )
                cost_col = (255, 212, 92) if affordable else (255, 96, 96)
        elif (
            tile.kind == tool_kind
            and tile.kind in UPGRADABLE_MACHINES
            and tile.dir_idx == build_dir % 4
            and (tool_kind != "sorter" or tile.color_key == filter_color)
            and world.machine_upgrade_cost(tile) is not None
        ):
            nxt_lvl = world.effective_machine_level(tile) + 1
            cost_txt = f"MK{nxt_lvl} ${net_cost}" if affordable else f"NEED ${net_cost}"
            cost_col = (118, 240, 255) if affordable else (255, 96, 96)
        elif tool_kind != "demolish" and net_cost > 0:
            cost_txt = f"${net_cost}" if affordable else f"NEED ${net_cost}"
            cost_col = (120, 246, 146) if affordable else (255, 96, 96)
        if cost_txt is not None:
            badge = self.small_font.render(cost_txt, True, cost_col)
            br = badge.get_rect(midbottom=(rect.centerx, rect.top - 3))
            pygame.draw.rect(screen, (18, 22, 32), br.inflate(6, 2), border_radius=3)
            screen.blit(badge, br.topleft)

    def _draw_popups(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        for p in world.popups:
            sx, sy = self.tile_to_screen(p.x, p.y)
            surf = self.small_font.render(p.text, True, p.color)
            r = surf.get_rect(center=(sx, sy))
            pygame.draw.rect(screen, (16, 18, 26), r.inflate(6, 2), border_radius=3)
            screen.blit(surf, r.topleft)

    def _draw_top_hud(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        bar = pygame.Rect(0, 0, self.screen_width, 64)
        pygame.draw.rect(screen, (18, 22, 34), bar)
        pygame.draw.line(
            screen, (78, 96, 134), (0, bar.bottom), (self.screen_width, bar.bottom), 2
        )

        p_box = pygame.Rect(8, 7, 50, 50)
        pygame.draw.rect(screen, (32, 40, 58), p_box, border_radius=6)
        pygame.draw.rect(screen, (100, 180, 140), p_box, width=2, border_radius=6)
        screen.blit(
            self.sprites.portrait_hud,
            self.sprites.portrait_hud.get_rect(center=p_box.center).topleft,
        )

        lvl_surf = self.title_font.render(
            world.current_level.title, True, (246, 250, 255)
        )
        screen.blit(lvl_surf, (68, 4))

        bar_rect = pygame.Rect(536, 7, 256, 26)
        pygame.draw.rect(screen, (28, 34, 48), bar_rect, border_radius=4)
        if world.money_rescued > 0:
            pct = min(1.0, world.money_rescued / max(1, world.money_quota))
            fill_rect = pygame.Rect(
                bar_rect.left,
                bar_rect.top,
                int(bar_rect.width * pct),
                bar_rect.height,
            )
            pygame.draw.rect(screen, (52, 184, 98), fill_rect, border_radius=4)
        if world.money_rescued >= 0:
            bar_bd = (118, 144, 188)
            bar_fg = (255, 255, 255)
        else:
            bar_bd = (224, 92, 92)
            bar_fg = (255, 138, 138)
        pygame.draw.rect(screen, bar_bd, bar_rect, width=2, border_radius=4)
        quota_txt = self.slot_font.render(
            f"RESCUED: {_fmt_money(world.money_rescued)} / ${world.money_quota:,}",
            True,
            bar_fg,
        )
        screen.blit(quota_txt, quota_txt.get_rect(center=bar_rect.center).topleft)

        cash_rect = pygame.Rect(800, 7, 144, 26)
        cash_neg = world.cash < 0
        pygame.draw.rect(
            screen,
            (54, 24, 28) if cash_neg else (30, 44, 34),
            cash_rect,
            border_radius=4,
        )
        pygame.draw.rect(
            screen,
            (236, 86, 86) if cash_neg else (242, 200, 74),
            cash_rect,
            width=2,
            border_radius=4,
        )
        cash_txt = self.slot_font.render(
            f"CASH: {_fmt_money(world.cash)}",
            True,
            (255, 132, 132) if cash_neg else (255, 228, 108),
        )
        screen.blit(cash_txt, cash_txt.get_rect(center=cash_rect.center).topleft)

        total_secs = int(world.elapsed_time)
        mins, secs = divmod(total_secs, 60)
        clock_str = "SETUP" if not world.started else f"{mins:02d}:{secs:02d}"
        clock_col = (128, 242, 162) if not world.started else (186, 212, 244)
        t_surf = self.title_font.render(clock_str, True, clock_col)
        screen.blit(t_surf, (1052, 17))

        self.speed_btn_rect = pygame.Rect(1134, 12, 134, 38)
        if not world.started:
            pygame.draw.rect(
                screen, (38, 112, 62), self.speed_btn_rect, border_radius=5
            )
            pygame.draw.rect(
                screen, (118, 246, 152), self.speed_btn_rect, width=2, border_radius=5
            )
            s_txt = self.small_font.render("START [F]", True, (240, 255, 244))
        else:
            spd_lbl = "PAUSED" if world.paused else f"SPEED {world.sim_speed:.0f}x"
            pygame.draw.rect(screen, (42, 54, 78), self.speed_btn_rect, border_radius=5)
            pygame.draw.rect(
                screen, (140, 168, 214), self.speed_btn_rect, width=1, border_radius=5
            )
            s_txt = self.small_font.render(f"[F] {spd_lbl}", True, (240, 246, 255))
        screen.blit(s_txt, s_txt.get_rect(center=self.speed_btn_rect.center).topleft)
        self.reset_btn_rect = pygame.Rect(954, 12, 88, 38)
        pygame.draw.rect(screen, (82, 34, 38), self.reset_btn_rect, border_radius=5)
        pygame.draw.rect(
            screen, (236, 112, 104), self.reset_btn_rect, width=1, border_radius=5
        )
        r_btn_txt = self.small_font.render("RESET", True, (255, 232, 232))
        screen.blit(
            r_btn_txt, r_btn_txt.get_rect(center=self.reset_btn_rect.center).topleft
        )

        self.settings_btn_rect = pygame.Rect(800, 36, 144, 22)
        s_bg = (68, 52, 26) if self.hide_all_popups else (34, 46, 68)
        s_bd = (255, 212, 92) if self.hide_all_popups else (120, 154, 208)
        pygame.draw.rect(screen, s_bg, self.settings_btn_rect, border_radius=4)
        pygame.draw.rect(screen, s_bd, self.settings_btn_rect, width=1, border_radius=4)
        s_lbl = "[O] POPUPS OFF" if self.hide_all_popups else "[O] SETTINGS"
        s_btn_txt = self.mini_font.render(s_lbl, True, (230, 240, 255))
        screen.blit(
            s_btn_txt, s_btn_txt.get_rect(center=self.settings_btn_rect.center).topleft
        )

    def _draw_settings_modal(
        self,
        screen: pygame.Surface,
        music_vol: float,
        sfx_vol: float,
        muted: bool,
    ) -> None:
        dim = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        dim.fill((8, 10, 16, 185))
        screen.blit(dim, (0, 0))
        box = pygame.Rect(
            self.screen_width // 2 - 250, self.screen_height // 2 - 205, 500, 410
        )
        pygame.draw.rect(screen, (22, 28, 42), box, border_radius=12)
        pygame.draw.rect(screen, (118, 178, 244), box, width=2, border_radius=12)

        t_surf = self.title_font.render("SETTINGS  ([O] / [TAB])", True, (255, 224, 120))
        screen.blit(t_surf, t_surf.get_rect(center=(box.centerx, box.top + 32)).topleft)

        self.settings_toggle_rects = {}
        toggles = [
            ("hide_all", "Hide All Popups  [TAB]", bool(self.hide_all_popups)),
            ("floating", "Floating Cash & Status Popups", bool(self.show_floating_popups)),
            ("prompts", "Machine & Tile Prompts ([E], MK2)", bool(self.show_world_prompts)),
            ("labels", "Pile & Bag Labels", bool(self.show_pile_bag_labels)),
        ]
        y = box.top + 64
        for key, label, enabled in toggles:
            row = pygame.Rect(box.left + 26, y, box.width - 52, 34)
            self.settings_toggle_rects[key] = row
            pygame.draw.rect(screen, (30, 38, 56), row, border_radius=6)
            pygame.draw.rect(screen, (82, 108, 152), row, width=1, border_radius=6)
            lbl_surf = self.small_font.render(label, True, (226, 236, 250))
            screen.blit(lbl_surf, (row.left + 12, row.top + 8))
            pill = pygame.Rect(row.right - 74, row.top + 5, 62, 24)
            is_hide_row = key == "hide_all"
            on_col = (164, 62, 54) if is_hide_row else (44, 138, 82)
            off_col = (52, 62, 82)
            pygame.draw.rect(screen, on_col if enabled else off_col, pill, border_radius=4)
            st_txt = self.mini_font.render("ON" if enabled else "OFF", True, (248, 252, 255))
            screen.blit(st_txt, st_txt.get_rect(center=pill.center).topleft)
            y += 42

        y += 10
        audio_hdr = self.slot_font.render("AUDIO", True, (156, 214, 255))
        screen.blit(audio_hdr, (box.left + 26, y))
        y += 28

        def _draw_vol_row(title: str, vol: float, row_y: int) -> tuple[pygame.Rect, pygame.Rect]:
            lbl = self.small_font.render(title, True, (226, 236, 250))
            screen.blit(lbl, (box.left + 26, row_y + 6))
            minus_r = pygame.Rect(box.right - 224, row_y, 32, 28)
            bar_r = pygame.Rect(box.right - 184, row_y + 4, 104, 20)
            plus_r = pygame.Rect(box.right - 72, row_y, 32, 28)
            for br, sym in ((minus_r, "-"), (plus_r, "+")):
                pygame.draw.rect(screen, (42, 54, 78), br, border_radius=5)
                pygame.draw.rect(screen, (132, 162, 212), br, width=1, border_radius=5)
                st = self.slot_font.render(sym, True, (244, 248, 255))
                screen.blit(st, st.get_rect(center=br.center).topleft)
            pygame.draw.rect(screen, (16, 20, 30), bar_r, border_radius=4)
            fill_w = max(0, int(bar_r.width * max(0.0, min(1.0, vol))))
            if fill_w > 0:
                pygame.draw.rect(
                    screen,
                    (92, 212, 148),
                    (bar_r.left, bar_r.top, fill_w, bar_r.height),
                    border_radius=4,
                )
            pygame.draw.rect(screen, (96, 122, 166), bar_r, width=1, border_radius=4)
            pct = self.mini_font.render(f"{int(round(vol * 100))}%", True, (244, 248, 255))
            screen.blit(pct, pct.get_rect(center=bar_r.center).topleft)
            return minus_r, plus_r

        self.settings_music_minus_rect, self.settings_music_plus_rect = _draw_vol_row(
            "Music Volume", music_vol, y
        )
        y += 38
        self.settings_sfx_minus_rect, self.settings_sfx_plus_rect = _draw_vol_row(
            "SFX Volume", sfx_vol, y
        )
        y += 42

        self.settings_mute_rect = pygame.Rect(box.left + 26, y, 168, 32)
        m_bg = (144, 54, 54) if muted else (40, 74, 58)
        pygame.draw.rect(screen, m_bg, self.settings_mute_rect, border_radius=6)
        pygame.draw.rect(screen, (168, 196, 232), self.settings_mute_rect, width=1, border_radius=6)
        m_txt = self.small_font.render(
            "[V] AUDIO: MUTED" if muted else "[V] AUDIO: ON", True, (248, 252, 255)
        )
        screen.blit(m_txt, m_txt.get_rect(center=self.settings_mute_rect.center).topleft)

        self.settings_close_rect = pygame.Rect(box.right - 146, y, 120, 32)
        pygame.draw.rect(screen, (48, 62, 92), self.settings_close_rect, border_radius=6)
        pygame.draw.rect(screen, (148, 182, 236), self.settings_close_rect, width=1, border_radius=6)
        c_txt = self.small_font.render("CLOSE [ESC]", True, (248, 252, 255))
        screen.blit(c_txt, c_txt.get_rect(center=self.settings_close_rect.center).topleft)

    def _draw_reset_confirm_modal(self, screen: pygame.Surface) -> None:
        dim = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        dim.fill((8, 10, 16, 185))
        screen.blit(dim, (0, 0))
        box = pygame.Rect(
            self.screen_width // 2 - 230, self.screen_height // 2 - 105, 460, 210
        )
        pygame.draw.rect(screen, (22, 28, 42), box, border_radius=12)
        pygame.draw.rect(screen, (236, 112, 104), box, width=2, border_radius=12)

        t_surf = self.title_font.render("RESET GAME?", True, (255, 224, 120))
        screen.blit(t_surf, t_surf.get_rect(center=(box.centerx, box.top + 42)).topleft)
        s_surf = self.small_font.render(
            "Clears all rooms, machines, cash, and progress.",
            True,
            (204, 218, 240),
        )
        screen.blit(s_surf, s_surf.get_rect(center=(box.centerx, box.top + 88)).topleft)

        self.reset_confirm_yes_rect = pygame.Rect(
            box.centerx - 170, box.bottom - 68, 155, 42
        )
        self.reset_confirm_no_rect = pygame.Rect(
            box.centerx + 15, box.bottom - 68, 155, 42
        )
        pygame.draw.rect(
            screen, (156, 44, 48), self.reset_confirm_yes_rect, border_radius=6
        )
        pygame.draw.rect(
            screen,
            (255, 138, 134),
            self.reset_confirm_yes_rect,
            width=2,
            border_radius=6,
        )
        y_txt = self.label_font.render("YES, RESET", True, (255, 244, 244))
        screen.blit(
            y_txt, y_txt.get_rect(center=self.reset_confirm_yes_rect.center).topleft
        )

        pygame.draw.rect(
            screen, (46, 58, 82), self.reset_confirm_no_rect, border_radius=6
        )
        pygame.draw.rect(
            screen,
            (148, 174, 218),
            self.reset_confirm_no_rect,
            width=1,
            border_radius=6,
        )
        n_txt = self.label_font.render("CANCEL", True, (230, 238, 255))
        screen.blit(
            n_txt, n_txt.get_rect(center=self.reset_confirm_no_rect.center).topleft
        )

    def _draw_reset_confirm_modal(self, screen: pygame.Surface) -> None:
        dim = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        dim.fill((8, 10, 16, 185))
        screen.blit(dim, (0, 0))
        box = pygame.Rect(
            self.screen_width // 2 - 230, self.screen_height // 2 - 105, 460, 210
        )
        pygame.draw.rect(screen, (22, 28, 42), box, border_radius=12)
        pygame.draw.rect(screen, (236, 112, 104), box, width=2, border_radius=12)

        t_surf = self.title_font.render("RESET GAME?", True, (255, 224, 120))
        screen.blit(t_surf, t_surf.get_rect(center=(box.centerx, box.top + 42)).topleft)
        s_surf = self.small_font.render(
            "Clears all rooms, machines, cash, and progress.",
            True,
            (204, 218, 240),
        )
        screen.blit(s_surf, s_surf.get_rect(center=(box.centerx, box.top + 88)).topleft)

        self.reset_confirm_yes_rect = pygame.Rect(
            box.centerx - 170, box.bottom - 68, 155, 42
        )
        self.reset_confirm_no_rect = pygame.Rect(
            box.centerx + 15, box.bottom - 68, 155, 42
        )
        pygame.draw.rect(
            screen, (156, 44, 48), self.reset_confirm_yes_rect, border_radius=6
        )
        pygame.draw.rect(
            screen,
            (255, 138, 134),
            self.reset_confirm_yes_rect,
            width=2,
            border_radius=6,
        )
        y_txt = self.label_font.render("YES, RESET", True, (255, 244, 244))
        screen.blit(
            y_txt, y_txt.get_rect(center=self.reset_confirm_yes_rect.center).topleft
        )

        pygame.draw.rect(
            screen, (46, 58, 82), self.reset_confirm_no_rect, border_radius=6
        )
        pygame.draw.rect(
            screen,
            (148, 174, 218),
            self.reset_confirm_no_rect,
            width=1,
            border_radius=6,
        )
        n_txt = self.label_font.render("CANCEL", True, (230, 238, 255))
        screen.blit(
            n_txt, n_txt.get_rect(center=self.reset_confirm_no_rect.center).topleft
        )

    def _draw_mission_strip(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        strip = pygame.Rect(0, 64, self.screen_width, 28)
        pygame.draw.rect(screen, (26, 32, 48), strip)
        pygame.draw.line(
            screen,
            (60, 78, 112),
            (0, strip.bottom),
            (self.screen_width, strip.bottom),
            1,
        )

        mult = world.combo_multiplier
        streak_box = pygame.Rect(10, strip.top + 3, 172, 22)
        s_bg = (52, 68, 36) if mult > 1.0 else (34, 42, 58)
        s_bd = (
            (255, 212, 72)
            if mult >= 1.5
            else ((122, 236, 136) if mult > 1.0 else (84, 102, 136))
        )
        s_fg = (255, 232, 112) if mult > 1.0 else (176, 194, 224)
        pygame.draw.rect(screen, s_bg, streak_box, border_radius=4)
        pygame.draw.rect(screen, s_bd, streak_box, width=1, border_radius=4)
        s_txt = self.small_font.render(
            f"STREAK x{world.streak} ({mult:.2g}x)", True, s_fg
        )
        screen.blit(s_txt, s_txt.get_rect(center=streak_box.center).topleft)

        rate_box = pygame.Rect(self.screen_width - 178, strip.top + 3, 168, 22)
        pygame.draw.rect(screen, (28, 46, 58), rate_box, border_radius=4)
        pygame.draw.rect(screen, (88, 186, 226), rate_box, width=1, border_radius=4)
        r_txt = self.small_font.render(
            f"RATE: ${world.throughput_per_min:,}/m", True, (156, 236, 255)
        )
        screen.blit(r_txt, r_txt.get_rect(center=rate_box.center).topleft)

        if not world.started:
            mission_area = pygame.Rect(
                streak_box.right + 8,
                strip.top,
                rate_box.left - streak_box.right - 16,
                28,
            )
            mission_txt = self.small_font.render(
                "SETUP PHASE: Spend starting cash to set up belts & machines, then click START [F]!",
                True,
                (128, 246, 166),
            )
            screen.blit(
                mission_txt, mission_txt.get_rect(center=mission_area.center).topleft
            )

    def _draw_hotbar(
        self,
        screen: pygame.Surface,
        world: FactoryWorld,
        selected_tool: int | None,
        build_dir: int,
        filter_color: str,
        show_shop: bool = False,
        muted: bool = False,
        hotbar_page: int = 0,
    ) -> None:
        bar = pygame.Rect(0, self.screen_height - 86, self.screen_width, 86)
        pygame.draw.rect(screen, (18, 22, 34), bar)
        pygame.draw.line(
            screen, (78, 96, 134), (0, bar.top), (self.screen_width, bar.top), 2
        )

        self.hotbar_rects = []
        self.hotbar_tool_indices = []
        page_size = 5
        total_pages = max(1, (len(TOOLS) + page_size - 1) // page_size)
        page = hotbar_page % total_pages
        start_idx = page * page_size
        end_idx = min(len(TOOLS), start_idx + page_size)

        nav_w = 38
        slot_w = 186
        gap = 6
        prev_x = 8
        self.hotbar_prev_rect = pygame.Rect(prev_x, bar.top + 8, nav_w, 70)
        pygame.draw.rect(screen, (34, 42, 60), self.hotbar_prev_rect, border_radius=6)
        pygame.draw.rect(
            screen, (116, 142, 188), self.hotbar_prev_rect, width=1, border_radius=6
        )
        p_txt = self.title_font.render("<", True, (240, 246, 255))
        screen.blit(p_txt, p_txt.get_rect(center=self.hotbar_prev_rect.center).topleft)

        start_x = self.hotbar_prev_rect.right + gap
        hotkey_tags = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=")
        hotbar_labels: dict[str, tuple[str, str]] = {
            "belt": ("Belt", "Moves [R] dir"),
            "bouncer": ("Bouncer", "Hops 3 tiles"),
            "sorter": ("Sorter", "Splits [T] col"),
            "scanner": ("Scanner", "Diverts Fraud"),
            "shredder": ("Shredder", "Shreds Fraud"),
            "stamper": ("Stamper", "Stamps RAW"),
            "splitter": ("Splitter", "50/50 Split"),
            "endorser": ("Booster", "+$100 (1x)"),
            "fixer": ("Fixer", "Fixes ERR"),
            "polisher": ("Polisher", "Wax Seals"),
            "depot": ("Depot", "Holds 5 [U]"),
            "demolish": ("Crowbar", f"Mop -${CLEAN_DECAL_COST}/Clr"),
        }
        for slot_i in range(page_size):
            idx = start_idx + slot_i
            rect = pygame.Rect(
                start_x + slot_i * (slot_w + gap), bar.top + 8, slot_w, 70
            )
            if idx >= end_idx:
                pygame.draw.rect(screen, (22, 26, 36), rect, border_radius=6)
                pygame.draw.rect(screen, (52, 62, 84), rect, width=1, border_radius=6)
                continue
            key, name, desc = TOOLS[idx]
            self.hotbar_rects.append(rect)
            self.hotbar_tool_indices.append(idx)
            selected = selected_tool is not None and idx == selected_tool
            cost = TOOL_COSTS.get(key, 0)
            affordable = world.cash >= cost or key == "demolish"
            pygame.draw.rect(
                screen,
                (40, 56, 86) if selected else (28, 34, 48),
                rect,
                border_radius=6,
            )
            pygame.draw.rect(
                screen,
                (255, 216, 72)
                if selected
                else ((86, 104, 140) if affordable else (168, 68, 68)),
                rect,
                width=2 if selected else 1,
                border_radius=6,
            )
            short_name, short_desc = hotbar_labels.get(key, (name, desc))
            htag = hotkey_tags[idx] if idx < len(hotkey_tags) else str(idx + 1)
            title_lbl = f"[{htag}] {short_name}"
            while (
                len(title_lbl) > 6 and self.slot_font.size(title_lbl)[0] > slot_w - 10
            ):
                title_lbl = title_lbl[:-1]
            t1 = self.slot_font.render(title_lbl, True, (255, 255, 255))
            desc_lbl = short_desc
            while len(desc_lbl) > 6 and self.mini_font.size(desc_lbl)[0] > slot_w - 10:
                desc_lbl = desc_lbl[:-1]
            t2 = self.mini_font.render(desc_lbl, True, (176, 196, 228))
            if key == "demolish":
                cost_lbl = f"Free / -${CLEAN_DECAL_COST}"
                cost_col = (156, 224, 248)
            elif cost == 0:
                cost_lbl = "FREE"
                cost_col = (156, 224, 248)
            else:
                cost_lbl = f"Cost: ${cost}"
                cost_col = (108, 242, 138) if affordable else (255, 96, 96)
            t3 = self.mini_font.render(cost_lbl, True, cost_col)
            screen.blit(t1, (rect.left + 8, rect.top + 5))
            screen.blit(t2, (rect.left + 8, rect.top + 27))
            screen.blit(t3, (rect.left + 8, rect.top + 48))

        next_x = start_x + page_size * (slot_w + gap)
        self.hotbar_next_rect = pygame.Rect(next_x, bar.top + 8, nav_w, 70)
        pygame.draw.rect(screen, (34, 42, 60), self.hotbar_next_rect, border_radius=6)
        pygame.draw.rect(
            screen, (116, 142, 188), self.hotbar_next_rect, width=1, border_radius=6
        )
        n_txt = self.title_font.render(">", True, (240, 246, 255))
        screen.blit(
            n_txt,
            n_txt.get_rect(
                center=(
                    self.hotbar_next_rect.centerx,
                    self.hotbar_next_rect.centery - 7,
                )
            ).topleft,
        )
        pg_txt = self.mini_font.render(
            f"{page + 1}/{total_pages}", True, (186, 210, 244)
        )
        screen.blit(
            pg_txt,
            pg_txt.get_rect(
                midbottom=(
                    self.hotbar_next_rect.centerx,
                    self.hotbar_next_rect.bottom - 4,
                )
            ).topleft,
        )

        shop_x = self.hotbar_next_rect.right + 8
        self.shop_btn_rect = pygame.Rect(shop_x, bar.top + 8, 92, 70)
        pygame.draw.rect(
            screen,
            (84, 68, 28) if show_shop else (48, 42, 24),
            self.shop_btn_rect,
            border_radius=6,
        )
        pygame.draw.rect(
            screen, (255, 212, 82), self.shop_btn_rect, width=2, border_radius=6
        )
        u_font = (
            self.small_font
            if self.label_font.size("[B] UPGRADE")[0] > self.shop_btn_rect.width - 10
            else self.label_font
        )
        s1 = u_font.render("[B] UPGRADE", True, (255, 228, 108))
        s2 = self.mini_font.render("Global (6)", True, (224, 212, 176))
        screen.blit(
            s1,
            s1.get_rect(
                center=(self.shop_btn_rect.centerx, self.shop_btn_rect.top + 22)
            ).topleft,
        )
        screen.blit(
            s2,
            s2.get_rect(
                center=(self.shop_btn_rect.centerx, self.shop_btn_rect.top + 48)
            ).topleft,
        )

        info_x = self.shop_btn_rect.right + 8
        dir_txt = self.small_font.render(
            f"[R] Dir: {DIR_NAMES[build_dir]}", True, (255, 224, 96)
        )
        screen.blit(dir_txt, (info_x, bar.top + 8))

        c_info = CHEQUE_TYPES[filter_color]
        c_rgb = tuple(c_info["color"])  # type: ignore[arg-type]
        filt_txt = self.small_font.render(f"[T] {c_info['label']}", True, c_rgb)
        screen.blit(filt_txt, (info_x, bar.top + 31))

        pwr_lbl = f"[V]{'MUTE' if muted else 'AUD'} [N]BGM"
        pwr_col = (255, 148, 128) if muted else (156, 224, 248)
        pwr_txt = self.mini_font.render(pwr_lbl, True, pwr_col)
        screen.blit(pwr_txt, (info_x, bar.top + 54))

    def _draw_tool_preview_icon(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        tool_kind: str,
        build_dir: int,
        filter_color: str,
        world: FactoryWorld,
    ) -> None:
        ts = rect.width
        anim_shift = (world.anim_time * 32.0) % 16.0
        preview_tile = Tile(
            kind=tool_kind,
            dir_idx=build_dir % 4,
            color_key=filter_color if tool_kind == "sorter" else "payroll",
        )
        pygame.draw.rect(screen, (36, 42, 54), rect, border_radius=5)
        if tool_kind == "belt":
            self._draw_belt_tile(screen, rect, preview_tile.dir_idx, anim_shift, ts)
        elif tool_kind == "bouncer":
            self._draw_bouncer_tile(screen, rect, preview_tile, ts)
        elif tool_kind == "sorter":
            self._draw_sorter_tile(screen, rect, preview_tile, anim_shift, ts)
        elif tool_kind == "scanner":
            self._draw_scanner_tile(screen, rect, preview_tile, anim_shift, ts)
        elif tool_kind == "shredder":
            self._draw_shredder_tile(screen, rect, preview_tile, world.anim_time, ts)
        elif tool_kind == "stamper":
            self._draw_stamper_tile(screen, rect, preview_tile, anim_shift, ts)
        elif tool_kind == "splitter":
            self._draw_splitter_tile(screen, rect, preview_tile, anim_shift, ts)
        elif tool_kind == "endorser":
            self._draw_endorser_tile(screen, rect, preview_tile, anim_shift, ts, world)
        elif tool_kind == "fixer":
            self._draw_fixer_tile(
                screen, rect, preview_tile, anim_shift, ts, -1, -1, world
            )
        elif tool_kind == "polisher":
            self._draw_polisher_tile(
                screen, rect, preview_tile, anim_shift, ts, -1, -1, world
            )
        elif tool_kind == "depot":
            self._draw_depot_tile(screen, rect, preview_tile, ts, world)
        else:
            crowbar = _scale_to_height(
                self.sprites.get_frame("crowbar", world.anim_time, False),
                max(24, ts - 10),
            )
            screen.blit(crowbar, crowbar.get_rect(center=rect.center).topleft)

    def _draw_shop_modal(
        self,
        screen: pygame.Surface,
        world: FactoryWorld,
        selected_tool: int | None,
        build_dir: int,
        filter_color: str,
    ) -> None:
        dim = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        dim.fill((10, 12, 20, 198))
        screen.blit(dim, (0, 0))

        card = pygame.Rect(self.screen_width // 2 - 530, 86, 1060, 470)
        pygame.draw.rect(screen, (22, 28, 42), card, border_radius=10)
        pygame.draw.rect(screen, (255, 212, 82), card, width=3, border_radius=10)

        title = self.big_font.render("GLOBAL PLANT UPGRADES", True, (255, 218, 92))
        screen.blit(title, (card.left + 24, card.top + 10))
        comm_pct = int(round(CASH_COMMISSION_RATE * 100))
        sub = self.small_font.render(
            f"Facility-wide upgrades (valid cheques pay {comm_pct}% cash). Click any placed machine for its own MK2/MK3 upgrade.",
            True,
            (184, 204, 236),
        )
        screen.blit(sub, (card.left + 24, card.top + 45))

        wallet_box = pygame.Rect(card.right - 348, card.top + 12, 176, 38)
        cash_neg = world.cash < 0
        pygame.draw.rect(
            screen,
            (54, 24, 28) if cash_neg else (28, 44, 34),
            wallet_box,
            border_radius=6,
        )
        pygame.draw.rect(
            screen,
            (236, 86, 86) if cash_neg else (108, 242, 138),
            wallet_box,
            width=2,
            border_radius=6,
        )
        w_txt = self.label_font.render(
            f"CASH: {_fmt_money(world.cash)}",
            True,
            (255, 132, 132) if cash_neg else (255, 232, 118),
        )
        screen.blit(w_txt, w_txt.get_rect(center=wallet_box.center).topleft)

        self.shop_close_rect = pygame.Rect(card.right - 160, card.top + 12, 136, 38)
        pygame.draw.rect(screen, (68, 40, 46), self.shop_close_rect, border_radius=6)
        pygame.draw.rect(
            screen, (214, 122, 130), self.shop_close_rect, width=1, border_radius=6
        )
        c_txt = self.small_font.render("CLOSE [B/ESC]", True, (255, 226, 226))
        screen.blit(c_txt, c_txt.get_rect(center=self.shop_close_rect.center).topleft)

        self.shop_card_rects = []
        grid_x = card.left + 24

        upg_hdr = self.label_font.render(
            "GLOBAL UPGRADES (3 TIERS EACH)  —  Click or Press [F5]-[F10]",
            True,
            (132, 228, 255),
        )
        screen.blit(upg_hdr, (grid_x, card.top + 82))

        self.shop_upgrade_rects = []
        u_cols = 3
        u_card_w = 328
        u_gap_x = 14
        upg_h = 132
        u_gap_y = 14
        upg_y = card.top + 116
        upg_keys = ("F5", "F6", "F7", "F8", "F9", "F10")
        for u_idx, u_entry in enumerate(UPGRADES):
            ukey, uname, _ucost, udesc = u_entry[:4]
            r_idx = u_idx // u_cols
            c_idx = u_idx % u_cols
            urect = pygame.Rect(
                grid_x + c_idx * (u_card_w + u_gap_x),
                upg_y + r_idx * (upg_h + u_gap_y),
                u_card_w,
                upg_h,
            )
            self.shop_upgrade_rects.append(urect)
            tier = world.upgrade_tier(ukey)
            next_cost = world.upgrade_next_cost(ukey)
            maxed = tier >= UPGRADE_MAX_TIER or next_cost is None
            affordable = next_cost is not None and world.cash >= next_cost
            if maxed:
                bg = (24, 60, 42)
                bd = (104, 242, 136)
            elif tier > 0 and affordable:
                bg = (24, 48, 56)
                bd = (96, 212, 188)
            elif affordable:
                bg = (26, 36, 54)
                bd = (96, 178, 232)
            else:
                bg = (44, 28, 34)
                bd = (188, 78, 78)
            pygame.draw.rect(screen, bg, urect, border_radius=7)
            pygame.draw.rect(
                screen,
                bd,
                urect,
                width=2 if (maxed or tier > 0) else 1,
                border_radius=7,
            )

            status_str = "MAXED" if maxed else f"${next_cost}"
            st_fg = (122, 248, 146) if (maxed or affordable) else (255, 114, 114)
            st_bg = (32, 66, 44) if (maxed or affordable) else (76, 30, 36)
            st_surf = self.small_font.render(status_str, True, st_fg)
            st_box = pygame.Rect(
                urect.right - st_surf.get_width() - 18,
                urect.top + 6,
                st_surf.get_width() + 12,
                21,
            )
            pygame.draw.rect(screen, st_bg, st_box, border_radius=4)
            pygame.draw.rect(screen, st_fg, st_box, width=1, border_radius=4)
            screen.blit(st_surf, st_surf.get_rect(center=st_box.center).topleft)

            title_str = f"[{upg_keys[u_idx]}] {uname}"
            title_font = (
                self.label_font
                if self.label_font.size(title_str)[0] <= st_box.left - urect.left - 14
                else self.small_font
            )
            u_title = title_font.render(title_str, True, (255, 255, 255))
            screen.blit(u_title, (urect.left + 10, urect.top + 7))

            u_max_px = urect.width - 20
            u_lines: list[str] = []
            u_cur: list[str] = []
            for w in udesc.split(" "):
                cand = " ".join(u_cur + [w])
                if self.small_font.size(cand)[0] <= u_max_px or not u_cur:
                    u_cur.append(w)
                else:
                    u_lines.append(" ".join(u_cur))
                    u_cur = [w]
            if u_cur:
                u_lines.append(" ".join(u_cur))
            for li, line_str in enumerate(u_lines[:2]):
                desc_surf = self.small_font.render(line_str, True, (198, 218, 244))
                screen.blit(desc_surf, (urect.left + 10, urect.top + 31 + li * 17))

            tier_lbl = self.mini_font.render(
                f"T{tier}/{UPGRADE_MAX_TIER}",
                True,
                (122, 248, 146)
                if maxed
                else ((132, 228, 255) if tier > 0 else (164, 182, 206)),
            )
            screen.blit(tier_lbl, (urect.left + 10, urect.bottom - 20))
            pip_x0 = urect.left + 50
            pip_y = urect.bottom - 16
            pip_w = 34
            pip_gap = 6
            for t_i in range(UPGRADE_MAX_TIER):
                prect = pygame.Rect(pip_x0 + t_i * (pip_w + pip_gap), pip_y, pip_w, 7)
                if t_i < tier:
                    p_fill = (104, 242, 136) if maxed else (96, 224, 255)
                elif t_i == tier and affordable:
                    p_fill = (82, 128, 172)
                else:
                    p_fill = (44, 54, 72)
                pygame.draw.rect(screen, p_fill, prect, border_radius=3)
                pygame.draw.rect(
                    screen, (92, 114, 144), prect, width=1, border_radius=3
                )

        foot = self.small_font.render(
            "Click / [F5]-[F10] Buy Global Upgrade   |   Click a placed machine (or press [E / U]) for machine MK2/MK3 upgrades",
            True,
            (164, 206, 242),
        )
        screen.blit(foot, (card.centerx - foot.get_width() // 2, card.bottom - 28))

    def _draw_story_modal(self, screen: pygame.Surface) -> None:
        # Full-screen opaque industrial blueprint backdrop so background/HUD cannot show through.
        screen.fill((12, 16, 26))
        for gx in range(0, self.screen_width, 48):
            pygame.draw.line(screen, (19, 25, 40), (gx, 0), (gx, self.screen_height), 1)
        for gy in range(0, self.screen_height, 48):
            pygame.draw.line(screen, (19, 25, 40), (0, gy), (self.screen_width, gy), 1)

        card = pygame.Rect(self.screen_width // 2 - 540, 26, 1080, 668)
        pygame.draw.rect(screen, (20, 26, 40), card, border_radius=12)
        pygame.draw.rect(screen, (255, 212, 82), card, width=3, border_radius=12)

        hdr = pygame.Rect(card.left + 3, card.top + 3, card.width - 6, 78)
        pygame.draw.rect(
            screen,
            (15, 20, 32),
            hdr,
            border_top_left_radius=10,
            border_top_right_radius=10,
        )
        pygame.draw.line(
            screen,
            (94, 118, 164),
            (card.left + 20, hdr.bottom),
            (card.right - 20, hdr.bottom),
            1,
        )

        title = self.big_font.render("CHEQUE MATE", True, (255, 220, 92))
        screen.blit(title, (card.left + 26, card.top + 6))
        sub = self.label_font.render(
            "CENTRAL CHEQUE PROCESSING PLANT  —  SHIFT BRIEFING",
            True,
            (154, 206, 248),
        )
        screen.blit(sub, (card.left + 26, card.top + 48))

        tag_box = pygame.Rect(card.right - 386, card.top + 22, 360, 36)
        pygame.draw.rect(screen, (28, 38, 58), tag_box, border_radius=6)
        pygame.draw.rect(screen, (94, 138, 198), tag_box, width=1, border_radius=6)
        tag_txt = self.small_font.render(
            "4 WINGS  |  11 TOOLS  |  6x3 UPGRADES", True, (204, 228, 255)
        )
        screen.blit(tag_txt, tag_txt.get_rect(center=tag_box.center).topleft)

        col_top = card.top + 92
        left_x = card.left + 26
        col_w = 280

        p_frame = pygame.Rect(left_x, col_top, col_w, 186)
        pygame.draw.rect(screen, (28, 38, 56), p_frame, border_radius=8)
        pygame.draw.rect(screen, (96, 176, 136), p_frame, width=2, border_radius=8)
        screen.blit(
            self.sprites.portrait_story,
            self.sprites.portrait_story.get_rect(
                center=(p_frame.centerx, p_frame.centery - 10)
            ).topleft,
        )
        op_lbl = self.small_font.render("OPERATOR: NIGHT SHIFT", True, (172, 232, 196))
        screen.blit(
            op_lbl,
            op_lbl.get_rect(center=(p_frame.centerx, p_frame.bottom - 16)).topleft,
        )

        ledger = pygame.Rect(left_x, p_frame.bottom + 14, col_w, 268)
        pygame.draw.rect(screen, (26, 34, 52), ledger, border_radius=8)
        pygame.draw.rect(screen, (72, 92, 132), ledger, width=1, border_radius=8)
        led_hdr = self.label_font.render("CHEQUE VALUES & FRAUD", True, (255, 220, 92))
        screen.blit(led_hdr, (ledger.left + 12, ledger.top + 10))

        ledger_rows = (
            ("payroll", "PAYROLL (45s)", "+$450 Quota", (66, 206, 114)),
            ("rent", "RENT (44s)", "+$520 Quota", (244, 198, 62)),
            ("vip", "VIP (28s+Pol)", "+$850 Quota", (68, 148, 250)),
            ("mortgage", "MORTGAGE (60s)", "+$650 Quota", (186, 128, 244)),
            ("void", "VOID/FAKE", "Shred / -Fine!", (232, 62, 62)),
        )
        for r_i, (_ckey, cname, cval, crgb) in enumerate(ledger_rows):
            ry = ledger.top + 40 + r_i * 44
            row_r = pygame.Rect(ledger.left + 10, ry, ledger.width - 20, 38)
            pygame.draw.rect(screen, (34, 42, 62), row_r, border_radius=5)
            pygame.draw.rect(
                screen, crgb, (row_r.left + 8, row_r.top + 10, 11, 18), border_radius=2
            )
            n_surf = self.small_font.render(cname, True, (238, 244, 255))
            v_surf = self.small_font.render(
                cval, True, (255, 132, 132) if _ckey == "void" else (152, 242, 174)
            )
            screen.blit(n_surf, (row_r.left + 26, row_r.top + 9))
            screen.blit(v_surf, (row_r.right - v_surf.get_width() - 8, row_r.top + 9))

        right_x = left_x + col_w + 22
        right_w = card.right - 26 - right_x

        story_box = pygame.Rect(right_x, col_top, right_w, 184)
        pygame.draw.rect(screen, (26, 34, 52), story_box, border_radius=8)
        pygame.draw.rect(screen, (72, 92, 132), story_box, width=1, border_radius=8)
        st_hdr = self.label_font.render("DISPATCH BRIEFING", True, (132, 228, 255))
        screen.blit(st_hdr, (story_box.left + 14, story_box.top + 10))
        y_txt = story_box.top + 38
        for line in STORY_LINES:
            if not line:
                y_txt += 10
                continue
            surf = self.small_font.render(line, True, (226, 236, 252))
            screen.blit(surf, (story_box.left + 14, y_txt))
            y_txt += 23

        rules_y = story_box.bottom + 14
        comm_pct = int(round(CASH_COMMISSION_RATE * 100))
        rule_cards = (
            (
                f"{comm_pct}% COMMISSION",
                f"Valid deliveries add 100% Quota and pay {comm_pct}% Cash.",
                (98, 232, 138),
            ),
            (
                "PAID CLEANUP",
                f"Mop oil slicks -${CLEAN_DECAL_COST} cash; clear floor piles -${CLEAR_PILEUP_COST}.",
                (255, 206, 82),
            ),
            (
                "FINES & DEBT",
                "Neglect, drops & fraud go negative if ignored!",
                (255, 108, 108),
            ),
        )
        r_w = (right_w - 28) // 3
        for rc_i, (r_title, r_body, r_col) in enumerate(rule_cards):
            rr = pygame.Rect(right_x + rc_i * (r_w + 14), rules_y, r_w, 140)
            pygame.draw.rect(screen, (26, 34, 52), rr, border_radius=8)
            pygame.draw.rect(screen, r_col, rr, width=1, border_radius=8)
            rt = self.slot_font.render(r_title, True, r_col)
            screen.blit(rt, (rr.left + 12, rr.top + 10))
            max_rw = rr.width - 24
            r_lines: list[str] = []
            r_cur: list[str] = []
            for w in r_body.split(" "):
                cand = " ".join(r_cur + [w])
                if self.small_font.size(cand)[0] <= max_rw or not r_cur:
                    r_cur.append(w)
                else:
                    r_lines.append(" ".join(r_cur))
                    r_cur = [w]
            if r_cur:
                r_lines.append(" ".join(r_cur))
            for li, lstr in enumerate(r_lines[:4]):
                ls = self.small_font.render(lstr, True, (212, 224, 246))
                screen.blit(ls, (rr.left + 12, rr.top + 38 + li * 22))

        ctrl_box = pygame.Rect(right_x, rules_y + 154, right_w, 116)
        pygame.draw.rect(screen, (26, 34, 52), ctrl_box, border_radius=8)
        pygame.draw.rect(screen, (72, 92, 132), ctrl_box, width=1, border_radius=8)
        c_hdr = self.label_font.render(
            "CONTROLS QUICK REFERENCE", True, (132, 228, 255)
        )
        screen.blit(c_hdr, (ctrl_box.left + 14, ctrl_box.top + 8))
        ctrl_lines = (
            "[WASD] Walk/Drive  [G] Forklift  [X] Lift/Place Machine  [E] Act / Upg  [U] Upg Machine",
            "[1-9,0,-] Part  [R] Rotate  [T] Filter Color  [B] Shop  [V] Mute  [N] Next Track",
            "[Left Drag] Paint Belts  [Right Drag] Crowbar/Mop  [F1-F4] View Room  [SPACE] Jump",
        )
        for ci, cline in enumerate(ctrl_lines):
            cs = self.small_font.render(cline, True, (206, 222, 246))
            screen.blit(cs, (ctrl_box.left + 14, ctrl_box.top + 36 + ci * 24))

        self.modal_btn_rect = pygame.Rect(card.centerx - 210, card.bottom - 66, 420, 52)
        pygame.draw.rect(screen, (44, 168, 86), self.modal_btn_rect, border_radius=8)
        pygame.draw.rect(
            screen, (186, 252, 206), self.modal_btn_rect, width=2, border_radius=8
        )
        btn_txt = self.title_font.render(
            "START SHIFT  [ENTER / CLICK]", True, (255, 255, 255)
        )
        screen.blit(
            btn_txt, btn_txt.get_rect(center=self.modal_btn_rect.center).topleft
        )

    def _draw_star(
        self,
        screen: pygame.Surface,
        cx: int,
        cy: int,
        outer_r: float,
        inner_r: float,
        fill_col: tuple[int, int, int],
        border_col: tuple[int, int, int],
    ) -> None:
        pts: list[tuple[int, int]] = []
        for i in range(10):
            ang = -math.pi * 0.5 + i * (math.pi / 5.0)
            rad = outer_r if i % 2 == 0 else inner_r
            pts.append(
                (
                    int(round(cx + math.cos(ang) * rad)),
                    int(round(cy + math.sin(ang) * rad)),
                )
            )
        pygame.draw.polygon(screen, fill_col, pts)
        pygame.draw.polygon(screen, border_col, pts, width=2)

    def _draw_end_modal(self, screen: pygame.Surface, world: FactoryWorld) -> None:
        dim = pygame.Surface((self.screen_width, self.screen_height), pygame.SRCALPHA)
        dim.fill((10, 12, 20, 185))
        screen.blit(dim, (0, 0))

        card = pygame.Rect(
            self.screen_width // 2 - 390, self.screen_height // 2 - 175, 780, 350
        )
        pygame.draw.rect(screen, (22, 28, 42), card, border_radius=10)
        accent = (88, 232, 126) if world.level_complete else (245, 88, 88)
        pygame.draw.rect(screen, accent, card, width=3, border_radius=10)

        if world.level_complete:
            heading = "ALL 4 ROOMS RESTORED! HERO OF THE PLANT!"
            btn_label = "NEW SHIFT  [ENTER]"
        else:
            heading = "SHIFT ENDED — CHEQUES STILL TRAPPED!"
            btn_label = "RETRY WING  [ENTER]"

        t1 = self.title_font.render(heading, True, accent)
        screen.blit(t1, (card.centerx - t1.get_width() // 2, card.top + 22))

        stars = world.star_rating
        for s_idx in range(3):
            sx = card.centerx + (s_idx - 1) * 52
            sy = card.top + 78
            earned = s_idx < stars
            self._draw_star(
                screen,
                sx,
                sy,
                19.0 if earned else 16.0,
                8.5 if earned else 7.0,
                (255, 214, 68) if earned else (44, 52, 70),
                (255, 246, 178) if earned else (96, 112, 142),
            )

        t2 = self.label_font.render(
            f"Money Rescued: {_fmt_money(world.money_rescued)} / ${world.money_quota:,}   |   Cash Left: {_fmt_money(world.cash)}",
            True,
            (244, 248, 255),
        )
        total_tiers = sum(world.upgrades.values())
        max_tiers = len(UPGRADES) * UPGRADE_MAX_TIER
        t3 = self.label_font.render(
            f"Fines: -${world.neglect_penalties:,}  |  Err: {world.wrong_deliveries}  |  Streak: x{world.max_streak}  |  Upgrades: {total_tiers}/{max_tiers}",
            True,
            (196, 214, 244),
        )

        screen.blit(t2, (card.centerx - t2.get_width() // 2, card.top + 120))
        screen.blit(t3, (card.centerx - t3.get_width() // 2, card.top + 154))

        self.modal_btn_rect = pygame.Rect(card.centerx - 190, card.bottom - 88, 380, 48)
        pygame.draw.rect(
            screen,
            (48, 174, 88) if world.level_complete else (186, 62, 62),
            self.modal_btn_rect,
            border_radius=6,
        )
        pygame.draw.rect(
            screen, (240, 248, 255), self.modal_btn_rect, width=2, border_radius=6
        )
        b_txt = self.title_font.render(btn_label, True, (255, 255, 255))
        screen.blit(b_txt, b_txt.get_rect(center=self.modal_btn_rect.center).topleft)
        if world.level_complete:
            esc_txt = self.small_font.render(
                "[ESC] Keep running this bay", True, (186, 212, 244)
            )
            screen.blit(
                esc_txt, (card.centerx - esc_txt.get_width() // 2, card.bottom - 30)
            )

    def _draw_arrow_triangle(
        self,
        screen: pygame.Surface,
        center: tuple[int, int],
        dir_idx: int,
        size: int,
        color: tuple[int, int, int],
    ) -> None:
        cx, cy = center
        if dir_idx == 0:
            pts = [(cx, cy - size), (cx - size, cy + size), (cx + size, cy + size)]
        elif dir_idx == 1:
            pts = [(cx + size, cy), (cx - size, cy - size), (cx - size, cy + size)]
        elif dir_idx == 2:
            pts = [(cx, cy + size), (cx - size, cy - size), (cx + size, cy - size)]
        else:
            pts = [(cx - size, cy), (cx + size, cy - size), (cx + size, cy + size)]
        pygame.draw.polygon(screen, color, pts)
