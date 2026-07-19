#!/usr/bin/env python3

# Copyright (c) 2026 Alex313031, midzer, and gz83

"""Safely replace a depot_tools checkout on Linux or Windows.

The reset also removes gsutil state and the current user's vpython cache, as
the original shell script did. Legacy vpython cache locations are removed only
when they still exist.
"""

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


DEPOT_TOOLS_URL = (
    "https://chromium.googlesource.com/chromium/tools/depot_tools.git"
)


class ResetError(RuntimeError):
    """An expected depot_tools reset failure."""


def environment_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replace depot_tools and clear gsutil and vpython state."
        ),
        epilog=(
            "Warning: this removes the user's gsutil state, including saved "
            "configuration and authentication state."
        ),
    )
    parser.add_argument(
        "--depot-tools",
        type=environment_path,
        default=default_depot_tools(),
        help=(
            "depot_tools directory (default: DEPOT_TOOLS_DIR, the gclient "
            "location, or the platform default)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned operations without changing anything",
    )
    parser.add_argument(
        "--keep-backup",
        action="store_true",
        help="keep the old depot_tools checkout after a successful reset",
    )
    return parser.parse_args()


def is_filesystem_root(path: Path) -> bool:
    return bool(path.anchor) and path == Path(path.anchor)


def validate_target(target: Path, thorium_root: Path) -> None:
    home = Path.home().resolve()
    resolved_target = target.resolve()
    resolved_thorium_root = thorium_root.resolve()
    target_present = os.path.lexists(target)
    forbidden = {home, resolved_thorium_root}
    if is_filesystem_root(resolved_target) or resolved_target in forbidden:
        raise ResetError(f"refusing to use dangerous depot_tools path: {target}")
    if home.is_relative_to(resolved_target):
        raise ResetError(
            f"refusing to replace {target}: it contains the user home directory"
        )
    if resolved_thorium_root.is_relative_to(resolved_target):
        raise ResetError(
            f"refusing to replace {target}: it contains the Thorium checkout"
        )
    if resolved_target.is_relative_to(resolved_thorium_root):
        raise ResetError(
            f"refusing to place depot_tools inside the Thorium checkout: {target}"
        )
    if target_present:
        if target.is_symlink():
            raise ResetError(f"refusing to replace symlink: {target}")
        if not target.is_dir():
            raise ResetError(f"depot_tools path is not a directory: {target}")
        if not (target / ".git").is_dir() or not (
            target / "gclient.py"
        ).is_file():
            raise ResetError(
                f"refusing to replace a directory that is not depot_tools: {target}"
            )

    executable = Path(sys.executable).resolve()
    if target_present and executable.is_relative_to(resolved_target):
        raise ResetError(
            "the current Python interpreter is inside depot_tools; rerun with "
            "an independent system Python 3.11 interpreter"
        )


def sibling_path_for(
    target: Path,
    label: str,
    *,
    reserved: set[Path] | None = None,
    ignored: set[Path] | None = None,
) -> Path:
    reserved = reserved or set()
    ignored = ignored or set()
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = target.with_name(f"{target.name}.{label}-{timestamp}")
    suffix = 1
    while candidate in reserved or (
        candidate not in ignored and os.path.lexists(candidate)
    ):
        candidate = target.with_name(
            f"{target.name}.{label}-{timestamp}-{suffix}"
        )
        suffix += 1
    return candidate


def remove_tree(path: Path, *, dry_run: bool, label: str) -> None:
    if not os.path.lexists(path):
        return
    print(f"Removing {label}: {path}")
    if not dry_run:
        if path.is_symlink() or path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path, onerror=remove_readonly)


def remove_readonly(function, path: str, error_info) -> None:
    """Retry removal after making a read-only path writable."""
    del error_info
    os.chmod(path, 0o700)
    function(path)


def clone_depot_tools(target: Path, *, dry_run: bool) -> None:
    print(f"Cloning depot_tools into: {target}")
    if dry_run:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", DEPOT_TOOLS_URL, str(target)],
        check=True,
    )
    if not (target / ".git").is_dir() or not (target / "gclient.py").is_file():
        raise ResetError("the new depot_tools checkout failed validation")


