"""Prepare, validate and install the pinned profile using locally owned inputs."""
from pathlib import Path
from collections import defaultdict
import argparse
import datetime
import json
import os
import re
import shutil
import struct
import subprocess
import uuid

from pak import index, payload, write_pak, file_hash, digest

ROOT = Path(__file__).resolve().parent.parent


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def patch_bytes(data, recipe):
    require(digest(data) == recipe['before_sha256'], 'Asset version differs from the pinned recipe')
    edited = bytearray(data)
    for change in recipe['edits']:
        fmt = {'int32': '<i', 'float32': '<f'}[change['type']]
        offset = change['offset']
        require(0 <= offset <= len(data) - 4, 'Patch offset out of bounds')
        require(struct.unpack_from(fmt, data, offset)[0] == change['before'], 'Patch preimage differs')
        struct.pack_into(fmt, edited, offset, change['after'])
    require(digest(edited) == recipe['after_sha256'], 'Patched asset checksum differs')
    return bytes(edited)


def prepare(downloads, game, build):
    lock = read_json(ROOT / 'profile/mods.lock.json')
    require(not build.exists(), 'Build folder exists; choose a fresh --build folder')
    require((game / 'StateOfDecay2/Binaries/Win64/StateOfDecay2-Win64-Shipping.exe').is_file(), 'Choose the State of Decay 2 installation root')
    manifest = game.parent.parent / 'appmanifest_495420.acf'
    require(manifest.is_file(), 'Steam app manifest not found; this recipe targets the Steam build')
    match = re.search(r'"buildid"\s+"(\d+)"', manifest.read_text())
    require(match and match[1] == lock['steam_build_id'], 'Game build differs; audit assets before updating the recipe')
    available = {file_hash(path): path for path in downloads.rglob('*.pak')}
    missing = [row['metadata']['display_name'] for row in lock['mods'] if row['input_sha256'] not in available]
    require(not missing, 'Missing exact downloaded PAK versions: ' + ', '.join(missing))
    paks = build / 'Paks'
    paks.mkdir(parents=True)
    records = []
    vehicle = read_json(ROOT / 'patches/vehicle-storage.json')
    changes = {row['path'].lower(): row for row in vehicle['patches']}
    for row in lock['mods']:
        source = available[row['input_sha256']]
        target = paks / row['file']
        if row['file'].startswith('110-'):
            assets = []
            for entry in index(source)['entries']:
                data = payload(source, entry)
                recipe = changes.get(entry['name'].lower())
                if recipe:
                    data = patch_bytes(data, recipe)
                assets.append((entry['name'], data))
            write_pak(target, assets)
        else:
            shutil.copy2(source, target)
        require(file_hash(target) == row['output_sha256'], 'Output PAK checksum differs: ' + row['file'])
        records.append(dict(file=row['file'], sha256=row['output_sha256'], metadata=row['metadata']))
    influence = read_json(ROOT / 'patches/influence.json')
    wanted = {r['game_path'].lower(): r for r in influence['patches']}
    native = {}
    for archive in sorted((game / 'StateOfDecay2/Content/Paks').glob('*.pak')):
        for entry in index(archive)['entries']:
            key = entry['name'].lower()
            if key in wanted:
                # Whole-asset SHA-256 preimages, rather than native compressed-entry
                # hashes, pin these four read-only game inputs.
                raw = payload(archive, entry, verify=False)
                if digest(raw) == wanted[key]['before_sha256']:
                    native[key] = raw
    require(set(native) == set(wanted), 'Pinned native influence assets were not all found')
    assets = [(r['path'], patch_bytes(native[r['game_path'].lower()], r)) for r in influence['patches']]
    assets.append(('StateOfDecay2/metadata.json', json.dumps(influence['metadata'], indent=2).encode()))
    target = paks / influence['file']
    write_pak(target, assets)
    require(file_hash(target) == influence['output_sha256'], 'Influence PAK checksum differs')
    records.append(dict(file=target.name, sha256=influence['output_sha256'], metadata=influence['metadata']))
    write_json(build / 'profile.json', records)
    print('Prepared 16 mod PAKs. Run Integrate-Profile.ps1 before validation or install.')


