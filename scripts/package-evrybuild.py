"""Package this evryBuild fork as a standalone Windows application.

Run from the repository root:
    python scripts/package-evrybuild.py --destination ../evryBuild-app

The checked-in compiled runtime is reused; this command does not download software, rebuild the native launcher,
or read another PoB installation. Current fork source is copied, including uncommitted Lua changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
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
                    "docs/images/localexile-export.png"}


class PackageError(Exception):
    pass


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
    for document in (Path("README.md"), Path("docs/LocalExile.md"), Path("docs/images/localexile-export.png")):
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


def package(source_root: Path, destination: Path) -> dict:
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
    stage = Path(tempfile.mkdtemp(prefix=".evrybuild-package-", dir=target.parent)).resolve()
    published = False
    try:
        hashes = {}
        for relative, input_path in files.items():
            output = stage / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, output)
            hashes[relative.as_posix()] = hashlib.sha256(output.read_bytes()).hexdigest()
        (stage / "Builds").mkdir()
        release = ET.Element("PoBVersion")
        ET.SubElement(release, "Version", number=version, branch="evrybuild", platform="win32")
        ET.ElementTree(release).write(stage / "manifest.xml", encoding="utf-8", xml_declaration=True)
        (stage / "evryBuild.cmd").write_bytes(
            b'@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\nstart "" "%~dp0evryBuild.exe" "%~dp0Launch.lua"\r\n')
        record = {"application": BRAND, "upstreamVersion": version, "sourceRevision": source_revision(source),
                  "executable": EXE, "portableUserData": True, "filesSha256": hashes}
        (stage / "evryBuild-package.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        if target.exists():
            raise PackageError("The destination appeared while packaging; it was not overwritten.")
        os.rename(stage, target)
        published = True
        return {"ok": True, "application": BRAND, "destination": str(target),
                "executablePath": str(target / EXE), "copiedApplicationFiles": len(files),
                "sourceRevision": record["sourceRevision"]}
    finally:
        if not published and stage.exists():
            clean_stage(stage, target.parent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path, help="New portable application folder")
    parser.add_argument("--source-root", type=Path, default=REPOSITORY, help="evryBuild checkout (default: this repository)")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(package(args.source_root, args.destination), indent=2))
        return 0
    except (PackageError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