def remove_failed_clone(path: Path) -> str | None:
    """Best-effort cleanup that does not hide the original clone failure."""
    if not os.path.lexists(path):
        return None
    try:
        remove_tree(path, dry_run=False, label="incomplete depot_tools checkout")
    except OSError as error:
        return f"; could not remove incomplete checkout {path}: {error}"
    return None


def stale_siblings(target: Path, label: str) -> list[Path]:
    return sorted(target.parent.glob(f"{target.name}.{label}-*"))


def validate_stale_staging(staging_paths: list[Path]) -> None:
    for staging in staging_paths:
        if staging.is_symlink() or not staging.is_dir():
            raise ResetError(
                f"refusing to remove unrecognized staging path: {staging}"
            )
        try:
            is_empty = next(staging.iterdir(), None) is None
        except OSError as error:
            raise ResetError(
                f"could not inspect staging path {staging}: {error}"
            ) from error
        git_directory = staging / ".git"
        if not is_empty and (
            git_directory.is_symlink() or not git_directory.is_dir()
        ):
            raise ResetError(
                f"refusing to remove unrecognized staging directory: {staging}"
            )


def remove_stale_staging(staging_paths: list[Path], *, dry_run: bool) -> None:
    for staging in staging_paths:
        remove_tree(
            staging,
            dry_run=dry_run,
            label="stale incomplete depot_tools clone",
        )


def validate_stale_rollbacks(target: Path, rollbacks: list[Path]) -> None:
    if not os.path.lexists(target) and len(rollbacks) > 1:
        raise ResetError(
            "depot_tools is missing and multiple interrupted rollback "
            f"directories exist: {', '.join(map(str, rollbacks))}"
        )
    for rollback in rollbacks:
        if rollback.is_symlink() or not (rollback / ".git").is_dir() or not (
            rollback / "gclient.py"
        ).is_file():
            raise ResetError(
                f"interrupted rollback is not a depot_tools checkout: {rollback}"
            )


def validate_preserved_checkouts(
    target: Path,
    preserved: list[Path],
    rollbacks: list[Path],
) -> None:
    if len(preserved) > 1:
        raise ResetError(
            "multiple interrupted preserved depot_tools checkouts exist: "
            f"{', '.join(map(str, preserved))}"
        )
    for checkout in preserved:
        if checkout.is_symlink() or not (checkout / ".git").is_dir() or not (
            checkout / "gclient.py"
        ).is_file():
            raise ResetError(
                f"preserved path is not a depot_tools checkout: {checkout}"
            )
    if (
        not os.path.lexists(target)
        and preserved
        and rollbacks
    ):
        raise ResetError(
            "depot_tools is missing and both rollback and preserved checkouts "
            "exist; manual recovery is required"
        )


def recover_interrupted_swap(
    target: Path,
    rollbacks: list[Path],
    *,
    dry_run: bool,
) -> bool:
    if not rollbacks:
        return False
    if not os.path.lexists(target):
        rollback = rollbacks[0]
        print(f"Restoring interrupted depot_tools rollback: {rollback} -> {target}")
        if not dry_run:
            rollback.rename(target)
        return True

    for rollback in rollbacks:
        remove_tree(
            rollback,
            dry_run=dry_run,
            label="stale interrupted depot_tools rollback",
        )
    return False


def recover_preserved_checkout(
    target: Path,
    preserved: list[Path],
    *,
    backup: Path | None,
    dry_run: bool,
) -> bool:
    if not preserved:
        return False
    checkout = preserved[0]
    if not os.path.lexists(target):
        print(f"Restoring preserved depot_tools checkout: {checkout} -> {target}")
        if not dry_run:
            checkout.rename(target)
        return True

    if backup is None:
        raise ResetError("no destination was reserved for the preserved checkout")
    print(f"Retaining interrupted depot_tools backup: {checkout} -> {backup}")
    if not dry_run:
        checkout.rename(backup)
    return False


