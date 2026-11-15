# Bag Weight and Capacity Design

## Goal

Make carrying more cheques visibly affect player movement and prevent the player
from collecting additional bag items once the bag is full.

## Behavior

- Movement speed scales linearly with bag load:
  - Empty bag: 100% of the existing movement speed.
  - Full bag (`MAX_CARRIED`): 50% of the existing movement speed.
- The load multiplier applies before existing sprint, oil, and upgrade modifiers,
  so those modifiers retain their current relative behavior.
- A full bag rejects pickups that would add an item to
  `carried_cheques`.
- Rejected pickups must not consume a pile or crate item, award pickup money, or
  increment rescue counters.
- Delivery, belt feeding, and pickups that do not occupy bag space retain their
  current behavior.
- The existing bag capacity remains unchanged.

## Implementation

The simulation remains the single source of truth:

1. `FactoryWorld.move_player` calculates a normalized bag-load multiplier from
   `len(carried_cheques)` and `MAX_CARRIED`, then applies it to the existing
   speed calculation.
2. `FactoryWorld.interact_tile` checks capacity before mutating a bag-consuming
   pile or crate pickup. The existing error feedback style is reused for a full
   bag.
3. Crate belt spawning remains possible even when the bag is full. A crate
   interaction may still process non-bag items according to the existing rules.

## Validation

Focused tests or runtime checks will verify:

- empty, partial, and full bags produce the expected movement scaling;
- a full bag cannot clear a bag-consuming pile;
- a full bag cannot unload a bag-consuming crate item;
- rejected pickups leave the source and player rewards unchanged;
- existing delivery and belt-feed behavior remains available at capacity.
