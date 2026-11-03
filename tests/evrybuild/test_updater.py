"""Exercise evryBuild's updater (UpdateCheck.lua, UpdateApply.lua) with the bundled LuaJIT runtime and libcurl.

A local HTTP server stands in for GitHub, including the redirect from releases/latest to the release's own files.
Run from the repository root on Windows:
  python tests/evrybuild/test_updater.py -v
"""
import hashlib
import http.server
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET

REPOSITORY = Path(__file__).resolve().parents[2]
SOURCE = REPOSITORY / "src"
spec = importlib.util.spec_from_file_location("evrybuild_lua_harness", Path(__file__).with_name("test_localexile.py"))
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)

TAG = "v1.1.0"
COMMIT = "c0ffee"


class Server:
    """Serves bytes by path; latest/download redirects to the tagged release, as GitHub does."""
    def __init__(self):
        self.files, self.requests = {}, []
        files, requests = self.files, self.requests

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if self.path.startswith("/releases/latest/download/"):
                    self.send_response(302)
                    self.send_header("Location", "/releases/download/" + TAG + "/" + self.path.rsplit("/", 1)[1])
                    self.end_headers()
                    return
                body = files.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}/"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def sha(data):
    return hashlib.sha256(data).hexdigest()


class UpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("These checks use the Windows PoB runtime DLLs.")
        cls.server = Server()
        # lcurl.dll finds libcurl.dll through the ordinary DLL search, which includes PATH but not the current folder
        # (the tests run inside a temporary application folder).
        os.environ["PATH"] = str(REPOSITORY / "runtime") + os.pathsep + os.environ.get("PATH", "")
        cls.lua = harness.Lua(REPOSITORY / "runtime")

    @classmethod
    def tearDownClass(cls):
        cls.lua.close()
        cls.server.close()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="evrybuild-updater-")
        self.app = Path(self.temporary.name) / "evryBuild"
        self.app.mkdir()
        self.previous = os.getcwd()
        os.chdir(self.app)
        self.server.files.clear()
        self.server.requests.clear()
        self.installed = {"Launch.lua": b"old launch", "Modules/Main.lua": b"old main", "Data/Old.lua": b"retired",
                          "zstd.dll": b"old native", "Unchanged.lua": b"same"}
        for name, data in self.installed.items():
            self.write(name, data)
        self.write("Builds/Mine.xml", b"personal build")
        self.write("Settings.xml", b"personal settings")
        self.write_manifest(self.app / "manifest.xml", "1.0.0", self.installed)

    def tearDown(self):
        os.chdir(self.previous)
        self.temporary.cleanup()

    def write(self, name, data):
        path = self.app / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def manifest(self, release, files, *, update=None, sources=None, notes="## Release\n\n- A change."):
        root = ET.Element("PoBVersion")
        ET.SubElement(root, "Version", number="2.67.2", branch="evrybuild", platform="win32", release=release)
        ET.SubElement(root, "Update", url=update or self.server.base + "releases/latest/download/evryBuild-update.xml")
        sources = sources or {"repo": self.server.base + f"raw/{COMMIT}/", "asset": self.server.base + f"releases/download/{TAG}/"}
        for part, url in sources.items():
            ET.SubElement(root, "Source", part=part, url=url)
        ET.SubElement(root, "Notes").text = notes
        for name, data in files.items():
            part, source = ("asset", name.rsplit("/", 1)[-1]) if name.endswith(".exe") and "/" in name else ("repo", "src/" + name)
            entry = ET.SubElement(root, "File", name=name, part=part, source=source, sha256=sha(data), size=str(len(data)))
            if "/" not in name and name.endswith((".dll", ".exe")):
                entry.set("native", "true")
        return ET.tostring(root, xml_declaration=True, encoding="utf-8")

    def write_manifest(self, path, release, files, **options):
        path.write_bytes(self.manifest(release, files, **options))

    def publish(self, release, files, *, served=None, **options):
        """Serves a release: its manifest behind the latest redirect, and each file at its source."""
        self.server.files[f"/releases/download/{TAG}/evryBuild-update.xml"] = self.manifest(release, files, **options)
        for name, data in (files if served is None else served).items():
            if name.endswith(".exe") and "/" in name:
                self.server.files[f"/releases/download/{TAG}/" + name.rsplit("/", 1)[-1]] = data
            else:
                self.server.files[f"/raw/{COMMIT}/src/" + name.replace(" ", "%20")] = data

    def run_lua(self, script, *args):
        """Runs an updater script as the application would and returns what it returned."""
        out = Path(self.temporary.name) / "result.json"
        out.unlink(missing_ok=True)
        self.lua.run(f"""
            local app = {json.dumps(self.app.as_posix())}
            progress = {{ }}
            function GetScriptPath() return app end
            function GetRuntimePath() return app end
            function MakeDir(path) os.execute('mkdir "' .. path:gsub('/', '\\\\') .. '" 2>nul') end
            function ConPrintf(...) end
            function UpdateProgress(fmt, ...) progress[#progress + 1] = string.format(fmt, ...) end
            local chunk = assert(loadfile({json.dumps((SOURCE / script).as_posix())}))
            local result = {{ chunk({", ".join(json.dumps(a) for a in args)}) }}
            local n = 0
            for k in pairs(result) do if k > n then n = k end end
            for i = 1, n do if result[i] == nil then result[i] = json_null end end
            local file = assert(io.open({json.dumps(out.as_posix())}, 'w'))
            file:write(require('dkjson').encode({{ result = result, n = n, progress = progress }}))
            file:close()
        """.replace("json_null", "require('dkjson').null"))
        data = json.loads(out.read_text(encoding="utf-8"))
        return [data["result"][i] if i < len(data["result"]) else None for i in range(data["n"])]

    def update_to(self, files, **options):
        self.publish("1.1.0", files, **options)
        check = self.run_lua("UpdateCheck.lua", "check")
        self.assertEqual("available", check[0], check)
        return check, self.run_lua("UpdateCheck.lua", "download")

    def test_offers_a_newer_release_through_the_latest_redirect(self):
        new = dict(self.installed, **{"Launch.lua": b"new launch", "Modules/New Thing.lua": b"added"})
        del new["Data/Old.lua"]
        self.publish("1.1.0", new)
        result = self.run_lua("UpdateCheck.lua", "check")
        self.assertEqual(["available", "1.1.0", 2, len(b"new launch") + len(b"added")], result)
        self.assertEqual("/releases/latest/download/evryBuild-update.xml", self.server.requests[0])
        self.assertIn(f"/releases/download/{TAG}/evryBuild-update.xml", self.server.requests)
        self.assertTrue((self.app / "Update/pending.xml").is_file())

    def test_same_or_older_release_is_not_offered(self):
        for release in ("1.0.0", "0.9.0"):
            self.publish(release, dict(self.installed, **{"Launch.lua": b"other"}))
            self.assertEqual(["none", "1.0.0"], self.run_lua("UpdateCheck.lua", "check"))
        self.assertFalse((self.app / "Update/pending.xml").exists())

    def test_releases_compare_by_semantic_version(self):
        cases = [("1.0.0", "1.0.1", True), ("1.9.0", "1.10.0", True), ("1.10.0", "1.9.0", False), ("2.0.0", "10.0.0", True),
                 ("1.1.0-rc.1", "1.1.0", True), ("1.1.0", "1.1.0-rc.2", False), ("1.1.0-rc.1", "1.1.0-rc.2", True),
                 ("1.1.0-rc.2", "1.1.0-rc.10", True), ("1.1.0-beta", "1.1.0-rc.1", True), ("1.1.0-alpha.1", "1.1.0-alpha", False),
                 ("1.1.0-1", "1.1.0-alpha", True), ("1.0.0", "1.0.0", False), ("not a version", "1.0.0", True)]
        changed = dict(self.installed, **{"Launch.lua": b"new launch"})
        for installed, remote, offered in cases:
            self.write_manifest(self.app / "manifest.xml", installed, self.installed)
            self.publish(remote, changed)
            result = self.run_lua("UpdateCheck.lua", "check")
            self.assertEqual("available" if offered else "none", result[0], (installed, remote, result))
        for invalid in ("1.1", "v1.1.0", "1.1.0-", "1.1.0-rc..1", "2026.11.10.2"):
            self.publish(invalid, changed)
            result = self.run_lua("UpdateCheck.lua", "check")
            self.assertIsNone(result[0], invalid)
            self.assertIn("invalid", result[1], invalid)

    def test_installs_changed_files_removes_retired_ones_and_keeps_personal_data(self):
        new = dict(self.installed, **{"Launch.lua": b"new launch", "Modules/New Thing.lua": b"added",
                                      "LocalExile/evryBuild.Export.exe": b"exporter bytes"})
        del new["Data/Old.lua"]
        check, download = self.update_to(new)
        self.assertEqual(["ready", "normal"], download)
        before = set(self.server.requests)
        self.assertEqual([True], self.run_lua("UpdateApply.lua", "Update/opFile.txt"))
        self.assertEqual(before, set(self.server.requests))
        self.assertEqual(b"new launch", (self.app / "Launch.lua").read_bytes())
        self.assertEqual(b"added", (self.app / "Modules/New Thing.lua").read_bytes())
        self.assertEqual(b"exporter bytes", (self.app / "LocalExile/evryBuild.Export.exe").read_bytes())
        self.assertFalse((self.app / "Data/Old.lua").exists())
        self.assertEqual(b"same", (self.app / "Unchanged.lua").read_bytes())
        self.assertEqual(b"personal build", (self.app / "Builds/Mine.xml").read_bytes())
        self.assertEqual(b"personal settings", (self.app / "Settings.xml").read_bytes())
        installed = ET.parse(self.app / "manifest.xml").getroot()
        self.assertEqual("1.1.0", installed.find("Version").get("release"))
        self.assertFalse(list(self.app.rglob("*.old")), "unlocked .old files are removed at once")
        self.assertFalse((self.app / "Update/opFile.txt").exists())
        self.assertIn(f"/releases/download/{TAG}/evryBuild.Export.exe", self.server.requests)
        self.assertNotIn(f"/raw/{COMMIT}/src/Unchanged.lua", self.server.requests)
        self.assertEqual(["none", "1.1.0"], self.run_lua("UpdateCheck.lua", "check"))

    def test_a_changed_dll_needs_a_new_process(self):
        _, download = self.update_to(dict(self.installed, **{"zstd.dll": b"new native"}))
        self.assertEqual(["ready", "native"], download)

    def test_a_corrupt_download_changes_nothing(self):
        new = dict(self.installed, **{"Launch.lua": b"new launch", "Modules/Main.lua": b"new main"})
        self.publish("1.1.0", new, served=dict(new, **{"Modules/Main.lua": b"tampered"}))
        self.assertEqual("available", self.run_lua("UpdateCheck.lua", "check")[0])
        result = self.run_lua("UpdateCheck.lua", "download")
        self.assertIsNone(result[0])
        self.assertIn("does not match the release", result[1])
        self.assertFalse((self.app / "Update/opFile.txt").exists())
        self.assertEqual(b"old launch", (self.app / "Launch.lua").read_bytes())
        self.assertEqual(b"old main", (self.app / "Modules/Main.lua").read_bytes())

    def test_a_missing_file_on_the_server_fails_the_download(self):
        new = dict(self.installed, **{"Launch.lua": b"new launch"})
        self.publish("1.1.0", new, served={})
        self.run_lua("UpdateCheck.lua", "check")
        result = self.run_lua("UpdateCheck.lua", "download")
        self.assertIsNone(result[0])
        self.assertIn("Couldn't download Launch.lua", result[1])
        self.assertIn("HTTP 404", result[1])

    def test_staged_files_from_an_interrupted_attempt_are_reused(self):
        new = dict(self.installed, **{"Launch.lua": b"new launch"})
        self.update_to(new)
        requests = len(self.server.requests)
        self.assertEqual(["ready", "normal"], self.run_lua("UpdateCheck.lua", "download"))
        self.assertEqual(requests, len(self.server.requests))

    def test_unsafe_names_and_untrusted_sources_are_refused(self):
        for name in ("../escape.lua", "Builds/Mine.xml", "Settings.xml", "Update/opFile.txt", "C:/Windows/x.dll",
                     "manifest.xml", "Data/x.old", "a\\b.lua"):
            self.publish("1.1.0", dict(self.installed, **{name: b"x"}))
            result = self.run_lua("UpdateCheck.lua", "check")
            self.assertIsNone(result[0], name)
            self.assertIn("unsafe file", result[1], name)
        self.publish("1.1.0", self.installed, sources={"repo": "https://evil.example/", "asset": "https://evil.example/"})
        result = self.run_lua("UpdateCheck.lua", "check")
        self.assertIsNone(result[0])
        self.assertIn("invalid entry", result[1])
        self.publish("1.1.0", self.installed, update="https://evil.example/update.xml")
        self.assertIn("untrusted update source", self.run_lua("UpdateCheck.lua", "check")[1])

    def test_a_copy_without_an_update_source_never_checks(self):
        root = ET.Element("PoBVersion")
        ET.SubElement(root, "Version", number="2.67.2", branch="evrybuild", platform="win32")
        ET.ElementTree(root).write(self.app / "manifest.xml")
        result = self.run_lua("UpdateCheck.lua", "check")
        self.assertIsNone(result[0])
        self.assertIn("no update source", result[1])
        self.assertEqual([], self.server.requests)

    def test_a_failed_install_restores_every_file(self):
        new = dict(self.installed, **{"Launch.lua": b"new launch", "Modules/Main.lua": b"new main", "Unchanged.lua": b"newer"})
        self.update_to(new)
        # Python opens files without delete sharing, so this one cannot be renamed while it is open.
        with open(self.app / "Unchanged.lua", "rb"):
            result = self.run_lua("UpdateApply.lua", "Update/opFile.txt")
        self.assertIsNone(result[0])
        self.assertIn("Unchanged.lua", result[1])
        self.assertEqual(b"old launch", (self.app / "Launch.lua").read_bytes())
        self.assertEqual(b"old main", (self.app / "Modules/Main.lua").read_bytes())
        self.assertEqual(b"same", (self.app / "Unchanged.lua").read_bytes())
        self.assertEqual("1.0.0", ET.parse(self.app / "manifest.xml").getroot().find("Version").get("release"))
        self.assertFalse(list(self.app.rglob("*.old")))
        self.assertEqual([True], self.run_lua("UpdateApply.lua", "Update/opFile.txt"), "the staged update can be retried")
        self.assertEqual(b"newer", (self.app / "Unchanged.lua").read_bytes())

    def test_old_files_still_in_use_are_removed_on_a_later_start(self):
        self.update_to(dict(self.installed, **{"zstd.dll": b"new native"}))
        # Stand in for a loaded DLL: Windows lets it be renamed, so hold only the renamed copy open afterwards.
        self.assertEqual([True], self.run_lua("UpdateApply.lua", "Update/opFile.txt"))
        self.assertEqual(b"new native", (self.app / "zstd.dll").read_bytes())
        (self.app / "zstd.dll.old").write_bytes(b"old native")
        (self.app / "Update/cleanup.txt").write_text((self.app / "zstd.dll.old").as_posix() + "\n")
        with open(self.app / "zstd.dll.old", "rb"):
            self.assertEqual([True], self.run_lua("UpdateApply.lua", None, True))
        self.assertTrue((self.app / "zstd.dll.old").exists())
        self.assertEqual([True], self.run_lua("UpdateApply.lua", None, True))
        self.assertFalse((self.app / "zstd.dll.old").exists())
        self.assertFalse((self.app / "Update/cleanup.txt").exists())


if __name__ == "__main__":
    unittest.main()
