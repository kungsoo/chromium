#!/usr/bin/env python3

# Copyright (c) 2026 Alex313031 and gz83.

"""Copy Thorium overlays and apply its patch series to Chromium."""

import argparse
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
from typing import Sequence


EXIT_FAILURE = 111
PGO_GS_URL = "chromium-optimization-profiles/pgo_profiles"
OVERLAY_COMPONENTS = ("chrome", "components", "content", "third_party", "ui")
SIMD_PROFILES = {
    "avx512": ("AVX512", "wrapper-avx512", None),
    "avx2": ("AVX2", "wrapper-avx2", None),
    "sse4": ("SSE4.1", "wrapper-sse4", None),
    "sse3": ("SSE3", "wrapper-sse3", "win32"),
    "sse2": ("SSE2", "wrapper-sse2", "win32"),
}


class SetupError(RuntimeError):
    """An expected setup or copy failure."""


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


def thor_ver_source(thorium_root: Path, profile: str) -> Path:
    if profile == "woa":
        return thorium_root / "arm" / "thor_ver"
    if profile in SIMD_PROFILES:
        source_name, _, _ = SIMD_PROFILES[profile]
        return thorium_root / "other" / source_name / "thor_ver"
    return thorium_root / "infra" / "thor_ver"


def pak_source(thorium_root: Path, profile: str) -> Path:
    filename = "pak_arm64" if profile == "raspi" else "pak"
    return thorium_root / "pak_src" / "binaries" / filename


def profile_downloads_pgo(profile: str) -> bool:
    if profile in ("woa", "android"):
        return True
    if profile in SIMD_PROFILES:
        return SIMD_PROFILES[profile][2] is not None
    return False


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy Thorium files and patches over the Chromium tree.",
        epilog=(
            "For optimized LLVM builds, run infra/build_llvm.py after this "
            "setup script and before building."
        ),
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
        help="Thorium repository root (default: THOR_DIR or ~/thorium)",
    )
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument(
        "--mac",
        "--macos",
        action="store_const",
        const="mac",
        dest="profile",
        help="prepare a macOS build",
    )
    profiles.add_argument(
        "--raspi",
        "--arm64",
        action="store_const",
        const="raspi",
        dest="profile",
        help="prepare a Raspberry Pi ARM64 build",
    )
    profiles.add_argument(
        "--woa",
        action="store_const",
        const="woa",
        dest="profile",
        help="prepare a Windows on ARM64 build",
    )
    for option, profile, description in (
        ("--avx512", "avx512", "an AVX-512"),
        ("--avx2", "avx2", "an AVX2"),
        ("--sse4", "sse4", "an SSE4.1"),
        ("--sse3", "sse3", "an SSE3"),
        ("--sse2", "sse2", "a 32-bit SSE2"),
    ):
        profiles.add_argument(
            option,
            action="store_const",
            const=profile,
            dest="profile",
            help=f"prepare {description} build",
        )
    profiles.add_argument(
        "--android",
        action="store_const",
        const="android",
        dest="profile",
        help="prepare an Android build",
    )
    profiles.add_argument(
        "--cros",
        action="store_const",
        const="cros",
        dest="profile",
        help="prepare a ChromiumOS build",
    )
    parser.set_defaults(profile="default")
    return parser.parse_args(argv)


def run(command: Sequence[str], cwd: Path) -> None:
    printable = subprocess.list2cmdline(command)
    print(f"\n[{cwd}] {printable}", flush=True)
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except OSError as error:
        raise SetupError(f"could not run {printable}: {error}") from error
    except subprocess.CalledProcessError as error:
        raise SetupError(
            f"command failed with exit code {error.returncode}: {printable}"
        ) from error


def require_directory(path: Path, description: str) -> None:
    if not path.is_dir():
        raise SetupError(f"{description} directory does not exist: {path}")


