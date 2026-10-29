"""Run the actual self-contained offline exporter against temporary SQLite databases."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
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


class ExportTests(unittest.TestCase):
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


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--data-folder',type=Path); parser.add_argument('--build',type=Path)
    args,remaining=parser.parse_known_args(); DATA=args.data_folder; BUILD=args.build
    if not EXE.is_file(): raise SystemExit('Run .\\scripts\\build-exporter.ps1 first.')
    unittest.main(argv=[__file__]+remaining)
