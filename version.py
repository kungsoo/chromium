#!/usr/bin/env python3

# Copyright (c) 2026 Alex313031 and gz83.

"""Install sysroots and download PGO profiles for the current Thorium version.

This step assumes `bootstrap.py` has already run: the Chromium checkout at
`--chromium-src` already exists, is already synced with gclient, and is
already pinned to the tag in THORIUM_VERSION. This script does not repeat
the fetch / checkout / clean / gclient sync / gclient runhooks steps --
those already happened in bootstrap.py, and re-running `gclient sync
--revision src@<tag>` here would hit the exact same "gclient does an
unbounded full-history fetch when given a tag name instead of a commit
SHA" issue that bootstrap.py works around (see resolve_pinned_commit()
there). Instead, this script does a fast, local, no-network check that the
checkout is where it should be, then moves on to the work bootstrap.py
doesn't do: sysroots and PGO profiles.
"""

import argparse
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence


EXIT_FAILURE = 111
THORIUM_VERSION = "150.0.7871.128"
PGO_GS_URL = "chromium-optimization-profiles/pgo_profiles"
PGO_TARGETS = (
    "win-arm64",
    "win32",
    "win64",
    "mac",
    "mac-arm",
    "linux",
)


class VersionError(RuntimeError):
    """An expected checkout or profile preparation failure."""


def environment_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def default_chromium_src() -> Path:
    configured = os.environ.get("CR_DIR")
    if configured:
        return environment_path(configured)
    if os.name == "nt":
        return Path("C:/src/chromium/src")
    return Path.home() / "chromium" / "src"


def default_depot_tools() -> Path:
    configured = os.environ.get("DEPOT_TOOLS_DIR")
    if configured:
        return environment_path(configured)
    gclient = shutil.which("gclient")
    if gclient:
        return Path(gclient).resolve().parent
    if os.name == "nt":
        return Path("C:/src/depot_tools")
    return Path.home() / "depot_tools"


def sysroot_architectures() -> tuple[str, ...]:
    return ("amd64", "arm64") if sys.platform.startswith("linux") else ()


def host_pgo_targets() -> tuple[str, ...]:
    system = platform.system()
    if system == "Linux":
        return ("linux",)
    if system == "Darwin":
        return ("mac", "mac-arm")
    if system == "Windows":
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            return ("win-arm64",)
        if machine in ("x86", "i386", "i686"):
            return ("win32",)
        if machine in ("amd64", "x86_64", "x64"):
            return ("win64",)
        raise VersionError(f"unsupported Windows architecture for PGO: {machine}")
    raise VersionError(f"unsupported host platform for Chromium PGO: {system}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Install sysroots and download PGO profiles for the Chromium "
            "checkout prepared by bootstrap.py."
        )
    )
    parser.add_argument(
        "--chromium-src",
        type=environment_path,
        default=default_chromium_src(),
        metavar="PATH",
        help="Chromium src directory (default: CR_DIR or the platform default)",
    )
    parser.add_argument(
        "--depot-tools",
        type=environment_path,
        default=default_depot_tools(),
        metavar="PATH",
        help=(
            "depot_tools directory (default: DEPOT_TOOLS_DIR, the gclient "
            "location, or the platform default)"
        ),
    )
    parser.add_argument(
        "--pgo-target",
        action="append",
        choices=PGO_TARGETS,
        dest="pgo_targets",
        help=(
            "Chromium PGO target to download; may be repeated. Defaults to "
            "the current host platform (both architectures on macOS)."
        ),
    )
    return parser.parse_args(argv)


