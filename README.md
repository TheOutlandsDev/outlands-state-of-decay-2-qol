# Outlands State of Decay 2 QOL

A relaxed, veteran-oriented State of Decay 2 setup with first person, roomy storage, easier community additions, longer mission timers, and more activity income. This repository contains **original setup tools, patch recipes, version locks, and documentation**. Download the actual mods from their authors.

**Version 0.1.0 — experimental.** The local build reproduces all 17 installed PAK hashes and passes archive/conflict checks. Campaign, Heartland, Daybreak, and co-op gameplay compatibility are **not fully verified**. This is for **State of Decay 2**, Steam app 495420/build 16535856; it is not a YOSE modpack.

## What changes

| Feature | Current preset |
| --- | --- |
| First person | MrYummi First Person Mode 1.3; Shift + F3 toggles the camera |
| Community additions | Enclave Editor 3.1.5; F3 opens the menu |
| Activity income | Positive host/client activity-currency rewards doubled; mission-specific payouts and trade prices unchanged |
| Cargo | 100 vehicle cargo slots; eight-slot backpacks with normal weight |
| Loot | Original map quotas. The previous 2x quota boost is removed; existing generated loot is not deleted |
| Base and scheduling | Improved facilities, expanded building flexibility, longer mission timers, lights, clock and follower HUD |
| Content | Army/Resident Evil outfits, bounty tabs, more specialization choices, Better Daybreak Rewards |

No increased zombie density or combat-difficulty overhaul is selected. The old Resident Evil helicopter actor and obsolete first-person actor are excluded from generated integration.

## Start here

1. Read the [mod list and credits](docs/MODS.md), then download the exact versions yourself. PAK hashes in `profile/mods.lock.json` identify the selected variants.
2. Follow [installation](docs/INSTALL.md) to prepare the profile locally, build integration and validate it before installing.
3. Read the [controls and Heartland notes](docs/CONTROLS.md).
4. Check [validation and remaining tests](docs/VALIDATION.md) before relying on a long-running community or co-op session.

The tools require Python 3.10+ and Windows PowerShell 5.1. Python dependencies are standard-library only. Integration uses your separately downloaded Mod Manager 2.2.22 and Mono.Cecil 0.11.6.

## Saves and rollback

Installation requires the game to be closed and makes a full, hash-verified local Saved backup before swapping the mod directory. Rollback restores **mods only** and preserves progress made after installation. Backups, download caches and generated PAKs stay in ignored local directories. Never restore an old save over newer progress casually.

## Distribution

There are no game files, mod archives, compiled mod PAKs, account identifiers or save files in this repository. The recipes apply locally to exact, separately acquired inputs. Nexus sign-in, downloads, mod author permissions and dependency terms remain the user's responsibility. The MIT license covers this project's original source and documentation only; it does not relicense any game, downloaded mod, integration output or dependency. See [third-party notices](THIRD_PARTY.md).

Not affiliated with Undead Labs, Xbox, Nexus Mods, or the credited mod authors.
