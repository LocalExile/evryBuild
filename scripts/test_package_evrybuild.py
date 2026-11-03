"""Focused release-packaging checks; no real game files or other installations are used."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("evrybuild_package", Path(__file__).with_name("package-evrybuild.py"))
package_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package_module)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="evrybuild-source-package-")
        self.folder = Path(self.temporary.name)
        self.source = self.folder / "source"
        self.source.mkdir()
        self.target = self.folder / "evryBuild"
        self.entries = [
            ("default", "LICENSE.md"), ("default", "help.txt"), ("default", "changelog.txt"),
            ("runtime", package_module.HOST), ("runtime", "lua51.dll"), ("runtime", "SimpleGraphic.dll"),
            ("runtime", "lcurl.dll"), ("runtime", "libcurl.dll"), ("runtime", "zlib1.dll"),
            ("runtime", "lua/dkjson.lua"), ("runtime", "lua/base64.lua"),
            ("runtime", "SimpleGraphic/Fonts/Vera.ttf"),
            ("program", "Launch.lua"), ("program", "GameVersions.lua"),
            ("program", "Modules/Main.lua"), ("program", "Classes/ImportTab.lua"),
            ("tree", "TreeData/3_29/tree.lua"),
        ]
        for part, name in self.entries:
            location = self.source / ({"default": "", "runtime": "runtime", "program": "src", "tree": "src"}[part]) / name
            location.parent.mkdir(parents=True, exist_ok=True)
            location.write_bytes(("current fork file: " + name).encode())
        (self.source / "src/Modules/LocalExile.lua").write_text("current fork integration", encoding="utf-8")
        (self.source / "runtime/msvcr100.dll").write_bytes(b"compatibility runtime")
        (self.source / "src/Modules/LocalExileNative.lua").write_text("local process bridge")
        (self.source / "README.md").write_text("Portable application quick start", encoding="utf-8")
        (self.source / "docs").mkdir()
        (self.source / "docs/LocalExile.md").write_text("Database export setup instructions", encoding="utf-8")
        (self.source / "docs/images").mkdir()
        (self.source / "docs/images/localexile-export.png").write_bytes(b"README screenshot fixture")
        (self.source / "docs/images/localexile-export-dialog.png").write_bytes(b"README dialog screenshot fixture")
        exporter = self.source / "runtime/LocalExile/evryBuild.Export.exe"
        exporter.parent.mkdir(parents=True)
        exporter.write_bytes(b"synthetic exporter runtime")
        (exporter.parent / "exporter-build.json").write_text(json.dumps({"sha256":hashlib.sha256(exporter.read_bytes()).hexdigest()}))
        notice = self.source / "tools/LocalExile.Export/NOTICE.md"
        notice.parent.mkdir(parents=True)
        notice.write_text("Exporter attribution")
        notices = notice.parent / 'notices'
        notices.mkdir()
        for name in ('DOTNET-LICENSE.txt', 'DOTNET-THIRD-PARTY-NOTICES.txt', 'SQLITEPCLRAW-LICENSE.txt'):
            (notices / name).write_text('Third-party license text')
        receipt = exporter.parent / "exporter-build.json"
        receipt.write_text(json.dumps({"sha256":hashlib.sha256(exporter.read_bytes()).hexdigest(),
                                      "sources":{p.relative_to(notice.parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                                 for p in notice.parent.rglob('*') if p.is_file()}}))
        for name in ("Settings.xml", "LocalExile.json", "imgui.ini", "first.run", "installed.cfg", "Builds/Personal.xml", "Update/private.tmp"):
            path = self.source / "src" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("personal state", encoding="utf-8")
        self.write_manifest()

    def write_manifest(self):
        manifest = ET.Element("PoBVersion")
        ET.SubElement(manifest, "Version", number="2.67.2")
        for part, name in self.entries:
            ET.SubElement(manifest, "File", name=name, part=part, sha1="upstream-old-hash")
        ET.ElementTree(manifest).write(self.source / "manifest.xml", encoding="utf-8", xml_declaration=True)

    def tearDown(self):
        self.temporary.cleanup()

    def package(self):
        with patch.object(package_module, "source_revision", return_value="source-commit"):
            return package_module.package(self.source, self.target)

    def test_packages_current_fork_and_compiled_runtime_without_an_external_installation(self):
        before = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        changed = self.source / "src/Modules/Main.lua"
        changed.write_bytes(b"uncommitted fork source is the packaging input")
        before[changed.relative_to(self.source)] = changed.read_bytes()
        result = self.package()
        self.assertTrue(result["ok"])
        self.assertEqual((self.target / "evryBuild.exe").read_bytes(), (self.source / "runtime" / package_module.HOST).read_bytes())
        self.assertEqual((self.target / "Modules/Main.lua").read_bytes(), changed.read_bytes())
        self.assertEqual((self.target / "Modules/LocalExile.lua").read_text(), "current fork integration")
        self.assertTrue((self.target / "lua/dkjson.lua").is_file())
        self.assertTrue((self.target / "SimpleGraphic/Fonts/Vera.ttf").is_file())
        self.assertTrue((self.target / "LICENSE.md").is_file())
        self.assertTrue((self.target / "msvcr100.dll").is_file())
        self.assertFalse((self.target / package_module.HOST).exists())
        self.assertEqual(before, {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob("*") if p.is_file()})

    def test_personal_profiles_downloads_and_unlisted_files_are_omitted(self):
        self.package()
        self.assertEqual([], list((self.target / "Builds").iterdir()))
        for name in ("Settings.xml", "LocalExile.json", "imgui.ini", "first.run", "installed.cfg", "Update"):
            self.assertFalse((self.target / name).exists(), name)
        release = ET.parse(self.target / "manifest.xml").getroot().find("Version")
        self.assertEqual("2.67.2", release.get("number"))
        self.assertEqual("win32", release.get("platform"))
        self.assertEqual("evrybuild", release.get("branch"))
        record = json.loads((self.target / "evryBuild-package.json").read_text())
        self.assertEqual("source-commit", record["sourceRevision"])
        self.assertTrue(record["portableUserData"])
        self.assertIn("Modules/LocalExile.lua", record["filesSha256"])
        self.assertIn('"%~dp0evryBuild.exe" "%~dp0Launch.lua"', (self.target / "evryBuild.cmd").read_text())

    def test_portable_includes_current_setup_instructions_and_refuses_missing_guide(self):
        guide = self.source / 'docs/LocalExile.md'
        expected = guide.read_bytes()
        guide.unlink()
        with self.assertRaisesRegex(package_module.PackageError, 'required application file'):
            self.package()
        self.assertFalse(self.target.exists())
        guide.write_bytes(expected)
        self.package()
        self.assertEqual(expected, (self.target / 'docs/LocalExile.md').read_bytes())
        self.assertEqual((self.source / 'README.md').read_bytes(), (self.target / 'README.md').read_bytes())
        record = json.loads((self.target / 'evryBuild-package.json').read_text())
        self.assertEqual(hashlib.sha256(expected).hexdigest(), record['filesSha256']['docs/LocalExile.md'])
        for screenshot in ('docs/images/localexile-export.png', 'docs/images/localexile-export-dialog.png'):
            self.assertEqual((self.source / screenshot).read_bytes(), (self.target / screenshot).read_bytes())
            self.assertEqual(hashlib.sha256((self.source / screenshot).read_bytes()).hexdigest(), record['filesSha256'][screenshot])

    def test_an_existing_application_or_profile_is_never_overwritten(self):
        self.target.mkdir()
        saved = self.target / "Settings.xml"
        saved.write_text("keep my profile")
        with self.assertRaisesRegex(package_module.PackageError, "already exists"):
            self.package()
        self.assertEqual("keep my profile", saved.read_text())

    def test_unsafe_source_overlap_is_refused_before_copying(self):
        for output in (self.source, self.source / "src/release", self.source / "runtime/release", self.folder):
            with self.subTest(output=output), self.assertRaisesRegex(package_module.PackageError, "source checkout"):
                package_module.package(self.source, output)

    def test_an_ignored_dist_directory_can_hold_a_new_release(self):
        dist = self.source / "dist"
        dist.mkdir()
        self.target = dist / "evryBuild"
        self.assertTrue(self.package()["ok"])

    def test_bad_manifest_paths_private_state_and_missing_files_stop_before_publication(self):
        for part, name in (("program", "../Settings.xml"), ("program", "Settings.xml"),
                           ("program", "/absolute.lua"), ("runtime", "C:/outside.dll"), ("program", "Unknown/private.lua")):
            self.entries.append((part, name))
            self.write_manifest()
            with self.subTest(name=name), self.assertRaises(package_module.PackageError):
                self.package()
            self.entries.pop()
            self.assertFalse(self.target.exists())
        self.write_manifest()
        (self.source / "runtime/lua51.dll").unlink()
        with self.assertRaisesRegex(package_module.PackageError, "required application file"):
            self.package()
        self.assertFalse(self.target.exists())

    def test_copy_failure_cleans_only_the_checked_staging_folder(self):
        original = package_module.shutil.copy2
        count = 0

        def fail_after_a_file(source, destination):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("synthetic copy failure")
            return original(source, destination)

        marker = self.folder / "keep.txt"
        marker.write_text("unrelated")
        with patch.object(package_module.shutil, "copy2", side_effect=fail_after_a_file):
            with self.assertRaisesRegex(OSError, "synthetic"):
                self.package()
        self.assertFalse(self.target.exists())
        self.assertEqual([], list(self.folder.glob(".evrybuild-package-*")))
        self.assertEqual("unrelated", marker.read_text())

    def test_omitted_required_integration_and_output_collisions_are_rejected(self):
        (self.source / "src/Modules/LocalExile.lua").unlink()
        with self.assertRaisesRegex(package_module.PackageError, "required application file"):
            self.package()
        (self.source / "src/Modules/LocalExile.lua").write_text("module")
        self.entries.append(("program", "Launch.lua"))
        self.write_manifest()
        with self.assertRaisesRegex(package_module.PackageError, "overwrite"):
            self.package()

    def test_stale_exporter_and_changed_source_are_refused(self):
        exporter = self.source / 'runtime/LocalExile/evryBuild.Export.exe'
        original = exporter.read_bytes()
        exporter.write_bytes(b'changed executable')
        with self.assertRaisesRegex(package_module.PackageError, 'build receipt'):
            self.package()
        exporter.write_bytes(original)
        (self.source / 'tools/LocalExile.Export/NOTICE.md').write_text('changed source input')
        with self.assertRaisesRegex(package_module.PackageError, 'source changed'):
            self.package()
        self.assertFalse(self.target.exists())

    def test_a_package_without_a_release_tag_never_updates_itself(self):
        self.package()
        manifest = ET.parse(self.target / "manifest.xml").getroot()
        self.assertIsNone(manifest.find("Update"))
        self.assertIsNone(manifest.find("Version").get("release"))
        self.assertEqual([], manifest.findall("File"))


TAG = "evrybuild-localexile-external-2026.11.10"


class ReleasePackageTests(PackageTests):
    """Release packages: built from a clean commit, with an update manifest of what GitHub serves for it."""
    def setUp(self):
        super().setUp()
        (self.source / "CHANGELOG.md").write_text("# Changelog\n\n## Next release\n\n- Updates in place.\n\n## Older\n\n- Old.\n")
        (self.source / ".gitignore").write_text("runtime/LocalExile/\nsrc/Builds/\nsrc/Update/\nsrc/*.xml\nsrc/*.json\nsrc/*.ini\nsrc/*.run\nsrc/*.cfg\n")
        # Committed with LF; the working copy then gets CRLF, as a Windows checkout does.
        (self.source / "src/Launch.lua").write_bytes(b"line one\nline two\n")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fixture")
        self.commit = self.git("rev-parse", "HEAD").strip()
        (self.source / "src/Launch.lua").write_bytes(b"line one\r\nline two\r\n")
        self.git("update-index", "--assume-unchanged", "src/Launch.lua")

    def git(self, *args):
        return package_module.subprocess.run(["git", "-C", str(self.source), "-c", "user.name=t", "-c", "user.email=t@t",
                                              "-c", "core.autocrlf=false", *args],
                                             capture_output=True, text=True, check=True).stdout

    def release_package(self, base=None, assets=None):
        return package_module.package(self.source, self.target, package_module.parse_release(TAG, base), assets)

    def test_release_manifest_lists_every_file_by_its_committed_bytes(self):
        assets = self.folder / "assets"
        result = self.release_package(assets=assets)
        self.assertEqual(("2026.11.10", TAG, self.commit), (result["release"], result["tag"], result["sourceRevision"]))
        self.assertEqual(b"line one\nline two\n", (self.target / "Launch.lua").read_bytes(), "the committed bytes, not the working copy")
        manifest = ET.parse(self.target / "manifest.xml").getroot()
        version = manifest.find("Version")
        self.assertEqual(("2026.11.10", TAG, self.commit, "evrybuild", "win32"),
                         tuple(version.get(k) for k in ("release", "tag", "commit", "branch", "platform")))
        self.assertEqual("https://github.com/LocalExile/evryBuild/releases/latest/download/evryBuild-update.xml",
                         manifest.find("Update").get("url"))
        sources = {s.get("part"): s.get("url") for s in manifest.findall("Source")}
        self.assertEqual({"repo": f"https://raw.githubusercontent.com/LocalExile/evryBuild/{self.commit}/",
                          "asset": f"https://github.com/LocalExile/evryBuild/releases/download/{TAG}/"}, sources)
        self.assertEqual("## Next release\n\n- Updates in place.", manifest.find("Notes").text)
        files = {f.get("name"): f for f in manifest.findall("File")}
        packaged = {p.relative_to(self.target).as_posix() for p in self.target.rglob("*") if p.is_file()}
        self.assertEqual(packaged - {"manifest.xml", "evryBuild.cmd"}, set(files))
        for name, entry in files.items():
            content = (self.target / name).read_bytes()
            self.assertEqual((hashlib.sha256(content).hexdigest(), str(len(content))), (entry.get("sha256"), entry.get("size")), name)
        self.assertEqual(("repo", "src/Launch.lua"), (files["Launch.lua"].get("part"), files["Launch.lua"].get("source")))
        self.assertEqual(("repo", "runtime/" + package_module.HOST), (files["evryBuild.exe"].get("part"), files["evryBuild.exe"].get("source")))
        self.assertEqual(("repo", "README.md"), (files["README.md"].get("part"), files["README.md"].get("source")))
        self.assertEqual(("asset", "evryBuild.Export.exe"), (files["LocalExile/evryBuild.Export.exe"].get("part"),
                                                             files["LocalExile/evryBuild.Export.exe"].get("source")))
        self.assertEqual("asset", files["evryBuild-package.json"].get("part"))
        self.assertEqual({"evryBuild.exe", "lua51.dll", "SimpleGraphic.dll", "lcurl.dll", "libcurl.dll", "zlib1.dll", "msvcr100.dll"},
                         {n for n, f in files.items() if f.get("native") == "true"})
        record = json.loads((self.target / "evryBuild-package.json").read_text())
        self.assertEqual(("2026.11.10", TAG, self.commit), (record["release"], record["tag"], record["sourceRevision"]))
        self.assertEqual({"evryBuild-update.xml", "evryBuild.Export.exe", "evryBuild-package.json"}, {p.name for p in assets.iterdir()})
        self.assertEqual((self.target / "manifest.xml").read_bytes(), (assets / "evryBuild-update.xml").read_bytes())

    def test_a_test_server_can_stand_in_for_github(self):
        self.release_package(base="http://127.0.0.1:8123/")
        manifest = ET.parse(self.target / "manifest.xml").getroot()
        self.assertEqual("http://127.0.0.1:8123/releases/latest/download/evryBuild-update.xml", manifest.find("Update").get("url"))
        self.assertEqual({"repo": f"http://127.0.0.1:8123/raw/{self.commit}/", "asset": f"http://127.0.0.1:8123/releases/download/{TAG}/"},
                         {s.get("part"): s.get("url") for s in manifest.findall("Source")})

    def test_uncommitted_or_untracked_application_files_are_refused(self):
        (self.source / "help.txt").write_text("changed but not committed")
        with self.assertRaisesRegex(package_module.PackageError, "clean commit"):
            self.release_package()
        self.git("checkout", "--", "help.txt")
        (self.source / "src/Modules/Untracked.lua").write_text("not committed")
        self.entries.append(("program", "Modules/Untracked.lua"))
        self.write_manifest()
        self.git("add", "manifest.xml")
        self.git("commit", "-q", "-m", "manifest lists an untracked file")
        with self.assertRaisesRegex(package_module.PackageError, "not committed"):
            self.release_package()
        self.assertFalse(self.target.exists())

    def test_release_tags_and_options_are_checked(self):
        for tag in ("v1.0.0", "evrybuild-localexile-external-2026-11-10", "evrybuild-localexile-external-2026.11.10-beta"):
            with self.assertRaisesRegex(package_module.PackageError, "Release tags"):
                package_module.parse_release(tag, None)
        self.assertEqual("2026.11.10.2", package_module.parse_release(TAG + ".2", None).label)
        with self.assertRaisesRegex(package_module.PackageError, "needs --release-tag"):
            package_module.parse_release(None, "http://127.0.0.1:1/")
        with self.assertRaisesRegex(package_module.PackageError, "ending in /"):
            package_module.parse_release(TAG, "http://127.0.0.1:1")
        with self.assertRaisesRegex(package_module.PackageError, "--assets is for release packages"):
            package_module.package(self.source, self.target, None, self.folder / "assets")


if __name__ == "__main__":
    unittest.main()
