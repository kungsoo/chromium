#!/usr/bin/env python3

# Copyright (c) 2026 Alex313031 and gz83.

"""Check whether this machine can run a Thorium x86 build profile."""

import argparse
import ctypes
import mmap
from pathlib import Path
import platform
import re
import sys
from typing import Sequence


MINIMUM_PYTHON = (3, 11)
DEFAULT_PROFILE = "sse3"

FEATURE_NAMES = {
    "sse2": "SSE2",
    "sse3": "SSE3",
    "ssse3": "SSSE3",
    "sse4_1": "SSE4.1",
    "sse4_2": "SSE4.2",
    "avx": "AVX with operating-system state support",
    "fma": "FMA",
    "f16c": "F16C",
    "avx2": "AVX2",
    "avx512f": "AVX-512 Foundation",
    "avx512cd": "AVX-512 Conflict Detection",
    "avx512vl": "AVX-512 Vector Length",
    "avx512bw": "AVX-512 Byte and Word",
    "avx512dq": "AVX-512 Doubleword and Quadword",
}

# Keep this table synchronized with build/config/compiler_opt.gni in
# other/thorium-build-config-and-simd.patch. Tuning flags do not add runtime
# requirements and therefore do not belong here.
PROFILE_REQUIREMENTS = {
    "none": (),
    "sse2": ("sse2",),
    "sse3": ("sse3",),
    "sse4_1": ("sse3", "ssse3", "sse4_1"),
    "sse4_2": ("sse3", "ssse3", "sse4_1", "sse4_2"),
    "avx": ("sse3", "avx"),
    "avx_fma": ("sse3", "avx", "fma"),
    "avx2": ("sse3", "avx", "avx2"),
    "avx2_fma": ("sse3", "avx", "avx2", "fma", "f16c"),
    "avx512_skx": (
        "sse3",
        "avx",
        "avx2",
        "fma",
        "f16c",
        "avx512f",
        "avx512cd",
        "avx512vl",
        "avx512bw",
        "avx512dq",
    ),
}


class CpuDetectionError(RuntimeError):
    """Raised when reliable CPU feature detection is unavailable."""


class ExecutableCode:
    """Own a small executable buffer used for CPUID or XGETBV."""

    def __init__(self, code: bytes) -> None:
        self._mapping: mmap.mmap | None = None
        self._address = 0
        if sys.platform == "win32":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            virtual_alloc = kernel32.VirtualAlloc
            virtual_alloc.argtypes = (
                ctypes.c_void_p,
                ctypes.c_size_t,
                ctypes.c_ulong,
                ctypes.c_ulong,
            )
            virtual_alloc.restype = ctypes.c_void_p
            self._virtual_free = kernel32.VirtualFree
            self._virtual_free.argtypes = (
                ctypes.c_void_p,
                ctypes.c_size_t,
                ctypes.c_ulong,
            )
            self._virtual_free.restype = ctypes.c_int
            self._address = virtual_alloc(None, len(code), 0x3000, 0x04) or 0
            if not self._address:
                raise CpuDetectionError(
                    f"VirtualAlloc failed with error {ctypes.get_last_error()}"
                )
            ctypes.memmove(self._address, code, len(code))
            virtual_protect = kernel32.VirtualProtect
            virtual_protect.argtypes = (
                ctypes.c_void_p,
                ctypes.c_size_t,
                ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong),
            )
            virtual_protect.restype = ctypes.c_int
            old_protection = ctypes.c_ulong()
            if not virtual_protect(
                self._address, len(code), 0x20, ctypes.byref(old_protection)
            ):
                error = ctypes.get_last_error()
                self.close()
                raise CpuDetectionError(
                    f"VirtualProtect failed with error {error}"
                )
        else:
            self._mapping = mmap.mmap(
                -1,
                len(code),
                flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS,
                prot=mmap.PROT_READ | mmap.PROT_WRITE,
            )
            self._mapping.write(code)
            self._address = ctypes.addressof(ctypes.c_char.from_buffer(self._mapping))
            mprotect = ctypes.CDLL(None, use_errno=True).mprotect
            mprotect.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int)
            mprotect.restype = ctypes.c_int
            if mprotect(
                self._address,
                len(code),
                mmap.PROT_READ | mmap.PROT_EXEC,
            ) != 0:
                error = ctypes.get_errno()
                self.close()
                raise CpuDetectionError(f"mprotect failed with error {error}")

    @property
    def address(self) -> int:
        return self._address

    def close(self) -> None:
        if self._mapping is not None:
            self._mapping.close()
            self._mapping = None
        elif self._address:
            self._virtual_free(self._address, 0, 0x8000)
        self._address = 0


