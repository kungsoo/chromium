#!/usr/bin/env python3

# Copyright (c) 2026 Alex313031 and gz83.

"""Download repositories and prepare a shallow Chromium checkout for Thorium."""

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

from trunk import CHROMIUM_NESTED_CHECKOUTS


DEPOT_TOOLS_URL = (
    "https://chromium.googlesource.com/chromium/tools/depot_tools.git"
)

THORIUM_URL = (
    "https://github.com/Alex313031/thorium.git"
)

CHROMIUM_URL = (
    "https://chromium.googlesource.com/chromium/src.git"
)

THORIUM_VERSION = "150.0.7871.179"

EXIT_FAILURE = 111


class BootstrapError(RuntimeError):
    """Expected bootstrap failure."""


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
        description=(
            "Download depot_tools, Thorium and shallow Chromium."
        )
    )

    parser.add_argument(
        "--chromium-src",
        type=environment_path,
        default=default_chromium_src(),
    )

    parser.add_argument(
        "--thorium-root",
        type=environment_path,
        default=default_thorium_root(),
    )

    parser.add_argument(
        "--depot-tools",
        type=environment_path,
        default=default_depot_tools(),
    )

    parser.add_argument(
        "--skip-build-deps",
        action="store_true",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
    )

    return parser.parse_args(argv)



def find_command(name: str) -> str:

    command = shutil.which(name)

    if command is None:
        raise BootstrapError(
            f"command not found: {name}"
        )

    return command



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

    except subprocess.CalledProcessError as error:
        raise BootstrapError(
            f"command failed: {printable}"
        ) from error



def require_checkout(
    path: Path,
    description: str,
) -> None:

    if not path.is_dir():
        raise BootstrapError(
            f"{description} missing: {path}"
        )

    if not (path / ".git").exists():
        raise BootstrapError(
            f"{description} is not git checkout: {path}"
        )



def depot_command(
    depot_tools: Path,
    name: str,
) -> Path:

    suffix = ".bat" if os.name == "nt" else ""

    command = depot_tools / f"{name}{suffix}"

    if not command.exists():
        raise BootstrapError(
            f"missing depot command: {command}"
        )

    return command



def remove_readonly(
    function,
    path,
    error_info,
):
    del error_info

    os.chmod(
        path,
        stat.S_IWRITE,
    )

    function(path)



def remove_tree(path: Path):

    if not path.exists():
        return

    shutil.rmtree(
        path,
        onerror=remove_readonly,
    )



def clone_repository(
    git: str,
    url: str,
    destination: Path,
    *,
    recursive=False,
):

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if destination.exists():
        return


    command = [
        git,
        "clone",
    ]

    if recursive:
        command.append(
            "--recursive"
        )


    command.extend(
        [
            url,
            str(destination),
        ]
    )


    run(
        command,
        destination.parent,
    )



def prepare_depot_tools(
    git: str,
    depot_tools: Path,
):

    if depot_tools.exists():

        require_checkout(
            depot_tools,
            "depot_tools",
        )

        return


    clone_repository(
        git,
        DEPOT_TOOLS_URL,
        depot_tools,
    )



def prepare_thorium(
    git: str,
    thorium_root: Path,
):

    if thorium_root.exists():

        require_checkout(
            thorium_root,
            "Thorium",
        )

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
        recursive=True,
    )



def prepare_chromium_clone(
    git: str,
    chromium_src: Path,
):

    if chromium_src.exists():

        require_checkout(
            chromium_src,
            "Chromium",
        )

        print(
            f"\nUsing Chromium checkout: {chromium_src}"
        )

        return


    chromium_src.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    print(
        f"\nCloning Chromium tag {THORIUM_VERSION}"
    )


    run(
        [
            git,
            "clone",
            "--depth=1",
            "--branch",
            f"refs/tags/{THORIUM_VERSION}",
            CHROMIUM_URL,
            str(chromium_src),
        ],
        chromium_src.parent,
    )


    require_checkout(
        chromium_src,
        "Chromium",
    )

def prepare_gclient(
    depot_tools: Path,
    chromium_src: Path,
):

    gclient = str(
        depot_command(
            depot_tools,
            "gclient",
        )
    )

    gclient_file = chromium_src.parent / ".gclient"

    if gclient_file.exists():
        return


    print("\nCreating .gclient")


    run(
        [
            gclient,
            "config",
            "--name",
            "src",
            CHROMIUM_URL,
        ],
        chromium_src.parent,
    )



