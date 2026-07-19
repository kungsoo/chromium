## Thorium x86 build profiles

This directory contains build argument files for Thorium's x86 CPU profiles.

Build argument files select exactly one `thorium_x86_profile`. Supported
profiles are `sse2`, `sse3`, `sse4_1`, `sse4_2`, `avx`, `avx_fma`, `avx2`,
`avx2_fma`, and `avx512_skx`. The profile is the single source of truth for
C/C++, Rust, installer labels, and Linux package suffixes.

The release AVX2 configuration uses `avx2_fma`; the minimal `avx2` profile is
available for compatibility validation without implicitly requiring FMA or
F16C. Profiles use explicit feature flags and never use `-march` aliases that
would silently add AES, PCLMUL, BMI, LZCNT, POPCNT, or other CPU capabilities.

It also contains configuration files for macOS and ChromiumOS/ThoriumOS.

The GN default for ordinary x86 targets is SSE3. Thorium's standard desktop
release argument files explicitly select
[AVX](https://en.wikipedia.org/wiki/Advanced_Vector_Extensions); compatibility
and higher-performance releases select the profile identified in their names.

### Other info

For Android or Raspberry Pi builds, see the [//arm](../arm) directory.
