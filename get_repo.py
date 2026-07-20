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



def run_capture(
    command: Sequence[str],
    cwd: Path,
) -> str:

    printable = subprocess.list2cmdline(command)

    print(
        f"\n[{cwd}] {printable}",
        flush=True,
    )

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )

    except subprocess.CalledProcessError as error:
        raise BootstrapError(
            f"command failed: {printable}"
        ) from error

    return result.stdout



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


    try:
        run(
            command,
            destination.parent,
        )

    except BootstrapError:

        # A failed clone can still leave behind a partial
        # directory (git creates it up front). Without cleanup, a retry
        # would see `destination.exists()` above and skip re-cloning,
        # getting stuck on a broken checkout instead.
        remove_tree(destination)

        raise



def prepare_depot_tools(
    git: str,
    depot_tools: Path,
):

    if depot_tools.exists():

        require_checkout(
            depot_tools,
            "depot_tools",
        )

    else:

        clone_repository(
            git,
            DEPOT_TOOLS_URL,
            depot_tools,
        )


    ensure_bootstrap = depot_tools / "ensure_bootstrap"

    if not ensure_bootstrap.exists():
        raise BootstrapError(
            f"missing bootstrap script: {ensure_bootstrap}"
        )


    run(
        [
            str(ensure_bootstrap),
        ],
        depot_tools,
    )


    python_bin = depot_tools / "python3_bin_reldir.txt"

    if not python_bin.exists():

        raise BootstrapError(
            "depot_tools bootstrap failed: "
            "python3_bin_reldir.txt missing"
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



def resolve_pinned_commit(
    git: str,
    chromium_src: Path,
    tag: str,
) -> str:
    # depot_tools' gclient_scm.py decides whether it can skip fetching
    # by calling scm.GIT.IsValidRevision(cwd, revision, sha_only=True),
    # which is implemented (in depot_tools/scm.py) as:
    #
    #     sha = GIT.ResolveCommit(cwd, rev)
    #     if sha is None:
    #         return False
    #     if sha_only:
    #         return sha == rev.lower()
    #
    # `sha_only=True` requires the *revision string itself* to already
    # be the full commit SHA -- resolving successfully isn't enough.
    # Passing a tag name (e.g. "150.0.7871.179") always fails this
    # comparison, even when the tag resolves locally to a commit that's
    # already present, so gclient falls through to an unconditional
    # `git fetch origin --prune --no-tags` to satisfy itself the
    # revision is reachable. On a repo the size of Chromium's src this
    # can take an hour or more and looks like gclient "hanging" on
    # "Still working on: src".
    #
    # Resolving the tag to its commit SHA ourselves and passing THAT to
    # `gclient sync --revision src@<sha>` lets IsValidRevision succeed
    # immediately (since the object is already present from the shallow
    # clone), so gclient skips the fetch entirely.
    commit = run_capture(
        [
            git,
            "-c",
            "color.ui=never",
            "rev-parse",
            "--verify",
            f"{tag}^{{commit}}",
        ],
        chromium_src,
    )

    return commit.strip().lower()



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


    # NOTE: `git clone --branch` expects a short ref name (branch or tag),
    # not a fully-qualified ref like "refs/tags/<tag>". Passing the fully
    # qualified form causes git to look for a *branch* literally named
    # "refs/tags/<tag>", which does not exist upstream and fails with:
    #   fatal: Remote branch refs/tags/<tag> not found in upstream origin
    # Passing the bare tag name lets git resolve it against both branches
    # and tags on the remote.
    try:
        run(
            [
                git,
                "clone",
                "--depth=1",
                "--branch",
                THORIUM_VERSION,
                CHROMIUM_URL,
                str(chromium_src),
            ],
            chromium_src.parent,
        )

    except BootstrapError:

        # Same rationale as clone_repository(): don't leave a partial
        # checkout behind, or a retry will think it's already done.
        remove_tree(chromium_src)

        raise


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

        content = gclient_file.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        # A stale .gclient from a prior run pointed at a different
        # solution/URL would otherwise be silently reused, causing
        # `gclient sync` to sync the wrong repo (or fail confusingly).
        if CHROMIUM_URL not in content or '"src"' not in content:

            raise BootstrapError(
                f".gclient exists but does not match expected "
                f"config (name=src, url={CHROMIUM_URL}): {gclient_file}\n"
                "Remove it and retry to regenerate."
            )

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
    pinned_commit: str,
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


    try:
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
                f"src@{pinned_commit}",
            ],
            chromium_src.parent,
        )

    except BootstrapError as error:

        # Unlike a fresh clone, a partially-synced tree already
        # represents real work (many DEPS entries fetched). Don't
        # auto-delete it; just surface actionable guidance.
        raise BootstrapError(
            f"{error}\n"
            "Partial sync left in place; re-run with "
            "'gclient sync -v -v ...' to see which entry stalled, "
            "or delete the affected sub-checkout and retry."
        ) from error


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


    # NOTE: DEPOT_TOOLS_DIR / PATH must be set *before*
    # prepare_depot_tools() runs, not after. prepare_depot_tools()
    # invokes depot_tools/ensure_bootstrap, which shells out through
    # gsutil.py -> luci-auth. depot_tools only resolves the
    # `luci-auth` executable correctly once depot_tools itself is on
    # PATH, so doing this afterwards (as in the original ordering)
    # causes ensure_bootstrap to fail with a subprocess lookup error
    # for luci-auth. It's safe to add depot_tools to PATH here even
    # before it's cloned -- it's just an inert entry until
    # prepare_depot_tools() populates the directory.
    os.environ["DEPOT_TOOLS_DIR"] = str(
        args.depot_tools
    )

    os.environ["PATH"] = (
        str(args.depot_tools)
        + os.pathsep
        + os.environ.get("PATH", "")
    )


    prepare_depot_tools(
        git,
        args.depot_tools,
    )


    prepare_thorium(
        git,
        args.thorium_root,
    )


    prepare_chromium_clone(
        git,
        args.chromium_src,
    )


    pinned_commit = resolve_pinned_commit(
        git,
        args.chromium_src,
        THORIUM_VERSION,
    )


    prepare_gclient(
        args.depot_tools,
        args.chromium_src,
    )


    sync_chromium(
        args.depot_tools,
        args.chromium_src,
        pinned_commit,
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

    # chromium_src itself is checked separately from its parent: the
    # original version only compared chromium_src.parent, which missed
    # the case where --chromium-src was pointed directly at
    # --thorium-root or --depot-tools (e.g. both set to the same dir).
    named_paths = [
        ("chromium-src", chromium_src),
        ("chromium-src parent", chromium_src.parent),
        ("thorium-root", thorium_root),
        ("depot-tools", depot_tools),
    ]


    for i, (left_name, left) in enumerate(named_paths):

        for right_name, right in named_paths[i + 1:]:

            # chromium-src is always inside (or equal to) its own
            # parent by construction; that relationship is expected
            # and not a conflict.
            if {left_name, right_name} == {
                "chromium-src",
                "chromium-src parent",
            }:
                continue

            if (
                left == right
                or left.is_relative_to(right)
                or right.is_relative_to(left)
            ):

                raise BootstrapError(
                    f"checkout paths overlap: "
                    f"{left} ({left_name}) {right} ({right_name})"
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