def chromium_required_checkouts_exist(
    chromium_src: Path,
) -> bool:

    if not (chromium_src.parent / ".gclient").exists():
        return False


    if not (chromium_src / ".git").exists():
        return False


    return all(
        (
            chromium_src / relative_path / ".git"
        ).exists()

        for relative_path, _ in CHROMIUM_NESTED_CHECKOUTS
    )



def sync_chromium(
    depot_tools: Path,
    chromium_src: Path,
):

    gclient = str(
        depot_command(
            depot_tools,
            "gclient",
        )
    )


    print(
        "\nSync Chromium dependencies"
    )


    run(
        [
            gclient,
            "sync",
            "--force",
            "--reset",
            "--nohooks",
            "--no-history",
            "--delete_unversioned_trees",
            "--revision",
            f"src@{THORIUM_VERSION}",
        ],
        chromium_src.parent,
    )


    if not chromium_required_checkouts_exist(
        chromium_src
    ):

        raise BootstrapError(
            "Chromium nested checkouts missing after sync"
        )



def install_linux_dependencies(
    chromium_src: Path,
    skip: bool,
):

    if skip:
        print(
            "\nSkipping build dependencies"
        )
        return


    if platform.system() != "Linux":
        return


    installer = (
        chromium_src
        / "build"
        / "install-build-deps.sh"
    )


    if not installer.exists():

        raise BootstrapError(
            f"missing dependency installer: {installer}"
        )


    run(
        [
            str(installer),
            "--arm",
            "--chromeos-fonts",
        ],
        chromium_src,
    )



def run_hooks(
    depot_tools: Path,
    chromium_src: Path,
):

    gclient = str(
        depot_command(
            depot_tools,
            "gclient",
        )
    )


    print(
        "\nRunning Chromium hooks"
    )


    run(
        [
            gclient,
            "runhooks",
        ],
        chromium_src,
    )



def bootstrap(
    args: argparse.Namespace,
):

    if os.name != "nt":
        os.umask(0o022)


    git = find_command(
        "git"
    )


    prepare_depot_tools(
        git,
        args.depot_tools,
    )


    prepare_thorium(
        git,
        args.thorium_root,
    )


    os.environ["DEPOT_TOOLS_DIR"] = str(
        args.depot_tools
    )

    os.environ["PATH"] = (
        str(args.depot_tools)
        + os.pathsep
        + os.environ.get("PATH", "")
    )


    prepare_chromium_clone(
        git,
        args.chromium_src,
    )


    prepare_gclient(
        args.depot_tools,
        args.chromium_src,
    )


    sync_chromium(
        args.depot_tools,
        args.chromium_src,
    )


    install_linux_dependencies(
        args.chromium_src,
        args.skip_build_deps,
    )


    run_hooks(
        args.depot_tools,
        args.chromium_src,
    )


    print(
        "\nBootstrap completed."
    )

    print(
        f"Chromium: {args.chromium_src}"
    )

    print(
        f"Thorium: {args.thorium_root}"
    )

    print(
        f"depot_tools: {args.depot_tools}"
    )



def validate_paths(
    chromium_src: Path,
    thorium_root: Path,
    depot_tools: Path,
):

    paths = [
        chromium_src.parent,
        thorium_root,
        depot_tools,
    ]


    for i, left in enumerate(paths):

        for right in paths[i + 1:]:

            if (
                left == right
                or left.is_relative_to(right)
                or right.is_relative_to(left)
            ):

                raise BootstrapError(
                    f"checkout paths overlap: {left} {right}"
                )



def main(
    argv: Sequence[str] | None = None,
):

    if sys.version_info < (3,11):

        print(
            "Python 3.11+ required",
            file=sys.stderr,
        )

        return 2


    args = parse_args(
        sys.argv[1:]
        if argv is None
        else argv
    )


    args.chromium_src = (
        args.chromium_src
        .expanduser()
        .resolve()
    )

    args.thorium_root = (
        args.thorium_root
        .expanduser()
        .resolve()
    )

    args.depot_tools = (
        args.depot_tools
        .expanduser()
        .resolve()
    )


    try:

        validate_paths(
            args.chromium_src,
            args.thorium_root,
            args.depot_tools,
        )


        bootstrap(
            args
        )


    except BootstrapError as error:

        print(
            f"{Path(sys.argv[0]).name}: {error}",
            file=sys.stderr,
        )

        return EXIT_FAILURE


    except KeyboardInterrupt:

        print(
            "\nInterrupted",
            file=sys.stderr,
        )

        return 130


    return 0



if __name__ == "__main__":

    raise SystemExit(
        main()
    )
