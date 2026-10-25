# Validation status

Version 0.1.0 is an experimental source/setup release, published October 25, 2026. It captures the October 22 local profile rather than claiming a new gameplay test.

## Verified

- The public source builder reproduced **all 17 existing profile PAK hashes**, including generated integration, from local author downloads and the pinned game installation.
- All **1,335** stored payload hashes verified and payloads decoded successfully.
- **1,317** unique game assets; **zero** duplicate active asset paths.
- **Eight** integration actors and **36** custom references resolve to supplied assets.
- All **55** explicit cargo edits produce **100-slot** properties; the 56th vehicle definition inherits the cargo-van capacity.
- **81** activity-currency fields doubled in **four** assets. Before/after asset hashes and exact property preimages guard each change.
- No map-quota asset override remains in this profile.
- During the October 22 local install, a fresh full save backup was verified and all six saves plus the other non-mod Saved files were unchanged afterward.
- The public package excludes downloaded binaries, game assets, saves, account-specific paths and identifiers. Generated files and local validation caches are ignored.

See `evidence/static-validation.json` for the sanitized static result. Local build receipts can contain private paths; do not publish them without sanitizing.

## Not verified

| Area | Status |
| --- | --- |
| First-person movement, aiming, melee and driving | Gameplay check still required |
| Enclave Editor additions in Heartland | Gameplay and story-progression check still required |
| Actual influence awards and storage transfers | Gameplay check still required |
| Campaign and Heartland loot generation | Gameplay check still required |
| Daybreak session, AI and rewards | Gameplay check still required |
| Co-op host/client compatibility and long-term save stability | Not tested |

An earlier profile reached the game's menus but authentication interrupted loading. Reaching menus or passing archive checks is not a successful gameplay test. No game was launched as part of preparing this public repository.

## Suggested playtest

Back up current saves first. Use a disposable community/slot where practical, then check the camera controls, a vehicle cargo transfer, backpack capacity, base storage, follower display and an activity reward. Test Heartland additions without duplicating active story NPCs. Check a private Daybreak session separately. Preserve original progress when reverting tests; do not overwrite newer real play with an older backup.

Run source/safety tests with:

```powershell
python -m unittest discover -s tests -v
```
