from __future__ import annotations

import asyncio
import math
import sys
from array import array
from pathlib import Path
import random
import pygame

from factory_data import CHEQUE_ORDER, DIRS, LEVELS, TOOLS, UPGRADES
from factory_renderer import (
    ChequeSprites,
    FactoryRenderer,
    ForkliftSprites,
    ThiefSprites,
    _load_ui_font,
)
from factory_sim import FactoryWorld, FloatingText

FPS = 60
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720

PLAY_TOP_Y = 90
PLAY_BOTTOM_Y = SCREEN_HEIGHT - 84
MUSIC_DIR = Path(__file__).resolve().parent.parent / "assets" / "music"
INTRO_DIR = Path(__file__).resolve().parent.parent / "assets" / "intro"
_TRACK_TITLE_MAP: dict[str, str] = {
    "lukrembo_affogato": "Lukrembo - Affogato",
    "massobeats_peach_prosecco": "massobeats - Peach Prosecco",
}


def _format_track_title(path: Path) -> str:
    if path.stem in _TRACK_TITLE_MAP:
        return _TRACK_TITLE_MAP[path.stem]
    return path.stem.replace("_", " ").replace("-", " ").title()


class SoundBank:
    """Procedural WebAssembly-safe SFX plus streaming OGG background music playlist."""

    def __init__(
        self,
        sounds: dict[str, pygame.mixer.Sound],
        music_tracks: list[tuple[str, Path]] | None = None,
    ) -> None:
        self.sounds = sounds
        self.music_tracks: list[tuple[str, Path]] = list(music_tracks or [])
        self.current_track_idx: int = 0
        self.music_volume: float = 0.42
        self.sfx_volume: float = 1.0
        self.music_started: bool = False

    @classmethod
    def _discover_music_tracks(cls) -> list[tuple[str, Path]]:
        if not MUSIC_DIR.is_dir():
            return []
        tracks: list[tuple[str, Path]] = []
        seen_stems: set[str] = set()
        for ext in ("*.ogg", "*.mp3", "*.wav"):
            for path in sorted(MUSIC_DIR.glob(ext)):
                if path.stem in seen_stems:
                    continue
                seen_stems.add(path.stem)
                tracks.append((_format_track_title(path), path))
        return tracks

    @classmethod
    def load(cls) -> SoundBank:
        sounds: dict[str, pygame.mixer.Sound] = {}
        music_tracks = cls._discover_music_tracks()
        try:
            init_info = pygame.mixer.get_init()
            if init_info is None and sys.platform != "emscripten":
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
                init_info = pygame.mixer.get_init()
            if init_info is None:
                return cls(sounds, music_tracks)
            freq, _fmt, channels = init_info
            sounds["place"] = cls._synth_sweep(freq, channels, 260, 390, 0.06, 0.22)
            sounds["remove"] = cls._synth_sweep(freq, channels, 310, 150, 0.07, 0.20)
            sounds["interact"] = cls._synth_sweep(freq, channels, 420, 660, 0.09, 0.24)
            sounds["bounce"] = cls._synth_sweep(freq, channels, 220, 680, 0.12, 0.26)
            sounds["stamp"] = cls._synth_sweep(freq, channels, 520, 420, 0.07, 0.22)
            sounds["shred"] = cls._synth_noise(freq, channels, 0.10, 0.22)
            sounds["deliver"] = cls._synth_chord(
                freq, channels, (523.25, 659.25, 783.99), 0.15, 0.24
            )
            sounds["upgrade"] = cls._synth_chord(
                freq, channels, (587.33, 739.99, 880.0, 1174.66), 0.22, 0.28
            )
            sounds["win"] = cls._synth_chord(
                freq, channels, (523.25, 659.25, 783.99, 1046.5), 0.34, 0.30
            )
            sounds["error"] = cls._synth_sweep(freq, channels, 190, 110, 0.14, 0.26)
        except Exception:
            return cls({}, music_tracks)
        return cls(sounds, music_tracks)

    @staticmethod
    def _build_sound(freq: int, channels: int, mono: list[int]) -> pygame.mixer.Sound:
        if channels >= 2:
            buf = array("h")
            for s in mono:
                for _ in range(channels):
                    buf.append(s)
        else:
            buf = array("h", mono)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    @classmethod
    def _synth_sweep(
        cls, freq: int, channels: int, f0: float, f1: float, dur: float, vol: float
    ) -> pygame.mixer.Sound:
        n = max(1, int(freq * dur))
        amp = int(32767 * vol)
        phase = 0.0
        samples: list[int] = []
        for i in range(n):
            t = i / n
            hz = f0 + (f1 - f0) * t
            phase += 2.0 * math.pi * hz / freq
            env = min(1.0, i / max(1, n * 0.08)) * (1.0 - t)
            samples.append(max(-32767, min(32767, int(math.sin(phase) * env * amp))))
        return cls._build_sound(freq, channels, samples)

    @classmethod
    def _synth_chord(
        cls, freq: int, channels: int, notes: tuple[float, ...], dur: float, vol: float
    ) -> pygame.mixer.Sound:
        n = max(1, int(freq * dur))
        amp = int(32767 * vol / max(1, len(notes)))
        samples: list[int] = []
        for i in range(n):
            t = i / n
            env = min(1.0, i / max(1, n * 0.06)) * (1.0 - t) ** 0.75
            val = sum(math.sin(2.0 * math.pi * hz * (i / freq)) for hz in notes)
            samples.append(max(-32767, min(32767, int(val * env * amp))))
        return cls._build_sound(freq, channels, samples)

    @classmethod
    def _synth_noise(
        cls, freq: int, channels: int, dur: float, vol: float
    ) -> pygame.mixer.Sound:
        n = max(1, int(freq * dur))
        amp = int(32767 * vol)
        state = 0x13579BDF
        samples: list[int] = []
        for i in range(n):
            state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
            noise = ((state >> 16) / 32767.5) - 1.0
            env = 1.0 - (i / n)
            samples.append(max(-32767, min(32767, int(noise * env * amp))))
        return cls._build_sound(freq, channels, samples)

    def set_sfx_volume(self, vol: float) -> None:
        self.sfx_volume = max(0.0, min(1.0, float(vol)))
        for snd in self.sounds.values():
            try:
                snd.set_volume(self.sfx_volume)
            except Exception:
                pass

    def set_music_volume(self, vol: float, muted: bool = False) -> None:
        self.music_volume = max(0.0, min(1.0, float(vol)))
        self.set_muted(muted)

    def play(self, name: str) -> None:
        if self.sfx_volume <= 0.0:
            return
        snd = self.sounds.get(name)
        if snd is not None:
            try:
                snd.set_volume(self.sfx_volume)
                snd.play()
            except Exception:
                pass

    @staticmethod
    def _web_music():
        if sys.platform != "emscripten":
            return None
        try:
            import platform

            return getattr(platform.window, "cmMusic", None)
        except Exception:
            return None

    def start_music(self, track_idx: int | None = None, muted: bool = False) -> bool:
        if not self.music_tracks:
            return False
        if track_idx is not None:
            self.current_track_idx = track_idx % len(self.music_tracks)
        _title, track_path = self.music_tracks[self.current_track_idx]
        if not track_path.is_file():
            return False
        wm = self._web_music()
        if wm is not None:
            try:
                ok = bool(
                    wm.play(
                        f"assets/music/{track_path.name}",
                        0.0 if muted else self.music_volume,
                    )
                )
                self.music_started = ok
                return ok
            except Exception:
                return False
        try:
            if pygame.mixer.get_init() is None:
                return False
            pygame.mixer.music.load(str(track_path))
            pygame.mixer.music.set_volume(0.0 if muted else self.music_volume)
            pygame.mixer.music.play(0)
            self.music_started = True
            return True
        except Exception:
            return False

    def update_music(self, muted: bool = False) -> None:
        if not self.music_tracks or muted:
            return
        wm = self._web_music()
        if wm is not None:
            try:
                if not self.music_started:
                    self.start_music(self.current_track_idx, muted=muted)
                    return
                if not wm.isBusy():
                    nxt = (self.current_track_idx + 1) % len(self.music_tracks)
                    self.start_music(nxt, muted=muted)
            except Exception:
                pass
            return
        try:
            if pygame.mixer.get_init() is None:
                return
            if not self.music_started:
                self.start_music(self.current_track_idx, muted=muted)
                return
            if not pygame.mixer.music.get_busy():
                nxt = (self.current_track_idx + 1) % len(self.music_tracks)
                self.start_music(nxt, muted=muted)
        except Exception:
            pass

    def next_track(self, muted: bool = False) -> str:
        if not self.music_tracks:
            return "No Tracks"
        nxt = (self.current_track_idx + 1) % len(self.music_tracks)
        self.current_track_idx = nxt
        title, _path = self.music_tracks[nxt]
        self.start_music(nxt, muted=muted)
        return title

    def set_muted(self, muted: bool) -> None:
        wm = self._web_music()
        if wm is not None:
            try:
                wm.setVolume(0.0 if muted else self.music_volume)
                if not muted and (not self.music_started or not wm.isBusy()):
                    self.start_music(self.current_track_idx, muted=False)
            except Exception:
                pass
            return
        try:
            if pygame.mixer.get_init() is None:
                return
            pygame.mixer.music.set_volume(0.0 if muted else self.music_volume)
            if not muted and (
                not self.music_started or not pygame.mixer.music.get_busy()
            ):
                self.start_music(self.current_track_idx, muted=False)
        except Exception:
            pass


