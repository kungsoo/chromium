#!/usr/bin/env python3

# Copyright (c) 2026 Alex313031 and gz83.

"""Download the repositories needed to build Thorium.

This script only bootstraps:
- depot_tools
- Thorium source
- Chromium source (shallow fetch only)

Chromium version checkout, gclient sync, hooks,
sysroots and PGO profiles are handled by version.py.
"""

import argparse
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import time
from typing import Sequence


DEPOT_TOOLS_URL = "https://chromium.googlesource.com/chromium/tools/depot_tools.git"

THORIUM_URL = "https://github.com/kungsoo/chromium.git"

EXIT_FAILURE = 111

FETCH_INCOMPLETE_MARKER = ".thorium-fetch-incomplete"


class BootstrapError(RuntimeError):
    """An expected repository bootstrap failure."""


def environment_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def default_chromium_src() -> Path:
    configured = os.environ.get("CR_DIR")

    if configured:
        return environment_path(configured)

    if os.name == "nt":
        return Path("C:/src/chromium/src")

    return Path.home() / "chromium" / "src"


def default_thorium_root() -> Path:
    configured = os.environ.get("THOR_DIR")

    if configured:
        return environment_path(configured)

    return Path.home() / "thorium"


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


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Download depot_tools, Thorium and Chromium source.")
    )

    parser.add_argument(
        "--chromium-src",
        type=environment_path,
        default=default_chromium_src(),
        metavar="PATH",
        help=("Chromium src directory " "(default: CR_DIR or platform default)"),
    )

    parser.add_argument(
        "--thorium-root",
        type=environment_path,
        default=default_thorium_root(),
        metavar="PATH",
        help=("Thorium checkout directory " "(default: THOR_DIR or ~/thorium)"),
    )

    parser.add_argument(
        "--depot-tools",
        type=environment_path,
        default=default_depot_tools(),
        metavar="PATH",
        help=("depot_tools checkout directory"),
    )

    parser.add_argument(
        "--no-history",
        action="store_true",
        default=True,
        help=("fetch Chromium without full Git history"),
    )

    parser.add_argument(
        "--skip-build-deps",
        action="store_true",
        help=("do not install Linux build dependencies"),
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help=("skip interactive confirmation"),
    )

    return parser.parse_args(argv)


def find_command(name: str) -> str:
    executable = shutil.which(name)

    if executable is None:
        raise BootstrapError(f"required command was not found: {name}")

    return executable


def run(
    command: Sequence[str],
    cwd: Path,
) -> None:

    printable = subprocess.list2cmdline(command)

    print(
        f"\n[{cwd}] {printable}",
        flush=True,
    )

    try:
        subprocess.run(
            command,
            cwd=cwd,
            check=True,
        )

    except OSError as error:
        raise BootstrapError(f"could not run {printable}: {error}") from error

    except subprocess.CalledProcessError as error:
        raise BootstrapError(
            f"command failed with exit code " f"{error.returncode}: {printable}"
        ) from error


def require_checkout(
    path: Path,
    description: str,
) -> None:

    if not path.is_dir():
        raise BootstrapError(f"{description} directory missing: {path}")

    if not (path / ".git").exists():
        raise BootstrapError(f"{description} is not a Git checkout: {path}")


def remove_readonly(function, path: str, error_info) -> None:
    """Retry removal after making Windows read-only path writable."""
    del error_info

    os.chmod(
        path,
        stat.S_IWRITE,
    )

    function(path)


def remove_incomplete_checkout(
    path: Path | None,
) -> str | None:

    if path is None:
        return None

    if not os.path.lexists(path):
        return None

    try:
        if path.is_symlink() or path.is_file():
            path.unlink()

        else:
            shutil.rmtree(
                path,
                onerror=remove_readonly,
            )

    except OSError as error:
        return f"could not remove incomplete checkout " f"{path}: {error}"

    return None


