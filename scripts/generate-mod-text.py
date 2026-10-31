"""Regenerate tools/LocalExile.Export/mod-text.json from PoB's own mod data, after updating src/Data.

Each entry is a Mods.dat Id with the lines PoB shows for that modifier. The exporter matches item text against this
index, so it can name a modifier its hand-written translations do not cover. Run from any folder:
  python scripts/generate-mod-text.py
"""
import json
from pathlib import Path

import parity

OUTPUT = parity.ROOT / 'tools/LocalExile.Export/mod-text.json'
# ModScalability, ModCache and the map files describe other things and are not item modifiers.
FILES = ['ModExplicit', 'ModItemExclusive', 'ModCorrupted', 'ModDelve', 'ModSynthesis', 'ModScourge', 'ModEldritch', 'ModFlask', 'ModTincture',
    'ModGraft', 'ModJewel', 'ModJewelAbyss', 'ModJewelCluster', 'ModJewelCharm', 'ModVeiled', 'ModMaster', 'ModFoulborn', 'ModNecropolis']


def main():
    temporary = OUTPUT.with_suffix('.raw.json')
    run = parity.open_lua()
    run(f'outPath={json.dumps(temporary.as_posix())}; files={json.dumps(json.dumps(FILES))}')
    run(r'''
        local json=require('dkjson')
        local lines={}
        for _,name in ipairs(json.decode(files)) do
            for id,mod in pairs(dofile('Data/'..name..'.lua')) do
                local text={}
                for _,value in ipairs(mod) do
                    if type(value)=='string' then
                        for line in value:gmatch('[^\n]+') do text[#text+1]=line end
                    end
                end
                -- Numbered entries are lists of crafting options, not Mods.dat rows.
                if type(id)=='string' and #text>0 and not lines[id] then lines[id]=text end
            end
        end
        local out=assert(io.open(outPath,'wb')); out:write(json.encode(lines)); out:close()
    ''')
    mods = json.loads(temporary.read_text(encoding='utf-8'))
    temporary.unlink()
    with OUTPUT.open('w', encoding='utf-8', newline='\n') as out:
        out.write('{\n' + ',\n'.join(f'{json.dumps(k, ensure_ascii=False)}:{json.dumps(mods[k], ensure_ascii=False, separators=(",", ":"))}' for k in sorted(mods)) + '\n}\n')
    print(f'{len(mods)} modifiers written to {OUTPUT}')


if __name__ == '__main__':
    main()