class BounceTheChequesGame:
    """Top-level game controller coordinating input, simulation, camera follow, and HUD."""

    def __init__(
        self,
        sprites: ThiefSprites,
        cheque_sprites: ChequeSprites,
        sfx: SoundBank | None = None,
        forklift_sprites: ForkliftSprites | None = None,
    ) -> None:
        self.world = FactoryWorld(level_idx=0)
        self.renderer = FactoryRenderer(
            SCREEN_WIDTH, SCREEN_HEIGHT, sprites, cheque_sprites, forklift_sprites
        )
        self.sfx = sfx if sfx is not None else SoundBank.load()
        self.renderer.reset_camera(
            self.world.cols, self.world.rows, self.world.player_x, self.world.player_y
        )

        self.show_story = True
        self.show_reset_confirm = False
        self.show_settings = False
        self.intro_stage = "manor"  # manor -> facility_ext -> office_int
        self.intro_px = 0.50
        self.intro_py = 0.39
        self.intro_facing_left = False
        self.intro_moving = False
        self.intro_timer = 0.0
        self.intro_fade_phase = "in"  # "in", "none", "out"
        self.intro_fade_alpha = 255.0
        self.intro_pending_stage: str | None = None
        self.intro_skip_rect = pygame.Rect(SCREEN_WIDTH - 164, 16, 144, 34)
        self.intro_desk_note: tuple[str, str] | None = None
        self.intro_viewed_desks: set[str] = set()
        self.intro_surfaces: dict[str, pygame.Surface] = self._load_intro_surfaces()
        self.intro_car_surf: pygame.Surface | None = self._load_intro_car()
        self.show_shop = False
        self.keep_playing = False
        self.muted = False
        self.selected_tool: int | None = 0
        self.hotbar_page = 0
        self.build_dir = 1  # East
        self.filter_color_idx = 0
        self.mouse_pos: tuple[int, int] = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)

        self.painting_place = False
        self.painting_remove = False
        self.panning = False
        self.minimap_dragging = False
        self.last_painted_tile: tuple[int, int] | None = None
        self.held_keys: set[int] = set()
        self.selected_part_tile: tuple[int, int] | None = None
        self.part_menu_tile: tuple[int, int] | None = None
        self.part_menu_pos: tuple[int, int] = (0, 0)
        self.sfx.start_music(0, muted=self.muted)

    @property
    def tool_kind(self) -> str:
        if self.selected_tool is None:
            return ""
        return TOOLS[self.selected_tool][0]

    @staticmethod
    def _load_intro_surfaces() -> dict[str, pygame.Surface]:
        out: dict[str, pygame.Surface] = {}
        for key in ("manor", "facility_ext", "office_int"):
            path = INTRO_DIR / f"{key}.png"
            if path.is_file():
                try:
                    raw = pygame.image.load(str(path))
                    if pygame.display.get_surface() is not None:
                        raw = raw.convert()
                    out[key] = pygame.transform.smoothscale(raw, (SCREEN_WIDTH, SCREEN_HEIGHT))
                except Exception:
                    pass
        return out

    @staticmethod
    def _load_intro_car() -> pygame.Surface | None:
        path = INTRO_DIR / "car.png"
        if not path.is_file():
            return None
        try:
            raw = pygame.image.load(str(path))
            if pygame.display.get_surface() is not None:
                raw = raw.convert_alpha()
            return raw
        except Exception:
            return None

    def _finish_intro(self) -> None:
        self.show_story = False
        self.world.player_x = 5.5
        self.world.player_y = 3.5
        self.renderer.reset_camera(
            self.world.cols, self.world.rows, self.world.player_x, self.world.player_y
        )
        self.sfx.update_music(muted=self.muted)

    def close_all_menus(self) -> bool:
        """Close any open UI overlay/menu; returns True if anything was open."""
        was_open = bool(
            self.show_story
            or self.show_shop
            or getattr(self, "show_settings", False)
            or getattr(self, "show_reset_confirm", False)
            or self.part_menu_tile is not None
            or self._showing_end_modal
        )
        if self.show_story:
            self.show_story = False
            self.sfx.update_music(muted=self.muted)
        if self._showing_end_modal:
            self.keep_playing = True
        self.show_shop = False
        self.show_settings = False
        self.show_reset_confirm = False
        self.part_menu_tile = None
        self.selected_part_tile = None
        return was_open

    def select_tool_slot(self, idx: int | None) -> None:
        """Select a hotbar tool index, or toggle back to nothing (None) if already selected."""
        if idx is None or self.selected_tool == idx:
            self.selected_tool = None
        else:
            self.selected_tool = idx
        self.show_shop = False

    @property
    def filter_color(self) -> str:
        return CHEQUE_ORDER[self.filter_color_idx]

    @property
    def _showing_end_modal(self) -> bool:
        return (
            self.world.level_complete or self.world.level_failed
        ) and not self.keep_playing

    def _in_play_viewport(self, pos: tuple[int, int]) -> bool:
        return PLAY_TOP_Y <= pos[1] <= PLAY_BOTTOM_Y

    def _cycle_speed(self) -> None:
        if not self.world.started:
            self.world.start_game()
            return
        if self.world.paused:
            self.world.paused = False
            self.world.sim_speed = 1.0
        elif self.world.sim_speed < 1.5:
            self.world.sim_speed = 2.0
        else:
            self.world.paused = True

    def _reset_level(self) -> None:
        self.keep_playing = False
        self.show_shop = False
        self.show_reset_confirm = False
        self.world.load_level(self.world.level_idx)
        self.renderer.reset_camera(
            self.world.cols, self.world.rows, self.world.player_x, self.world.player_y
        )

    def _reset_game(self) -> None:
        self.keep_playing = False
        self.show_shop = False
        self.show_reset_confirm = False
        self.selected_tool = None
        self.selected_part_tile = None
        self.part_menu_tile = None
        self.world.load_level(0)
        self.renderer.reset_camera(
            self.world.cols, self.world.rows, self.world.player_x, self.world.player_y
        )

    def _advance_or_retry(self) -> None:
        self.keep_playing = False
        self.show_shop = False
        self.world.load_level(0)
        self.renderer.reset_camera(
            self.world.cols, self.world.rows, self.world.player_x, self.world.player_y
        )

    def _movement_axes(self) -> tuple[float, float, bool]:
        keys = pygame.key.get_pressed()

        def is_down(k: int) -> bool:
            return k in self.held_keys or bool(keys[k])

        dx = 0.0
        dy = 0.0
        if is_down(pygame.K_a) or is_down(pygame.K_LEFT):
            dx -= 1.0
        if is_down(pygame.K_d) or is_down(pygame.K_RIGHT):
            dx += 1.0
        if is_down(pygame.K_w) or is_down(pygame.K_UP):
            dy -= 1.0
        if is_down(pygame.K_s) or is_down(pygame.K_DOWN):
            dy += 1.0
        sprinting = is_down(pygame.K_LSHIFT) or is_down(pygame.K_RSHIFT)
        return dx, dy, sprinting

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Process one pygame event; return False to quit the application."""
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
            if self.show_story:
                self.panning = False
                self.minimap_dragging = False
                return True
            if self.panning:
                self.renderer.pan(event.rel[0], event.rel[1])
            elif self.minimap_dragging:
                wpos = self.renderer.minimap_to_world(
                    *event.pos, self.world.cols, self.world.rows
                )
                if wpos is not None:
                    self.renderer.center_camera_at(
                        wpos[0], wpos[1], self.world.cols, self.world.rows
                    )
            elif (
                not self.world.paused
                and not self._showing_end_modal
                and not self.show_shop
                and self._in_play_viewport(event.pos)
            ):
                tile = self.renderer.screen_to_tile(*event.pos)
                if tile != self.last_painted_tile:
                    if self.painting_place and self.selected_tool is not None:
                        if (
                            self.tool_kind == "belt"
                            and self.last_painted_tile is not None
                        ):
                            dc = tile[0] - self.last_painted_tile[0]
                            dr = tile[1] - self.last_painted_tile[1]
                            if abs(dc) + abs(dr) == 1:
                                drag_dir = DIRS.index((dc, dr))
                                self.build_dir = drag_dir
                                lx, ly = self.last_painted_tile
                                if (
                                    self.world.in_bounds(lx, ly)
                                    and self.world.grid[ly][lx].kind == "belt"
                                ):
                                    self.world.grid[ly][lx].dir_idx = drag_dir
                        if self.world.in_build_reach(*tile):
                            self.world.place_tile(
                                tile[0],
                                tile[1],
                                self.tool_kind,
                                self.build_dir,
                                self.filter_color,
                            )
                            self.last_painted_tile = tile
                    elif self.painting_remove and self.world.in_build_reach(*tile):
                        self.world.remove_tile(
                            tile[0], tile[1], allow_clean=(self.tool_kind == "demolish")
                        )
                        self.last_painted_tile = tile
            return True

        if event.type == pygame.MOUSEWHEEL:
            if self.show_story or self.show_shop or self._showing_end_modal:
                return True
            factor = 1.1 if event.y > 0 else (1.0 / 1.1)
            self.renderer.zoom_at(factor, self.mouse_pos)
            return True

        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.painting_place = False
                self.minimap_dragging = False
                self.last_painted_tile = None
            elif event.button == 2:
                self.panning = False
            elif event.button == 3:
                self.painting_remove = False
                self.last_painted_tile = None
            return True

        if event.type == pygame.MOUSEBUTTONDOWN:
            self.mouse_pos = event.pos
            return self._handle_mouse_down(event.button, event.pos)

        if event.type == pygame.KEYUP:
            self.held_keys.discard(event.key)
            return True

        if event.type == pygame.KEYDOWN:
            self.held_keys.add(event.key)
            return self._handle_key_down(event.key)

        return True

    OFFICE_DESKS: tuple[tuple[float, float, float, float, str, str], ...] = (
        (
            0.11,
            0.30,
            0.24,
            0.44,
            "BELTS & ROUTING",
            "Use Belts [1-3] and Splitters/Sorters [5-6] to route cheques to matching Tubes. Press [R] to rotate.",
        ),
        (
            0.43,
            0.29,
            0.58,
            0.40,
            "STAMPS & TIMERS",
            "Real cheques must be Stamped [7] before delivery. Depots buffer cheques and slow their timers by 50%+!",
        ),
        (
            0.73,
            0.31,
            0.86,
            0.43,
            "FRAUD & SHREDDING",
            "VOID and FAKE cheques cost huge fines! Use Scanners to catch them and Shredders to cash bounties.",
        ),
        (
            0.12,
            0.64,
            0.26,
            0.77,
            "CROWBAR & CLEANUP",
            "Select Crowbar [`] to mop spills, clear floor piles, or refund parts. Unclean floors trigger Mess Audits!",
        ),
        (
            0.35,
            0.59,
            0.43,
            0.78,
            "VIP & POLISHER",
            "Blue VIP cheques pay big! They sparkle, expire fast, and need a Polisher before entering the VIP Tube.",
        ),
        (
            0.56,
            0.59,
            0.64,
            0.78,
            "FORKLIFT & MOVING",
            "Press [G] near a Forklift to drive it, and [X] to pick up and relocate whole machines without selling!",
        ),
        (
            0.74,
            0.65,
            0.87,
            0.78,
            "UPGRADES & ROOMS",
            "Press [B] for Global Upgrades and [U] to upgrade machines to 100% accuracy. Hit quota + cash to unlock rooms!",
        ),
    )

    def _nearest_office_desk(self) -> tuple[float, float, float, float, str, str] | None:
        if self.intro_stage != "office_int":
            return None
        best = None
        best_d = 0.14
        for desk in self.OFFICE_DESKS:
            x1, y1, x2, y2, _, _ = desk
            cx = max(x1, min(x2, self.intro_px))
            cy = max(y1, min(y2, self.intro_py))
            d = math.hypot(self.intro_px - cx, (self.intro_py - cy) * (SCREEN_HEIGHT / SCREEN_WIDTH))
            if d <= best_d:
                best_d = d
                best = desk
        return best

    def _intro_collides_desk(self, px: float, py: float) -> bool:
        rx, ry = 0.022, 0.020
        for x1, y1, x2, y2, _, _ in self.OFFICE_DESKS:
            if (x1 - rx) < px < (x2 + rx) and (y1 - ry) < py < (y2 + ry):
                return True
        return False

    def _handle_mouse_down(self, button: int, pos: tuple[int, int]) -> bool:
        if self.show_story:
            if button == 1 and (
                self.intro_skip_rect.collidepoint(pos)
                or self.renderer.modal_btn_rect.collidepoint(pos)
            ):
                self._finish_intro()
            elif button == 1 and self.intro_stage == "office_int":
                if self.intro_desk_note is not None:
                    self.intro_desk_note = None
                    return True
                nx = pos[0] / SCREEN_WIDTH
                ny = pos[1] / SCREEN_HEIGHT
                near = self._nearest_office_desk()
                if near is not None and near[0] - 0.03 <= nx <= near[2] + 0.03 and near[1] - 0.03 <= ny <= near[3] + 0.03:
                    self.intro_desk_note = (near[4], near[5])
                    if hasattr(self, "intro_viewed_desks"):
                        self.intro_viewed_desks.add(near[4])
                    self.world._emit_sfx("interact")
            return True

        if button == 2:
            self.panning = True
            return True

        if self._showing_end_modal:
            if button == 1 and self.renderer.modal_btn_rect.collidepoint(pos):
                self._advance_or_retry()
            return True

        if getattr(self, "show_reset_confirm", False):
            if button == 1:
                if self.renderer.reset_confirm_yes_rect.collidepoint(pos):
                    self._reset_game()
                    self.world._emit_sfx("interact")
                else:
                    self.show_reset_confirm = False
            return True

        if getattr(self, "show_settings", False):
            if button == 1:
                if self.renderer.settings_close_rect.collidepoint(pos):
                    self.show_settings = False
                    return True
                toggles = getattr(self.renderer, "settings_toggle_rects", {})
                if toggles.get("hide_all") and toggles["hide_all"].collidepoint(pos):
                    self.renderer.hide_all_popups = not getattr(
                        self.renderer, "hide_all_popups", False
                    )
                    return True
                if toggles.get("floating") and toggles["floating"].collidepoint(pos):
                    self.renderer.show_floating_popups = not getattr(
                        self.renderer, "show_floating_popups", True
                    )
                    return True
                if toggles.get("prompts") and toggles["prompts"].collidepoint(pos):
                    self.renderer.show_world_prompts = not getattr(
                        self.renderer, "show_world_prompts", True
                    )
                    return True
                if toggles.get("labels") and toggles["labels"].collidepoint(pos):
                    self.renderer.show_pile_bag_labels = not getattr(
                        self.renderer, "show_pile_bag_labels", True
                    )
                    return True
                if self.renderer.settings_music_minus_rect.collidepoint(pos):
                    self.sfx.set_music_volume(
                        round(self.sfx.music_volume - 0.10, 2), muted=self.muted
                    )
                    return True
                if self.renderer.settings_music_plus_rect.collidepoint(pos):
                    self.sfx.set_music_volume(
                        round(self.sfx.music_volume + 0.10, 2), muted=self.muted
                    )
                    return True
                if self.renderer.settings_sfx_minus_rect.collidepoint(pos):
                    self.sfx.set_sfx_volume(
                        round(getattr(self.sfx, "sfx_volume", 1.0) - 0.10, 2)
                    )
                    self.sfx.play("interact")
                    return True
                if self.renderer.settings_sfx_plus_rect.collidepoint(pos):
                    self.sfx.set_sfx_volume(
                        round(getattr(self.sfx, "sfx_volume", 1.0) + 0.10, 2)
                    )
                    self.sfx.play("interact")
                    return True
                if self.renderer.settings_mute_rect.collidepoint(pos):
                    self.muted = not self.muted
                    self.sfx.set_muted(self.muted)
                    return True
            return True

        if button == 1:
            if self.renderer.settings_btn_rect.collidepoint(pos):
                self.show_settings = not getattr(self, "show_settings", False)
                self.world._emit_sfx("interact")
                return True
            if self.renderer.reset_btn_rect.collidepoint(pos):
                self.show_reset_confirm = True
                self.world._emit_sfx("interact")
                return True
            if self.renderer.speed_btn_rect.collidepoint(pos):
                self._cycle_speed()
                return True
            if self.renderer.shop_btn_rect.collidepoint(pos):
                if not self.world._blocked_if_in_forklift():
                    self.show_shop = not self.show_shop
                return True
            if self.renderer.hotbar_prev_rect.collidepoint(pos):
                total_pages = max(1, (len(TOOLS) + 4) // 5)
                self.hotbar_page = (self.hotbar_page - 1) % total_pages
                return True
            if self.renderer.hotbar_next_rect.collidepoint(pos):
                total_pages = max(1, (len(TOOLS) + 4) // 5)
                self.hotbar_page = (self.hotbar_page + 1) % total_pages
                return True
            for idx, rect in enumerate(self.renderer.hotbar_rects):
                if rect.collidepoint(pos):
                    tool_idx = (
                        self.renderer.hotbar_tool_indices[idx]
                        if idx < len(self.renderer.hotbar_tool_indices)
                        else idx
                    )
                    self.select_tool_slot(tool_idx)
                    return True
            if self.show_shop:
                if self.renderer.shop_close_rect.collidepoint(pos):
                    self.show_shop = False
                    return True
                for u_idx, rect in enumerate(self.renderer.shop_upgrade_rects):
                    if rect.collidepoint(pos):
                        if u_idx < len(UPGRADES):
                            self.world.buy_upgrade(UPGRADES[u_idx][0])
                        return True
                return True
            if self.part_menu_tile is not None:
                col, row = self.part_menu_tile
                if self.world.in_bounds(col, row) and self.world.grid[row][col].kind == "splitter":
                    tile = self.world.grid[row][col]
                    if self.renderer.part_menu_straight_rect.collidepoint(pos):
                        tile.splitter_straight_color = CHEQUE_ORDER[
                            (CHEQUE_ORDER.index(tile.splitter_straight_color) + 1)
                            % len(CHEQUE_ORDER)
                        ]
                        return True
                    if self.renderer.part_menu_branch_rect.collidepoint(pos):
                        tile.splitter_branch_color = CHEQUE_ORDER[
                            (CHEQUE_ORDER.index(tile.splitter_branch_color) + 1)
                            % len(CHEQUE_ORDER)
                        ]
                        return True
                elif self.world.in_bounds(col, row) and self.world.grid[row][col].kind == "sorter":
                    tile = self.world.grid[row][col]
                    if self.renderer.part_menu_branch_rect.collidepoint(pos):
                        tile.sorter_branch_color = CHEQUE_ORDER[
                            (CHEQUE_ORDER.index(tile.sorter_branch_color) + 1)
                            % len(CHEQUE_ORDER)
                        ]
                        return True
                if self.renderer.part_menu_upgrade_rect.collidepoint(pos):
                    self.world.upgrade_machine_tile(col, row, ignore_reach=True)
                    return True
                if self.renderer.part_menu_rotate_rect.collidepoint(pos):
                    col, row = self.part_menu_tile
                    if self.world.in_bounds(col, row):
                        self.world.grid[row][col].dir_idx = (
                            self.world.grid[row][col].dir_idx + 1
                        ) % 4
                    return True
                if self.renderer.part_menu_delete_rect.collidepoint(pos):
                    col, row = self.part_menu_tile
                    self.world.remove_tile(
                        col, row, allow_clean=(self.tool_kind == "demolish")
                    )
                    self.part_menu_tile = None
                    self.selected_part_tile = None
                    return True
            wpos = self.renderer.minimap_to_world(
                *pos, self.world.cols, self.world.rows
            )
            if wpos is not None:
                self.renderer.center_camera_at(
                    wpos[0], wpos[1], self.world.cols, self.world.rows
                )
                self.minimap_dragging = True
                return True
            if self._in_play_viewport(pos):
                col, row = self.renderer.screen_to_tile(*pos)
                if self.selected_tool is None:
                    self.part_menu_tile = None
                    if self.world.in_bounds(col, row) and self.world.grid[row][col].kind != "empty":
                        self.selected_part_tile = (col, row)
                        self.world.interact_tile(col, row)
                    else:
                        self.selected_part_tile = None
                    return True
                if self.world.in_bounds(col, row) and self.world.grid[row][col].kind != "empty":
                    self.selected_part_tile = (col, row)
                    self.part_menu_tile = None
                    return True
                self.part_menu_tile = None
                self.world.place_tile(
                    col, row, self.tool_kind, self.build_dir, self.filter_color
                )
                self.painting_place = True
                self.last_painted_tile = (col, row)
        elif button == 3 and not self.show_shop and self._in_play_viewport(pos):
            col, row = self.renderer.screen_to_tile(*pos)
            if self.world.in_bounds(col, row) and self.world.grid[row][col].kind != "empty":
                self.selected_part_tile = (col, row)
                self.part_menu_tile = (col, row)
                self.part_menu_pos = pos

        return True

    def _pipette_tile(self) -> bool:
        if not self._in_play_viewport(self.mouse_pos):
            return False
        col, row = self.renderer.screen_to_tile(*self.mouse_pos)
        if not self.world.in_bounds(col, row):
            return False
        t = self.world.grid[row][col]
        tool_names = [tool[0] for tool in TOOLS]
        if t.kind in tool_names:
            self.selected_tool = tool_names.index(t.kind)
            self.build_dir = t.dir_idx % 4
            if t.kind == "sorter" and t.color_key in CHEQUE_ORDER:
                self.filter_color_idx = CHEQUE_ORDER.index(t.color_key)
            self.world._emit_sfx("interact")
            return True
        return False

    def _handle_key_down(self, key: int) -> bool:
        if key == pygame.K_ESCAPE:
            if not self.close_all_menus():
                self.selected_tool = None
            return True
        if key == pygame.K_BACKQUOTE:
            self.selected_tool = None
            return True

        if self.show_story:
            if key == pygame.K_e and self.intro_stage == "office_int":
                if self.intro_desk_note is not None:
                    self.intro_desk_note = None
                else:
                    near = self._nearest_office_desk()
                    if near is not None:
                        self.intro_desk_note = (near[4], near[5])
                        if hasattr(self, "intro_viewed_desks"):
                            self.intro_viewed_desks.add(near[4])
                        self.world._emit_sfx("interact")
                return True
            if key == pygame.K_ESCAPE and self.intro_desk_note is not None:
                self.intro_desk_note = None
                return True
            if key in (
                pygame.K_RETURN,
                pygame.K_KP_ENTER,
                pygame.K_SPACE,
            ):
                self._finish_intro()
            return True

        if self._showing_end_modal:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._advance_or_retry()
            return True

        if getattr(self, "show_reset_confirm", False):
            if key == pygame.K_ESCAPE:
                self.show_reset_confirm = False
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._reset_game()
            return True

        if getattr(self, "show_settings", False):
            if key in (pygame.K_ESCAPE, pygame.K_o):
                self.show_settings = False
            elif key == pygame.K_TAB:
                self.renderer.hide_all_popups = not getattr(
                    self.renderer, "hide_all_popups", False
                )
            elif key == pygame.K_v:
                self.muted = not self.muted
                self.sfx.set_muted(self.muted)
            return True

        if key == pygame.K_TAB:
            self.renderer.hide_all_popups = not getattr(
                self.renderer, "hide_all_popups", False
            )
            return True

        if key == pygame.K_o:
            self.show_settings = not getattr(self, "show_settings", False)
            return True

        if key == pygame.K_b:
            if not self.world._blocked_if_in_forklift():
                self.show_shop = not self.show_shop
        elif key == pygame.K_f:
            self._cycle_speed()
        elif key == pygame.K_m:
            self.renderer.show_minimap = not self.renderer.show_minimap
        elif key == pygame.K_v:
            self.muted = not self.muted
            self.sfx.set_muted(self.muted)
        elif key == pygame.K_n:
            title = self.sfx.next_track(muted=self.muted)
            self.world.popups.append(
                FloatingText(
                    self.world.player_x,
                    self.world.player_y - 0.6,
                    f"BGM: {title}",
                    (148, 224, 255),
                )
            )
        elif key == pygame.K_c:
            self.renderer.reset_camera(
                self.world.cols,
                self.world.rows,
                self.world.player_x,
                self.world.player_y,
            )
        elif key == pygame.K_r and not self.show_shop:
            fl = self.world.active_forklift
            if fl is not None and fl.carried_machine is not None:
                cur_d = int(fl.carried_machine.get("dir_idx", 1))  # type: ignore[arg-type]
                fl.carried_machine["dir_idx"] = (cur_d + 1) % 4
                self.world._emit_sfx("interact")
            else:
                self.build_dir = (self.build_dir + 1) % 4
        elif key == pygame.K_t and not self.show_shop:
            if not self.world.paused and self._in_play_viewport(self.mouse_pos):
                col, row = self.renderer.screen_to_tile(*self.mouse_pos)
                if self.world.in_bounds(col, row):
                    ht = self.world.grid[row][col]
                    if ht.kind == "scanner":
                        ht.scanner_mode = "error" if ht.scanner_mode == "fraud" else "fraud"
                        self.world._emit_sfx("interact")
                        return True
                    if ht.kind == "sorter":
                        self.filter_color_idx = (self.filter_color_idx + 1) % len(CHEQUE_ORDER)
                        ht.color_key = self.filter_color
                        self.world._emit_sfx("interact")
                        return True
            self.filter_color_idx = (self.filter_color_idx + 1) % len(CHEQUE_ORDER)
        elif key == pygame.K_q and not self.show_shop:
            self._pipette_tile()
        elif key == pygame.K_e and not self.show_shop:
            self.world.selected_tool_kind = self.tool_kind
            self.world.interact_nearest()
        elif key == pygame.K_g and not self.show_shop:
            self.world.toggle_forklift()
        elif key == pygame.K_x and not self.show_shop:
            self.world.relocate_machine_with_forklift()
        elif key == pygame.K_DELETE and not self.show_shop:
            target = self.selected_part_tile
            if target is None and self._in_play_viewport(self.mouse_pos):
                target = self.renderer.screen_to_tile(*self.mouse_pos)
            if target is not None and self.world.in_bounds(*target):
                self.world.remove_tile(
                    *target, allow_clean=(self.tool_kind == "demolish")
                )
                self.selected_part_tile = None
                self.part_menu_tile = None
        elif key == pygame.K_u and not self.show_shop:
            hover_tile = (
                self.renderer.screen_to_tile(*self.mouse_pos)
                if self._in_play_viewport(self.mouse_pos)
                else None
            )
            self.world.upgrade_nearest_machine(hover_tile)
        elif key == pygame.K_SPACE and not self.show_shop:
            dx, dy, _ = self._movement_axes()
            self.world.trigger_jump(dx, dy)
        elif pygame.K_1 <= key <= pygame.K_9:
            idx = key - pygame.K_1
            if idx < len(TOOLS):
                self.select_tool_slot(idx)
        elif key == pygame.K_0:
            if len(TOOLS) > 9:
                self.select_tool_slot(9)
        elif key == pygame.K_MINUS:
            if len(TOOLS) > 10:
                self.select_tool_slot(10)
        elif key in (pygame.K_EQUALS, pygame.K_BACKSPACE):
            if len(TOOLS) > 11:
                self.select_tool_slot(11)
        elif pygame.K_F1 <= key <= pygame.K_F4:
            target_stage = (key - pygame.K_F1) + 1
            if target_stage <= self.world.room_stage and target_stage - 1 < len(LEVELS):
                lvl = LEVELS[target_stage - 1]
                mid_x = lvl.start_col + (lvl.room_cols - lvl.start_col) * 0.5
                self.renderer.center_camera_at(
                    mid_x, self.world.rows * 0.5, self.world.cols, self.world.rows
                )
            else:
                self.world.sfx_queue.append("error")
                self.world.popups.append(
                    FloatingText(
                        self.world.player_x,
                        self.world.player_y - 0.5,
                        f"RM{target_stage} LOCKED! UNLOCK AT EAST GATE [E]!",
                        (255, 118, 92),
                    )
                )
        elif pygame.K_F5 <= key <= pygame.K_F10:
            u_idx = key - pygame.K_F5
            if u_idx < len(UPGRADES):
                self.world.buy_upgrade(UPGRADES[u_idx][0])

        return True

    def _start_intro_fade(self, next_stage: str) -> None:
        if self.intro_fade_phase == "out":
            return
        self.intro_fade_phase = "out"
        self.intro_pending_stage = next_stage
        self.intro_moving = False

    def _update_intro(self, dt: float) -> None:
        self.world.anim_time += dt
        if not self.intro_surfaces:
            self.renderer.update_camera(self.world, dt)
            return

        fade_speed = 420.0
        if self.intro_fade_phase == "out":
            self.intro_fade_alpha = min(255.0, self.intro_fade_alpha + fade_speed * dt)
            if self.intro_fade_alpha >= 255.0:
                nxt = self.intro_pending_stage
                self.intro_pending_stage = None
                if nxt == "done":
                    self._finish_intro()
                    return
                if nxt == "facility_ext":
                    self.intro_stage = "facility_ext"
                    self.intro_px = 0.47
                    self.intro_py = 0.84
                elif nxt == "office_int":
                    self.intro_stage = "office_int"
                    self.intro_px = 0.50
                    self.intro_py = 0.48
                    self.intro_desk_note = None
                self.intro_fade_phase = "in"
            return
        if self.intro_fade_phase == "in":
            self.intro_fade_alpha = max(0.0, self.intro_fade_alpha - fade_speed * dt)
            if self.intro_fade_alpha <= 0.0:
                self.intro_fade_phase = "none"

        dx, dy, sprinting = self._movement_axes()
        spd = (0.30 if sprinting else 0.21) * dt
        self.intro_moving = abs(dx) > 1e-4 or abs(dy) > 1e-4
        if abs(dx) > 1e-4:
            self.intro_facing_left = dx < 0
        nx = self.intro_px + dx * spd
        ny = self.intro_py + dy * spd * (SCREEN_WIDTH / SCREEN_HEIGHT)
        if self.intro_stage == "office_int":
            if not self._intro_collides_desk(nx, self.intro_py):
                self.intro_px = nx
            if not self._intro_collides_desk(self.intro_px, ny):
                self.intro_py = ny
            if self.intro_desk_note is not None and self._nearest_office_desk() is None:
                self.intro_desk_note = None
        else:
            self.intro_px = nx
            self.intro_py = ny

        if self.intro_stage == "manor":
            self.intro_px = max(0.24, min(0.76, self.intro_px))
            self.intro_py = max(0.36, min(0.94, self.intro_py))
            if 0.40 <= self.intro_px <= 0.60 and self.intro_py >= 0.84:
                self._start_intro_fade("facility_ext")
        elif self.intro_stage == "facility_ext":
            self.intro_px = max(0.14, min(0.86, self.intro_px))
            self.intro_py = max(0.54, min(0.93, self.intro_py))
            if 0.40 <= self.intro_px <= 0.54 and self.intro_py <= 0.60:
                self._start_intro_fade("office_int")
        elif self.intro_stage == "office_int":
            self.intro_px = max(0.14, min(0.86, self.intro_px))
            self.intro_py = max(0.24, min(0.95, self.intro_py))
            if 0.42 <= self.intro_px <= 0.58 and self.intro_py >= 0.88:
                self._start_intro_fade("done")

    def _draw_intro_car(
        self, screen: pygame.Surface, cx: int, cy: int, size: tuple[int, int]
    ) -> None:
        w, h = size
        if self.intro_car_surf is not None:
            car_img = pygame.transform.smoothscale(self.intro_car_surf, (w, h))
            pygame.draw.ellipse(
                screen, (8, 10, 16), (cx - int(w * 0.44), cy + int(h * 0.16), int(w * 0.88), int(h * 0.28))
            )
            screen.blit(car_img, car_img.get_rect(center=(cx, cy)).topleft)
            return
        pygame.draw.ellipse(screen, (8, 10, 16), (cx - 64, cy + 12, 128, 22))
        body = pygame.Rect(cx - 58, cy - 22, 116, 40)
        pygame.draw.rect(screen, (28, 36, 54), body, border_radius=10)

    def _draw_intro(self, screen: pygame.Surface) -> None:
        bg = self.intro_surfaces.get(self.intro_stage)
        if bg is not None:
            screen.blit(bg, (0, 0))
        else:
            screen.fill((14, 18, 28))

        if self.intro_stage == "manor":
            self._draw_intro_car(screen, int(0.50 * SCREEN_WIDTH), int(0.89 * SCREEN_HEIGHT), (200, 100))
            prompt = "Walk out of the manor into your car [WASD / Arrows]"
            gx, gy = int(0.50 * SCREEN_WIDTH), int(0.89 * SCREEN_HEIGHT)
            target_h = 76
        elif self.intro_stage == "facility_ext":
            self._draw_intro_car(screen, int(0.37 * SCREEN_WIDTH), int(0.84 * SCREEN_HEIGHT), (240, 120))
            prompt = "Walk into the Clearing Facility entrance [WASD / Arrows]"
            gx, gy = int(0.47 * SCREEN_WIDTH), int(0.58 * SCREEN_HEIGHT)
            target_h = 108
        else:
            prompt = "Head through the south doorway onto the Factory Floor [WASD / Arrows]"
            gx, gy = int(0.50 * SCREEN_WIDTH), int(0.92 * SCREEN_HEIGHT)
            target_h = 112

        pulse = 12 + int(4 * math.sin(self.world.anim_time * 5.0))
        pygame.draw.circle(screen, (255, 220, 96), (gx, gy), pulse, width=2)

        px = int(self.intro_px * SCREEN_WIDTH)
        py = int(self.intro_py * SCREEN_HEIGHT)
        raw_frame = self.renderer.sprites.get_frame(
            "walk" if self.intro_moving else "idle",
            self.world.anim_time,
            self.intro_facing_left,
        )
        fw, fh = raw_frame.get_size()
        scale_w = max(1, int(round(fw * (target_h / max(1, fh)))))
        frame = pygame.transform.smoothscale(raw_frame, (scale_w, target_h))
        sh_w = int(target_h * 0.72)
        sh_h = max(10, int(target_h * 0.22))
        pygame.draw.ellipse(screen, (10, 12, 18), (px - sh_w // 2, py - sh_h // 2, sh_w, sh_h))
        screen.blit(frame, frame.get_rect(midbottom=(px, py)).topleft)

        if self.intro_stage == "office_int":
            viewed = getattr(self, "intro_viewed_desks", set())
            for d_idx, (x0, y0, x1, _y1, d_title, _tip) in enumerate(self.OFFICE_DESKS):
                if d_title in viewed:
                    continue
                bx = int(((x0 + x1) * 0.5) * SCREEN_WIDTH)
                bob = int(round(math.sin(self.world.anim_time * 5.2 + d_idx * 0.85) * 5.0))
                by = int(y0 * SCREEN_HEIGHT) - 22 + bob
                badge_r = pygame.Rect(bx - 11, by - 13, 22, 24)
                pygame.draw.rect(screen, (24, 30, 44), badge_r, border_radius=6)
                pygame.draw.rect(screen, (255, 212, 82), badge_r, width=2, border_radius=6)
                ex_s = self.renderer.label_font.render("!", True, (255, 224, 96))
                screen.blit(ex_s, ex_s.get_rect(center=badge_r.center).topleft)
            near = self._nearest_office_desk()
            if near is not None and self.intro_desk_note is None:
                dx_mid = int(((near[0] + near[2]) * 0.5) * SCREEN_WIDTH)
                dy_top = int(near[1] * SCREEN_HEIGHT) - 18
                hint = self.renderer.small_font.render("[E] / Click Desk", True, (255, 240, 140))
                hbox = hint.get_rect(center=(dx_mid, dy_top)).inflate(12, 6)
                pygame.draw.rect(screen, (18, 24, 38), hbox, border_radius=5)
                pygame.draw.rect(screen, (255, 212, 82), hbox, width=1, border_radius=5)
                screen.blit(hint, hint.get_rect(center=hbox.center).topleft)
            if self.intro_desk_note is not None:
                title, tip = self.intro_desk_note
                card = pygame.Rect(SCREEN_WIDTH // 2 - 340, 26, 680, 114)
                pygame.draw.rect(screen, (18, 24, 38), card, border_radius=10)
                pygame.draw.rect(screen, (255, 212, 82), card, width=2, border_radius=10)
                t_s = self.renderer.label_font.render(title, True, (255, 224, 116))
                screen.blit(t_s, (card.left + 18, card.top + 12))
                c_s = self.renderer.small_font.render("[E / Click] Close", True, (158, 188, 232))
                screen.blit(c_s, (card.right - c_s.get_width() - 16, card.top + 14))
                words = tip.split(" ")
                lines: list[str] = []
                cur = ""
                for w in words:
                    cand = f"{cur} {w}".strip()
                    if self.renderer.small_font.size(cand)[0] <= card.width - 36:
                        cur = cand
                    else:
                        lines.append(cur)
                        cur = w
                if cur:
                    lines.append(cur)
                for li, ln in enumerate(lines[:3]):
                    l_s = self.renderer.small_font.render(ln, True, (232, 240, 255))
                    screen.blit(l_s, (card.left + 18, card.top + 44 + li * 22))

        bar = pygame.Rect(SCREEN_WIDTH // 2 - 360, SCREEN_HEIGHT - 54, 720, 40)
        pygame.draw.rect(screen, (16, 22, 34), bar, border_radius=8)
        pygame.draw.rect(screen, (255, 212, 82), bar, width=2, border_radius=8)
        p_surf = self.renderer.label_font.render(prompt, True, (240, 246, 255))
        screen.blit(p_surf, p_surf.get_rect(center=bar.center).topleft)

        pygame.draw.rect(screen, (36, 46, 68), self.intro_skip_rect, border_radius=6)
        pygame.draw.rect(screen, (148, 186, 238), self.intro_skip_rect, width=1, border_radius=6)
        sk_surf = self.renderer.small_font.render("SKIP [SPACE]", True, (226, 238, 255))
        screen.blit(sk_surf, sk_surf.get_rect(center=self.intro_skip_rect.center).topleft)

        if self.intro_fade_alpha > 1.0:
            fade_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            fade_surf.fill((0, 0, 0))
            fade_surf.set_alpha(int(self.intro_fade_alpha))
            screen.blit(fade_surf, (0, 0))

    def update(self, dt: float) -> None:
        self.sfx.update_music(muted=self.muted)
        if self.show_story:
            self._update_intro(dt)
            return

        self.world.selected_tool_kind = self.tool_kind
        dx, dy, sprinting = self._movement_axes()
        self.world.move_player(dx, dy, dt, sprinting=sprinting)
        self.world.update(dt, keep_playing=self.keep_playing)
        self.renderer.update_camera(self.world, dt)

        if self.world.sfx_queue:
            if not self.muted:
                for sfx_name in self.world.sfx_queue:
                    self.sfx.play(sfx_name)
            self.world.sfx_queue.clear()

    def draw(self, screen: pygame.Surface) -> None:
        if self.show_story and self.intro_surfaces:
            self._draw_intro(screen)
            return
        hover_tile = (
            self.renderer.screen_to_tile(*self.mouse_pos)
            if self._in_play_viewport(self.mouse_pos)
            else None
        )
        self.renderer.draw(
            screen,
            self.world,
            self.selected_tool,
            self.build_dir,
            self.filter_color,
            hover_tile,
            self.show_story,
            keep_playing=self.keep_playing,
            show_shop=self.show_shop,
            muted=self.muted,
            part_menu_tile=self.part_menu_tile,
            part_menu_pos=self.part_menu_pos,
            hotbar_page=self.hotbar_page,
        )
        if getattr(self, "show_reset_confirm", False):
            self.renderer._draw_reset_confirm_modal(screen)
        elif getattr(self, "show_settings", False):
            self.renderer._draw_settings_modal(
                screen,
                self.sfx.music_volume,
                getattr(self.sfx, "sfx_volume", 1.0),
                self.muted,
            )


def _draw_boot_loader(screen: pygame.Surface, status: str, pct: float) -> None:
    """Render a themed vault loading frame during synchronous asset/audio startup."""
    screen.fill((13, 17, 26))
    card = pygame.Rect(SCREEN_WIDTH // 2 - 290, SCREEN_HEIGHT // 2 - 100, 580, 200)
    pygame.draw.rect(screen, (20, 27, 41), card, border_radius=12)
    pygame.draw.rect(screen, (255, 212, 82), card, width=3, border_radius=12)
    title_f = _load_ui_font(32)
    sub_f = _load_ui_font(17)
    t_surf = title_f.render("CHEQUE MATE", True, (255, 216, 89))
    screen.blit(t_surf, t_surf.get_rect(center=(card.centerx, card.top + 48)).topleft)
    track = pygame.Rect(card.left + 40, card.top + 96, card.width - 80, 18)
    pygame.draw.rect(screen, (10, 15, 24), track, border_radius=9)
    fill_w = max(14, int(track.width * max(0.0, min(1.0, pct))))
    pygame.draw.rect(
        screen,
        (68, 206, 114),
        (track.left, track.top, fill_w, track.height),
        border_radius=9,
    )
    pygame.draw.rect(screen, (72, 92, 132), track, width=1, border_radius=9)
    s_surf = sub_f.render(status, True, (208, 224, 248))
    screen.blit(s_surf, s_surf.get_rect(center=(card.centerx, card.top + 148)).topleft)
    pygame.display.flip()


async def async_main() -> None:
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=4096)
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Cheque Mate - Central Factory")
    clock = pygame.time.Clock()

    _draw_boot_loader(screen, "Loading operator & cheque sprites...", 0.25)
    await asyncio.sleep(0)
    sprites = ThiefSprites.load()
    _draw_boot_loader(screen, "Loading vault cheque sheets...", 0.55)
    await asyncio.sleep(0)
    cheque_sprites = ChequeSprites.load()
    _draw_boot_loader(screen, "Loading factory forklifts...", 0.72)
    await asyncio.sleep(0)
    forklift_sprites = ForkliftSprites.load()
    _draw_boot_loader(screen, "Synthesizing factory audio...", 0.88)
    await asyncio.sleep(0)
    try:
        sfx = SoundBank.load()
    except Exception:
        sfx = SoundBank({}, SoundBank._discover_music_tracks())
    _draw_boot_loader(screen, "Building factory floor...", 0.95)
    await asyncio.sleep(0)
    try:
        game = BounceTheChequesGame(
            sprites=sprites,
            cheque_sprites=cheque_sprites,
            sfx=sfx,
            forklift_sprites=forklift_sprites,
        )
    except Exception as exc:
        _draw_boot_loader(screen, f"Boot error: {exc}", 0.95)
        await asyncio.sleep(5)
        raise

    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        for event in pygame.event.get():
            if not game.handle_event(event):
                running = False
                break
        if not running:
            break

        game.update(dt)
        game.draw(screen)
        pygame.display.flip()
        await asyncio.sleep(0)

    pygame.quit()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
