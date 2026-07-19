#!/usr/bin/env python3

# Copyright (c) 2026 Alex313031 and gz83.

"""Remove the Thorium build output and downloaded Chromium PGO profiles."""

import argparse
import os
from pathlib import Path
import platform
import shutil
import stat
import sys
from typing import Sequence


EXIT_FAILURE = 111


class CleanError(RuntimeError):
    """An expected build cleanup failure."""


def environment_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def default_chromium_src() -> Path:
    configured = os.environ.get("CR_DIR")
    if configured:
        return environment_path(configured)
    if os.name == "nt":
        return Path("C:/src/chromium/src")
    return Path.home() / "chromium" / "src"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Delete out/thorium and downloaded Chromium PGO profile files."
        ),
        epilog="This cleanup cannot be undone.",
    )
    parser.add_argument(
        "--chromium-src",
        type=environment_path,
        default=default_chromium_src(),
        metavar="PATH",
        help="Chromium src directory (default: CR_DIR or the platform default)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the files that would be removed without changing anything",
    )
    return parser.parse_args(argv)


def require_chromium_checkout(chromium_src: Path) -> None:
    if not chromium_src.is_dir() or not (chromium_src / ".git").exists():
        raise CleanError(f"Chromium source is not a Git checkout: {chromium_src}")
    if not (chromium_src / "BUILD.gn").is_file():
        raise CleanError(f"Chromium root BUILD.gn does not exist: {chromium_src}")


def remove_readonly(function, path: str, error_info) -> None:
    """Retry removal after making a read-only path writable."""
    del error_info
    os.chmod(path, 0o700)
    function(path)


def is_windows_reparse_point(path: Path) -> bool:
    try:
        attributes = path.stat(follow_symlinks=False).st_file_attributes
    except AttributeError:
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def validate_removable_directory(path: Path, description: str) -> None:
    if (
        path.is_symlink()
        or os.path.ismount(path)
        or is_windows_reparse_point(path)
    ):
        raise CleanError(f"refusing to clean linked or mounted {description}: {path}")
    if not path.is_dir():
        raise CleanError(f"{description} is not a directory: {path}")


def validate_output(output: Path) -> bool:
    if not os.path.lexists(output):
        return False
    validate_removable_directory(output, "build output")
    return True


def inspect_pgo_profiles(profile_directory: Path) -> tuple[Path, ...]:
    if not os.path.lexists(profile_directory):
        return ()
    validate_removable_directory(profile_directory, "PGO profile directory")

    files = []
    for path in sorted(profile_directory.iterdir()):
        if (path.is_symlink() or path.is_file()) and path.suffix == ".profdata":
            files.append(path)
        elif path.is_symlink() or path.is_file():
            print(f"Preserving non-profile file: {path}")
        elif path.is_dir():
            print(f"Preserving unexpected PGO subdirectory: {path}")
        else:
            raise CleanError(f"unrecognized PGO profile entry: {path}")
    return tuple(files)


def remove_output(output: Path, *, dry_run: bool) -> None:
    print(f"Removing Thorium build output: {output}")
    if not dry_run:
        shutil.rmtree(output, onerror=remove_readonly)


def remove_pgo_profiles(profile_files: tuple[Path, ...], *, dry_run: bool) -> None:
    for path in profile_files:
        print(f"Removing Chromium PGO profile: {path}")
        if not dry_run:
            try:
                path.unlink()
            except PermissionError:
                path.chmod(0o600)
                path.unlink()


def clean(chromium_src: Path, *, dry_run: bool) -> None:
    chromium_src = chromium_src.expanduser().resolve()
    require_chromium_checkout(chromium_src)

    output = chromium_src / "out" / "thorium"
    profile_directory = chromium_src / "chrome" / "build" / "pgo_profiles"
    output_present = validate_output(output)
    profile_files = inspect_pgo_profiles(profile_directory)

    if output_present:
        remove_output(output, dry_run=dry_run)
    remove_pgo_profiles(profile_files, dry_run=dry_run)

    if dry_run:
        print("\nDry run completed; no files were changed.")
    elif output_present or profile_files:
        print("\nDone cleaning Thorium build output and PGO profiles.")
    else:
        print("\nNothing needed to be cleaned.")


def main(argv: Sequence[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print("error: Python 3.11 or newer is required", file=sys.stderr)
        return 2
    if platform.system() not in ("Linux", "Darwin", "Windows"):
        print("error: only Linux, macOS, and Windows are supported", file=sys.stderr)
        return 2

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        clean(args.chromium_src, dry_run=args.dry_run)
    except (CleanError, OSError) as error:
        print(f"{Path(sys.argv[0]).name}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    except KeyboardInterrupt:
        print(f"\n{Path(sys.argv[0]).name}: interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
