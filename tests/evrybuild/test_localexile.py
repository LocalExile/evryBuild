"""Exercise evryBuild with its bundled Lua, JSON and curl libraries.

Run from the repository root on Windows:
  python tests/evrybuild/test_localexile.py -v
  python tests/evrybuild/test_localexile.py --runtime-dir ../evryBuild-app -v
"""
import argparse
import ctypes
import http.server
import json
import os
from pathlib import Path
import tempfile
import threading
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

    def test_visible_button_and_dialog_token_masking(self):
        self.lua.run(r'''
            M.Attach(tab)
            assert(tab.controls.localExileSend.kind == 'ButtonControl')
            assert(tab.controls.localExileSend.buf == 'Forge Character')
            assert(main.windowTitle == 'evryBuild - POB for LocalExile')
            tab.controls.localExileSend.onClick()
            assert(main.popup.title == 'evryBuild')
            assert(main.popup.controls.intro.buf == 'POB for LocalExile')
            assert(main.popup.controls.create.buf == 'Forge Character')
            assert(main.popup.controls.token.protected == true)
            assert(main.popup.controls.token.buf == '')
            assert(tab.controls.sectionBuild.height == 222)
        ''')

    def test_url_validation(self):
        self.lua.run(r'''
            for _, url in ipairs({'http://127.0.0.1:20496', 'http://localhost:20496/', 'http://[::1]:20496', 'https://my-server.example/pob'}) do
                assert(M.ValidateServer(url), url)
            end
            for _, url in ipairs({'http://example.com', 'http://localhost.evil.example', 'https://user:password@example.com', 'ftp://example.com', 'https://example.com?x=1', 'https://example.com#x', 'http://127.0.0.1:99999', 'https://example.com/'..string.char(13)..'Injected'}) do
                assert(not M.ValidateServer(url), url)
            end
        ''')

    def test_request_and_worker_refuse_non_localexile_routes_without_starting_network(self):
        self.lua.run(r'''
            local worker = assert(loadstring(M.RequestScript))
            for _, url in ipairs({
                'https://www.pathofexile.com/character-window/get-items',
                'https://pobb.in/example', 'http://127.0.0.1:20496/other',
                'http://127.0.0.1:20496/api/pob/preview?next=external',
                'https://example.com/%2e%2e/api/pob/preview',
                'http://example.com/api/pob/preview'
            }) do
                local failure
                M.Request(url, 'synthetic-token', {}, function(reply, err) assert(not reply); failure=err end)
                assert(failure and #workers == 0, url)
                local body, err, status = worker(url, 'synthetic-token', '{}')
                assert(not body and err and status == 0, url)
            end
            assert(M.ValidateRequestUrl('https://my-localexile.example/pob/api/pob/preview'))
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

    def test_only_localexile_has_an_http_transport(self):
        roots = [REPOSITORY / 'src/Classes', REPOSITORY / 'src/Modules']
        files = [p for root in roots for p in root.glob('*.lua')] + list((REPOSITORY / 'src').glob('*.lua'))
        transports = [p for p in files if 'lcurl.safe' in p.read_text(encoding='utf-8')]
        # HeadlessWrapper only has a compatibility require-name check, not a transport.
        self.assertEqual(sorted(p.name for p in transports), ['HeadlessWrapper.lua', 'LocalExile.lua'])

    def test_preferences_only_save_nonsecret_fields(self):
        self.lua.run(r'''
            local path = userPath .. 'LocalExile.json'
            assert(M.SavePreferences(path, {serverUrl='https://one.example', account='Alice', league='Standard', token='never-persist-this'}))
            assert(M.SavePreferences(path, {serverUrl='https://two.example', account='Bob', league='evryLeague', token='second-secret'}))
            local preferences = M.ReadPreferences(path)
            assert(preferences.serverUrl == 'https://two.example')
            assert(preferences.account == 'Bob' and preferences.league == 'evryLeague')
            local f = assert(io.open(path, 'rb')); local saved = f:read('*a'); f:close()
            assert(not saved:find('secret',1,true) and not saved:find('token',1,true))
        ''')

    def test_preview_exports_active_build_and_does_not_send_create(self):
        self.lua.run(r'''
            M.Open(tab)
            local c = main.popup.controls
            c.account:SetText('Alice'); c.token:SetText('synthetic-token')
            c.preview.onClick()
            assert(#workers == 1)
            local worker = workers[1]
            assert(worker.args[1] == 'http://127.0.0.1:20496/api/pob/preview')
            assert(worker.args[2] == 'synthetic-token')
            local body = require('dkjson').decode(worker.args[3])
            assert(body.account == 'Alice' and body.code == 'compressed-code' and body.league == 'Standard')
            assert(c.create.enabled() == false)
            launch.subScripts[1].callback('{"ok":true,"preview":true,"class":"Witch","level":20,"warnings":["Example warning"]}', nil, 200)
            assert(c.results.buf:find('Ready to import',1,true))
            assert(c.results.buf:find('Example warning',1,true))
            assert(c.token.buf == 'synthetic-token')
        ''')

    def test_create_validates_name_and_clears_token_after_success(self):
        self.lua.run(r'''
            M.Open(tab); local c = main.popup.controls
            c.account:SetText('Alice'); c.token:SetText('synthetic-token')
            c.name:SetText('x'); c.create.onClick(); assert(#workers == 0)
            c.name:SetText('ImportedWitch'); c.create.onClick(); assert(#workers == 0)
            c.preview.onClick()
            launch.subScripts[1].callback('{"ok":true,"preview":true}', nil, 200)
            assert(c.create.enabled())
            c.create.onClick()
            assert(workers[2].args[1]:match('/api/pob/characters$'))
            launch.subScripts[2].callback('{"ok":true,"preview":false,"character":"ImportedWitch"}', nil, 200)
            assert(c.results.buf:find('Character created: ImportedWitch',1,true))
            assert(c.token.buf == '')
        ''')

    def test_partial_results_show_equipment_omissions_and_shortened_warnings(self):
        self.lua.run(r'''
            local description = M.Describe({preview=true, partial=true, items=2, gems=2,
                activeItems=1, activeGems=1, inactiveWeaponItems=1, inactiveWeaponGems=1,
                skippedItems=3, skippedGems=4, warnings={'Skipped unsupported modifier'},
                warningsTruncated=true, warningCount=80})
            assert(description:find('Ready with omissions',1,true))
            assert(description:find('Active equipment: 1 items, 1 gems',1,true))
            assert(description:find('Inactive weapon set: 1 items, 1 gems',1,true))
            assert(description:find('Omitted: 3 items, 4 enabled gems',1,true))
            assert(description:find('shortened (80 distinct warnings)',1,true))
        ''')

    def test_changing_the_build_or_destination_requires_another_preview(self):
        self.lua.run(r'''
            M.Open(tab); local c = main.popup.controls
            c.account:SetText('Alice'); c.token:SetText('synthetic-token'); c.name:SetText('FirstName')
            c.preview.onClick()
            launch.subScripts[1].callback('{"ok":true,"preview":true}', nil, 200)
            c.name:SetText('SecondName'); c.create.onClick()
            assert(#workers == 1 and not c.create.enabled())
            assert(c.results.buf:find('Preview this build',1,true))
            c.preview.onClick()
            launch.subScripts[2].callback('{"ok":true,"preview":true}', nil, 200)
            common.base64.encode = function() return 'changed-code' end
            c.create.onClick()
            assert(#workers == 2 and not c.create.enabled())
        ''')

    def test_server_errors_and_worker_failures_are_visible(self):
        self.lua.run(r'''
            local errors = {}
            M.Request('http://localhost/api/pob/preview', 'x', {}, function(result, error) errors[#errors+1] = error end)
            launch.subScripts[1].callback('{"ok":false,"error":"Unsupported ascendancy"}', nil, 422)
            assert(errors[1] == 'Unsupported ascendancy')
            M.Request('http://localhost/api/pob/preview', 'x', {}, function(result, error) errors[#errors+1] = error end)
            launch.subScripts[2].callback(nil, 'Worker failed')
            assert(errors[2] == 'Worker failed')
            M.Request('http://localhost/api/pob/preview', 'x', {}, function(result, error) errors[#errors+1] = error end)
            launch.subScripts[3].callback('<html>Wrong server</html>', nil, 200)
            assert(errors[3]:find('did not return LocalExile JSON',1,true))
        ''')

    def test_close_discards_token(self):
        self.lua.run(r'''
            M.Open(tab); local c = main.popup.controls
            c.token:SetText('synthetic-token'); c.close.onClick()
            assert(c.token.buf == '' and main.popup == nil)
        ''')

    def test_worker_uses_actual_pob_curl_and_refuses_redirects(self):
        requests = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append((self.path, self.headers.get("Authorization")))
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if self.path == "/api/pob/characters":
                    self.send_response(302)
                    self.send_header("Location", "/leak-token")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true,"preview":true}')

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            self.lua.run("testUrl = " + json.dumps(url))
            self.lua.run(r'''
                local worker = assert(loadstring(M.RequestScript))
                local body, error, status = worker(testUrl .. '/api/pob/preview', 'synthetic-token', '{}')
                assert(not error, tostring(error)); assert(status == 200 and body:find('true',1,true))
                local body, error, status = worker(testUrl .. '/api/pob/characters', 'synthetic-token', '{}')
                assert(body == nil and status == 302 and error:find('redirected',1,true))
            ''')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertEqual(requests, [("/api/pob/preview", "Bearer synthetic-token"), ("/api/pob/characters", "Bearer synthetic-token")])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path, default=REPOSITORY / "runtime",
                        help="Complete Windows PoB runtime folder (default: this checkout's runtime)")
    args, remaining = parser.parse_known_args()
    INSTALLATION = args.runtime_dir
    unittest.main(argv=[__file__] + remaining)