def validate(build):
    records = read_json(build / 'profile.json')
    paks = build / 'Paks'
    expected = {row['file'] for row in records} | {'000-0ModIntegration_P.pak'}
    require({p.name for p in paks.iterdir()} == expected, 'Unexpected, missing or nested build files')
    require(len(expected) == 17, 'This revision expects exactly 17 PAKs')
    owners = defaultdict(list)
    data = {}
    count = 0
    for path in sorted(paks.glob('*.pak')):
        for entry in index(path)['entries']:
            raw = payload(path, entry)
            count += 1
            key = entry['name'].lower()
            if key.endswith(('.uasset', '.uexp', '.umap')):
                owners[key].append(path.name)
                data[key] = raw
                if key.endswith('.uasset'):
                    require(raw[:4] == bytes.fromhex('c1832a9e'), 'Invalid Unreal asset header')
    conflicts = {key: value for key, value in owners.items() if len(value) > 1}
    require(not conflicts, 'Conflicting asset overrides: ' + repr(conflicts))
    actors = []
    refs = []
    for row in records:
        require(file_hash(paks / row['file']) == row['sha256'], 'Mod PAK checksum differs: ' + row['file'])
        actors += row['metadata'].get('spawn_actor') or []
        refs += [value[0] for value in row['metadata'].get('new_outfit') or []]
    for ref in actors + refs:
        require('stateofdecay2/content/' + ref[6:].lower() + '.uasset' in data, 'Missing custom asset: ' + ref)
    extender = next((raw for key, raw in data.items() if key.endswith('/extenderindex.uasset')), None)
    require(extender is not None, 'Integration extender asset missing')
    for actor in actors:
        require(actor.encode() in extender, 'Unregistered actor: ' + actor)
    require(b'CopterSpawn' not in extender and b'/Game/FirstPerson/' not in extender, 'An excluded legacy actor was enabled')
    require(not any('mapquota' in key for key in data), 'Loot quota override remains active')
    for recipe_name in ('vehicle-storage', 'influence'):
        for recipe in read_json(ROOT / ('patches/' + recipe_name + '.json'))['patches']:
            require(digest(data[recipe['path'].lower()]) == recipe['after_sha256'], 'Patched asset checksum differs')
    result = dict(status='STATIC_VALIDATION_PASSED', pak_count=17, payloads_verified=count,
                  unique_assets=len(owners), conflicting_assets=0, registered_actors=len(actors),
                  custom_references=len(actors + refs), runtime_tested=False,
                  pak_manifest=[dict(file=p.name, sha256=file_hash(p)) for p in sorted(paks.glob('*.pak'))])
    return result


def game_closed():
    require(os.name == 'nt', 'Installation is supported on Windows only')
    result = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, check=True)
    require(not any(name in result.stdout.lower() for name in ('stateofdecay2.exe', 'stateofdecay2-win64-shipping.exe')), 'Close State of Decay 2 first')


def checked_saved(path):
    path = path.resolve()
    require(path.name.lower() == 'saved' and path.parent.name.lower() == 'stateofdecay2', 'Saved path must end with StateOfDecay2/Saved')
    require(path.is_dir(), 'Saved folder does not exist; launch and exit the game once first')
    require(not path.is_symlink() and not (path / 'Paks').is_symlink(), 'Refusing a linked save/mod directory')
    return path