@contextmanager
def defer_termination_signals():
    """Prevent an interrupt from landing between the two swap renames."""
    blocked_signals = {signal.SIGINT, signal.SIGTERM}
    if hasattr(signal, "pthread_sigmask"):
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, blocked_signals)
        try:
            yield
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        return

    received_signals = []

    def record_signal(signum, frame) -> None:
        del frame
        received_signals.append(signum)

    previous_handlers = {
        signum: signal.signal(signum, record_signal)
        for signum in blocked_signals
    }
    try:
        yield
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    if received_signals:
        signum = received_signals[0]
        previous_handler = previous_handlers[signum]
        if previous_handler == signal.SIG_IGN:
            return
        if previous_handler == signal.SIG_DFL:
            if signum == signal.SIGINT:
                raise KeyboardInterrupt
            os.kill(os.getpid(), signum)
            return
        previous_handler(signum, None)


def cleanup_targets() -> tuple[tuple[Path, str], ...]:
    home = Path.home()
    default_gsutil_root = (
        Path(os.environ.get("USERPROFILE", home)) if os.name == "nt" else home
    )
    gsutil = environment_path(
        os.environ.get("GSUTIL_DIR", str(default_gsutil_root / ".gsutil"))
    )
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise ResetError("LOCALAPPDATA is not defined")
        vpython = environment_path(
            os.environ.get(
                "VPYTHON_ROOT_DIR",
                str(Path(local_app_data) / ".vpython-root"),
            )
        )
        return (
            (gsutil, "gsutil state (including saved configuration)"),
            (vpython, "vpython cache"),
        )

    cache = home / ".cache"
    return (
        (gsutil, "gsutil state (including saved configuration)"),
        (cache / f".vpython-root.{os.getuid()}", "current-user vpython cache"),
        (home / ".vpython_cipd_cache", "legacy vpython CIPD cache"),
        (home / ".vpython-root", "legacy vpython cache"),
        (cache / ".vpython-root", "legacy vpython cache"),
    )


def validate_cleanup_target(
    path: Path,
    *,
    depot_tools: Path,
    thorium_root: Path,
) -> None:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    resolved_depot_tools = depot_tools.resolve()
    resolved_thorium_root = thorium_root.resolve()
    forbidden = {home, resolved_depot_tools, resolved_thorium_root}
    if is_filesystem_root(resolved) or resolved in forbidden:
        raise ResetError(f"refusing to remove dangerous cleanup path: {path}")
    if home.is_relative_to(resolved):
        raise ResetError(f"cleanup path contains the user home directory: {path}")
    if resolved_depot_tools.is_relative_to(resolved):
        raise ResetError(f"cleanup path contains depot_tools: {path}")
    if resolved_thorium_root.is_relative_to(resolved):
        raise ResetError(f"cleanup path contains the Thorium checkout: {path}")
    if resolved.is_relative_to(resolved_thorium_root):
        raise ResetError(f"cleanup path is inside the Thorium checkout: {path}")