def machine_family() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "x64"
    if machine in {"i386", "i486", "i586", "i686", "x86"}:
        return "x86"
    return machine or "unknown"


def native_functions():
    family = machine_family()
    pointer_bits = ctypes.sizeof(ctypes.c_void_p) * 8
    if family == "x64" and pointer_bits == 64:
        if sys.platform == "win32":
            cpuid_code = bytes.fromhex(
                "53 89 c8 89 d1 0f a2 41 89 00 41 89 58 04 "
                "41 89 48 08 41 89 50 0c 5b c3"
            )
            xgetbv_code = bytes.fromhex("0f 01 d0 48 c1 e2 20 48 09 d0 c3")
        else:
            cpuid_code = bytes.fromhex(
                "53 49 89 d0 89 f8 89 f1 0f a2 41 89 00 41 89 58 04 "
                "41 89 48 08 41 89 50 0c 5b c3"
            )
            xgetbv_code = bytes.fromhex("89 f9 0f 01 d0 48 c1 e2 20 48 09 d0 c3")
    elif family == "x86" and pointer_bits == 32:
        cpuid_code = bytes.fromhex(
            "53 56 8b 44 24 0c 8b 4c 24 10 0f a2 8b 74 24 14 "
            "89 06 89 5e 04 89 4e 08 89 56 0c 5e 5b c3"
        )
        xgetbv_code = bytes.fromhex("8b 4c 24 04 0f 01 d0 c3")
    else:
        raise CpuDetectionError(
            f"x86 CPUID is unavailable on this {family} host "
            f"with a {pointer_bits}-bit Python interpreter"
        )

    allocated: list[ExecutableCode] = []
    try:
        cpuid_memory = ExecutableCode(cpuid_code)
        allocated.append(cpuid_memory)
        xgetbv_memory = ExecutableCode(xgetbv_code)
        allocated.append(xgetbv_memory)
        cpuid_type = ctypes.CFUNCTYPE(
            None,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32),
        )
        xgetbv_type = ctypes.CFUNCTYPE(ctypes.c_uint64, ctypes.c_uint32)
        return (
            cpuid_memory,
            cpuid_type(cpuid_memory.address),
            xgetbv_memory,
            xgetbv_type(xgetbv_memory.address),
        )
    except Exception as error:
        for memory in reversed(allocated):
            memory.close()
        if isinstance(error, CpuDetectionError):
            raise
        raise CpuDetectionError(
            f"cannot create the native CPU feature detector: {error}"
        ) from error