def find_command(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise VersionError(
            f"required command '{name}' was not found in PATH; "
            "ensure depot_tools and Git are installed"
        )
    return executable


def run(command: Sequence[str], cwd: Path) -> None:
    printable = subprocess.list2cmdline(command)
    print(f"\n[{cwd}] {printable}", flush=True)
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except OSError as error:
        raise VersionError(f"could not run {printable}: {error}") from error
    except subprocess.CalledProcessError as error:
        raise VersionError(
            f"command failed with exit code {error.returncode}: {printable}"
        ) from error


def capture(command: Sequence[str], cwd: Path) -> str:
    printable = subprocess.list2cmdline(command)
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise VersionError(f"could not run {printable}: {error}") from error
    except subprocess.CalledProcessError as error:
        raise VersionError(
            f"command failed with exit code {error.returncode}: {printable}\n"
            f"{error.stderr}"
        ) from error
    return result.stdout


def require_directory(path: Path, description: str) -> None:
    if not path.is_dir():
        raise VersionError(f"{description} directory does not exist: {path}")


def require_checkout(path: Path, description: str) -> None:
    require_directory(path, description)
    if not (path / ".git").exists():
        raise VersionError(f"{description} is not a Git checkout: {path}")


def require_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise VersionError(f"{description} does not exist: {path}")


def verify_pinned_checkout(chromium_src: Path) -> None:
    """Fast, local, no-network check that bootstrap.py already put the
    checkout where this script expects it to be. This replaces the
    fetch/checkout/clean/gclient-sync steps the old version of this script
    used to repeat -- those are bootstrap.py's job."""

    git = find_command("git")

    head = capture(
        [git, "-c", "color.ui=never", "rev-parse", "HEAD"],
        chromium_src,
    ).strip().lower()

    try:
        pinned = capture(
            [
                git,
                "-c",
                "color.ui=never",
                "rev-parse",
                "--verify",
                f"{THORIUM_VERSION}^{{commit}}",
            ],
            chromium_src,
        ).strip().lower()
    except VersionError as error:
        raise VersionError(
            f"tag {THORIUM_VERSION} not found in {chromium_src}; "
            "run bootstrap.py first"
        ) from error

    if head != pinned:
        raise VersionError(
            f"{chromium_src} is checked out at {head}, not the pinned "
            f"Thorium tag {THORIUM_VERSION} ({pinned}); run bootstrap.py first"
        )


def prepare_pgo(
    chromium_src: Path,
    depot_tools: Path,
    pgo_targets: Sequence[str],
) -> None:
    chromium_src = chromium_src.expanduser().resolve()
    depot_tools = depot_tools.expanduser().resolve()

    os.environ["DEPOT_TOOLS_DIR"] = str(depot_tools)
    os.environ["PATH"] = str(depot_tools) + os.pathsep + os.environ.get("PATH", "")

    require_checkout(chromium_src, "Chromium")
    require_file(
        depot_tools / "download_from_google_storage.py",
        "depot_tools download_from_google_storage.py",
    )

    print(f"\nCurrent Thorium version is: {THORIUM_VERSION}\n")

    verify_pinned_checkout(chromium_src)

    sysroot_arches = sysroot_architectures()
    if sysroot_arches:
        print("\nInstalling Linux sysroots for AMD64 and ARM64", flush=True)
        sysroot_installer = (
            chromium_src / "build" / "linux" / "sysroot_scripts" / "install-sysroot.py"
        )
        require_file(sysroot_installer, "Linux sysroot installer")
        for architecture in sysroot_arches:
            run(
                [sys.executable, str(sysroot_installer), f"--arch={architecture}"],
                chromium_src,
            )
    else:
        print("\nSkipping Linux sysroots on non-Linux host")

    pgo_updater = chromium_src / "tools" / "update_pgo_profiles.py"
    require_file(pgo_updater, "Chromium PGO profile updater")
    print(f"\nDownloading Chromium PGO profiles: {', '.join(pgo_targets)}")
    for target in pgo_targets:
        run(
            [
                sys.executable,
                str(pgo_updater),
                f"--target={target}",
                "update",
                f"--gs-url-base={PGO_GS_URL}",
            ],
            chromium_src,
        )

    v8_pgo_downloader = (
        chromium_src / "v8" / "tools" / "builtins-pgo" / "download_profiles.py"
    )
    require_file(v8_pgo_downloader, "V8 builtins PGO profile downloader")
    print("\nDownloading V8 builtins PGO profiles")
    run(
        [
            sys.executable,
            str(v8_pgo_downloader),
            f"--depot-tools={depot_tools}",
            "--force",
            "download",
        ],
        chromium_src,
    )

    print(f"\nChromium tree is checked out at tag: {THORIUM_VERSION}")
    print("\nDone! You can now run 'setup.py'.")


def main(argv: Sequence[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print("error: Python 3.11 or newer is required", file=sys.stderr)
        return 2
    if platform.system() not in ("Linux", "Darwin", "Windows"):
        print("error: only Linux, macOS, and Windows are supported", file=sys.stderr)
        return 2

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        pgo_targets = list(dict.fromkeys(args.pgo_targets or host_pgo_targets()))
        prepare_pgo(
            args.chromium_src,
            args.depot_tools,
            pgo_targets,
        )
    except VersionError as error:
        print(f"{Path(sys.argv[0]).name}: {error}", file=sys.stderr)
        return EXIT_FAILURE
    except OSError as error:
        print(
            f"{Path(sys.argv[0]).name}: filesystem operation failed: {error}",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    except KeyboardInterrupt:
        print(f"\n{Path(sys.argv[0]).name}: interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