def clone_repository(
    git: str,
    url: str,
    destination: Path,
    *,
    description: str,
    marker: str | None = None,
    recursive: bool = False,
) -> None:

    staging = None

    try:
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        timestamp = time.strftime("%Y%m%d-%H%M%S")

        staging = destination.with_name(f"{destination.name}.new-{timestamp}")

        index = 1

        while os.path.lexists(staging):
            staging = destination.with_name(
                f"{destination.name}.new-{timestamp}-{index}"
            )
            index += 1

        command = [
            git,
            "clone",
        ]

        if recursive:
            command.append("--recursive")

        command.extend(
            [
                url,
                str(staging),
            ]
        )

        run(
            command,
            destination.parent,
        )

        require_checkout(
            staging,
            description,
        )

        if marker:
            if not (staging / marker).exists():
                raise BootstrapError(f"{description} missing {marker}")

        staging.rename(destination)

    except (
        BootstrapError,
        KeyboardInterrupt,
        OSError,
    ) as error:

        cleanup_error = remove_incomplete_checkout(staging)

        message = str(error)

        if cleanup_error:
            message += f"; {cleanup_error}"

        raise BootstrapError(message) from error


def prepare_depot_tools(
    git: str,
    depot_tools: Path,
) -> None:

    if depot_tools.exists():

        require_checkout(
            depot_tools,
            "depot_tools",
        )

        print(f"\nUsing existing depot_tools: " f"{depot_tools}")

        return

    clone_repository(
        git,
        DEPOT_TOOLS_URL,
        depot_tools,
        description="depot_tools",
        marker="gclient.py",
    )


def prepare_thorium(
    git: str,
    thorium_root: Path,
) -> None:

    if thorium_root.exists():

        require_checkout(
            thorium_root,
            "Thorium",
        )

        print(f"\nUsing existing Thorium: " f"{thorium_root}")

        run(
            [
                git,
                "submodule",
                "update",
                "--init",
                "--recursive",
            ],
            thorium_root,
        )

        return

    clone_repository(
        git,
        THORIUM_URL,
        thorium_root,
        description="Thorium",
        marker="trunk.py",
        recursive=True,
    )


def depot_command(
    depot_tools: Path,
    name: str,
) -> Path:

    suffix = ".bat" if os.name == "nt" else ""

    command = depot_tools / f"{name}{suffix}"

    if not command.is_file():
        raise BootstrapError(f"depot_tools command missing: {command}")

    return command


def chromium_checkout_state(
    chromium_src: Path,
) -> str:

    if not chromium_src.exists():
        return "absent"

    if chromium_src.is_dir() and (chromium_src / ".git").exists():
        return "existing"

    return "incomplete"


def prepare_chromium(
    chromium_src: Path,
    depot_tools: Path,
    *,
    no_history: bool,
) -> str:

    state = chromium_checkout_state(chromium_src)

    if state == "existing":

        print(f"\nUsing existing Chromium checkout: " f"{chromium_src}")

        return "existing"

    if state == "incomplete":

        raise BootstrapError(f"incomplete Chromium checkout: " f"{chromium_src}")

    if chromium_src.name != "src":

        raise BootstrapError("Chromium path must end with src: " f"{chromium_src}")

    checkout_root = chromium_src.parent

    checkout_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = [
        str(
            depot_command(
                depot_tools,
                "fetch",
            )
        ),
        "--nohooks",
    ]

    if no_history:
        command.append("--no-history")

    command.append("chromium")

    print("\nFetching Chromium source only.")

    print("Checkout, sync and hooks are handled by version.py.")

    run(
        command,
        checkout_root,
    )

    require_checkout(
        chromium_src,
        "Chromium",
    )

    print("\nChromium fetch completed.")

    return "new"


def install_linux_dependencies(
    chromium_src: Path,
    *,
    skip: bool,
) -> None:

    if skip:
        print("\nSkipping Linux build dependencies.")
        return

    if platform.system() != "Linux":

        print("\nSkipping Linux dependencies on non-Linux host.")

        return

    find_command("sudo")

    installer = chromium_src / "build" / "install-build-deps.sh"

    if not installer.is_file():

        raise BootstrapError(f"Chromium dependency installer missing: " f"{installer}")

    print("\nInstalling Linux build dependencies.")

    run(
        [
            str(installer),
            "--arm",
            "--chromeos-fonts",
        ],
        chromium_src,
    )


