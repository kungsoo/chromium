#!/usr/bin/env python3

# Copyright (c) 2026 Alex313031 and gz83.

"""Build Thorium's macOS 26 asset catalog and compatibility app icon."""

import argparse
from contextlib import contextmanager
import errno
import filecmp
import json
import os
import plistlib
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Sequence


MINIMUM_PYTHON = (3, 11)
MINIMUM_ACTOOL_VERSION = (24127,)
ICON_SIZES = (16, 32, 128, 256, 512)
VERSION_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")
TRANSACTION_FILE = ".thorium-mac-icon-transaction.json"
LOCK_FILE = ".thorium-mac-icon.lock"


class IconBuildError(RuntimeError):
    """An expected icon generation failure."""


@contextmanager
def icon_build_lock(path: Path):
    try:
        import fcntl
    except ImportError as error:
        raise IconBuildError("macOS file locking is unavailable") from error

    try:
        lock = path.open("a+", encoding="utf-8")
    except OSError as error:
        raise IconBuildError(
            f"could not open icon build lock {path}: {error}"
        ) from error
    try:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise IconBuildError(
                    f"another macOS icon build is already running: {path}"
                ) from error
            raise IconBuildError(f"could not lock {path}: {error}") from error
        yield
    finally:
        lock.close()


def run(command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(command, check=True, capture_output=True)
    except subprocess.CalledProcessError as error:
        diagnostics = []
        if error.stdout:
            diagnostics.append(error.stdout.decode(errors="replace").strip())
        if error.stderr:
            diagnostics.append(error.stderr.decode(errors="replace").strip())
        detail = (
            f": {'; '.join(filter(None, diagnostics))}" if diagnostics else ""
        )
        raise IconBuildError(
            f"{Path(command[0]).name} failed with exit code "
            f"{error.returncode}{detail}"
        ) from error
    except OSError as error:
        raise IconBuildError(f"could not run {command[0]}: {error}") from error


def require_tool(name: str) -> str:
    tool = shutil.which(name)
    if tool is None:
        raise IconBuildError(f"required tool was not found in PATH: {name}")
    return tool


def check_actool(xcrun: str) -> None:
    result = run((xcrun, "actool", "--output-format=xml1", "--version"))
    try:
        values = plistlib.loads(result.stdout)
        version_text = values["com.apple.actool.version"]["bundle-version"]
        version = parse_numeric_version(version_text)
    except (KeyError, TypeError, ValueError, plistlib.InvalidFileException) as error:
        raise IconBuildError("could not determine the actool version") from error
    if version < MINIMUM_ACTOOL_VERSION:
        raise IconBuildError(
            f"actool {version_text} is too old; Xcode 26 or newer is required"
        )


def parse_numeric_version(value: object) -> tuple[int, ...]:
    if not isinstance(value, str) or not VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"invalid numeric version: {value!r}")
    components = [int(component) for component in value.split(".")]
    while len(components) > 1 and components[-1] == 0:
        components.pop()
    return tuple(components)


