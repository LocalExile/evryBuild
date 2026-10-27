"""Exercise ExileForge with its bundled Lua, JSON and curl libraries.

Run from the repository root on Windows:
  python tests/exileforge/test_localexile.py -v
  python tests/exileforge/test_localexile.py --runtime-dir F:/evry/evryPath/ExileForge -v
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
        self.temporary = tempfile.TemporaryDirectory(prefix="exileforge-test-")
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
            function new(kind, anchor, rect, value, callback)
                local c = {kind=kind, anchor=anchor, rect=rect, buf=tostring(value or ''), enabled=true}
                if kind == 'ButtonControl' then c.onClick = callback end
                function c:SetText(value) self.buf = tostring(value) end
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
            assert(main.windowTitle == 'ExileForge — Path of Building for LocalExile')
            tab.controls.localExileSend.onClick()
            assert(main.popup.title == 'ExileForge')
            assert(main.popup.controls.intro.buf == 'Path of Building for LocalExile')
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
            assert(c.results.buf:find('Preview passed',1,true))
            assert(c.results.buf:find('Example warning',1,true))
            assert(c.token.buf == 'synthetic-token')
        ''')

    def test_create_validates_name_and_clears_token_after_success(self):
        self.lua.run(r'''
            M.Open(tab); local c = main.popup.controls
            c.account:SetText('Alice'); c.token:SetText('synthetic-token')
            c.name:SetText('x'); c.create.onClick(); assert(#workers == 0)
            c.name:SetText('ImportedWitch'); c.create.onClick()
            assert(workers[1].args[1]:match('/api/pob/characters$'))
            launch.subScripts[1].callback('{"ok":true,"preview":false,"character":"ImportedWitch"}', nil, 200)
            assert(c.results.buf:find('Character created: ImportedWitch',1,true))
            assert(c.token.buf == '')
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
                if self.path == "/redirect":
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
                local body, error, status = worker(testUrl .. '/preview', 'synthetic-token', '{}')
                assert(not error, tostring(error)); assert(status == 200 and body:find('true',1,true))
                local body, error, status = worker(testUrl .. '/redirect', 'synthetic-token', '{}')
                assert(body == nil and status == 302 and error:find('redirected',1,true))
            ''')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertEqual(requests, [("/preview", "Bearer synthetic-token"), ("/redirect", "Bearer synthetic-token")])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", type=Path, default=REPOSITORY / "runtime",
                        help="Complete Windows PoB runtime folder (default: this checkout's runtime)")
    args, remaining = parser.parse_known_args()
    INSTALLATION = args.runtime_dir
    unittest.main(argv=[__file__] + remaining)
