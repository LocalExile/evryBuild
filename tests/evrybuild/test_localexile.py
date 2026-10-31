"""Exercise the external exporter UI with the bundled LuaJIT runtime and local pipe bridge.

Run from the repository root on Windows:
  python tests/evrybuild/test_localexile.py -v
  python tests/evrybuild/test_localexile.py --runtime-dir ../evryBuild-app -v
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import tempfile
import unittest


class Lua:
    def __init__(self, installation):
        self.installation = Path(installation).resolve()
        self.directory = os.add_dll_directory(str(self.installation))
        self.lib = ctypes.CDLL(str(self.installation / "lua51.dll"))
        self.lib.luaL_newstate.restype = ctypes.c_void_p
        self.lib.luaL_openlibs.argtypes = [ctypes.c_void_p]
        self.lib.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lib.luaL_loadstring.restype = ctypes.c_int
        self.lib.lua_pcall.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.lib.lua_pcall.restype = ctypes.c_int
        self.lib.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
        self.lib.lua_tolstring.restype = ctypes.c_void_p
        self.lib.lua_settop.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.lua_close.argtypes = [ctypes.c_void_p]
        self.state = self.lib.luaL_newstate()
        self.lib.luaL_openlibs(self.state)
        self.run("install = " + json.dumps(self.installation.as_posix()))
        self.run("package.path = install .. '/lua/?.lua;' .. install .. '/lua/?/init.lua;' .. package.path; package.cpath = install .. '/?.dll;' .. package.cpath")

    def run(self, source):
        status = self.lib.luaL_loadstring(self.state, source.encode())
        if not status:
            status = self.lib.lua_pcall(self.state, 0, 0, 0)
        if status:
            size = ctypes.c_size_t()
            pointer = self.lib.lua_tolstring(self.state, -1, ctypes.byref(size))
            message = ctypes.string_at(pointer, size.value).decode("utf-8", "replace")
            self.lib.lua_settop(self.state, 0)
            raise AssertionError(message)

    def close(self):
        self.lib.lua_close(self.state)
        self.directory.close()


REPOSITORY = Path(__file__).resolve().parents[2]
INSTALLATION = REPOSITORY / "runtime"


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("These integration checks use the Windows PoB runtime DLLs.")
        runtime = Path(INSTALLATION).resolve()
        if not (runtime / "lua51.dll").is_file():
            raise FileNotFoundError(f"lua51.dll is missing from {runtime}; use --runtime-dir to select a complete runtime.")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="evrybuild-test-")
        self.addCleanup(self.temporary.cleanup)
        self.lua = Lua(INSTALLATION)
        self.addCleanup(self.lua.close)
        self.lua.run("sourceRoot = " + json.dumps((REPOSITORY / "src").as_posix()))
        self.lua.run("modulePath = " + json.dumps((REPOSITORY / "src/Modules/LocalExile.lua").as_posix()))
        self.lua.run("userPath = " + json.dumps(Path(self.temporary.name).as_posix() + "/"))
        self.lua.run(r'''
            main = { userPath = userPath }
            APP_NAME = 'Path of Building'
            function main:SetWindowTitleSubtext() self.windowTitle = APP_NAME end
            function main:OpenPopup(width, height, title, controls)
                self.popup = {width=width, height=height, title=title, controls=controls}
                return self.popup
            end
            function main:ClosePopup() self.popup = nil end
            function new(kind, anchor, rect, value, callback, ...)
                local c = {kind=kind, anchor=anchor, rect=rect, buf=tostring(value or ''), enabled=true}
                if kind == 'ButtonControl' then c.onClick = callback end
                if kind == 'DropDownControl' then c.list=value; c.selIndex=1 end
                if kind == 'EditControl' then c.onChange=select(3, ...) end
                function c:SetText(value, trigger)
                    self.buf = tostring(value)
                    if self.onChange and trigger ~= false then self.onChange(self.buf) end
                end
                function c:SetProtected(value) self.protected = value end
                return c
            end
            common = { base64 = {encode=function(value) return 'compressed-code' end} }
            function Deflate(value) return value end
            function Copy(value) copied = value end
            function GetRuntimePath() return install end
            function GetScriptPath() return sourceRoot end
            launch = {subScripts={}}
            workers = {}
            function LaunchSubScript(script, functions, callbacks, ...)
                local id = #workers + 1
                workers[id] = {script=script, args={...}}
                return id
            end
            build = { SaveDB=function(self, mode) assert(mode == 'code'); return '<PathOfBuilding />' end }
            tab = {build=build, controls={sectionBuild={height=182}, importCodeMode={}}}
            M = assert(loadfile(modulePath))()
        ''')

    def test_generic_downloads_updates_and_browser_links_never_start_workers(self):
        self.lua.run('launchFile = ' + json.dumps((REPOSITORY / 'src/Launch.lua').as_posix()))
        self.lua.run(r'''
            function GetTime() return 1 end
            function SetWindowTitle() end
            function ConExecute() end
            function SetMainObject() end
            browserCalls=0
            function OpenURL() browserCalls=browserCalls+1 end
            assert(loadfile(launchFile))()
            local count=0
            for _, url in ipairs({'https://www.pathofexile.com', 'https://pobb.in', 'http://localhost/unused'}) do
                launch:DownloadPage(url,function(reply,err) assert(reply==nil and err); count=count+1 end)
                assert(OpenURL(url)==false)
            end
            launch.evryBuildEdition=false -- This policy must not depend on an optional edition flag.
            launch:CheckForUpdate(); launch:ApplyUpdate('normal')
            assert(count==3 and browserCalls==0 and #workers==0)
        ''')

    def test_legacy_account_and_build_site_apis_are_offline(self):
        self.lua.run('apiFile = ' + json.dumps((REPOSITORY / 'src/Classes/PoEAPI.lua').as_posix()))
        self.lua.run('sitesFile = ' + json.dumps((REPOSITORY / 'src/Modules/BuildSiteTools.lua').as_posix()))
        self.lua.run(r'''
            local methods, construct
            function newClass(name, constructor) methods={}; construct=constructor; return methods end
            assert(loadfile(apiFile))()
            local account=setmetatable({}, {__index=methods}); construct(account,'old-secret','refresh',0)
            assert(account.authToken==nil and account.refreshToken==nil)
            local calls=0
            account:ValidateAuth(function(valid,err) assert(not valid and err); calls=calls+1 end)
            account:FetchAuthToken(function(err) assert(err); calls=calls+1 end)
            account:DownloadCharacterList('pc',function(value,err) assert(not value and err); calls=calls+1 end)
            assert(loadfile(sitesFile))()
            assert(#buildSites.websiteList==0 and buildSites.UploadBuild('private-build')==nil)
            buildSites.DownloadBuild('https://pobb.in/build',nil,function(valid,err) assert(not valid and err); calls=calls+1 end)
            assert(calls==4 and #workers==0)
        ''')

    def test_import_tab_keeps_offline_codes_and_removes_account_and_web_controls(self):
        self.lua.run('importFile = ' + json.dumps((REPOSITORY / 'src/Classes/ImportTab.lua').as_posix()))
        self.lua.run(r'''
            itemLib={influenceInfo={all={}}}; colorCodes={NEGATIVE='',POSITIVE=''}
            local constructor
            function newClass(name,...) constructor=select(select('#',...),...); return {} end
            function LoadModule(name, tab) assert(name=='Modules/LocalExile'); M.Attach(tab) end
            build.partyTab={}; build.dbFileName=false
            function build:Shutdown() self.closed=true end
            function build:Init(file,name,xml) self.loadedXML=xml end
            local target={controls={},build=build,ControlHost=function() end,Control=function() end}
            assert(loadfile(importFile))(); constructor(target,build)
            local c=target.controls
            assert(c.localExileSend and c.generateCode and c.generateCodeCopy and c.importCodeIn)
            assert(not c.authenticateButton and not c.sectionOauthCharImport and not c.sectionCharSiteImport)
            assert(not c.exportFrom and not c.generateCodeByLink)
            for _,url in ipairs({'https://pobb.in/example','https://www.pathofexile.com/account','pob://pobbin/id'}) do
                c.importCodeIn:SetText(url); assert(not target.importCodeValid)
            end
            common.base64.decode=function() return 'compressed' end
            Inflate=function() return '<PathOfBuilding />' end
            c.importCodeIn:SetText('offline-code'); assert(target.importCodeValid)
            c.importCodeGo.onClick()
            assert(build.closed and build.loadedXML=='<PathOfBuilding />' and build.viewMode=='TREE')
            assert(#workers==0)
        ''')

    def test_all_application_lua_modules_compile(self):
        files = list((REPOSITORY / 'src/Classes').glob('*.lua')) + list((REPOSITORY / 'src/Modules').glob('*.lua'))
        files += list((REPOSITORY / 'src').glob('*.lua'))
        for file in files:
            self.lua.run('assert(loadfile(' + json.dumps(file.as_posix()) + '))')

    def test_external_dialog_has_database_fields_and_no_api_credentials(self):
        self.lua.run('''
            M.Attach(tab); assert(tab.controls.localExileSend.buf == 'Export to LocalExile')
            M.Open(tab); local c=main.popup.controls
            assert(c.database and c.dataFolder and c.databaseBrowse and c.dataBrowse)
            assert(not c.serverUrl and not c.token and not c.create.enabled())
        ''')

    def test_preview_and_changed_destination_guard_export(self):
        self.lua.run('''
            M.Open(tab); local c=main.popup.controls
            c.database:SetText('C:/server/data/saves.db'); c.account:SetText('Alice'); c.name:SetText('NewName')
            c.preview.onClick()
            local payload=require('dkjson').decode(workers[1].args[3])
            assert(payload.operation=='preview' and payload.code and not payload.token and not payload.serverUrl)
            launch.subScripts[1].callback('{"ok":true,"preview":true,"previewKey":"checked"}')
            assert(c.create.enabled())
            c.name:SetText('ChangedName'); c.create.onClick()
            assert(#workers==1 and not c.create.enabled())
        ''')

    def test_database_inspection_requires_an_explicit_choice_between_accounts(self):
        self.lua.run('''
            M.Open(tab); local c=main.popup.controls
            c.account:SetText('UnrelatedPreviousAccount'); c.inspect.onClick()
            launch.subScripts[1].callback('{"ok":true,"accounts":["Alice","Bob"],"leagues":["Standard"]}')
            assert(c.account.buf=='')
            c.account:SetText('bOB'); c.inspect.onClick()
            launch.subScripts[2].callback('{"ok":true,"accounts":["Alice","Bob"],"leagues":["Standard"]}')
            assert(c.account.buf=='Bob')
            c.account:SetText(''); c.inspect.onClick()
            launch.subScripts[3].callback('{"ok":true,"accounts":["Alice"],"leagues":["Standard"]}')
            assert(c.account.buf=='Alice')
        ''')

    def test_preview_key_is_sent_only_for_confirmed_export(self):
        self.lua.run('''
            M.Open(tab); local c=main.popup.controls
            c.database:SetText('C:/server/data/saves.db'); c.account:SetText('Alice'); c.name:SetText('NewName')
            c.preview.onClick()
            launch.subScripts[1].callback('{"ok":true,"preview":true,"previewKey":"checked"}')
            c.create.onClick()
            local payload=require('dkjson').decode(workers[2].args[3])
            assert(payload.operation=='export' and payload.previewKey=='checked')
            launch.subScripts[2].callback('{"ok":true,"character":"NewName","backup":"backup.db"}')
            assert(not c.create.enabled() and c.results.buf:find('Character created: NewName',1,true))
        ''')

    def open_item_dialog(self):
        self.lua.run('''
            itemTab = {displayItem = {BuildRaw=function() return 'Rarity: NORMAL\\nIron Ring' end}}
            M.SavePreferences(userPath..'LocalExile.json', {database='C:/server/data/saves.db',dataFolder='C:/server/data',account='Alice',league='Standard'})
            M.OpenItem(itemTab); c=main.popup.controls
            json=require('dkjson')
            local inspect=json.decode(workers[1].args[3])
            assert(inspect.operation=='inspect' and inspect.account=='Alice')
        ''')

    def test_item_dialog_checks_at_once_and_fills_the_only_character(self):
        self.open_item_dialog()
        self.lua.run('''
            launch.subScripts[1].callback('{"ok":true,"accounts":["Alice"],"characters":[{"name":"Witch","level":90,"league":"Standard"}]}')
            assert(c.name.buf=='Witch')
            local payload=json.decode(workers[2].args[3])
            assert(payload.operation=='item-preview' and payload.name=='Witch' and payload.item:find('Iron Ring',1,true))
            launch.subScripts[2].callback('{"ok":true,"preview":true,"previewKey":"checked","character":"Witch","item":"Iron Ring","x":0,"y":0,"next":"Ready.","commands":["/item Iron Ring"]}')
            assert(c.send.enabled() and c.results.buf:find('column 1, row 1',1,true))
            c.send.onClick()
            payload=json.decode(workers[3].args[3])
            assert(payload.operation=='item-send' and payload.previewKey=='checked')
            launch.subScripts[3].callback('{"ok":true,"preview":false,"character":"Witch","item":"Iron Ring","backup":"old.save.json","next":"Log in."}')
            assert(not c.send.enabled() and c.results.buf:find('Sent: Iron Ring to Witch',1,true) and itemTab.localExileCharacter=='Witch')
        ''')

    def test_blocked_item_shows_what_to_do_and_keeps_commands_usable(self):
        self.open_item_dialog()
        self.lua.run('''
            launch.subScripts[1].callback('{"ok":true,"accounts":["Alice"],"characters":[{"name":"Witch","level":90,"league":"Standard"}]}')
            launch.subScripts[2].callback('{"ok":true,"preview":true,"previewKey":"key","blocked":"You are in game.","next":"You are in game.","item":"Iron Ring","commands":["/item Iron Ring","/item_mod clear"]}')
            assert(not c.send.enabled() and c.copy.enabled() and c.results.buf:find('You are in game.',1,true))
            assert(c.copy.label()=='Copy Command 1/2'); c.copy.onClick(); assert(copied=='/item Iron Ring')
            c.copy.onClick(); assert(copied=='/item_mod clear'); assert(c.copy.label()=='Copy Command 1/2')
        ''')

    def test_changed_destination_needs_another_check_before_sending(self):
        self.open_item_dialog()
        self.lua.run('''
            launch.subScripts[1].callback('{"ok":true,"accounts":["Alice"],"characters":[{"name":"Witch","level":90,"league":"Standard"}]}')
            launch.subScripts[2].callback('{"ok":true,"preview":true,"previewKey":"key","item":"Iron Ring","commands":[]}')
            c.name:SetText('SomeoneElse'); c.send.onClick()
            assert(#workers==2 and not c.send.enabled() and c.results.buf:find('Check Again',1,true))
        ''')

    def test_item_dialog_needs_a_displayed_item(self):
        self.lua.run('main.popup=nil; assert(M.OpenItem({})==nil and main.popup==nil and #workers==0)')

    def test_items_tab_offers_send_to_localexile(self):
        source = (REPOSITORY / 'src/Classes/ItemsTab.lua').read_text(encoding='utf-8-sig')
        self.assertIn('LoadModule("Modules/LocalExile").OpenItem(self)', source)

    def test_legacy_tokens_and_server_urls_are_not_persisted(self):
        self.lua.run('''
            assert(M.SavePreferences(userPath..'LocalExile.json', {database='C:/saves.db',dataFolder='C:/data',account='Alice',league='Standard',token='secret',serverUrl='https://old'}))
            local f=assert(io.open(userPath..'LocalExile.json')); local text=f:read('*a'); f:close()
            assert(not text:find('secret',1,true) and not text:find('https://old',1,true))
            assert(M.ReadPreferences(userPath..'LocalExile.json').database=='C:/saves.db')
        ''')

    def test_compatibility_warnings_keep_valid_entries(self):
        self.lua.run('''
            local text=M.Describe({preview=true,compatibility={{source='gem',effect='Frostblink',status='partial',reason='Movement only',action='kept'}},compatibilityCount=1})
            assert(text:find('[partial]',1,true) and text:find('valid entries are kept',1,true))
        ''')

    def test_local_worker_errors_are_visible(self):
        self.lua.run('''
            local err
            M.Request({operation='inspect',database='x'},function(reply,message) err=message end)
            launch.subScripts[1].callback('{"ok":false,"error":"Database busy"}')
            assert(err=='Database busy')
        ''')

    def test_no_application_http_transport_remains(self):
        for folder in (REPOSITORY / 'src/Modules', REPOSITORY / 'src/Classes'):
            for path in folder.rglob('*.lua'):
                self.assertNotIn('require("lcurl.safe")', path.read_text(encoding='utf-8-sig'), str(path))

    def test_native_bridge_starts_bundled_exporter_without_a_shell(self):
        self.lua.run('native = assert(loadfile(sourceRoot.."/Modules/LocalExileNative.lua"))()')
        executable = REPOSITORY / 'runtime/LocalExile/evryBuild.Export.exe'
        self.assertTrue(executable.is_file(), 'Build the local exporter before running these checks.')
        self.lua.run('exe='+json.dumps(executable.as_posix()))
        self.lua.run('''
            local response,err=native.Run(exe, '{"operation":"inspect","database":"C:/does-not-exist.db"}',30000)
            assert(response,tostring(err)); local reply=require('dkjson').decode(response)
            assert(reply and reply.ok==false and reply.error:find('does not exist',1,true))
        ''')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime-dir',type=Path,default=REPOSITORY/'runtime')
    args,remaining=parser.parse_known_args(); INSTALLATION=args.runtime_dir
    unittest.main(argv=[__file__]+remaining)
