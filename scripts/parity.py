"""Compare what Path of Building and a LocalExile checkout compute for one saved build.

Both sides run offline. PoB runs headless through the bundled runtime. The server side exports the build into a
temporary database and runs the checkout's own stat code on it, so no client, Gateway or real save is involved.

Run from any folder:
  python scripts/parity.py --localexile C:\\LocalExile --build C:\\Builds\\Example.xml

PoB's formulas are the project's reference, not proof of the official game: treat a mismatch as a lead to check.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
EXPORTER = ROOT / 'runtime/LocalExile/evryBuild.Export.exe'
PROBE_PROJECT = ROOT / 'tools/LocalExile.Parity'
PROBE_OUTPUT = ROOT / 'artifacts/parity-probe'
PROBE = PROBE_OUTPUT / 'bin/LocalExile.Parity/debug/GameServer.Gateway.Tests.dll'
CHARACTER = 'ParityCheck'
CLASSES = ['Scion', 'Marauder', 'Ranger', 'Witch', 'Duelist', 'Templar', 'Shadow']
# PoB's slot names by Inventories.dat row, as the exporter writes them.
SLOTS = {1: 'Body Armour', 2: 'Weapon 1', 3: 'Weapon 2', 4: 'Helmet', 5: 'Amulet', 6: 'Ring 1', 7: 'Ring 2', 8: 'Gloves', 9: 'Boots',
    10: 'Belt', 14: 'Weapon 1 Swap', 15: 'Weapon 2 Swap'}
# (label, PoB output key, server field). Resistances are uncapped, so a change above the cap still shows.
STATS = [
    ('Strength', 'Str', 'Strength'), ('Dexterity', 'Dex', 'Dexterity'), ('Intelligence', 'Int', 'Intelligence'),
    ('Life', 'Life', 'Life'), ('Mana', 'Mana', 'Mana'), ('Energy Shield', 'EnergyShield', 'EnergyShield'), ('Ward', 'Ward', 'Ward'),
    ('Armour', 'Armour', 'Armour'), ('Evasion', 'Evasion', 'Evasion'), ('Accuracy', 'Accuracy', 'Accuracy'),
    ('Fire resistance', 'FireResistTotal', 'FireResistance'), ('Cold resistance', 'ColdResistTotal', 'ColdResistance'),
    ('Lightning resistance', 'LightningResistTotal', 'LightningResistance'), ('Chaos resistance', 'ChaosResistTotal', 'ChaosResistance'),
    ('Max fire resistance', 'FireResistMax', 'FireMaxResistance'), ('Max cold resistance', 'ColdResistMax', 'ColdMaxResistance'),
    ('Max lightning resistance', 'LightningResistMax', 'LightningMaxResistance'), ('Max chaos resistance', 'ChaosResistMax', 'ChaosMaxResistance'),
    ('Attack block', 'BlockChance', 'BlockChance'), ('Spell block', 'SpellBlockChance', 'SpellBlockChance'),
    ('Spell suppression', 'SpellSuppressionChance', 'SpellSuppressionChance'),
]


def normalize(xml):
    """Remove what the exporter or a fresh server character cannot hold, so both sides describe one character."""
    xml = re.sub(r'<Socket\s[^>]*/>', '', xml)  # Passive-tree jewels: the exporter skips them.
    xml = re.sub(r'(<Slot\b[^>]*?)\s+active="true"', r'\1', xml)  # Flasks in use: the server's start unused.
    return re.sub(r'\b(bandit|pantheonMajorGod|pantheonMinorGod)="[^"]*"', r'\1="None"', xml)


def clear_slots(xml, slots):
    """Empty these equipment slots: PoB must not count an item the exporter could not write."""
    def clear(match):
        tag = match.group(0)
        name = re.search(r'\bname="([^"]*)"', tag)
        return re.sub(r'\bitemId="\d+"', 'itemId="0"', tag) if name and name.group(1) in slots else tag
    return re.sub(r'<Slot\s[^>]*>', clear, xml)


def skipped_slots(warnings):
    return {m.group(1) for m in (re.match(r'Skipped item in (.+?): ', w) for w in warnings) if m}


def skipped_lines(warnings):
    """The modifier lines the exporter could not write, as (base item, line). The last quote ends the line, which may hold quotes."""
    found = (re.match(r"Skipped modifier on (.+?): .*?'(.+)'", w) for w in warnings)
    return [dict(base=m.group(1), line=m.group(2)) for m in found if m]


def still_counted(unmatched, dropped):
    """Unremoved lines that matter: not on an item PoB dropped whole, and not an influence header, which PoB does not count as a modifier."""
    return [line for line in unmatched if line.split(': ')[0] not in dropped and not line.endswith(' Item')]


def saved_progress(database, warnings):
    connection = sqlite3.connect(database)
    try:
        save = json.loads(connection.execute('SELECT save FROM characters WHERE name=?', (CHARACTER,)).fetchone()[0])
    finally:
        connection.close()
    return dict(passives=save.get('Passives') or [], masteries=save.get('MasteryEffects') or {}, skipped=skipped_lines(warnings))


def compare(pob, server):
    """One row per stat, with its difference from PoB and a status of match, rounding or mismatch."""
    rows = []
    for label, pob_key, server_key in STATS:
        expected, actual = pob.get(pob_key), server.get(server_key)
        if expected is None or actual is None:
            rows.append(dict(stat=label, pob=expected, server=actual, difference=None, status='missing'))
            continue
        difference = actual - expected
        status = 'match' if abs(difference) < 0.5 else 'rounding' if abs(difference) <= 1 else 'mismatch'
        rows.append(dict(stat=label, pob=expected, server=actual, difference=difference, status=status))
    return rows


def number(value):
    return 'n/a' if value is None else f'{value:g}'


def render(rows, skipped, unmatched, identity, show_skipped=False, inactive=()):
    counts = {status: sum(r['status'] == status for r in rows) for status in ('match', 'rounding', 'mismatch', 'missing')}
    width = max(len(r['stat']) for r in rows)
    lines = [identity, '', f"{'Stat':<{width}}  {'PoB':>10}  {'Server':>10}  {'Diff':>10}  Status"]
    for r in rows:
        difference = '' if r['difference'] is None else f"{r['difference']:+g}"
        lines.append(f"{r['stat']:<{width}}  {number(r['pob']):>10}  {number(r['server']):>10}  {difference:>10}  {'' if r['status'] == 'match' else r['status']}")
    lines += ['', f"{counts['match']} match, {counts['rounding']} rounding, {counts['mismatch']} mismatch, {counts['missing']} missing"]
    if inactive:
        lines += ['', f'The server treats {len(inactive)} worn item(s) as inactive, so they are left out of both columns above:'] + [f'  - {name}' for name in inactive]
    if skipped:
        lines += ['', f'The exporter could not write {len(skipped)} modifier line(s), so neither side counts them.']
        if show_skipped:
            lines += [f"  - {s['base']}: {s['line']}" for s in skipped]
    if unmatched:
        lines += ['', f'{len(unmatched)} of those lines were not found in PoB, so PoB still counts them. They can explain a mismatch:']
        lines += [f'  - {line}' for line in unmatched]
    return '\n'.join(lines)


def pob_worker(xml_path, progress_path, out_path):
    """Runs in its own process: PoB prints through the C runtime and changes the working directory."""
    runtime = ROOT / 'runtime'
    os.add_dll_directory(str(runtime))
    lua = ctypes.CDLL(str(runtime / 'lua51.dll'))
    lua.luaL_newstate.restype = ctypes.c_void_p
    lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
    lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lua.luaL_loadstring.restype = ctypes.c_int
    lua.lua_pcall.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lua.lua_pcall.restype = ctypes.c_int
    lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
    lua.lua_tolstring.restype = ctypes.c_void_p
    state = lua.luaL_newstate()
    lua.luaL_openlibs(state)

    def run(source):
        if lua.luaL_loadstring(state, source.encode()) or lua.lua_pcall(state, 0, 0, 0):
            size = ctypes.c_size_t()
            pointer = lua.lua_tolstring(state, -1, ctypes.byref(size))
            raise SystemExit(ctypes.string_at(pointer, size.value).decode('utf-8', 'replace'))

    os.chdir(ROOT / 'src')
    run("package.path='../runtime/lua/?.lua;../runtime/lua/?/init.lua;'..package.path; package.cpath='../runtime/?.dll;'..package.cpath; arg={}")
    run("dofile('HeadlessWrapper.lua')")
    run(f'xmlPath={json.dumps(Path(xml_path).as_posix())}; progressPath={json.dumps(Path(progress_path).as_posix())}; '
        f'outPath={json.dumps(Path(out_path).as_posix())}; keys={json.dumps(json.dumps([s[1] for s in STATS]))}')
    run(r'''
        local json=require('dkjson')
        local function read(path) local file=assert(io.open(path,'rb')); local text=file:read('*a'); file:close(); return text end
        loadBuildFromXML(read(xmlPath))
        -- PoB calculates the tree the save holds, not the build's: clusters, tattoos and special nodes were not exported.
        local progress=json.decode(read(progressPath))
        local masteries={}
        for node,effect in pairs(progress.masteries) do masteries[tonumber(node)]=effect end
        build.spec:ImportFromNodeList(nil,build.spec.curClassId,0,0,progress.passives,{},masteries)
        -- PoB also drops the lines the exporter could not write. Lines match by base and wording: rolls and catalysts
        -- change the numbers, which the two programs can also round differently.
        local function wording(line) return (line:gsub('%(%-?%d+%.?%d*%-%-?%d+%.?%d*%)','#'):gsub('%-?%d+%.?%d*','#')) end
        local skipped,unmatched={},{}
        for _,entry in ipairs(progress.skipped) do skipped[entry.base..'\n'..wording(entry.line)]=entry end
        local removed={}
        for _,slot in pairs(build.itemsTab.slots) do
            local item=build.itemsTab.items[slot.selItemId]
            if item then
                local changed=false
                for _,lines in ipairs({item.enchantModLines,item.scourgeModLines,item.implicitModLines,item.explicitModLines,item.crucibleModLines}) do
                    for index=#lines,1,-1 do
                        local key=item.baseName..'\n'..wording(lines[index].line)
                        if skipped[key] then removed[key]=true; table.remove(lines,index); changed=true end
                    end
                end
                if changed then item:BuildAndParseRaw() end
            end
        end
        for key,entry in pairs(skipped) do if not removed[key] then unmatched[#unmatched+1]=entry.base..': '..entry.line end end
        build.itemsTab:PopulateSlots()
        -- Auras and other skill effects are off on a fresh server character, and the Kitava penalties need quest flags.
        for _,group in ipairs(build.skillsTab.socketGroupList) do group.enabled=false end
        build.configTab.input.resistancePenalty=0
        build.configTab:BuildModList()
        build.buildFlag=true
        runCallback('OnFrame')
        local output=build.calcsTab.mainOutput
        local values={}
        for _,key in ipairs(json.decode(keys)) do values[key]=output[key] end
        -- CalcDefence keeps the maximum in a local, so it is read the same way here.
        local modDB=build.calcsTab.mainEnv.player.modDB
        for _,element in ipairs({'Fire','Cold','Lightning','Chaos'}) do
            local stat=element..'ResistMax'
            values[stat]=modDB:Override(nil,stat) or math.min(data.misc.MaxResistCap,
                modDB:Sum('BASE',nil,stat,element~='Chaos' and 'ElementalResistMax' or nil))
        end
        values.unmatched=unmatched
        local out=assert(io.open(outPath,'wb')); out:write(json.encode(values)); out:close()
    ''')


def pob_values(xml, progress, folder):
    folder = Path(folder)
    xml_path, progress_path, out = folder / 'build.xml', folder / 'progress.json', folder / 'pob.json'
    xml_path.write_text(xml, encoding='utf-8')
    progress_path.write_text(json.dumps(progress), encoding='utf-8')
    done = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--pob-worker', str(xml_path), str(progress_path), str(out)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    if done.returncode or not out.is_file():
        raise SystemExit(f'PoB could not calculate this build:\n{done.stderr.strip()}')
    return json.loads(out.read_text(encoding='utf-8'))


def probe(localexile, *arguments):
    done = subprocess.run(['dotnet', str(PROBE), *arguments], cwd=localexile, capture_output=True, text=True, encoding='utf-8')
    if done.returncode:
        raise SystemExit(f'The server probe failed:\n{done.stderr.strip()}')
    return done.stdout


def export(database, data, xml):
    def request(operation, **values):
        payload = dict(operation=operation, database=str(database), dataFolder=str(data), account='parity', name=CHARACTER, league='Standard', code=xml, **values)
        done = subprocess.run([str(EXPORTER)], input=json.dumps(payload), capture_output=True, text=True, encoding='utf-8')
        reply = json.loads(done.stdout)
        if not reply['ok']:
            raise SystemExit(f"The exporter refused this build: {reply['error']}")
        return reply
    preview = request('preview')
    created = request('export', previewKey=preview['previewKey'])
    # A reply shows at most 45 warnings; the report beside the backup has all of them.
    report = json.loads(Path(created['compatibilityReport']).read_text(encoding='utf-8'))
    return {**preview, 'warnings': report['warnings']}


def run(localexile, build, build_probe=True):
    localexile = Path(localexile).resolve()
    if not (localexile / 'data/tables').is_dir():
        raise SystemExit(f'{localexile} has no extracted game data in data/tables.')
    if not EXPORTER.is_file():
        raise SystemExit('Run scripts/build-exporter.ps1 first.')
    if build_probe:
        done = subprocess.run(['dotnet', 'build', str(PROBE_PROJECT), '--artifacts-path', str(PROBE_OUTPUT), f'-p:LocalExilePath={localexile}',
            '--nologo', '--verbosity', 'quiet'], capture_output=True, text=True, encoding='utf-8')
        if done.returncode:
            raise SystemExit(f'The server probe did not build:\n{done.stdout}{done.stderr}')
    elif not PROBE.is_file():
        raise SystemExit('The server probe is not built. Run once without --no-build.')
    xml = normalize(Path(build).read_text(encoding='utf-8-sig'))
    with tempfile.TemporaryDirectory(prefix='evrybuild-parity-', ignore_cleanup_errors=True) as folder:
        database = Path(folder) / 'saves.db'
        probe(localexile, 'init', str(database))
        connection = sqlite3.connect(database)
        with connection:
            connection.execute('INSERT INTO accounts VALUES(?,?,?)', (str(uuid.uuid4()), 'parity', '{}'))
        connection.close()
        exported = export(database, localexile / 'data', xml)
        # The Gateway logs to the same stream; the probe's result is always the last line.
        server = json.loads(probe(localexile, 'stats', str(database), CHARACTER, str(CLASSES.index(exported['class']))).strip().splitlines()[-1])
        inactive = [item for item in server['Equipment'] if item['Inactive']]
        # A whole item the server switched off is reported as one finding. PoB drops it too, so what remains is formulas.
        empty = skipped_slots(exported['warnings']) | {SLOTS[item['Row']] for item in inactive}
        pob = pob_values(clear_slots(xml, empty), saved_progress(database, exported['warnings']), folder)
    commit = subprocess.run(['git', '-C', str(localexile), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip() or 'unknown'
    identity = f"{Path(build).stem}: {exported['class']} level {server['Level']}, {server['Passives']} passives, {exported['items']} items, LocalExile {commit}"
    names = [item['Name'] for item in inactive]
    return dict(identity=identity, rows=compare(pob, server), skipped=skipped_lines(exported['warnings']),
        unmatched=still_counted(pob.get('unmatched') or [], names), inactive=names)


def main():
    if len(sys.argv) == 5 and sys.argv[1] == '--pob-worker':
        pob_worker(*sys.argv[2:])
        return 0
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--localexile', required=True, help='a LocalExile checkout with extracted game data')
    parser.add_argument('--build', required=True, type=Path, help='a saved PoB build (.xml)')
    parser.add_argument('--no-build', action='store_true', help='reuse the server probe from the last run')
    parser.add_argument('--show-skipped', action='store_true', help='list the modifier lines the exporter could not write')
    parser.add_argument('--json', type=Path, help='also write the result here')
    args = parser.parse_args()
    result = run(args.localexile, args.build, not args.no_build)
    print(render(result['rows'], result['skipped'], result['unmatched'], result['identity'], args.show_skipped, result['inactive']))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
