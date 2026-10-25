# Installation from source

This is a pinned setup kit, not a one-click download of other authors' files. The public repository contains no PAKs. Use an official game installation and obtain every mod from its original author. Older pinned variants may require the author's file/version history; do not substitute a different file just to bypass a checksum.

## 1. Prepare downloads

Download and extract the 15 external mod PAKs listed in [MODS.md](MODS.md) into `.downloads` inside this checkout. The builder searches recursively and identifies files by SHA-256, so original filenames can differ. Only one intended variant of each mod is selected.

Separately download [State of Decay 2 Mod Manager 2.2.22](https://www.nexusmods.com/stateofdecay2/mods/96) and [Mono.Cecil 0.11.6](https://www.nuget.org/packages/Mono.Cecil/0.11.6). Extract these under `.downloads/tools`; use Mono.Cecil's **lib/net40/Mono.Cecil.dll**. Tool hashes are pinned in `profile/tool-versions.json`. A NuGet `.nupkg` is a ZIP archive; extract it locally.

Do not commit `.downloads`, `.work`, tools from other authors, generated PAKs, or backups. They are ignored.

## 2. Build the profile

Open a terminal in the repository. Replace the example game/tool paths with your own:

```powershell
python tools/profile.py prepare --downloads .downloads --game "D:\SteamLibrary\steamapps\common\StateOfDecay2"

powershell -NoProfile -File tools/Build-Integration.ps1 -IntegratorExe ".downloads\tools\ModIntegrator.exe" -CecilDll ".downloads\tools\Mono.Cecil\lib\net40\Mono.Cecil.dll"

python tools/profile.py validate
```

`prepare` only reads game/downloaded inputs and writes `.work/build`. It checks the Steam build, all mod input hashes, every changed asset's preimage hash, exact old property values, and complete output hashes. It creates the cargo adjustment and influence PAK locally. It does not edit your installed game or saves.

The integration script extracts dependency DLL resources from your supplied official tool and makes a local copy with UI calls suppressed. It registers only the metadata in the prepared profile. The original tool is preserved. All extracted/modified dependencies remain under `.work/build`. No patched executable is shipped in this repository or placed in the game's mod folder.

If a build folder exists, use a new directory rather than overwriting it. Pass the same `--build <directory>` to the Python commands and `-ProfileDirectory <directory>` to PowerShell. Missing/wrong-version inputs stop the build; they are not downloaded automatically.

Expected static result: 17 PAKs, 1,335 verified payloads, 1,317 unique game assets, zero duplicate asset paths, eight registered actors and 36 custom references. A static pass does not prove gameplay behavior.

## 3. Install

Exit State of Decay 2 and allow Steam to finish syncing first. Then run:

```powershell
python tools/profile.py install
```

The default target is your own `AppData/Local/StateOfDecay2/Saved` directory. If needed, specify it explicitly:

```powershell
python tools/profile.py install --saved "D:\CustomProfile\StateOfDecay2\Saved"
```

The installer refuses a running game and unresolved loose `Saved/Cooked` assets. It backs up the entire current Saved directory to `.work/backups/<timestamp>` and verifies every copied file. It swaps only `Saved/Paks`, validates installed hashes, and confirms all non-mod Saved files are unchanged. Original mod files are retained for rollback. Steam Cloud settings and original game archives/executables are not edited.

Launch through Steam normally. No manager has to remain open.

## 4. Roll back the mod setup

With the game closed, use the exact backup path printed by installation:

```powershell
python tools/profile.py restore-mods --backup ".work\backups\YOUR-INSTALL-TIMESTAMP"
```

This checks that the active mods still match the installed profile, archives them, and restores the previous mods. It does not restore old saves or erase later progress. If you changed mods afterward, review the differences before rollback.

Before playing without the storage mods, empty oversized cargo into your locker so items do not become inaccessible with smaller vanilla capacities.