def validate_paths(
    chromium_src: Path,
    thorium_root: Path,
    depot_tools: Path,
) -> None:

    paths = (
        ("Chromium", chromium_src.parent),
        ("Thorium", thorium_root),
        ("depot_tools", depot_tools),
    )

    for index, (left_name, left_path) in enumerate(paths):

        for right_name, right_path in paths[index + 1 :]:

            if left_path.is_relative_to(right_path) or right_path.is_relative_to(
                left_path
            ):

                raise BootstrapError(
                    f"checkout paths overlap: "
                    f"{left_name}={left_path}, "
                    f"{right_name}={right_path}"
                )


def resolve_paths(
    args: argparse.Namespace,
) -> None:

    args.chromium_src = args.chromium_src.expanduser().resolve()

    args.thorium_root = args.thorium_root.expanduser().resolve()

    args.depot_tools = args.depot_tools.expanduser().resolve()

    validate_paths(
        args.chromium_src,
        args.thorium_root,
        args.depot_tools,
    )


def confirm(
    args: argparse.Namespace,
) -> None:

    if args.yes:
        return

    if not sys.stdin.isatty():

        raise BootstrapError("interactive confirmation unavailable; " "use --yes")

    print("\nThis will download:")

    print(f"  depot_tools: {args.depot_tools}")

    print(f"  Thorium:     {args.thorium_root}")

    print(f"  Chromium:    {args.chromium_src}")

    input("Press Enter to continue...")


def bootstrap(
    args: argparse.Namespace,
) -> None:

    chromium_src = args.chromium_src
    thorium_root = args.thorium_root
    depot_tools = args.depot_tools

    if os.name != "nt":
        os.umask(0o022)

    git = find_command("git")

    prepare_depot_tools(
        git,
        depot_tools,
    )

    prepare_thorium(
        git,
        thorium_root,
    )

    os.environ["DEPOT_TOOLS_DIR"] = str(depot_tools)

    os.environ["PATH"] = (
        str(depot_tools)
        + os.pathsep
        + os.environ.get(
            "PATH",
            "",
        )
    )

    chromium_state = prepare_chromium(
        chromium_src,
        depot_tools,
        no_history=args.no_history,
    )

    install_linux_dependencies(
        chromium_src,
        skip=args.skip_build_deps,
    )

    print("\nBootstrap completed.")

    print(f"Chromium source: {chromium_src}")

    print(f"Thorium source:  {thorium_root}")

    print(f"depot_tools:     {depot_tools}")

    print("\nNext step:")

    print(
        f"{sys.executable} "
        f"{thorium_root / 'version.py'} "
        f"--chromium-src={chromium_src} "
        f"--depot-tools={depot_tools}"
    )


def main(
    argv: Sequence[str] | None = None,
) -> int:

    if sys.version_info < (3, 11):

        print(
            "error: Python 3.11+ required",
            file=sys.stderr,
        )

        return 2

    if platform.system() not in (
        "Linux",
        "Darwin",
        "Windows",
    ):

        print(
            "error: unsupported platform",
            file=sys.stderr,
        )

        return 2

    args = parse_args(sys.argv[1:] if argv is None else argv)

    try:

        resolve_paths(args)

        confirm(args)

        bootstrap(args)

    except BootstrapError as error:

        print(
            f"{Path(sys.argv[0]).name}: {error}",
            file=sys.stderr,
        )

        return EXIT_FAILURE

    except OSError as error:

        print(
            f"{Path(sys.argv[0]).name}: filesystem error: {error}",
            file=sys.stderr,
        )

        return EXIT_FAILURE

    except KeyboardInterrupt:

        print(
            "\nInterrupted.",
            file=sys.stderr,
        )

        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