def read_icon_layers(icon_document: Path) -> tuple[Path, ...]:
    try:
        document = json.loads(icon_document.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IconBuildError(f"could not read {icon_document}: {error}") from error

    groups = document.get("groups") if isinstance(document, dict) else None
    if not isinstance(groups, list) or not groups:
        raise IconBuildError(f"invalid groups in {icon_document}")
    image_names = []
    for group in groups:
        layers = group.get("layers") if isinstance(group, dict) else None
        if not isinstance(layers, list) or not layers:
            raise IconBuildError(f"invalid layers in {icon_document}")
        for layer in layers:
            if not isinstance(layer, dict):
                raise IconBuildError(f"invalid layer in {icon_document}")
            image_name = layer.get("image-name")
            if not isinstance(image_name, str) or not image_name:
                if "image-name-specializations" in layer:
                    raise IconBuildError(
                        "compatibility ICNS generation does not support "
                        f"image-name-specializations in {icon_document}"
                    )
                raise IconBuildError(f"invalid image-name in {icon_document}")
            image_names.append(image_name)

    assets = icon_document.parent / "Assets"
    return tuple(assets / image_name for image_name in image_names)


def render_iconset(
    rsvg_convert: str,
    magick: str,
    layer_sources: Sequence[Path],
    iconset: Path,
) -> None:
    iconset.mkdir()
    rendered_sizes: dict[int, Path] = {}
    for size in ICON_SIZES:
        for scale in (1, 2):
            pixels = size * scale
            suffix = "@2x" if scale == 2 else ""
            output = iconset / f"icon_{size}x{size}{suffix}.png"
            rendered = rendered_sizes.get(pixels)
            if rendered is not None:
                shutil.copy2(rendered, output)
                continue

            layer_outputs = []
            for index, source in enumerate(layer_sources):
                layer_output = iconset.parent / f"layer-{pixels}-{index}.png"
                run(
                    (
                        rsvg_convert,
                        "--width",
                        str(pixels),
                        "--height",
                        str(pixels),
                        "--output",
                        str(layer_output),
                        str(source),
                    )
                )
                layer_outputs.append(layer_output)
            run(
                (
                    magick,
                    *map(str, layer_outputs),
                    "-background",
                    "none",
                    "-layers",
                    "merge",
                    "+repage",
                    str(output),
                )
            )
            rendered_sizes[pixels] = output


def compile_assets(
    xcrun: str,
    source_dir: Path,
    temporary_dir: Path,
    minimum_deployment_target: str,
) -> Path:
    partial_plist = temporary_dir / "partial.plist"
    command = (
        xcrun,
        "actool",
        "--output-format=xml1",
        "--notices",
        "--warnings",
        "--errors",
        "--platform=macosx",
        "--target-device=mac",
        "--lightweight-asset-runtime-mode=enabled",
        "--app-icon=AppIcon",
        f"--minimum-deployment-target={minimum_deployment_target}",
        f"--output-partial-info-plist={partial_plist}",
        f"--compile={temporary_dir}",
        str(source_dir / "Assets.xcassets"),
        str(source_dir / "AppIcon.icon"),
    )
    try:
        result = subprocess.run(command, check=False, capture_output=True)
    except OSError as error:
        raise IconBuildError(f"could not run {command[0]}: {error}") from error
    try:
        messages = plistlib.loads(result.stdout)
    except plistlib.InvalidFileException as error:
        stderr = result.stderr.decode(errors="replace").strip()
        raise IconBuildError(
            f"actool returned invalid output"
            f"{f': {stderr}' if stderr else ''}"
        ) from error
    problems = []
    if result.returncode:
        problems.append(f"return code: {result.returncode}")
    for key in (
        "com.apple.actool.errors",
        "com.apple.actool.document.errors",
        "com.apple.actool.warnings",
        "com.apple.actool.document.warnings",
        "com.apple.actool.notices",
        "com.apple.actool.document.notices",
    ):
        problems.extend(messages.get(key) or ())
    stderr = result.stderr.decode(errors="replace").strip()
    if stderr and problems:
        problems.append(f"stderr: {stderr}")
    if problems:
        raise IconBuildError(f"actool reported diagnostics: {problems}")
    if stderr:
        print(f"warning: actool wrote to stderr: {stderr}", file=sys.stderr)

    generated = temporary_dir / "Assets.car"
    if not generated.is_file():
        raise IconBuildError("actool did not generate Assets.car")
    return generated


def read_deployment_target(chromium_src: Path) -> str:
    config = chromium_src / "build/config/mac/mac_sdk.gni"
    try:
        contents = config.read_text(encoding="utf-8")
    except OSError as error:
        raise IconBuildError(f"could not read {config}: {error}") from error
    matches = re.findall(
        r'^\s*mac_deployment_target\s*=\s*"([^"]+)"(?:\s*#.*)?$',
        contents,
        re.MULTILINE,
    )
    if len(matches) != 1:
        raise IconBuildError(
            f"could not determine mac_deployment_target from {config}"
        )
    return validate_deployment_target(matches[0])


def validate_deployment_target(value: str) -> str:
    if not VERSION_PATTERN.fullmatch(value):
        raise IconBuildError(f"invalid minimum deployment target: {value!r}")
    return value


def validate_document_badges(repo_root: Path, source_dir: Path) -> tuple[Path, ...]:
    pairs = (
        (
            repo_root / "logos/NEW/product_logo_256.png",
            source_dir / "Assets.xcassets/Icon.iconset/icon_256x256.png",
        ),
        (
            repo_root / "logos/NEW/product_logo_512.png",
            source_dir / "Assets.xcassets/Icon.iconset/icon_256x256@2x.png",
        ),
    )
    missing = [str(path) for pair in pairs for path in pair if not path.is_file()]
    if missing:
        raise IconBuildError(f"missing document badge input: {', '.join(missing)}")
    mismatched = [
        str(catalog)
        for source, catalog in pairs
        if not filecmp.cmp(source, catalog, shallow=False)
    ]
    if mismatched:
        raise IconBuildError(
            "document badge catalog inputs are not synchronized with "
            f"Thorium product logos: {', '.join(mismatched)}"
        )
    return tuple(catalog for _, catalog in pairs)


def write_transaction(path: Path, transaction: dict[str, object]) -> None:
    temporary = path.with_name(f"{path.name}.new")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(transaction, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise IconBuildError(f"could not write transaction {path}: {error}") from error


def transaction_entries(
    transaction: dict[str, object], directory: Path
) -> list[tuple[Path, Path, Path, bool]]:
    raw_entries = transaction.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise IconBuildError("invalid icon transaction entries")
    entries = []
    output_names = set()
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise IconBuildError("invalid icon transaction entry")
        names = tuple(raw_entry.get(key) for key in ("output", "stage", "backup"))
        existed = raw_entry.get("existed")
        if (
            any(
                not isinstance(name, str)
                or name in (".", "..")
                or Path(name).parts != (name,)
                for name in names
            )
            or not isinstance(existed, bool)
        ):
            raise IconBuildError("unsafe icon transaction entry")
        if names[0] in output_names:
            raise IconBuildError("duplicate icon transaction output")
        output_names.add(names[0])
        entries.append(
            (directory / names[0], directory / names[1], directory / names[2], existed)
        )
    return entries


def recover_transaction(path: Path) -> None:
    if not path.exists():
        return
    try:
        transaction = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IconBuildError(f"could not read transaction {path}: {error}") from error
    if not isinstance(transaction, dict):
        raise IconBuildError(f"invalid transaction document: {path}")
    phase = transaction.get("phase")
    if phase not in ("prepared", "backed-up", "published"):
        raise IconBuildError(f"invalid transaction phase in {path}: {phase!r}")
    entries = transaction_entries(transaction, path.parent)

    errors = []
    if phase == "published":
        missing_outputs = [
            str(output) for output, _, _, _ in entries if not output.is_file()
        ]
        if missing_outputs:
            can_roll_back = all(
                not existed or backup.is_file()
                for _, _, backup, existed in entries
            )
            if not can_roll_back:
                raise IconBuildError(
                    "published icon transaction is incomplete and cannot be "
                    f"safely rolled back; missing outputs: {missing_outputs}"
                )
            for output, stage, backup, existed in reversed(entries):
                try:
                    stage.unlink(missing_ok=True)
                    output.unlink(missing_ok=True)
                    if existed:
                        backup.replace(output)
                    else:
                        backup.unlink(missing_ok=True)
                except OSError as error:
                    errors.append(str(error))
        else:
            for _, stage, backup, _ in entries:
                for temporary in (stage, backup):
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError as error:
                        errors.append(str(error))
    else:
        for output, stage, backup, existed in reversed(entries):
            try:
                stage.unlink(missing_ok=True)
                if backup.exists():
                    output.unlink(missing_ok=True)
                    backup.replace(output)
                elif not existed:
                    output.unlink(missing_ok=True)
                elif not output.exists():
                    errors.append(f"missing original and backup for {output}")
            except OSError as error:
                errors.append(str(error))
    if errors:
        raise IconBuildError(f"could not recover icon transaction: {errors}")
    try:
        path.unlink()
    except OSError as error:
        raise IconBuildError(f"could not remove transaction {path}: {error}") from error


def publish_outputs(generated: dict[Path, Path]) -> None:
    directories = {output.parent for output in generated}
    if len(directories) != 1:
        raise IconBuildError("icon outputs must share one directory")
    directory = directories.pop()
    journal = directory / TRANSACTION_FILE
    recover_transaction(journal)

    entries = []
    try:
        for output, source in generated.items():
            stage = output.with_name(f"{output.name}.new")
            backup = output.with_name(f"{output.name}.previous")
            if backup.exists():
                raise IconBuildError(
                    f"orphaned backup without transaction: {backup}"
                )
            stage.unlink(missing_ok=True)
            shutil.copy2(source, stage)
            entries.append((output, stage, backup, output.exists()))
    except (OSError, IconBuildError):
        for _, stage, _, _ in entries:
            stage.unlink(missing_ok=True)
        raise

    transaction: dict[str, object] = {
        "phase": "prepared",
        "entries": [
            {
                "output": output.name,
                "stage": stage.name,
                "backup": backup.name,
                "existed": existed,
            }
            for output, stage, backup, existed in entries
        ],
    }
    write_transaction(journal, transaction)
    try:
        for output, _, backup, existed in entries:
            if existed:
                output.replace(backup)
        transaction["phase"] = "backed-up"
        write_transaction(journal, transaction)
        for output, stage, _, _ in entries:
            stage.replace(output)
        transaction["phase"] = "published"
        write_transaction(journal, transaction)
    except (OSError, IconBuildError) as error:
        try:
            recover_transaction(journal)
        except IconBuildError as recovery_error:
            raise IconBuildError(
                f"could not publish icon resources: {error}; {recovery_error}"
            ) from error
        raise IconBuildError(f"could not publish icon resources: {error}") from error

    try:
        recover_transaction(journal)
    except IconBuildError as error:
        print(f"warning: generated resources are valid, but {error}", file=sys.stderr)


def build(
    repo_root: Path, chromium_src: Path, minimum_deployment_target: str | None
) -> tuple[Path, Path]:
    if platform.system() != "Darwin":
        raise IconBuildError("macOS is required to run Xcode asset tools")

    xcrun = require_tool("xcrun")
    iconutil = require_tool("iconutil")
    rsvg_convert = require_tool("rsvg-convert")
    magick = require_tool("magick")
    check_actool(xcrun)

    source_dir = repo_root / "src/chrome/app/theme/chromium/mac"
    with icon_build_lock(source_dir / LOCK_FILE):
        output_car = source_dir / "Assets.car"
        output_icns = source_dir / "app.icns"
        icon_document = source_dir / "AppIcon.icon/icon.json"
        layer_sources = read_icon_layers(icon_document)
        document_badges = validate_document_badges(repo_root, source_dir)
        required = (
            icon_document,
            source_dir / "Assets.xcassets/Contents.json",
            *document_badges,
            *layer_sources,
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise IconBuildError(f"missing input: {', '.join(missing)}")
        deployment_target = (
            validate_deployment_target(minimum_deployment_target)
            if minimum_deployment_target
            else read_deployment_target(chromium_src)
        )

        with tempfile.TemporaryDirectory(prefix="thorium-mac-icon-") as temporary:
            temporary_dir = Path(temporary)
            generated_car = compile_assets(
                xcrun, source_dir, temporary_dir, deployment_target
            )

            iconset = temporary_dir / "Thorium.iconset"
            render_iconset(rsvg_convert, magick, layer_sources, iconset)
            generated_icns = temporary_dir / "app.icns"
            run(
                (iconutil, "-c", "icns", "-o", str(generated_icns), str(iconset))
            )
            if not generated_icns.is_file():
                raise IconBuildError("iconutil did not generate app.icns")
            publish_outputs(
                {output_car: generated_car, output_icns: generated_icns}
            )

    return output_car, output_icns


def default_chromium_src() -> Path:
    configured = os.environ.get("CR_DIR")
    if configured:
        return Path(os.path.expandvars(configured)).expanduser()
    return Path.home() / "chromium" / "src"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[4],
        help="Thorium repository root (default: inferred from this script)",
    )
    parser.add_argument(
        "--chromium-src",
        type=Path,
        default=default_chromium_src(),
        help=(
            "Chromium src directory used to read mac_sdk.gni "
            "(default: CR_DIR or ~/chromium/src)"
        ),
    )
    parser.add_argument(
        "--minimum-deployment-target",
        metavar="VERSION",
        help="override mac_deployment_target instead of reading Chromium sources",
    )
    return parser.parse_args()


def main() -> int:
    if sys.version_info < MINIMUM_PYTHON:
        print("error: Python 3.11 or newer is required", file=sys.stderr)
        return 2
    args = parse_args()
    try:
        outputs = build(
            args.repo_root.resolve(),
            args.chromium_src.expanduser().resolve(),
            args.minimum_deployment_target,
        )
    except (IconBuildError, OSError) as error:
        print(f"{Path(sys.argv[0]).name}: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"\n{Path(sys.argv[0]).name}: interrupted", file=sys.stderr)
        return 130

    for output in outputs:
        print(f"Generated: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
