from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pygame  # noqa: F401  (ensures pygbag detects pygame dependency from entry script)

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

_spec = importlib.util.spec_from_file_location("game_src_main", SRC_DIR / "main.py")
assert _spec is not None and _spec.loader is not None
_src_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_src_main)
async_main = _src_main.async_main


async def main() -> None:
    """Entry point compatible with desktop Python and pygbag/itch.io WebAssembly."""
    await async_main()


if __name__ == "__main__":
    asyncio.run(main())
