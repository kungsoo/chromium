#!/usr/bin/env python3

# Copyright (c) 2026 Alex313031 and gz83.

"""Build and package Thorium debug products."""

import argparse
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Sequence


MINIMUM_PYTHON = (3, 11)
NINJA_STATUS = "[%r processes, %f/%t @ %o/s | %e sec. ] "
PACKAGE_NAME = "Thorium_UI_Debug_Shell"
SUPPORTED_TARGET_OSES = ("linux", "mac", "win")

FULL_TARGETS = {
    "linux": (
        "chrome",
        "chrome_sandbox",
        "chromedriver",
        "thorium_shell",
        "thorium_ui_debug_shell",
        "clear_key_cdm",
    ),
    "mac": (
        "chrome",
        "chromedriver",
        "thorium_shell",
        "thorium_ui_debug_shell",
        "clear_key_cdm",
    ),
    "win": (
        "chrome",
        "chromedriver",
        "thorium_shell",
        "setup",
        "mini_installer",
        "thorium_ui_debug_shell",
        "clear_key_cdm",
    ),
}

SHELL_TARGETS = {
    "linux": (
        "thorium_ui_debug_shell",
        "minidump_stackwalk",
        "dump_syms",
        "clear_key_cdm",
    ),
    "mac": ("thorium_ui_debug_shell",),
    "win": ("thorium_ui_debug_shell",),
}

COMMON_FILES = (
    "icudtl.dat",
    "content_resources.pak",
    "vk_swiftshader_icd.json",
    "v8_context_snapshot.bin",
    "ui_test.pak",
    "views_examples_resources.pak",
)
LINUX_FILES = (
    "libEGL.so",
    "libGLESv2.so",
    "libvk_swiftshader.so",
    "libvulkan.so.1",
    "thorium_ui_debug_shell",
)
WINDOWS_FILES = (
    "libEGL.dll",
    "libGLESv2.dll",
    "vk_swiftshader.dll",
    "vulkan-1.dll",
    "thorium_ui_debug_shell.exe",
)
LINUX_SHELL_ONLY_FILES = ("minidump_stackwalk", "dump_syms")
ICON_NAMES = (
    "icon_16.png",
    "icon_24.png",
    "icon_32.png",
    "icon_48.png",
    "icon_64.png",
    "icon_128.png",
    "icon_256.png",
)


class DebugBuildError(RuntimeError):
    """An expected debug build or packaging failure."""


class BuildFailure(DebugBuildError):
    """A failed autoninja phase whose status should be preserved."""

    def __init__(self, phase: int, phase_count: int, returncode: int) -> None:
        super().__init__(
            f"build phase {phase}/{phase_count} failed with exit code {returncode}"
        )
        self.returncode = returncode


class PackageRollbackFailure(DebugBuildError):
    """A package installation failure that requires manual recovery."""


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
    return Path(__file__).resolve().parents[2]


def positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if number < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-os",
        required=True,
        choices=SUPPORTED_TARGET_OSES,
        help="GN target operating system",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=("full", "shell"),
        help="build the full debug product set or only the UI Debug Shell",
    )
    parser.add_argument(
        "--chromium-src",
        type=environment_path,
        default=default_chromium_src(),
        metavar="PATH",
        help="Chromium src directory (default: CR_DIR or the platform default)",
    )
    parser.add_argument(
        "--thorium-root",
        type=environment_path,
        default=default_thorium_root(),
        metavar="PATH",
        help="Thorium checkout (default: THOR_DIR or this repository)",
    )
    parser.add_argument(
        "-C",
        "--out-dir",
        type=environment_path,
        default=Path("out/thorium"),
        metavar="PATH",
        help="GN output directory, relative to Chromium src (default: out/thorium)",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=positive_integer,
        help="maximum parallel jobs (default: let autoninja choose)",
    )
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument(
        "--build-only",
        action="store_true",
        help="build targets without assembling the Debug Shell package",
    )
    operation.add_argument(
        "--package-only",
        action="store_true",
        help="assemble existing products without running autoninja",
    )
    parser.add_argument(
        "--single-pass",
        action="store_true",
        help="build all targets in one autoninja invocation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print build commands without building or packaging",
    )
    return parser.parse_args(argv)


def resolve_out_dir(chromium_src: Path, out_dir: Path) -> Path:
    if not out_dir.is_absolute():
        out_dir = chromium_src / out_dir
    return out_dir.resolve()


