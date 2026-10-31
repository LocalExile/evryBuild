"""Run the actual self-contained offline exporter against temporary SQLite databases."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[2]
EXE = ROOT / 'runtime/LocalExile/evryBuild.Export.exe'
DATA = None
BUILD = None
XML = '<PathOfBuilding><Build level="20" className="Witch"/><Tree activeSpec="1"><Spec nodes="" classId="3" ascendClassId="0" treeVersion="3_29"/></Tree></PathOfBuilding>'


@contextmanager
def connect(path):
    connection=sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


RING = 'Rarity: NORMAL\nIron Ring'
RING_HASH, ARMOUR_HASH = 1001, 1002


class ExportBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='evrybuild-offline-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.data = self.folder/'data'; (self.data/'tables').mkdir(parents=True)
        self.database = self.data/'saves.db'; self.account = str(uuid.uuid4())
        with connect(self.database) as db:
            db.executescript('''PRAGMA journal_mode=WAL;
                CREATE TABLE accounts(id TEXT PRIMARY KEY,name TEXT UNIQUE COLLATE NOCASE,account TEXT NOT NULL) STRICT;
                CREATE TABLE account_characters(id TEXT PRIMARY KEY,account_id TEXT NOT NULL,name TEXT UNIQUE COLLATE NOCASE,created_utc TEXT NOT NULL,character TEXT NOT NULL) STRICT;
                CREATE TABLE characters(name TEXT PRIMARY KEY COLLATE NOCASE,save TEXT NOT NULL) STRICT;''')
            db.execute('INSERT INTO accounts VALUES(?,?,?)',(self.account,'alice','{"private":"untouched"}'))
        self.table('Characters',[{'IntegerId':3}])
        self.table('ExperienceLevels',[{'Level':20,'Experience':123000}])
        for name in ('PassiveSkills','BaseItemTypes','ItemVisualIdentity','Stats'):
            self.table(name,[])
        (self.data/'item-types.json').write_text('{"types":[]}')

    def table(self, name, rows):
        (self.data/'tables'/f'{name}.json').write_text(json.dumps(rows),encoding='utf-8')

    def request(self, operation='preview', **values):
        payload=dict(operation=operation,database=str(self.database),account='alice',name='ExternalWitch',league='Standard',code=XML)
        payload.update(values)
        result=subprocess.run([str(EXE)],input=json.dumps(payload),capture_output=True,text=True,encoding='utf-8',timeout=45)
        reply=json.loads(result.stdout)
        self.assertEqual(0 if reply['ok'] else 1,result.returncode,result.stderr)
        return reply

    def state(self):
        with connect(self.database) as db:
            return tuple(db.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall() for table in ('accounts','account_characters','characters'))


class ExportTests(ExportBase):
    def test_inspect_detects_data_and_lists_accounts_without_credentials(self):
        before=self.state(); reply=self.request('inspect')
        self.assertTrue(reply['ok']); self.assertEqual(['alice'],reply['accounts'])
        self.assertEqual(str(self.data),reply['dataFolder']); self.assertNotIn('private',json.dumps(reply))
        self.assertEqual(before,self.state())

    def test_preview_is_read_only_and_does_not_create_backups(self):
        before=self.state(); digest=hashlib.sha256(self.database.read_bytes()).hexdigest()
        reply=self.request(); self.assertTrue(reply['preview']); self.assertTrue(reply['previewKey'])
        self.assertEqual(before,self.state()); self.assertEqual(digest,hashlib.sha256(self.database.read_bytes()).hexdigest())
        self.assertFalse((self.data/'evryBuild-backups').exists())

    def test_export_commits_both_records_and_online_backup_has_prior_state(self):
        before=self.state(); preview=self.request(); created=self.request('export',previewKey=preview['previewKey'])
        self.assertTrue(created['ok'],created); self.assertFalse(created['preview'])
        report=json.loads(Path(created['compatibilityReport']).read_text(encoding='utf-8'))
        self.assertIn('prepared export',report['status']); self.assertEqual('ExternalWitch',report['character'])
        with connect(self.database) as db:
            character=json.loads(db.execute('SELECT character FROM account_characters').fetchone()[0])
            save=json.loads(db.execute('SELECT save FROM characters').fetchone()[0])
            self.assertEqual(20,character['Level']); self.assertEqual(self.account,character['AccountId'])
            self.assertEqual(123000,save['Experience']); self.assertEqual('1_1_town',character['LastTown'])
        with connect(created['backup']) as backup:
            self.assertEqual([],backup.execute('SELECT * FROM account_characters').fetchall())
            self.assertEqual(before[0],backup.execute('SELECT * FROM accounts ORDER BY 1').fetchall())

    def test_existing_name_is_refused_case_insensitively(self):
        preview=self.request(); self.assertTrue(self.request('export',previewKey=preview['previewKey'])['ok'])
        before=self.state(); duplicate=self.request(name='externalwitch')
        self.assertFalse(duplicate['ok']); self.assertEqual(before,self.state())

    def test_failed_save_rolls_back_metadata_and_preserves_accounts(self):
        preview=self.request(); before=self.state()
        with connect(self.database) as db:
            db.execute("CREATE TRIGGER failure BEFORE INSERT ON characters BEGIN SELECT RAISE(FAIL,'intentional'); END")
        reply=self.request('export',previewKey=preview['previewKey'])
        self.assertFalse(reply['ok']); self.assertEqual(before,self.state()); self.assertNotIn('intentional',reply['error'])

    def test_changed_destination_or_build_requires_new_preview(self):
        preview=self.request()
        for change in ({'name':'OtherName'},{'league':'OtherLeague'},{'code':XML.replace('level="20"','level="20" extra="changed"')}):
            with self.subTest(change=change):
                reply=self.request('export',previewKey=preview['previewKey'],**change)
                self.assertFalse(reply['ok']); self.assertIn('Preview again',reply['error'])
        self.assertEqual([],self.state()[1])

    def test_unknown_account_invalid_names_and_ruthless_are_refused(self):
        for change in ({'account':'missing'},{'name':'x'},{'name':'bad name'},{'name':'bad/../name'},{'league':'Ruthless Standard'}):
            with self.subTest(change=change): self.assertFalse(self.request(**change)['ok'])

    def test_two_exports_of_same_preview_create_only_one_character(self):
        preview=self.request()
        with ThreadPoolExecutor(max_workers=2) as executor:
            replies=list(executor.map(lambda _:self.request('export',previewKey=preview['previewKey']),range(2)))
        self.assertEqual(1,sum(r['ok'] for r in replies))
        with connect(self.database) as db:
            self.assertEqual(1,db.execute('SELECT count(*) FROM account_characters').fetchone()[0])
            self.assertEqual(1,db.execute('SELECT count(*) FROM characters').fetchone()[0])

    def test_native_encoding_and_xml_errors_do_not_write(self):
        before=self.state()
        for code in ('<broken', '<!DOCTYPE PathOfBuilding [<!ENTITY x SYSTEM "file:///private">]><PathOfBuilding>&x;</PathOfBuilding>',
                     XML.replace('treeVersion="3_29"','treeVersion="3_28"')):
            with self.subTest(code=code): self.assertFalse(self.request(code=code)['ok'])
        self.assertEqual(before,self.state())

    def test_full_account_is_refused_before_conversion(self):
        with connect(self.database) as db:
            for n in range(24): db.execute('INSERT INTO account_characters VALUES(?,?,?,?,?)',(str(uuid.uuid4()),self.account,'Slot'+str(n),'2026-01-01','{}'))
        self.assertIn('24-character',self.request()['error'])

    def test_legacy_save_collision_is_refused(self):
        legacy=self.data/'saves'; legacy.mkdir(); (legacy/'externalwitch.json').write_text('{}')
        self.assertIn('legacy save',self.request()['error'])

    def test_missing_database_is_never_created_and_wrong_schema_is_not_migrated(self):
        missing=self.folder/'missing.db'; self.assertFalse(self.request(database=str(missing))['ok']); self.assertFalse(missing.exists())
        wrong=self.folder/'wrong.db'
        with connect(wrong) as db: db.execute('CREATE TABLE unrelated(value TEXT)')
        digest=hashlib.sha256(wrong.read_bytes()).hexdigest()
        self.assertFalse(self.request(database=str(wrong))['ok']); self.assertEqual(digest,hashlib.sha256(wrong.read_bytes()).hexdigest())

    def test_unknown_mechanic_passive_is_retained_and_reported(self):
        def node(graph, starts, stats):
            return dict(PassiveSkillGraphId=graph,Id='Node'+str(graph),Name='Fixture',Characters=starts,Stats=stats,Stat1Value=10,
                SkillPointsGranted=0,AscendancyKey=None,IsExpansion=False,IsMultipleChoice=False,MasteryGroup=None,SkillType=0,DescendancyKey=None)
        self.table('Stats',[{'Id':'unknown_fixture_mechanic'}]); self.table('PassiveSkills',[node(10,[0],[]),node(11,[],[0])])
        (self.data/'passive-skill-graphs.json').write_text(json.dumps({'revision':'3.29.3b','normal':{'nodes':[{'id':10,'adjacent':[11]},{'id':11,'adjacent':[10]}]}}))
        reply=self.request(code=XML.replace('nodes=""','nodes="11"'))
        self.assertTrue(reply['ok'],reply); self.assertEqual(1,reply['passives'])
        self.assertTrue(any(f['effect']=='unknown_fixture_mechanic' and f['status']=='unknown' and f['action']=='kept' for f in reply['compatibility']))

    def test_real_saved_build_preserves_equipment_gems_and_passives(self):
        if not (DATA and BUILD): self.skipTest('Pass --data-folder and --build to validate a real saved build.')
        preview=self.request(dataFolder=str(DATA),code=BUILD.read_text(encoding='utf-8-sig'))
        self.assertTrue(preview['ok'],preview); self.assertGreater(preview['items'],0); self.assertGreater(preview['gems'],0)
        self.assertGreater(preview['passives'],0)
        created=self.request('export',dataFolder=str(DATA),code=BUILD.read_text(encoding='utf-8-sig'),previewKey=preview['previewKey'])
        self.assertTrue(created['ok'],created)
        with connect(self.database) as db:
            save=json.loads(db.execute('SELECT save FROM characters').fetchone()[0])
            self.assertEqual(preview['items'],sum(len(v) for v in save['Inventories'].values()))
            self.assertEqual(preview['gems'],sum(sum(1 for s in (i['Item'].get('Sockets') or []) if s['Gem']) for v in save['Inventories'].values() for i in v))
        self.assertTrue(any(f['status']=='unknown' for f in created['compatibility']))


class ItemSendTests(ExportBase):
    """Gateway states are simulated on a private port, so a running local Gateway cannot affect these tests."""
    def setUp(self):
        super().setUp()
        self.port=self.free_port(); self.gateway_env=dict(os.environ,Game_GATEWAY_PORT=str(self.port))
        def row(name,hash32,width,height):
            return dict(Id='Metadata/Items/'+name.replace(' ',''),Name=name,HASH32=hash32,Width=width,Height=height,ItemVisualIdentity=0,
                ItemClassesKey=None,ItemStance=None,DropLevel=1,Implicit_ModsKeys=[],TagsKeys=[],ModDomain=1)
        self.table('BaseItemTypes',[row('Iron Ring',RING_HASH,1,1),row('Plate Vest',ARMOUR_HASH,2,3)])
        self.table('ItemVisualIdentity',[{'HASH16':7}])
        (self.data/'item-types.json').write_text(json.dumps({'types':[
            {'type':'Metadata/Items/IronRing','components':['Base','Mods'],'read':2},
            {'type':'Metadata/Items/PlateVest','components':['Base','Mods','Armour'],'read':3}]}))
        self.character('Witch')

    def free_port(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0)); return probe.getsockname()[1]

    def character(self, name, played='2026-01-01T00:00:00+00:00', league='Standard', save=None):
        record=dict(Name=name,Level=90,League=league,LastPlayedUtc=played)
        saved={'Inventories':{'0':[{'Id':4,'X':0,'Y':0,'Item':{'Type':RING_HASH}}],'2':[{'Id':9,'X':0,'Y':0,'Item':{'Type':RING_HASH}}]},
            'Passives':[11],'FutureServerField':{'kept':True}} if save is None else save
        with connect(self.database) as db:
            db.execute('INSERT INTO account_characters VALUES(?,?,?,?,?)',(str(uuid.uuid4()),self.account,name,'2026-01-01',json.dumps(record)))
            if saved is not False: db.execute('INSERT INTO characters VALUES(?,?)',(name,json.dumps(saved)))

    def send(self, operation='item-preview', item=RING, **values):
        payload=dict(operation=operation,database=str(self.database),account='alice',name='Witch',item=item); payload.update(values)
        result=subprocess.run([str(EXE)],input=json.dumps(payload),capture_output=True,text=True,encoding='utf-8',timeout=45,env=self.gateway_env)
        return json.loads(result.stdout)

    def saved(self, name='Witch'):
        with connect(self.database) as db:
            return json.loads(db.execute('SELECT save FROM characters WHERE name=?',(name,)).fetchone()[0])

    @contextmanager
    def gateway(self, connected=False):
        """Listens on the private port as a Gateway would. This Python process's start time stands in for the Gateway's."""
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',self.port)); listener.listen()
            if not connected: yield; return
            with socket.create_connection(('127.0.0.1',self.port)) as client:
                accepted,_=listener.accept()
                with accepted: yield

    def test_inspect_lists_the_accounts_characters(self):
        reply=self.request('inspect')
        self.assertEqual([{'name':'Witch','level':90,'league':'Standard'}],reply['characters'])

    def test_preview_is_read_only_and_finds_a_free_cell(self):
        before=self.state(); digest=hashlib.sha256(self.database.read_bytes()).hexdigest()
        reply=self.send()
        self.assertTrue(reply['ok'],reply); self.assertIsNone(reply['blocked']); self.assertEqual((0,1),(reply['x'],reply['y']))
        self.assertEqual(['/item Iron Ring'],reply['commands'])
        self.assertEqual(before,self.state()); self.assertEqual(digest,hashlib.sha256(self.database.read_bytes()).hexdigest())

    def test_send_adds_only_the_item_and_backs_up_the_row(self):
        before=self.saved(); preview=self.send()
        sent=self.send('item-send',previewKey=preview['previewKey'])
        self.assertTrue(sent['ok'],sent); after=self.saved()
        placed=after['Inventories']['0'][1]
        self.assertEqual(10,placed['Id']); self.assertEqual((0,1),(placed['X'],placed['Y'])); self.assertEqual(RING_HASH,placed['Item']['Type'])
        after['Inventories']['0'].pop(); self.assertEqual(before,after)
        self.assertEqual(before,json.loads(Path(sent['backup']).read_text(encoding='utf-8')))

    def test_item_ids_ignore_stash_ids_held_by_the_character(self):
        save={'Inventories':{'0':[{'Id':0x40000005,'X':0,'Y':0,'Item':{'Type':RING_HASH}}]}}
        self.character('Stashed',save=save); preview=self.send(name='Stashed')
        self.assertTrue(self.send('item-send',name='Stashed',previewKey=preview['previewKey'])['ok'])
        self.assertEqual(1,self.saved('Stashed')['Inventories']['0'][1]['Id'])

    def test_large_items_respect_their_shape_and_a_full_inventory_is_refused(self):
        rings=[{'Id':n+1,'X':n%12,'Y':n//12,'Item':{'Type':RING_HASH}} for n in range(59)]
        self.character('Full',save={'Inventories':{'0':rings}})
        self.assertEqual((11,4),(lambda r:(r['x'],r['y']))(self.send(name='Full')))
        self.assertIn('no free 2x3',self.send(name='Full',item='Rarity: NORMAL\nPlate Vest')['error'])

    def test_client_in_game_blocks_send_but_keeps_chat_commands(self):
        preview=self.send(); before=self.state()
        with self.gateway(connected=True):
            blocked=self.send()
            self.assertIn('Log out',blocked['blocked']); self.assertEqual(['/item Iron Ring'],blocked['commands'])
            refused=self.send('item-send',previewKey=preview['previewKey'])
        self.assertFalse(refused['ok']); self.assertIn('Log out',refused['error']); self.assertEqual(before,self.state())

    def test_character_played_since_gateway_start_needs_a_restart(self):
        now=datetime.now(timezone.utc).isoformat(); self.character('Recent',played=now)
        with self.gateway():
            reply=self.send(name='Recent'); self.assertIn('Restart the Gateway',reply['blocked']); self.assertIn('live.ps1 -Only Gateway',reply['blocked'])
            preview=self.send(name='Recent')
            self.assertFalse(self.send('item-send',name='Recent',previewKey=preview['previewKey'])['ok'])

    def test_character_not_played_since_gateway_start_can_be_sent_to(self):
        with self.gateway():
            preview=self.send(); self.assertIsNone(preview['blocked'],preview)
            self.assertTrue(self.send('item-send',previewKey=preview['previewKey'])['ok'])

    def test_changed_save_needs_a_new_preview(self):
        preview=self.send()
        with connect(self.database) as db: db.execute("UPDATE characters SET save=replace(save,'[11]','[12]') WHERE name='Witch'")
        before=self.state(); reply=self.send('item-send',previewKey=preview['previewKey'])
        self.assertFalse(reply['ok']); self.assertIn('Preview again',reply['error']); self.assertEqual(before,self.state())

    def test_unknown_character_ruthless_and_unsaved_characters_are_refused(self):
        self.character('Hard',league='Ruthless Standard'); self.character('Unplayed',save=False)
        self.assertIn('no character named',self.send(name='Missing')['error'])
        self.assertIn('Ruthless',self.send(name='Hard')['error'])
        self.assertIn('no save yet',self.send(name='Unplayed')['error'])

    def test_no_character_still_gives_the_chat_commands(self):
        reply=self.send(name='')
        self.assertTrue(reply['ok'],reply); self.assertIn('Choose a character',reply['blocked']); self.assertEqual(['/item Iron Ring'],reply['commands'])

    def test_unknown_item_type_in_the_inventory_stops_the_send(self):
        self.character('Odd',save={'Inventories':{'0':[{'Id':1,'X':0,'Y':0,'Item':{'Type':999}}]}})
        self.assertIn('does not know',self.send(name='Odd')['error'])

    def test_a_database_without_the_unique_catalogue_still_previews(self):
        self.table('Words',[{'Text':'Fixture','HASH32':5,'Wordlist':6}])
        self.table('UniqueStashLayout',[{'WordsKey':0,'ItemVisualIdentityKey':0}])
        reply=self.send(item='Rarity: UNIQUE\nFixture\nIron Ring')
        self.assertTrue(reply['ok'],reply); self.assertEqual(['/item Fixture'],reply['commands'])

    def test_unsupported_base_is_refused_without_writing(self):
        before=self.state()
        self.assertIn('cannot be sent',self.send(item='Rarity: NORMAL\nNo Such Base')['error']); self.assertEqual(before,self.state())


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--data-folder',type=Path); parser.add_argument('--build',type=Path)
    args,remaining=parser.parse_known_args(); DATA=args.data_folder; BUILD=args.build
    if not EXE.is_file(): raise SystemExit('Run .\\scripts\\build-exporter.ps1 first.')
    unittest.main(argv=[__file__]+remaining)
