#!/usr/bin/env python3

# Copyright (c) 2026 Alex313031 and gz83.

"""Create a Thorium portable ZIP from a Linux package or Windows installer."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Sequence
import zipfile


MINIMUM_PYTHON = (3, 11)
VERSION_PATTERN = re.compile(r"(?<!\d)(\d+\.\d+\.\d+\.\d+)(?!\d)")
WINDOWS_PROFILES = (
    ("AVX512", "AVX512"),
    ("AVX2", "AVX2"),
    ("SSE4.2", "SSE4.2"),
    ("SSE4", "SSE4"),
    ("SSE3", "SSE3"),
    ("SSE2", "SSE2"),
    ("ARM64", "ARM64"),
    ("AVX", "AVX"),
)


class PortableError(RuntimeError):
    """An expected portable packaging failure."""


def environment_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def profile_argument(value: str) -> str:
    profiles = {label.upper(): label for _, label in WINDOWS_PROFILES}
    try:
        return profiles[value.upper()]
    except KeyError as error:
        allowed = ", ".join(profiles.values())
        raise argparse.ArgumentTypeError(
            f"unsupported profile {value!r}; choose one of: {allowed}"
        ) from error


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform",
        choices=("auto", "linux", "windows"),
        default="auto",
        help="input package platform (default: infer from its suffix)",
    )
    parser.add_argument(
        "--input",
        type=environment_path,
        required=True,
        metavar="PATH",
        help="Thorium .deb package or Windows mini installer",
    )
    parser.add_argument(
        "--output",
        type=environment_path,
        metavar="PATH",
        help="output ZIP path (default: next to the input package)",
    )
    parser.add_argument(
        "--seven-zip",
        type=environment_path,
        metavar="PATH",
        help="7-Zip executable for Windows installers (default: search PATH)",
    )
    parser.add_argument(
        "--profile",
        type=profile_argument,
        metavar="NAME",
        help="Windows SIMD profile used in the output name when it cannot be inferred",
    )
    parser.add_argument(
        "--expected-version",
        metavar="VERSION",
        help="require the extracted Thorium version to match this value",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing output archive",
    )
    return parser.parse_args(argv)


def detect_platform(requested: str, package: Path) -> str:
    suffix = package.suffix.lower()
    if requested != "auto":
        conflicting = {("linux", ".exe"), ("windows", ".deb")}
        if (requested, suffix) in conflicting:
            raise PortableError(
                f"--platform {requested} conflicts with input suffix {suffix}"
            )
        return requested
    if suffix == ".deb":
        return "linux"
    if suffix == ".exe":
        return "windows"
    raise PortableError("could not infer the platform; pass --platform explicitly")


def run(command: Sequence[str]) -> None:
    print(f"Running: {subprocess.list2cmdline(command)}")
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as error:
        raise PortableError(
            f"command failed with exit code {error.returncode}: {command[0]}"
        ) from error
    except OSError as error:
        raise PortableError(f"could not run {command[0]}: {error}") from error


def run_capture(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout).strip()
        suffix = f": {details}" if details else ""
        raise PortableError(
            f"command failed with exit code {error.returncode}: {command[0]}{suffix}"
        ) from error
    except OSError as error:
        raise PortableError(f"could not run {command[0]}: {error}") from error
    return result.stdout.strip()


def find_program(name: str, configured: Path | None = None) -> str:
    if configured is not None:
        configured = configured.resolve()
        if not configured.is_file():
            raise PortableError(f"program does not exist: {configured}")
        return str(configured)
    found = shutil.which(name)
    if not found and name == "7z" and os.name == "nt":
        candidates = (
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "7-Zip/7z.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
            / "7-Zip/7z.exe",
        )
        found = next((str(path) for path in candidates if path.is_file()), None)
    if not found:
        raise PortableError(f"{name} was not found in PATH")
    return found


def copy_contents(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise PortableError(f"package payload directory is missing: {source}")
    shutil.copytree(source, destination, symlinks=True)


def validate_payload_tree(root: Path) -> None:
    if not root.is_dir():
        raise PortableError(f"package payload directory is missing: {root}")
    root = root.resolve()
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    pending.append(path)
                elif stat.S_ISREG(mode):
                    continue
                elif stat.S_ISLNK(mode):
                    target = os.readlink(path)
                    try:
                        resolved_target = (path.parent / target).resolve(strict=True)
                    except FileNotFoundError as error:
                        raise PortableError(
                            f"broken symbolic link in package payload: "
                            f"{path.relative_to(root)} -> {target}"
                        ) from error
                    if not resolved_target.is_relative_to(root):
                        raise PortableError(
                            f"symbolic link escapes the package payload: "
                            f"{path.relative_to(root)} -> {target}"
                        )
                else:
                    raise PortableError(
                        f"unsupported special file in package payload: "
                        f"{path.relative_to(root)}"
                    )


def extract_linux(package: Path, staging: Path, work: Path) -> tuple[str, str]:
    dpkg_deb = find_program("dpkg-deb")
    package_name = run_capture((dpkg_deb, "--field", str(package), "Package"))
    if package_name != "thorium-browser":
        raise PortableError(
            f"unexpected Debian package name {package_name!r}; expected "
            "'thorium-browser'"
        )
    package_version = run_capture((dpkg_deb, "--field", str(package), "Version"))
    architecture = run_capture((dpkg_deb, "--field", str(package), "Architecture"))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", architecture):
        raise PortableError(f"invalid Debian architecture {architecture!r}")
    version_match = VERSION_PATTERN.search(package_version)
    if not version_match:
        raise PortableError(
            f"could not determine Thorium version from Debian version "
            f"{package_version!r}"
        )
    extracted = work / "deb"
    run((dpkg_deb, "--extract", str(package), str(extracted)))
    payload = extracted / "opt/chromium.org/thorium"
    validate_payload_tree(payload)
    copy_contents(payload, staging)
    for obsolete in ("cron", "thorium-browser"):
        path = staging / obsolete
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()
    browser = staging / "thorium"
    if not browser.is_file() or browser.is_symlink():
        raise PortableError("Thorium browser executable is missing from the DEB payload")
    if not browser.stat().st_mode & 0o111:
        raise PortableError("Thorium browser file in the DEB is not executable")
    shell = staging / "thorium_shell"
    if not shell.is_file() or shell.is_symlink():
        raise PortableError("Thorium Content Shell is missing from the DEB payload")
    if not shell.stat().st_mode & 0o111:
        raise PortableError("Thorium Content Shell file in the DEB is not executable")
    return version_match.group(1), architecture


def find_unique(root: Path, name: str) -> Path:
    matches = [path for path in root.rglob(name) if path.is_file()]
    if len(matches) != 1:
        raise PortableError(
            f"expected exactly one {name} in the extracted installer; "
            f"found {len(matches)}"
        )
    return matches[0]


def extract_windows(
    package: Path,
    staging: Path,
    work: Path,
    seven_zip: Path | None,
) -> tuple[str, None]:
    executable = find_program("7z", seven_zip)
    installer = work / "installer"
    payload = work / "payload"
    installer.mkdir()
    payload.mkdir()
    run((executable, "x", "-y", f"-o{installer}", str(package)))
    chrome_archive = find_unique(installer, "chrome.7z")
    run((executable, "x", "-y", f"-o{payload}", str(chrome_archive)))
    chrome_bin = payload / "Chrome-bin"
    if not chrome_bin.is_dir():
        directories = [path for path in payload.rglob("Chrome-bin") if path.is_dir()]
        if len(directories) != 1:
            raise PortableError("Chrome-bin was not found in the installer payload")
        chrome_bin = directories[0]
    validate_payload_tree(chrome_bin)
    copy_contents(chrome_bin, staging / "BIN")
    (staging / "USER_DATA").mkdir()
    browser = staging / "BIN/thorium.exe"
    if not browser.is_file() or browser.is_symlink():
        raise PortableError("Thorium browser executable is missing from the installer")
    return windows_version_directory(staging).name, None


def windows_version_directory(staging: Path) -> Path:
    bin_dir = staging / "BIN"
    versions = [
        path
        for path in bin_dir.iterdir()
        if path.is_dir() and VERSION_PATTERN.fullmatch(path.name)
    ]
    if len(versions) != 1:
        raise PortableError(
            "expected exactly one version directory in the Windows payload; "
            f"found {len(versions)}"
        )
    return versions[0]


def windows_shell_path(staging: Path) -> Path:
    version_directory = windows_version_directory(staging)
    matches = [path for path in version_directory.rglob("thorium_shell.exe")]
    if len(matches) != 1:
        raise PortableError(
            "expected exactly one thorium_shell.exe in the Windows version "
            f"directory; found {len(matches)}"
        )
    return matches[0]


def inferred_profile(package: Path) -> str | None:
    upper_name = package.name.upper()
    for marker, label in WINDOWS_PROFILES:
        if marker in upper_name:
            return label
    return None


def profile_name(package: Path, configured: str | None) -> str | None:
    inferred = inferred_profile(package)
    if configured and inferred and configured != inferred:
        raise PortableError(
            f"--profile {configured!r} conflicts with profile {inferred!r} "
            "in the installer filename"
        )
    return configured or inferred


def default_output(
    package: Path,
    platform_name: str,
    version: str,
    architecture: str | None,
    configured_profile: str | None,
) -> Path:
    profile = profile_name(package, configured_profile)
    if platform_name == "windows" and version and profile:
        name = f"Thorium_{profile}_{version}.zip"
    elif platform_name == "windows" and version:
        print(
            "warning: could not infer the Windows SIMD profile; use --profile "
            "to include it in the archive name",
            file=sys.stderr,
        )
        name = f"Thorium_{version}_portable.zip"
    elif platform_name == "linux" and architecture:
        name = f"Thorium_Linux_{architecture}_{version}_portable.zip"
    else:
        name = f"{package.stem}_portable.zip"
    return package.parent / name


def copy_support_files(
    portable_dir: Path,
    staging: Path,
    platform_name: str,
) -> None:
    if platform_name == "linux":
        files = (
            ("README.linux", "README.txt"),
            ("launchers/linux-browser.sh", "THORIUM-PORTABLE"),
            ("launchers/linux-shell.sh", "THORIUM-SHELL"),
            (
                "desktop/thorium-portable.desktop.in",
                "thorium-portable.desktop.example",
            ),
            (
                "desktop/thorium-shell.desktop.in",
                "thorium-shell.desktop.example",
            ),
        )
    else:
        shell_path = windows_shell_path(staging)
        files = (
            ("README.win", "README.txt"),
            ("launchers/windows-browser.cmd", "THORIUM.cmd"),
            ("launchers/windows-shell.cmd", "THORIUM_SHELL.cmd"),
        )
    for source_name, destination_name in files:
        source = portable_dir / source_name
        if not source.is_file():
            raise PortableError(f"portable support file is missing: {source}")
        shutil.copy2(source, staging / destination_name)
    if platform_name == "windows":
        launcher = staging / "THORIUM_SHELL.cmd"
        relative_shell = shell_path.relative_to(staging).as_posix().replace("/", "\\")
        launcher.write_text(
            launcher.read_text(encoding="utf-8").replace(
                "@THORIUM_SHELL_RELATIVE@", relative_shell
            ),
            encoding="utf-8",
        )
    if platform_name == "linux":
        for name in ("THORIUM-PORTABLE", "THORIUM-SHELL"):
            path = staging / name
            path.chmod(path.stat().st_mode | 0o111)


def process_state(process_id: int) -> tuple[bool, str | None]:
    if process_id <= 0:
        return False, None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        )
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        )
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(
            process_query_limited_information, False, process_id
        )
        if not handle:
            # ERROR_INVALID_PARAMETER means the PID does not exist. Other errors,
            # such as access denial, cannot safely prove that a lock is stale.
            return ctypes.get_last_error() != 87, None
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True, None
            if exit_code.value != still_active:
                return False, None
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                return True, None
            identity = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            return True, str(identity)
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False, None
    except PermissionError:
        return True, None
    except OSError:
        return True, None
    try:
        result = subprocess.run(
            ("ps", "-o", "lstart=", "-p", str(process_id)),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "LC_ALL": "C"},
        )
    except OSError:
        return True, None
    identity = result.stdout.strip() if result.returncode == 0 else ""
    return True, identity or None


@contextmanager
def output_lock(output: Path):
    lock = output.with_name(f".{output.name}.lock")
    current_running, current_identity = process_state(os.getpid())
    if not current_running:
        raise PortableError("could not identify the current packaging process")
    for attempt in range(2):
        descriptor, pending_name = tempfile.mkstemp(
            prefix=f".{lock.name}.", suffix=".new", dir=lock.parent
        )
        pending = Path(pending_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as lock_file:
                json.dump(
                    {"pid": os.getpid(), "identity": current_identity}, lock_file
                )
                lock_file.write("\n")
                lock_file.flush()
                os.fsync(lock_file.fileno())
            try:
                os.link(pending, lock)
            except FileExistsError as error:
                lock_error = error
            else:
                acquired_stat = lock.stat()
                break
        finally:
            try:
                pending.unlink()
            except FileNotFoundError:
                pass
        try:
            lock_stat = lock.stat()
        except OSError as stat_error:
            raise PortableError(
                f"could not inspect output lock {lock}: {stat_error}"
            ) from stat_error
        try:
            record = json.loads(lock.read_text(encoding="utf-8"))
            process_id = int(record["pid"])
            recorded_identity = record.get("identity")
            if recorded_identity is not None:
                recorded_identity = str(recorded_identity)
        except (OSError, TypeError, ValueError, KeyError):
            process_id = -1
            recorded_identity = None
        running, observed_identity = process_state(process_id)
        same_process = running and (
            recorded_identity is None
            or observed_identity is None
            or recorded_identity == observed_identity
        )
        if same_process:
            raise PortableError(
                f"another portable packaging process holds the output lock: {lock}"
            ) from lock_error
        if attempt:
            raise PortableError(
                f"stale output lock could not be recovered automatically: {lock}"
            ) from lock_error
        try:
            if lock.stat().st_ino != lock_stat.st_ino:
                continue
            lock.unlink()
        except OSError as cleanup_error:
            raise PortableError(
                f"could not remove stale output lock {lock}: {cleanup_error}"
            ) from cleanup_error
        print(f"warning: removed stale output lock: {lock}", file=sys.stderr)
    else:
        raise PortableError(f"could not acquire output lock: {lock}")

    try:
        yield
    finally:
        try:
            if lock.stat().st_ino != acquired_stat.st_ino:
                print(
                    f"warning: output lock changed ownership and was preserved: {lock}",
                    file=sys.stderr,
                )
            else:
                lock.unlink()
        except FileNotFoundError:
            pass
        except OSError as error:
            print(f"warning: could not remove output lock {lock}: {error}", file=sys.stderr)


def write_zip(staging: Path, output: Path, *, force: bool) -> None:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output_lock(output):
        if output.exists() and not force:
            raise PortableError(
                f"output already exists; pass --force to replace it: {output}"
            )
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".new", dir=output.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
            ) as archive:
                staging_root = staging.resolve()
                for path in sorted(staging.rglob("*")):
                    relative = path.relative_to(staging).as_posix()
                    if path.is_symlink():
                        target = os.readlink(path)
                        try:
                            resolved_target = (path.parent / target).resolve(strict=True)
                        except FileNotFoundError as error:
                            raise PortableError(
                                f"broken symbolic link in package payload: "
                                f"{relative} -> {target}"
                            ) from error
                        if not resolved_target.is_relative_to(staging_root):
                            raise PortableError(
                                f"symbolic link escapes the package payload: "
                                f"{relative} -> {target}"
                            )
                        info = zipfile.ZipInfo(relative)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        archive.writestr(info, os.fsencode(target))
                    elif path.is_dir():
                        info = zipfile.ZipInfo(f"{relative}/")
                        info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
                        archive.writestr(info, b"")
                    elif path.is_file():
                        archive.write(path, relative)
                    else:
                        raise PortableError(
                            f"unsupported special file in package payload: {relative}"
                        )
            if force:
                os.replace(temporary, output)
            else:
                try:
                    os.link(temporary, output)
                except FileExistsError as error:
                    raise PortableError(
                        f"output was created while packaging; pass --force to "
                        f"replace it: {output}"
                    ) from error
        finally:
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()


def main(argv: Sequence[str] | None = None) -> int:
    if sys.version_info < MINIMUM_PYTHON:
        print("error: Python 3.11 or newer is required", file=sys.stderr)
        return 2
    args = parse_arguments(sys.argv[1:] if argv is None else argv)
    try:
        package = args.input.resolve()
        if not package.is_file():
            raise PortableError(f"input package does not exist: {package}")
        if args.output is not None and args.output.resolve() == package:
            raise PortableError("output archive must not replace the input package")
        platform_name = detect_platform(args.platform, package)
        if platform_name == "linux" and args.seven_zip is not None:
            raise PortableError("--seven-zip is only valid for Windows packages")
        if platform_name == "linux" and args.profile is not None:
            raise PortableError("--profile is only valid for Windows packages")
        selected_profile = (
            profile_name(package, args.profile)
            if platform_name == "windows"
            else None
        )
        portable_dir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix="thorium-portable-") as temporary:
            work = Path(temporary)
            staging = work / "staging"
            if platform_name == "linux":
                version, architecture = extract_linux(package, staging, work)
            else:
                staging.mkdir()
                version, architecture = extract_windows(
                    package, staging, work, args.seven_zip
                )
            if args.expected_version and version != args.expected_version:
                raise PortableError(
                    f"version mismatch: expected {args.expected_version!r}, "
                    f"package contains {version!r}"
                )
            copy_support_files(portable_dir, staging, platform_name)
            output = (
                args.output.resolve()
                if args.output is not None
                else default_output(
                    package,
                    platform_name,
                    version,
                    architecture,
                    selected_profile,
                ).resolve()
            )
            write_zip(staging, output, force=args.force)
        print(f"Portable archive: {output}")
    except (PortableError, OSError, shutil.Error) as error:
        print(f"{Path(sys.argv[0]).name}: {error}", file=sys.stderr)
        return 111
    except KeyboardInterrupt:
        print(f"\n{Path(sys.argv[0]).name}: interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
