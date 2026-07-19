#!/usr/bin/env python3

# Copyright (c) 2026 Alex313031 and gz83.

"""Build Thorium's optimized LLVM toolchain on Linux."""

import argparse
import ast
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys


UPSTREAM_SCRIPT = Path("tools/clang/scripts/build.py")
BUILD_ARGUMENTS = (
    "--bootstrap",
    "--without-android",
    "--without-fuchsia",
    "--disable-asserts",
    "--thinlto",
    "--pgo",
    "--bolt",
    "--llvm-force-head-revision",
)


class BuildLlvmError(RuntimeError):
    """Raised when the optimized LLVM build cannot be started safely."""


def default_chromium_src() -> Path:
    configured = os.environ.get("CR_DIR") or os.environ.get("CR_SRC_DIR")
    return Path(configured).expanduser() if configured else Path.home() / "chromium/src"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the optimized LLVM/Clang, LLD and Polly toolchain required "
            "by Thorium's LLVM optimization patch."
        )
    )
    parser.add_argument(
        "--chromium-src",
        type=Path,
        default=default_chromium_src(),
        help="Chromium src directory (default: CR_DIR, CR_SRC_DIR, or ~/chromium/src)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the checkout and print the command without running it",
    )
    mode.add_argument(
        "--upstream-help",
        action="store_true",
        help="show help from Chromium's LLVM build script",
    )
    return parser.parse_args()


def required_patch_features(source: str) -> dict[str, bool]:
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise BuildLlvmError(f"cannot parse Chromium's LLVM build script: {error}") from error

    main = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        ),
        None,
    )
    if main is None:
        return {
            "Polly LLVM project": False,
            "mimalloc integration": False,
            "Linux-only policy": False,
            "mandatory bootstrap policy": False,
            "checkout policy": False,
        }

    projects_include_polly = any(
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "projects" for target in node.targets)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        and "polly" in node.value.value.split(";")
        for node in ast.walk(main)
    )
    defines_mimalloc_builder = any(
        isinstance(node, ast.FunctionDef) and node.name == "BuildLibMimalloc"
        for node in tree.body
    )
    calls_mimalloc_builder = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "BuildLibMimalloc"
        for node in ast.walk(main)
    )
    direct_conditions = {
        ast.unparse(node.test) for node in main.body if isinstance(node, ast.If)
    }
    return {
        "Polly LLVM project": projects_include_polly,
        "mimalloc integration": defines_mimalloc_builder and calls_mimalloc_builder,
        "Linux-only policy": "not sys.platform.startswith('linux')" in direct_conditions,
        "mandatory bootstrap policy": "not args.bootstrap" in direct_conditions,
        "checkout policy": "args.skip_checkout" in direct_conditions,
    }


def validate_checkout(chromium_src: Path, *, require_patch: bool) -> Path:
    if platform.system() != "Linux":
        raise BuildLlvmError("the optimized LLVM toolchain build is supported only on Linux")

    chromium_src = chromium_src.resolve()
    script = chromium_src / UPSTREAM_SCRIPT
    if not (chromium_src / "BUILD.gn").is_file() or not script.is_file():
        raise BuildLlvmError(f"not a Chromium src checkout: {chromium_src}")

    if require_patch:
        source = script.read_text(encoding="utf-8")
        patch_features = required_patch_features(source)
        missing = [name for name, present in patch_features.items() if not present]
        if missing:
            raise BuildLlvmError(
                "the Chromium checkout lacks a required optimized-toolchain "
                f"integration: {missing[0]}"
            )
    return chromium_src


def main() -> int:
    args = parse_args()
    try:
        chromium_src = validate_checkout(
            args.chromium_src,
            require_patch=not args.upstream_help,
        )
        command = [sys.executable, str(UPSTREAM_SCRIPT)]
        if args.upstream_help:
            command.append("--help")
        else:
            command.extend(BUILD_ARGUMENTS)

        print(f"Chromium source: {chromium_src}")
        print(f"Command: {shlex.join(command)}")
        if args.dry_run:
            return 0

        returncode = subprocess.run(command, cwd=chromium_src).returncode
        return returncode if returncode >= 0 else 128 + abs(returncode)
    except BuildLlvmError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(
            f"error: LLVM build preparation or launch failed: {error}",
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        print("\nLLVM build interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