def reset_depot_tools(target: Path, thorium_root: Path, args: argparse.Namespace) -> None:
    target = Path(os.path.abspath(target.expanduser()))
    thorium_root = thorium_root.expanduser().resolve()
    validate_target(target, thorium_root)
    targets_to_clean = cleanup_targets()
    for path, _ in targets_to_clean:
        validate_cleanup_target(
            path,
            depot_tools=target,
            thorium_root=thorium_root,
        )

    rollbacks = stale_siblings(target, "rollback")
    preserved = stale_siblings(target, "preserve")
    stale_staging = stale_siblings(target, "new")
    validate_stale_rollbacks(target, rollbacks)
    validate_preserved_checkouts(target, preserved, rollbacks)
    validate_stale_staging(stale_staging)

    reserved_paths: set[Path] = set()
    virtually_removed = (
        set(rollbacks + preserved + stale_staging) if args.dry_run else set()
    )
    preserved_backup = None
    if preserved and os.path.lexists(target):
        preserved_backup = sibling_path_for(
            target,
            "backup",
            reserved=reserved_paths,
            ignored=virtually_removed,
        )
        reserved_paths.add(preserved_backup)

    recovered_rollback = recover_interrupted_swap(
        target,
        rollbacks,
        dry_run=args.dry_run,
    )
    recovered_preserved = recover_preserved_checkout(
        target,
        preserved,
        backup=preserved_backup,
        dry_run=args.dry_run,
    )
    recovered_checkout = recovered_rollback or recovered_preserved
    remove_stale_staging(stale_staging, dry_run=args.dry_run)
    if not args.dry_run and recovered_checkout:
        validate_target(target, thorium_root)

    old_checkout = sibling_path_for(
        target,
        "preserve" if args.keep_backup else "rollback",
        reserved=reserved_paths,
        ignored=virtually_removed,
    )
    reserved_paths.add(old_checkout)
    retained_backup = sibling_path_for(
        target,
        "backup",
        reserved=reserved_paths,
        ignored=virtually_removed,
    )
    reserved_paths.add(retained_backup)
    staging = sibling_path_for(
        target,
        "new",
        reserved=reserved_paths,
        ignored=virtually_removed,
    )
    had_checkout = recovered_checkout or os.path.lexists(target)
    try:
        clone_depot_tools(staging, dry_run=args.dry_run)
    except (
        KeyboardInterrupt,
        OSError,
        subprocess.CalledProcessError,
        ResetError,
    ) as error:
        cleanup_error = None if args.dry_run else remove_failed_clone(staging)
        if isinstance(error, KeyboardInterrupt):
            if cleanup_error:
                raise ResetError(
                    "depot_tools clone was cancelled" + cleanup_error
                ) from error
            raise
        message = f"failed to clone depot_tools: {error}"
        raise ResetError(message + (cleanup_error or "")) from error

    if had_checkout:
        print(f"Moving existing depot_tools to: {old_checkout}")
    print(f"Installing the new depot_tools checkout at: {target}")
    if not args.dry_run:
        with defer_termination_signals():
            try:
                if had_checkout:
                    target.rename(old_checkout)
                staging.rename(target)
            except OSError as error:
                restore_error = None
                if (
                    had_checkout
                    and old_checkout.exists()
                    and not os.path.lexists(target)
                ):
                    try:
                        old_checkout.rename(target)
                    except OSError as rollback_error:
                        restore_error = rollback_error
                cleanup_error = remove_failed_clone(staging)
                message = (
                    f"failed to install the new depot_tools checkout: {error}"
                )
                if restore_error is not None:
                    message += (
                        f"; failed to restore {old_checkout} to {target}: "
                        f"{restore_error}"
                    )
                message += cleanup_error or ""
                raise ResetError(message) from error
            if had_checkout and args.keep_backup:
                try:
                    old_checkout.rename(retained_backup)
                except OSError as error:
                    raise ResetError(
                        f"depot_tools was installed at {target}, but the old "
                        f"checkout could not be retained as {retained_backup}: "
                        f"{error}"
                    ) from error

    cleanup_errors = []
    for path, label in targets_to_clean:
        try:
            remove_tree(path, dry_run=args.dry_run, label=label)
        except OSError as error:
            cleanup_errors.append(f"failed to remove {path}: {error}")

    if had_checkout and args.keep_backup:
        print(f"Keeping old depot_tools checkout at: {retained_backup}")
    elif had_checkout:
        if args.dry_run:
            print(f"Removing old depot_tools checkout: {old_checkout}")
        else:
            try:
                remove_tree(
                    old_checkout,
                    dry_run=False,
                    label="old depot_tools checkout",
                )
            except OSError as error:
                cleanup_errors.append(
                    f"failed to remove {old_checkout}: {error}"
                )

    if args.dry_run:
        print("\nDry run completed; no files were changed.")
    else:
        if cleanup_errors:
            details = "; ".join(cleanup_errors)
            raise ResetError(
                f"depot_tools was installed successfully at {target}, but "
                f"cleanup was incomplete: {details}"
            )
        print(f"\nCompleted. depot_tools is available at: {target}")
        print(f'You can now run: python3 "{thorium_root / "trunk.py"}"')


def main() -> int:
    if not (sys.platform.startswith("linux") or os.name == "nt"):
        print("error: reset_depot_tools.py supports Linux and Windows", file=sys.stderr)
        return 2
    if sys.version_info < (3, 11):
        print("error: Python 3.11 or newer is required", file=sys.stderr)
        return 2
    args = parse_args()
    if sys.platform.startswith("linux") and os.geteuid() == 0:
        print(
            "error: do not run reset_depot_tools.py as root or through sudo",
            file=sys.stderr,
        )
        return 2

    try:
        reset_depot_tools(
            args.depot_tools,
            Path(__file__).resolve().parent,
            args,
        )
    except (OSError, ResetError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("error: depot_tools reset was cancelled", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