def require_checkout(path: Path, description: str) -> None:
    require_directory(path, description)
    if not (path / ".git").exists():
        raise SetupError(f"{description} is not a Git checkout: {path}")


def require_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise SetupError(f"{description} does not exist: {path}")


def copy_file(source: Path, destination: Path) -> None:
    require_file(source, "source file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Copying {source} -> {destination}")
    try:
        # Keep executable mode bits, but refresh the destination timestamp so
        # Ninja observes an overlaid source file as changed.
        shutil.copy(source, destination)
    except OSError as error:
        raise SetupError(
            f"failed to copy {source} to {destination}: {error}"
        ) from error


def copy_tree(source: Path, destination: Path) -> None:
    require_directory(source, "source")
    print(f"Copying directory {source} -> {destination}")
    try:
        shutil.copytree(
            source,
            destination,
            copy_function=shutil.copy,
            dirs_exist_ok=True,
        )
    except OSError as error:
        raise SetupError(
            f"failed to copy {source} to {destination}: {error}"
        ) from error


def remove_file(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    print(f"Removing {path}")
    try:
        path.unlink()
    except PermissionError:
        try:
            path.chmod(stat.S_IWRITE)
            path.unlink()
        except OSError as error:
            raise SetupError(f"failed to remove {path}: {error}") from error
    except OSError as error:
        raise SetupError(f"failed to remove {path}: {error}") from error


def read_art(path: Path) -> None:
    require_file(path, "ASCII art")
    try:
        print(f"\n{path.read_text(encoding='utf-8')}")
    except (OSError, UnicodeError) as error:
        raise SetupError(f"failed to read {path}: {error}") from error


def apply_patch_series(
    thorium_root: Path, chromium_src: Path, profile: str
) -> None:
    script = thorium_root / "patch_scripts" / "series" / "apply_series.py"
    condition = {
        "woa": "woa",
        "raspi": "raspi",
        "sse2": "sse2",
    }.get(profile)
    command = [
        sys.executable,
        str(script),
        "--thorium-root",
        str(thorium_root),
        "--source-tree",
        str(chromium_src),
        "--apply",
    ]
    if condition:
        command.extend(("--condition", condition))
    print("\nApplying Thorium patch series")
    run(command, thorium_root)


def apply_grd_rebase(thorium_root: Path, chromium_src: Path) -> None:
    grd_rebase = thorium_root / "patch_scripts" / "grd_rebase"
    config = grd_rebase / "config"
    sync_script = grd_rebase / "sync_grd_strings.py"
    merge_script = grd_rebase / "merge_thorium_xtb.py"

    print("\nApplying Thorium GRD/XTB rebase")
    run(
        [
            sys.executable,
            str(sync_script),
            str(chromium_src),
            "--file-allowlist",
            str(config / "file_allowlist.csv"),
            "--message-allowlist",
            str(config / "message_allowlist.csv"),
            "--feature-message-ownership",
            str(config / "feature_patch_message_ownership.csv"),
        ],
        thorium_root,
    )
    run([sys.executable, str(merge_script), str(chromium_src)], thorium_root)


def download_pgo(chromium_src: Path, target: str) -> None:
    updater = chromium_src / "tools" / "update_pgo_profiles.py"
    print(f"\nDownloading Chromium PGO profile: {target}")
    run(
        [
            sys.executable,
            str(updater),
            f"--target={target}",
            "update",
            f"--gs-url-base={PGO_GS_URL}",
        ],
        chromium_src,
    )


def copy_version_metadata(
    thorium_root: Path,
    chromium_src: Path,
    source_directory: Path,
    wrapper_name: str | None = None,
) -> None:
    text_resources = chromium_src / "ui" / "webui" / "resources" / "text"
    copy_file(
        source_directory / "thorium_version.txt",
        text_resources / "thorium_version.txt",
    )
    if wrapper_name and sys.platform.startswith("linux"):
        copy_file(
            thorium_root / "other" / "thor_ver_linux" / wrapper_name,
            chromium_src / "chrome" / "installer" / "linux" / "common" / "wrapper",
        )


def prepare_profile(profile: str, thorium_root: Path, chromium_src: Path) -> None:
    if profile == "default":
        return
    text_resources = chromium_src / "ui" / "webui" / "resources" / "text"
    if profile == "mac":
        print("\nCopying files for macOS")
        copy_file(
            thorium_root / "other" / "Mac" / "thorium_version.txt",
            text_resources / "thorium_version.txt",
        )
        return
    if profile == "raspi":
        print("\nCopying Raspberry Pi ARM64 files")
        copy_tree(
            thorium_root / "arm" / "third_party" / "widevine",
            chromium_src / "third_party" / "widevine",
        )
        copy_file(
            thorium_root / "arm" / "thorium_version.txt",
            text_resources / "thorium_version.txt",
        )
        copy_file(
            thorium_root / "other" / "thor_ver_linux" / "wrapper-raspi",
            chromium_src / "chrome" / "installer" / "linux" / "common" / "wrapper",
        )
        read_art(thorium_root / "logos" / "raspi_ascii_art.txt")
        return
    if profile == "woa":
        print("\nCopying Windows on ARM64 files")
        copy_version_metadata(thorium_root, chromium_src, thorium_root / "arm")
        download_pgo(chromium_src, "win-arm64")
        return

    if profile in SIMD_PROFILES:
        source_name, wrapper_name, pgo_target = SIMD_PROFILES[profile]
        print(f"\nCopying {source_name} build files")
        copy_version_metadata(
            thorium_root,
            chromium_src,
            thorium_root / "other" / source_name,
            wrapper_name,
        )
        if pgo_target:
            download_pgo(chromium_src, pgo_target)
        return

    if profile == "android":
        print("\nRemoving replaced Android launcher resources")
        android_resources = (
            "chrome/android/java/res_base/drawable-v26/ic_launcher.xml",
            "chrome/android/java/res_base/drawable-v26/ic_launcher_round.xml",
            "chrome/android/java/res_chromium_base/mipmap-mdpi/"
            "layered_app_icon_background.png",
            "chrome/android/java/res_chromium_base/mipmap-xhdpi/"
            "layered_app_icon_background.png",
            "chrome/android/java/res_chromium_base/mipmap-xxxhdpi/"
            "layered_app_icon_background.png",
            "chrome/android/java/res_chromium_base/mipmap-nodpi/"
            "layered_app_icon_foreground.xml",
            "chrome/android/java/res_chromium_base/mipmap-hdpi/"
            "layered_app_icon_background.png",
            "chrome/android/java/res_chromium_base/mipmap-xxhdpi/"
            "layered_app_icon_background.png",
        )
        for relative_path in android_resources:
            remove_file(chromium_src / relative_path)
        download_pgo(chromium_src, "android-arm32")
        return
    if profile == "cros":
        print("\nCopying ChromiumOS build files")
        copy_file(
            thorium_root / "other" / "CrOS" / "thorium_version.txt",
            text_resources / "thorium_version.txt",
        )
        return


def validate_inputs(profile: str, thorium_root: Path, chromium_src: Path) -> None:
    require_checkout(chromium_src, "Chromium")
    require_file(chromium_src / "BUILD.gn", "Chromium root BUILD.gn")

    for component in OVERLAY_COMPONENTS:
        require_directory(thorium_root / "src" / component, "overlay source")
    for directory in (
        thorium_root / "thorium_shell",
        thorium_root / "pak_src" / "binaries" / "pak-win",
    ):
        require_directory(directory, "Thorium setup source")
    for path in (
        pak_source(thorium_root, profile),
        thor_ver_source(thorium_root, profile),
        thorium_root / "logos" / "thorium_ascii_art.txt",
        thorium_root / "patch_scripts" / "series" / "apply_series.py",
        thorium_root / "patch_scripts" / "grd_rebase" / "sync_grd_strings.py",
        thorium_root / "patch_scripts" / "grd_rebase" / "merge_thorium_xtb.py",
        thorium_root
        / "patch_scripts"
        / "grd_rebase"
        / "config"
        / "file_allowlist.csv",
        thorium_root
        / "patch_scripts"
        / "grd_rebase"
        / "config"
        / "message_allowlist.csv",
        thorium_root
        / "patch_scripts"
        / "grd_rebase"
        / "config"
        / "feature_patch_message_ownership.csv",
    ):
        require_file(path, "Thorium setup input")

    profile_files: tuple[Path, ...] = ()
    profile_directories: tuple[Path, ...] = ()
    if profile == "mac":
        profile_files = (thorium_root / "other" / "Mac" / "thorium_version.txt",)
    elif profile == "raspi":
        profile_directories = (thorium_root / "arm" / "third_party" / "widevine",)
        profile_files = (
            thorium_root / "arm" / "thorium_version.txt",
            thorium_root / "other" / "thor_ver_linux" / "wrapper-raspi",
            thorium_root / "logos" / "raspi_ascii_art.txt",
        )
    elif profile == "woa":
        profile_files = (
            thorium_root / "arm" / "thorium_version.txt",
        )
    elif profile in SIMD_PROFILES:
        source_name, wrapper_name, _ = SIMD_PROFILES[profile]
        profile_files = (
            thorium_root / "other" / source_name / "thorium_version.txt",
        )
        if sys.platform.startswith("linux"):
            profile_files += (
                thorium_root / "other" / "thor_ver_linux" / wrapper_name,
            )
    elif profile == "cros":
        profile_files = (
            thorium_root / "other" / "CrOS" / "thorium_version.txt",
        )
    elif profile not in ("default", "android"):
        raise SetupError(f"unsupported setup profile: {profile}")

    if profile_downloads_pgo(profile):
        profile_files += (
            chromium_src / "tools" / "update_pgo_profiles.py",
            chromium_src
            / "third_party"
            / "depot_tools"
            / "download_from_google_storage.py",
        )

    for directory in profile_directories:
        require_directory(directory, "profile source")
    for path in profile_files:
        require_file(path, "profile input")


def setup(thorium_root: Path, chromium_src: Path, profile: str) -> None:
    thorium_root = thorium_root.expanduser().resolve()
    chromium_src = chromium_src.expanduser().resolve()

    require_directory(thorium_root, "Thorium")
    validate_inputs(profile, thorium_root, chromium_src)

    output = chromium_src / "out" / "thorium"
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise SetupError(f"failed to create {output}: {error}") from error

    print("\nCopying Thorium source overlays over the Chromium tree")
    for component in OVERLAY_COMPONENTS:
        copy_tree(thorium_root / "src" / component, chromium_src / component)
    copy_tree(thorium_root / "thorium_shell", output)
    copy_file(pak_source(thorium_root, profile), output / "pak")
    copy_tree(thorium_root / "pak_src" / "binaries" / "pak-win", output)

    apply_patch_series(thorium_root, chromium_src, profile)
    apply_grd_rebase(thorium_root, chromium_src)

    print("\nCopying build metadata to out/thorium")
    copy_file(thor_ver_source(thorium_root, profile), output / "thor_ver")
    prepare_profile(profile, thorium_root, chromium_src)

    print("\nDone!")
    read_art(thorium_root / "logos" / "thorium_ascii_art.txt")
    print("\nEnjoy Thorium!\n")


def main(argv: Sequence[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print("error: Python 3.11 or newer is required", file=sys.stderr)
        return 2
    if platform.system() not in ("Linux", "Darwin", "Windows"):
        print("error: only Linux, macOS, and Windows are supported", file=sys.stderr)
        return 2

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        setup(args.thorium_root, args.chromium_src, args.profile)
    except SetupError as error:
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
