"""Package this evryBuild fork as a standalone Windows application.

Run from the repository root:
    python scripts/package-evrybuild.py --destination ../evryBuild-app

The checked-in compiled runtime is reused; this command does not download software, rebuild the native launcher,
or read another PoB installation. Current fork source is copied, including uncommitted Lua changes.

A release package (--release-tag) is different: it must be built from a clean commit whose VERSION file and newest
CHANGELOG.md heading match the tag, copies each file exactly as git stores it (what GitHub serves for that commit),
and writes a manifest that lets the portable application update itself from later releases. --assets collects the
files that release must attach.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import NamedTuple
import xml.etree.ElementTree as ET


REPOSITORY = Path(__file__).resolve().parents[1]
BRAND = "evryBuild - POB for LocalExile"
HOST = "Path{space}of{space}Building.exe"
EXE = "evryBuild.exe"
PRIVATE_NAMES = {"builds", "settings.xml", "localexile.json", "imgui.ini", "update", "installed.cfg",
                 "first.run", ".git", "logs", "captures", "backups", "__pycache__"}
DEFAULT_FILES = {"LICENSE.md", "help.txt", "changelog.txt"}
APPLICATION_DIRECTORIES = {"Assets", "Classes", "Data", "Modules", "TreeData"}
APPLICATION_FILES = {"Launch.lua", "LaunchServer.lua", "GameVersions.lua", "UpdateApply.lua", "UpdateCheck.lua"}
REQUIRED_OUTPUTS = {EXE, "Launch.lua", "GameVersions.lua", "Modules/Main.lua", "Classes/ImportTab.lua",
                    "Modules/LocalExile.lua", "LICENSE.md", "help.txt", "changelog.txt", "lua51.dll",
                    "SimpleGraphic.dll", "lcurl.dll", "libcurl.dll", "zlib1.dll", "lua/dkjson.lua", "lua/base64.lua",
                    "Modules/LocalExileNative.lua", "LocalExile/evryBuild.Export.exe", "README.md", "docs/LocalExile.md",
                    "docs/images/localexile-export.png", "docs/images/localexile-export-dialog.png"}


REPOSITORY_NAME = "LocalExile/evryBuild"
UPDATE_ASSET = "evryBuild-update.xml"
# This fork carries upstream PoB's own tags (v1.0.0 to v2.67.2), so evryBuild's tags have a prefix of their own.
TAG_PREFIX = "evrybuild-v"
# Semantic Versioning 2.0.0 without build metadata: MAJOR.MINOR.PATCH, optionally -rc.1 and the like.
IDENTIFIER = r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
SEMVER = rf"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-{IDENTIFIER}(?:\.{IDENTIFIER})*)?"
EXPORTER_OUTPUT = "LocalExile/evryBuild.Export.exe"
EXPORTER_ASSET = "evryBuild.Export.exe"
PACKAGE_RECORD = "evryBuild-package.json"


class PackageError(Exception):
    pass


class Release(NamedTuple):
    """Where a release package updates from. A test server stands in for GitHub with --update-base."""
    tag: str
    update_base: str | None = None

    @property
    def label(self) -> str:
        """The version the tag names: evrybuild-v1.2.0 is 1.2.0."""
        return self.tag[len(TAG_PREFIX):]

    def update_url(self) -> str:
        base = self.update_base or f"https://github.com/{REPOSITORY_NAME}/"
        return f"{base}releases/latest/download/{UPDATE_ASSET}"

    def repo_url(self, commit: str) -> str:
        if self.update_base:
            return f"{self.update_base}raw/{commit}/"
        return f"https://raw.githubusercontent.com/{REPOSITORY_NAME}/{commit}/"

    def asset_url(self) -> str:
        base = self.update_base or f"https://github.com/{REPOSITORY_NAME}/"
        return f"{base}releases/download/{self.tag}/"


def parse_release(tag: str | None, update_base: str | None) -> Release | None:
    if tag is None:
        if update_base:
            raise PackageError("--update-base needs --release-tag.")
        return None
    if not re.fullmatch(re.escape(TAG_PREFIX) + SEMVER, tag):
        raise PackageError(f"Release tags are {TAG_PREFIX} and a semantic version, such as {TAG_PREFIX}1.2.0 or "
                           f"{TAG_PREFIX}1.3.0-rc.1. Plain v1.2.0 tags belong to upstream PoB.")
    if update_base is not None and not re.fullmatch(r"https?://[^/\s]+/(?:[^\s\"]*/)?", update_base):
        raise PackageError("--update-base must be an http(s) URL ending in /.")
    return Release(tag, update_base)


def relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or "\\" in value or ":" in value or path.is_absolute() or any(p in (".", "..") for p in path.parts):
        raise PackageError(f"Invalid application manifest path: {value}")
    if any(p.casefold() in PRIVATE_NAMES for p in path.parts) or value.lower().endswith((".log", ".tmp", ".credentials")):
        raise PackageError(f"Application manifests cannot include personal state: {value}")
    return path


def checked_file(root: Path, relative: Path) -> Path:
    candidate = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise PackageError(f"Application files cannot be symlinks or junctions: {relative}")
    if not candidate.resolve().is_relative_to(root) or not candidate.is_file():
        raise PackageError(f"A required application file is missing or outside the source checkout: {relative}")
    return candidate


def application_files(source: Path) -> tuple[str, dict[Path, Path]]:
    manifest_path = checked_file(source, Path("manifest.xml"))
    if manifest_path.stat().st_size > 4 * 1024 * 1024:
        raise PackageError("The application manifest is unexpectedly large.")
    try:
        manifest = ET.fromstring(manifest_path.read_bytes())
    except ET.ParseError as error:
        raise PackageError("The source application manifest is unreadable.") from error
    version = manifest.find("Version")
    if manifest.tag != "PoBVersion" or version is None or not version.get("number"):
        raise PackageError("The source manifest must identify its upstream application version.")
    files: dict[Path, Path] = {}
    names: set[str] = set()

    def add(input_path: Path, output_path: Path) -> None:
        if output_path.as_posix().casefold() in names:
            raise PackageError(f"Two application files would overwrite the same output: {output_path}")
        files[output_path] = checked_file(source, input_path)
        names.add(output_path.as_posix().casefold())

    for item in manifest.findall("File"):
        name = relative_path(item.get("name", ""))
        part = item.get("part")
        output = Path(*name.parts)
        if part == "default":
            if name.as_posix() not in DEFAULT_FILES:
                raise PackageError(f"Unsupported default application file: {name}")
            input_path = output
        elif part == "runtime":
            # The repository stores the launcher with literal {space} tokens; release folders use evryBuild.exe.
            input_path = Path("runtime") / output
            if name.as_posix() == HOST:
                output = Path(EXE)
            else:
                output = Path(*[p.replace("{space}", " ") for p in name.parts])
                if len(name.parts) == 1 and not name.as_posix().lower().endswith(".dll"):
                    raise PackageError(f"Unsupported native runtime file: {name}")
                if len(name.parts) > 1 and name.parts[0] not in ("lua", "SimpleGraphic"):
                    raise PackageError(f"Unsupported native runtime folder: {name}")
        elif part in ("program", "tree"):
            if (len(name.parts) == 1 and name.as_posix() not in APPLICATION_FILES
                    or len(name.parts) > 1 and name.parts[0] not in APPLICATION_DIRECTORIES):
                raise PackageError(f"Unsupported program or tree file: {name}")
            input_path = Path("src") / output
        else:
            raise PackageError(f"Unsupported manifest part for {name}: {part}")
        add(input_path, output)

    # Fork-owned files are intentionally not generated into upstream's update manifest.
    for module in (Path("Modules/LocalExile.lua"), Path("Modules/LocalExileNative.lua")):
        if module.as_posix().casefold() not in names:
            add(Path("src") / module, module)
    for document in (Path("README.md"), Path("docs/LocalExile.md"), Path("docs/images/localexile-export.png"),
                     Path("docs/images/localexile-export-dialog.png")):
        add(document, document)
    exporter = Path("runtime/LocalExile/evryBuild.Export.exe")
    if not (source / exporter).is_file():
        raise PackageError("Build the bundled local exporter first: .\\scripts\\build-exporter.ps1")
    receipt = checked_file(source, Path("runtime/LocalExile/exporter-build.json"))
    try:
        exporter_receipt = json.loads(receipt.read_text(encoding="utf-8-sig"))
        digest = exporter_receipt["sha256"]
    except (KeyError, ValueError) as error:
        raise PackageError("The exporter build receipt is invalid; rebuild the exporter.") from error
    if hashlib.sha256(checked_file(source, exporter).read_bytes()).hexdigest() != digest:
        raise PackageError("The exporter differs from its build receipt; rebuild the exporter.")
    source_folder = source / "tools/LocalExile.Export"
    expected_sources = {p.relative_to(source_folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in source_folder.rglob("*") if p.is_file() and p.suffix in (".cs", ".csproj", ".json", ".md", ".txt")
                        and not any(part in ("bin", "obj") for part in p.relative_to(source_folder).parts)}
    if exporter_receipt.get("sources") != expected_sources:
        raise PackageError("The exporter source changed since its build; run scripts/build-exporter.ps1 again.")
    add(exporter, Path("LocalExile/evryBuild.Export.exe"))
    add(Path("tools/LocalExile.Export/NOTICE.md"), Path("LocalExile/NOTICE.md"))
    for notice in ("DOTNET-LICENSE.txt", "DOTNET-THIRD-PARTY-NOTICES.txt", "SQLITEPCLRAW-LICENSE.txt"):
        add(Path("tools/LocalExile.Export/notices") / notice, Path("LocalExile/notices") / notice)
    compatibility = Path("runtime/msvcr100.dll")
    if (source / compatibility).is_file() and "msvcr100.dll" not in names:
        add(compatibility, Path("msvcr100.dll"))
    missing = REQUIRED_OUTPUTS - {p.as_posix() for p in files}
    if missing:
        raise PackageError("The manifest omits required program/runtime files: " + ", ".join(sorted(missing)))
    return version.get("number"), files


def read_version(source: Path) -> str:
    """evryBuild's own version, from the committed VERSION file (PoB's version in manifest.xml is the planner base)."""
    path = source / "VERSION"
    if not path.is_file():
        raise PackageError("The VERSION file is missing; it holds evryBuild's version, such as 1.0.0.")
    version = path.read_text(encoding="utf-8-sig").strip()
    if not re.fullmatch(SEMVER, version):
        raise PackageError(f"VERSION must hold a semantic version such as 1.2.0, not '{version}'.")
    return version


def check_release_version(source: Path, release: Release, version: str) -> None:
    """The tag, the committed VERSION and the newest changelog heading must name the same release."""
    if release.label != version:
        raise PackageError(f"The tag {release.tag} does not match VERSION {version}. Bump VERSION and commit, or use {TAG_PREFIX}{version}.")
    heading = next((line for line in release_notes(source).splitlines() if line.startswith("## ")), "")
    if not re.match(rf"## {re.escape(version)}(?:\s|$)", heading):
        raise PackageError(f"CHANGELOG.md's newest section must be headed '## {version} - <date>'; it is '{heading}'.")
    if "unreleased" in heading.lower():
        raise PackageError(f"CHANGELOG.md still calls {version} unreleased; put the release date in its heading.")


def release_notes(source: Path) -> str:
    """The newest CHANGELOG.md section: what the update popup shows."""
    changelog = source / "CHANGELOG.md"
    if not changelog.is_file():
        return ""
    section: list[str] = []
    for line in changelog.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("## "):
            if section:
                break
            section.append(line)
        elif section:
            section.append(line)
    return "\n".join(section).strip()


def git(source: Path, *args: str, data: bytes | None = None) -> bytes:
    try:
        return subprocess.run(["git", "-C", str(source), *args], input=data, capture_output=True, check=True, timeout=300).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise PackageError(f"git {args[0]} failed; release packages need the git checkout.") from error


def committed_files(source: Path, paths: list[str]) -> tuple[str, dict[str, bytes]]:
    """The checkout's commit and each path's bytes as git stores them, which is what GitHub serves for it."""
    if git(source, "status", "--porcelain", "--untracked-files=no").strip():
        raise PackageError("Release packages are built from a clean commit; commit or discard the changes first.")
    commit = git(source, "rev-parse", "HEAD").decode().strip()
    output = git(source, "cat-file", "--batch", data="".join(f"{commit}:{p}\n" for p in paths).encode())
    blobs: dict[str, bytes] = {}
    position = 0
    for path in paths:
        end = output.index(b"\n", position)
        header = output[position:end].decode()
        if header.endswith(" missing") or len(header.split()) != 3:
            raise PackageError(f"{path} is not committed; release packages contain only committed files.")
        size = int(header.split()[2])
        blobs[path] = output[end + 1:end + 1 + size]
        position = end + 1 + size + 1
    return commit, blobs


def source_revision(source: Path) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True,
                                text=True, check=True, timeout=10)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def clean_stage(stage: Path, parent: Path) -> None:
    resolved = stage.resolve()
    if resolved.parent != parent.resolve() or not resolved.name.startswith(".evrybuild-package-") \
            or stage.is_symlink() or getattr(stage, "is_junction", lambda: False)():
        raise PackageError("Refused to clean a staging folder outside the intended output parent.")
    shutil.rmtree(resolved)


def package(source_root: Path, destination: Path, release: Release | None = None, assets: Path | None = None) -> dict:
    source = source_root.expanduser().resolve()
    target = destination.expanduser().resolve()
    if not source.is_dir():
        raise PackageError("Choose the evryBuild source repository containing src, runtime and manifest.xml.")
    if target == source or source.is_relative_to(target) or any(target.is_relative_to(source / p) for p in ("src", "runtime")):
        raise PackageError("The destination cannot overwrite the source checkout or its application/runtime folders.")
    if target.exists() or destination.is_symlink():
        raise PackageError("The destination already exists. Choose a new folder; existing applications and profiles are never overwritten.")
    if not target.parent.is_dir():
        raise PackageError("The destination's parent folder must already exist.")
    version, files = application_files(source)
    evrybuild_version = read_version(source)
    if assets is not None:
        if release is None:
            raise PackageError("--assets is for release packages; add --release-tag.")
        assets = assets.expanduser().resolve()
        if assets.exists() or not assets.parent.is_dir():
            raise PackageError("--assets must name a new folder whose parent exists.")
    # Every application file is committed except the exporter, which is built and attached to the release.
    repository_paths = {relative: input_path.relative_to(source).as_posix() for relative, input_path in files.items()
                        if relative.as_posix() != EXPORTER_OUTPUT}
    commit, blobs = committed_files(source, sorted({*repository_paths.values(), "VERSION"})) if release else (None, {})
    if release:
        if blobs["VERSION"].decode("utf-8-sig").strip() != evrybuild_version:
            raise PackageError("VERSION differs from its committed copy; commit it first.")
        check_release_version(source, release, evrybuild_version)
    stage = Path(tempfile.mkdtemp(prefix=".evrybuild-package-", dir=target.parent)).resolve()
    published = False
    try:
        hashes = {}
        for relative, input_path in files.items():
            output = stage / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            if release and relative in repository_paths:
                output.write_bytes(blobs[repository_paths[relative]])
            else:
                shutil.copy2(input_path, output)
            hashes[relative.as_posix()] = hashlib.sha256(output.read_bytes()).hexdigest()
        (stage / "Builds").mkdir()
        (stage / "evryBuild.cmd").write_bytes(
            b'@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\nstart "" "%~dp0evryBuild.exe" "%~dp0Launch.lua"\r\n')
        record = {"application": BRAND, "version": evrybuild_version, "upstreamVersion": version,
                  "sourceRevision": commit if release else source_revision(source),
                  "executable": EXE, "portableUserData": True, "filesSha256": hashes}
        if release:
            record.update(tag=release.tag)
        (stage / PACKAGE_RECORD).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        manifest = ET.Element("PoBVersion")
        # number is PoB's version (the planner base); release is evryBuild's own, which updates compare.
        version_element = ET.SubElement(manifest, "Version", number=version, branch="evrybuild", platform="win32",
                                        release=evrybuild_version)
        if release:
            version_element.set("tag", release.tag)
            version_element.set("commit", commit)
            ET.SubElement(manifest, "Update", url=release.update_url())
            ET.SubElement(manifest, "Source", part="repo", url=release.repo_url(commit))
            ET.SubElement(manifest, "Source", part="asset", url=release.asset_url())
            ET.SubElement(manifest, "Notes").text = release_notes(source)
            managed = {relative.as_posix(): ("repo", repository_paths[relative]) for relative in repository_paths}
            managed[EXPORTER_OUTPUT] = ("asset", EXPORTER_ASSET)
            managed[PACKAGE_RECORD] = ("asset", PACKAGE_RECORD)
            for name in sorted(managed, key=str.casefold):
                part, origin = managed[name]
                content = (stage / name).read_bytes()
                entry = ET.SubElement(manifest, "File", name=name, part=part, source=origin,
                                      sha256=hashlib.sha256(content).hexdigest(), size=str(len(content)))
                if "/" not in name and name.lower().endswith((".dll", ".exe")):
                    # Loaded by the running application: installing it needs a new process.
                    entry.set("native", "true")
        ET.ElementTree(manifest).write(stage / "manifest.xml", encoding="utf-8", xml_declaration=True)
        if target.exists():
            raise PackageError("The destination appeared while packaging; it was not overwritten.")
        os.rename(stage, target)
        published = True
        result = {"ok": True, "application": BRAND, "version": evrybuild_version, "destination": str(target),
                  "executablePath": str(target / EXE), "copiedApplicationFiles": len(files),
                  "sourceRevision": record["sourceRevision"]}
        if release:
            result.update(tag=release.tag)
        if assets is not None:
            assets.mkdir()
            shutil.copy2(target / "manifest.xml", assets / UPDATE_ASSET)
            shutil.copy2(target / EXPORTER_OUTPUT, assets / EXPORTER_ASSET)
            shutil.copy2(target / PACKAGE_RECORD, assets / PACKAGE_RECORD)
            result["assets"] = str(assets)
        return result
    finally:
        if not published and stage.exists():
            clean_stage(stage, target.parent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path, help="New portable application folder")
    parser.add_argument("--source-root", type=Path, default=REPOSITORY, help="evryBuild checkout (default: this repository)")
    parser.add_argument("--release-tag", help=f"Build a self-updating release package for this tag: {TAG_PREFIX} and the VERSION file, such as {TAG_PREFIX}1.2.0")
    parser.add_argument("--assets", type=Path, help="New folder for the files the release must attach")
    parser.add_argument("--update-base", help="Test only: serve updates from this URL instead of GitHub")
    args = parser.parse_args(argv)
    try:
        release = parse_release(args.release_tag, args.update_base)
        print(json.dumps(package(args.source_root, args.destination, release, args.assets), indent=2))
        return 0
    except (PackageError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
