# Bag Weight and Capacity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slow the player proportionally as the cheque bag fills and prevent bag-consuming pickups when the bag is full.

**Architecture:** Keep both behaviors in `FactoryWorld`, the existing simulation source of truth. Add a normalized load multiplier to `move_player`, and add an early capacity check to `interact_tile` before pile or crate state/reward mutations. Preserve sprint, oil, upgrade, delivery, belt-feed, and non-bag-item behavior.

**Tech Stack:** Python 3.10+, pygame 2.5.2, unittest, Poetry.

---

### Task 1: Add focused simulation tests

**Files:**
- Create: `tests/test_factory_sim.py`
- Modify: `tests/tests.txt` only if the repository's test inventory requires documenting the new test file

- [ ] **Step 1: Write tests for movement load scaling**

Create a `unittest.TestCase` that constructs `FactoryWorld`, stubs `_step_with_corner_slide` to capture its first velocity argument, and calls `move_player(1.0, 0.0, 1.0)` with:

```python
world.carried_cheques = []
world.move_player(1.0, 0.0, 1.0)
empty_distance = captured_velocity[0]

world.carried_cheques = ["payroll"] * (MAX_CARRIED // 2)
world.move_player(1.0, 0.0, 1.0)
half_distance = captured_velocity[0]

world.carried_cheques = ["payroll"] * MAX_CARRIED
world.move_player(1.0, 0.0, 1.0)
full_distance = captured_velocity[0]

self.assertAlmostEqual(half_distance / empty_distance, 0.75)
self.assertAlmostEqual(full_distance / empty_distance, 0.5)
```

Use the existing `factory_sim` import path from `src`, and make the test independent of pygame rendering.

- [ ] **Step 2: Write tests for full-bag pickup rejection**

Add tests that set up a world tile containing a non-bad pile and a crate, fill `carried_cheques` to `MAX_CARRIED`, and call `interact_tile` with reach ignored. Assert that:

```python
self.assertFalse(world.interact_tile(col, row, ignore_reach=True))
self.assertEqual(tile.pile_tier, original_pile_tier)
self.assertEqual(len(world.carried_cheques), MAX_CARRIED)
self.assertEqual(world.money_rescued, original_money)
```

For the crate case, also assert `crate_stock` is unchanged. Choose existing level tiles or construct minimal `Tile` values using the same fields consumed by `interact_tile`; do not depend on a display or event loop.

- [ ] **Step 3: Run the new tests to verify they fail**

Run:

```powershell
poetry run python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: the movement test fails because no bag-load multiplier exists, and the pile test fails because a full bag currently consumes a pile item.

### Task 2: Implement bag-weighted movement

**Files:**
- Modify: `src/factory_sim.py:739-817`

- [ ] **Step 1: Add the load factor to the existing speed calculation**

In `FactoryWorld.move_player`, calculate a clamped load ratio and multiplier immediately before the existing `speed` expression:

```python
bag_load = min(1.0, len(self.carried_cheques) / MAX_CARRIED)
bag_mult = 1.0 - (0.5 * bag_load)
speed = (
    PLAYER_SPEED
    * exo_mult
    * (PLAYER_SPRINT_MULT if sprinting else 1.0)
    * oil_mult
    * bag_mult
)
```

This keeps empty bags at the current speed, makes a half-full bag 75% speed, and makes a full bag 50% speed. The `min` guard keeps the multiplier valid if an unrelated caller temporarily exceeds capacity.

- [ ] **Step 2: Run the movement tests**

Run:

```powershell
poetry run python -m unittest tests.test_factory_sim.BagBehaviorTests.test_movement_scales_with_bag_load -v
```

Expected: PASS.

### Task 3: Reject bag-consuming pickups at capacity

**Files:**
- Modify: `src/factory_sim.py:1000-1140`

- [ ] **Step 1: Guard pile pickups before mutation**

In the `tile.pile_tier > 0` branch, resolve whether the pile is a bad cheque before decrementing `pile_tier`. For a non-bad cheque and a full bag, emit the existing `"error"` sound and `"BAG FULL! DELIVER/BELT!"` popup, then return `False`. Leave bad-cheque shredding unchanged.

The guard must run before `self.cash -= CLEAR_PILEUP_COST`, `tile.pile_tier -= 1`, money changes, rescue counters, particles, and success popups.

- [ ] **Step 2: Preserve crate belt spawning while blocking bag insertion**

Keep the existing crate `can_belt_spawn` path available at capacity. Before entering the bag append branch, the existing `bag_room <= 0` condition must cause the interaction to return `False` when no belt spawn is available. If a crate can spawn onto a belt, it may still spawn as before; bag-consuming crate items must never be silently discarded or charged when capacity is unavailable.

- [ ] **Step 3: Run full-bag pickup tests**

Run:

```powershell
poetry run python -m unittest tests.test_factory_sim.BagBehaviorTests.test_full_bag_rejects_pile_pickup tests.test_factory_sim.BagBehaviorTests.test_full_bag_rejects_crate_pickup -v
```

Expected: PASS, with source tile state, bag length, and rewards unchanged after rejected pickups.

### Task 4: Validate the complete change

**Files:**
- Modify: `src/factory_sim.py`
- Test: `tests/test_factory_sim.py`

- [ ] **Step 1: Run the focused suite**

Run:

```powershell
poetry run python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: all focused tests pass.

- [ ] **Step 2: Run a syntax/type-oriented check**

Run:

```powershell
poetry run python -m compileall src tests
```

Expected: no syntax errors.

- [ ] **Step 3: Inspect the final diff**

Run:

```powershell
git diff --check
git diff -- src/factory_sim.py tests/test_factory_sim.py
```

Confirm that only bag-weight movement, full-bag pickup prevention, and their focused tests changed; do not alter unrelated pre-existing worktree changes.

- [ ] **Step 4: Commit the implementation**

```powershell
git add src/factory_sim.py tests/test_factory_sim.py
git commit -m "feat: add bag weight and capacity limits"
```