def install(build, saved, backups):
    game_closed()
    result = validate(build)
    saved = checked_saved(saved)
    cooked = saved / 'Cooked'
    require(not cooked.exists() or not any(p.is_file() for p in cooked.rglob('*')), 'Loose Cooked mods exist; resolve these conflicts before installation')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    backup = backups.resolve() / stamp
    require(not backup.is_relative_to(saved), 'Backup must be outside the active Saved directory')
    require(not build.resolve().is_relative_to(saved), 'Build must be outside the active Saved directory')
    require(not saved.is_relative_to(backups.resolve()), 'Do not place Saved inside the backup root')
    backup.mkdir(parents=True, exist_ok=False)
    manifest = []
    for source in sorted(saved.rglob('*')):
        if source.is_file():
            relative = source.relative_to(saved)
            target = backup / 'Saved' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            value = file_hash(source)
            require(file_hash(target) == value, 'Backup checksum mismatch')
            manifest.append(dict(path=relative.as_posix(), sha256=value))
    write_json(backup / 'backup-manifest.json', manifest)
    game_closed()
    for row in manifest:
        require(file_hash(saved / row['path']) == row['sha256'], 'Saved data changed during backup; deployment cancelled')
    active = saved / 'Paks'
    candidate = saved / ('Paks-prepared-' + stamp)
    shutil.copytree(build / 'Paks', candidate)
    previous = backup / 'previous-Paks'
    had_previous = active.exists()
    if had_previous:
        active.rename(previous) if active.drive == previous.drive else shutil.move(str(active), str(previous))
    try:
        candidate.rename(active)
        for row in result['pak_manifest']:
            require(file_hash(active / row['file']) == row['sha256'], 'Installed checksum mismatch')
        for row in manifest:
            if not row['path'].lower().startswith('paks/'):
                require(file_hash(saved / row['path']) == row['sha256'], 'Non-mod Saved data changed')
    except BaseException:
        if active.exists():
            shutil.move(str(active), str(backup / 'failed-new-Paks'))
        if had_previous:
            shutil.move(str(previous), str(active))
        raise
    write_json(backup / 'installation.json', dict(saved=str(saved), had_previous=had_previous, validation=result))
    print('Installed. Full verified backup: ' + str(backup))
    print('Saves and Steam Cloud settings were not edited.')


def restore_mods(backup):
    game_closed()
    receipt = read_json(backup / 'installation.json')
    saved = checked_saved(Path(receipt['saved']))
    active = saved / 'Paks'
    expected = receipt['validation']['pak_manifest']
    require(active.is_dir(), 'Current Paks folder is missing')
    require({p.name for p in active.iterdir()} == {r['file'] for r in expected}, 'Current mods differ; review them before rollback')
    for row in expected:
        require(file_hash(active / row['file']) == row['sha256'], 'Current mod changed; review before rollback')
    old = backup / 'previous-Paks'
    if receipt['had_previous']:
        manifest = [r for r in read_json(backup / 'backup-manifest.json') if r['path'].lower().startswith('paks/')]
        require(old.is_dir(), 'Previous PAK backup is missing')
        for row in manifest:
            require(file_hash(old / Path(row['path']).relative_to('Paks')) == row['sha256'], 'Previous mod backup differs')
    destination = backup / ('disabled-profile-' + uuid.uuid4().hex[:8])
    require(not destination.exists(), 'Rollback destination exists')
    shutil.move(str(active), str(destination))
    if receipt['had_previous']:
        shutil.copytree(old, active)
    print('Previous mods restored. Current game progress was not rolled back.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--downloads', type=Path, required=True)
    p.add_argument('--game', type=Path, required=True)
    p.add_argument('--build', type=Path, default=ROOT / '.work/build')
    p = sub.add_parser('validate')
    p.add_argument('--build', type=Path, default=ROOT / '.work/build')
    p = sub.add_parser('install')
    p.add_argument('--build', type=Path, default=ROOT / '.work/build')
    p.add_argument('--saved', type=Path, default=Path.home() / 'AppData/Local/StateOfDecay2/Saved')
    p.add_argument('--backups', type=Path, default=ROOT / '.work/backups')
    p = sub.add_parser('restore-mods')
    p.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare(args.downloads, args.game, args.build)
        elif args.command == 'validate':
            print(json.dumps(validate(args.build), indent=2))
        elif args.command == 'install':
            install(args.build, args.saved, args.backups)
        elif args.command == 'restore-mods':
            restore_mods(args.backup.resolve())
    except (ValueError, OSError) as error:
        parser.exit(1, 'Stopped: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