def detect_x86_features() -> set[str]:
    cpuid_memory, cpuid_function, xgetbv_memory, xgetbv_function = (
        native_functions()
    )
    registers = (ctypes.c_uint32 * 4)()

    def cpuid(leaf: int, subleaf: int = 0) -> tuple[int, int, int, int]:
        cpuid_function(leaf, subleaf, registers)
        return registers[0], registers[1], registers[2], registers[3]

    try:
        maximum_leaf = cpuid(0)[0]
        if maximum_leaf < 1:
            raise CpuDetectionError("the processor does not expose CPUID leaf 1")

        _, _, leaf1_ecx, leaf1_edx = cpuid(1)
        features: set[str] = set()
        leaf1_bits = {
            "sse2": (leaf1_edx, 26),
            "sse3": (leaf1_ecx, 0),
            "ssse3": (leaf1_ecx, 9),
            "fma": (leaf1_ecx, 12),
            "sse4_1": (leaf1_ecx, 19),
            "sse4_2": (leaf1_ecx, 20),
            "f16c": (leaf1_ecx, 29),
        }
        for name, (value, bit) in leaf1_bits.items():
            if value & (1 << bit):
                features.add(name)

        has_xsave = bool(leaf1_ecx & (1 << 26))
        has_osxsave = bool(leaf1_ecx & (1 << 27))
        has_hardware_avx = bool(leaf1_ecx & (1 << 28))
        xcr0 = xgetbv_function(0) if has_xsave and has_osxsave else 0
        avx_usable = has_hardware_avx and xcr0 & 0x6 == 0x6
        if avx_usable:
            features.add("avx")
        else:
            features.difference_update({"fma", "f16c"})

        if maximum_leaf >= 7:
            _, leaf7_ebx, _, _ = cpuid(7)
            if avx_usable and leaf7_ebx & (1 << 5):
                features.add("avx2")
            avx512_usable = avx_usable and xcr0 & 0xE6 == 0xE6
            avx512_bits = {
                "avx512f": 16,
                "avx512dq": 17,
                "avx512cd": 28,
                "avx512bw": 30,
                "avx512vl": 31,
            }
            if avx512_usable:
                for name, bit in avx512_bits.items():
                    if leaf7_ebx & (1 << bit):
                        features.add(name)
        return features
    finally:
        xgetbv_memory.close()
        cpuid_memory.close()


def profile_from_args_file(path: Path) -> str:
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as error:
        raise CpuDetectionError(f"cannot read {path}: {error}") from error
    assignments = re.findall(
        r'^\s*thorium_x86_profile\s*=\s*"([^"]+)"',
        contents,
        flags=re.MULTILINE,
    )
    if not assignments:
        raise CpuDetectionError(f"{path} does not set thorium_x86_profile")
    profile = assignments[-1]
    if profile not in PROFILE_REQUIREMENTS:
        raise CpuDetectionError(
            f"{path} contains unsupported thorium_x86_profile {profile!r}"
        )
    return profile


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether this host can run a Thorium x86 profile.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--profile",
        choices=tuple(PROFILE_REQUIREMENTS),
        help=f"profile to check (default: {DEFAULT_PROFILE})",
    )
    mode.add_argument(
        "--args-file",
        type=Path,
        help="read the last thorium_x86_profile assignment from an args.gn file",
    )
    mode.add_argument(
        "--list-profiles",
        action="store_true",
        help="list known profiles and their requirements, then exit",
    )
    return parser.parse_args(argv)


def list_profiles() -> None:
    for profile, requirements in PROFILE_REQUIREMENTS.items():
        names = ", ".join(FEATURE_NAMES[item] for item in requirements)
        print(f"{profile:12} {names or 'No additional x86 requirement'}")


def main(argv: Sequence[str] | None = None) -> int:
    if sys.version_info < MINIMUM_PYTHON:
        print("error: Python 3.11 or newer is required", file=sys.stderr)
        return 2

    arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
    if arguments.list_profiles:
        list_profiles()
        return 0

    try:
        profile = (
            profile_from_args_file(arguments.args_file)
            if arguments.args_file
            else arguments.profile or DEFAULT_PROFILE
        )
        requirements = PROFILE_REQUIREMENTS[profile]
        print(f"Host: {platform.system()} {platform.machine()}")
        print(f"Thorium profile: {profile}")

        if not requirements:
            print("SUPPORTED: this profile adds no Thorium x86 ISA requirement.")
            return 0

        available = detect_x86_features()
        supported = all(item in available for item in requirements)
        for feature in requirements:
            status = "PASS" if feature in available else "FAIL"
            print(f"[{status}] {FEATURE_NAMES[feature]}")

        if not supported:
            print(
                f"UNSUPPORTED: this machine cannot safely run the {profile} build.",
                file=sys.stderr,
            )
            return 1
        print(f"SUPPORTED: this machine can run the {profile} build.")
        return 0
    except CpuDetectionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