def find_tool(name: str) -> Path:
    executable = shutil.which(name)
    if not executable:
        raise DebugBuildError(
            f"{name} was not found in PATH; add depot_tools to PATH first"
        )
    return Path(executable).resolve()


def platform_command(executable: Path, arguments: Sequence[str]) -> list[str]:
    if os.name == "nt" and executable.suffix.lower() in {".bat", ".cmd"}:
        python_wrapper = executable.with_suffix(".py")
        if not python_wrapper.is_file():
            raise DebugBuildError(
                "refusing to invoke a batch wrapper without its Python companion: "
                f"{executable}"
            )
        return [sys.executable, str(python_wrapper), *arguments]
    return [str(executable), *arguments]


def display_command(command: Sequence[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def read_gn_argument(
    gn: Path, chromium_src: Path, out_dir: Path, name: str
) -> str:
    command = platform_command(
        gn,
        ("args", str(out_dir), f"--list={name}", "--short"),
    )
    try:
        result = subprocess.run(
            command,
            cwd=chromium_src,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or "").strip()
        suffix = f": {details}" if details else ""
        raise DebugBuildError(f"could not read GN argument {name}{suffix}") from error
    except OSError as error:
        raise DebugBuildError(f"could not run GN: {error}") from error

    prefix = f"{name} = "
    for line in result.stdout.splitlines():
        value = line.strip()
        if not value.startswith(prefix):
            continue
        value = value[len(prefix) :].strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            return value[1:-1]
        return value
    raise DebugBuildError(f"GN did not report a value for {name}")


def validate_configuration(
    chromium_src: Path,
    thorium_root: Path,
    out_dir: Path,
    target_os: str,
    *,
    build_only: bool,
) -> tuple[Path, Path]:
    chromium_src = chromium_src.resolve()
    thorium_root = thorium_root.resolve()
    out_dir = resolve_out_dir(chromium_src, out_dir)
    if not (chromium_src / "BUILD.gn").is_file():
        raise DebugBuildError(f"not a Chromium src directory: {chromium_src}")
    if not (thorium_root / "infra" / "DEBUG").is_dir():
        raise DebugBuildError(f"not a Thorium checkout: {thorium_root}")
    if not (out_dir / "args.gn").is_file() or not (out_dir / "build.ninja").is_file():
        raise DebugBuildError(
            f"GN output directory is not configured: {out_dir}; generate it first"
        )
    if target_os == "mac" and platform.system() != "Darwin":
        raise DebugBuildError("macOS debug targets must be built on macOS")
    if target_os == "linux" and platform.system() != "Linux":
        raise DebugBuildError("Linux debug targets must be built on Linux")
    if target_os == "mac" and not build_only:
        raise DebugBuildError(
            "macOS Debug Shell packaging has no verified payload definition; "
            "use --build-only"
        )

    gn = find_tool("gn")
    actual_os = read_gn_argument(gn, chromium_src, out_dir, "target_os")
    if actual_os != target_os:
        raise DebugBuildError(
            f"target OS mismatch: requested {target_os!r}, GN reports {actual_os!r}"
        )
    if read_gn_argument(gn, chromium_src, out_dir, "is_debug") != "true":
        raise DebugBuildError(f"GN output directory is not a debug build: {out_dir}")
    target_cpu = read_gn_argument(gn, chromium_src, out_dir, "target_cpu")
    if not build_only and target_os in ("linux", "win") and target_cpu != "x64":
        raise DebugBuildError(
            f"Debug Shell packaging is defined only for x64 {target_os}; "
            f"GN reports target_cpu={target_cpu!r}"
        )
    return chromium_src, out_dir


def normalize_exit_status(returncode: int) -> int:
    if returncode < 0:
        return 128 + abs(returncode)
    return returncode or 1


def selected_targets(target_os: str, mode: str) -> tuple[str, ...]:
    return (FULL_TARGETS if mode == "full" else SHELL_TARGETS)[target_os]


def build_targets(
    autoninja: Path,
    chromium_src: Path,
    out_dir: Path,
    targets: Sequence[str],
    jobs: int | None,
    *,
    single_pass: bool,
    dry_run: bool,
) -> None:
    phases = [list(targets)] if single_pass else [[target] for target in targets]
    environment = os.environ.copy()
    environment["NINJA_SUMMARIZE_BUILD"] = "1"
    environment.setdefault("NINJA_STATUS", NINJA_STATUS)
    relative_out = os.path.relpath(out_dir, chromium_src)

    for phase, phase_targets in enumerate(phases, start=1):
        arguments = ["-C", relative_out, *phase_targets]
        if jobs is not None:
            arguments.extend(("-j", str(jobs)))
        command = platform_command(autoninja, arguments)
        print(
            f"\nBuild phase {phase}/{len(phases)}: {display_command(command)}",
            flush=True,
        )
        if dry_run:
            continue
        try:
            result = subprocess.run(
                command,
                cwd=chromium_src,
                env=environment,
                check=False,
            )
        except OSError as error:
            raise DebugBuildError(f"could not run autoninja: {error}") from error
        if result.returncode:
            raise BuildFailure(
                phase,
                len(phases),
                normalize_exit_status(result.returncode),
            )


def required_payload(
    out_dir: Path,
    debug_dir: Path,
    target_os: str,
    mode: str,
) -> tuple[list[tuple[Path, Path]], list[tuple[Path, Path]]]:
    directories: list[tuple[Path, Path]] = []
    files = [(out_dir / name, Path(name)) for name in COMMON_FILES]
    platform_files = LINUX_FILES if target_os == "linux" else WINDOWS_FILES
    files.extend((out_dir / name, Path(name)) for name in platform_files)
    if mode == "shell" and target_os == "linux":
        files.extend(
            (out_dir / name, Path(name)) for name in LINUX_SHELL_ONLY_FILES
        )

    files.extend(
        (debug_dir / "icons" / name, Path("icons") / name)
        for name in ICON_NAMES
    )
    files.append((debug_dir / "DEBUG_SHELL_README.md", Path("README.md")))
    if target_os == "linux":
        files.append(
            (debug_dir / "Thorium_Debug_Shell.sh", Path("Thorium_Debug_Shell.sh"))
        )
        directories.append((out_dir / "ClearKeyCdm", Path("ClearKeyCdm")))
        files.append(
            (
                out_dir
                / "ClearKeyCdm/_platform_specific/linux_x64/libclearkeycdm.so",
                Path("lib/libclearkeycdm.so"),
            )
        )
    else:
        files.append(
            (
                debug_dir / "icons" / "thorium_debug_shell.ico",
                Path("thorium_debug_shell.ico"),
            )
        )
    return directories, files


def validate_payload(
    directories: Sequence[tuple[Path, Path]],
    files: Sequence[tuple[Path, Path]],
) -> None:
    missing = [str(source) for source, _ in directories if not source.is_dir()]
    missing.extend(str(source) for source, _ in files if not source.is_file())
    if missing:
        formatted = "\n  ".join(missing)
        raise DebugBuildError(f"required Debug Shell payload is missing:\n  {formatted}")


def copy_payload(
    staging: Path,
    directories: Sequence[tuple[Path, Path]],
    files: Sequence[tuple[Path, Path]],
) -> None:
    for source, relative_destination in directories:
        destination = staging / relative_destination
        print(f"Copying directory {source} -> {destination}")
        shutil.copytree(source, destination, symlinks=True)
    for source, relative_destination in files:
        destination = staging / relative_destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        print(f"Copying {source} -> {destination}")
        shutil.copy2(source, destination)


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def create_zip(staging: Path, output: Path) -> Path:
    temporary_base = output.with_name(f".{output.stem}.new")
    temporary_archive = Path(f"{temporary_base}.zip")
    if temporary_archive.exists() or temporary_archive.is_symlink():
        remove_path(temporary_archive)
    try:
        archive = Path(
            shutil.make_archive(
                str(temporary_base),
                "zip",
                root_dir=staging,
                base_dir=".",
            )
        )
        archive.replace(output)
    finally:
        if temporary_archive.exists() or temporary_archive.is_symlink():
            remove_path(temporary_archive)
    return output


def replace_package_outputs(
    staging: Path,
    temporary_archive: Path | None,
    destination: Path,
    archive: Path,
    backup_root: Path,
) -> None:
    if destination.is_symlink() or (
        destination.exists() and not destination.is_dir()
    ):
        raise DebugBuildError(
            f"refusing to replace a non-directory package path: {destination}"
        )
    if archive.is_symlink() or (archive.exists() and not archive.is_file()):
        raise DebugBuildError(f"archive output is not a regular file: {archive}")

    directory_backup = backup_root / "previous-package"
    archive_backup = backup_root / "previous-package.zip"
    had_destination = destination.exists()
    had_archive = archive.exists()
    installed_destination = False
    installed_archive = False

    try:
        if had_destination:
            destination.rename(directory_backup)
        if had_archive:
            archive.rename(archive_backup)

        staging.rename(destination)
        installed_destination = True
        if temporary_archive is not None:
            temporary_archive.rename(archive)
            installed_archive = True
    except OSError as error:
        rollback_errors = []
        try:
            if installed_archive and archive.exists():
                remove_path(archive)
            if had_archive and archive_backup.exists():
                archive_backup.rename(archive)
        except OSError as rollback_error:
            rollback_errors.append(f"archive: {rollback_error}")
        try:
            if installed_destination and destination.exists():
                remove_path(destination)
            if had_destination and directory_backup.exists():
                directory_backup.rename(destination)
        except OSError as rollback_error:
            rollback_errors.append(f"directory: {rollback_error}")

        if rollback_errors:
            details = "; ".join(rollback_errors)
            raise PackageRollbackFailure(
                f"could not install package outputs ({error}); "
                f"rollback was incomplete ({details}); backups are in {backup_root}"
            ) from error
        raise


def package_debug_shell(
    thorium_root: Path,
    out_dir: Path,
    target_os: str,
    mode: str,
) -> None:
    debug_dir = thorium_root / "infra" / "DEBUG"
    directories, files = required_payload(out_dir, debug_dir, target_os, mode)
    validate_payload(directories, files)
    destination = out_dir / PACKAGE_NAME
    archive = out_dir / f"{PACKAGE_NAME}.zip"
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{PACKAGE_NAME}.staging-", dir=out_dir)
    )
    preserve_temporary = False
    try:
        staging = temporary / PACKAGE_NAME
        staging.mkdir()
        copy_payload(staging, directories, files)
        temporary_archive = None
        if mode == "shell":
            temporary_archive = create_zip(staging, Path(temporary) / archive.name)
        replace_package_outputs(
            staging,
            temporary_archive,
            destination,
            archive,
            temporary,
        )
    except PackageRollbackFailure:
        preserve_temporary = True
        raise
    finally:
        if preserve_temporary:
            print(
                f"warning: preserving temporary package directory for manual "
                f"recovery: {temporary}",
                file=sys.stderr,
            )
        else:
            try:
                shutil.rmtree(temporary)
            except OSError as error:
                print(
                    f"warning: could not remove temporary package directory "
                    f"{temporary}: {error}",
                    file=sys.stderr,
                )

    print(f"\nDebug Shell package: {destination}")
    if mode == "shell":
        print(f"Debug Shell archive: {archive}")


def main(argv: Sequence[str] | None = None) -> int:
    if sys.version_info < MINIMUM_PYTHON:
        print("error: Python 3.11 or newer is required", file=sys.stderr)
        return 2
    if platform.system() not in ("Linux", "Darwin", "Windows"):
        print("error: only Linux, macOS, and Windows hosts are supported", file=sys.stderr)
        return 2

    args = parse_arguments(sys.argv[1:] if argv is None else argv)
    try:
        if args.package_only and (args.jobs is not None or args.single_pass):
            raise DebugBuildError(
                "--jobs and --single-pass cannot be used with --package-only"
            )
        if args.package_only and args.dry_run:
            raise DebugBuildError("--dry-run cannot be used with --package-only")
        chromium_src, out_dir = validate_configuration(
            args.chromium_src,
            args.thorium_root,
            args.out_dir,
            args.target_os,
            build_only=args.build_only or args.dry_run,
        )
        targets = selected_targets(args.target_os, args.mode)
        print(f"Chromium source: {chromium_src}")
        print(f"Output directory: {out_dir}")
        print(f"Target: {args.target_os} {args.mode}")

        if not args.package_only:
            build_targets(
                find_tool("autoninja"),
                chromium_src,
                out_dir,
                targets,
                args.jobs,
                single_pass=args.single_pass,
                dry_run=args.dry_run,
            )
        if not args.build_only and not args.dry_run:
            package_debug_shell(
                args.thorium_root.resolve(),
                out_dir,
                args.target_os,
                args.mode,
            )
    except BuildFailure as error:
        print(f"{Path(sys.argv[0]).name}: {error}", file=sys.stderr)
        return error.returncode
    except (DebugBuildError, OSError, shutil.Error) as error:
        print(f"{Path(sys.argv[0]).name}: {error}", file=sys.stderr)
        return 111
    except KeyboardInterrupt:
        print(f"\n{Path(sys.argv[0]).name}: interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
