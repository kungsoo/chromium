# Debug build GN arguments

The `.gn` files in this directory are maintained examples for Thorium Debug,
Release-with-DCHECK, and Release-with-symbols builds. GN itself is the source of truth for available arguments and
their defaults. After generating an output directory, inspect an argument with:

```shell
gn args out/thorium --list=ARGUMENT_NAME
```

Do not copy an args file to a different operating system or CPU without
reviewing its platform-specific values.

## Files

- `linux_x64_debug_args.gn`: Linux x64 debug build.
- `win_x64_debug_args.gn`: Windows x64 debug build.
- `mac_x64_debug_args.gn`: macOS x64 debug build.
- `mac_arm64_debug_args.gn`: macOS ARM64 debug build.
- `linux_x64_release_dcheck_args.gn`: Linux x64 optimized Release build with
  DCHECKs retained.
- `win_x64_release_dcheck_args.gn`: Windows x64 optimized Release build with
  DCHECKs retained.
- `win_x64_release_symbols_args.gn`: Windows x64 Release build retaining
  balanced symbols for crash analysis.

## Build identity and diagnostics

- `target_os`, `target_cpu`, and `v8_target_cpu` select the target platform.
- `is_debug = true` enables Chromium's debug build configuration.
- `is_official_build = false` keeps these as developer builds.
- `dcheck_always_on = true` retains DCHECKs in the Release DCHECK files.
- `symbol_level`, `v8_symbol_level`, and `blink_symbol_level` control debug
  information. Level 2 is the most detailed and expensive.
- `is_component_build = false` produces the non-component layout used by the
  packaging script.
- `enable_stripping = false` retains symbols in applicable outputs.
- `exclude_unwind_tables = false` retains unwind information.
- `use_debug_fission = true` is Linux-specific and places debug information in
  split files.
- `enable_iterator_debugging` and `win_enable_cfg_guards` are Windows-specific
  debugging and security choices.
- `thorium_debug` controls Thorium's additional debug-mode behavior where that
  patch is present.

## Optimization controls

- `thorium_x86_profile` selects Thorium's x86 ISA profile. It must match the
  processors on which the resulting binaries will run.
- `use_thin_lto` and `thin_lto_enable_optimizations` are disabled in true Debug
  configurations to keep linking and debugging practical; Release DCHECK
  configurations may enable them.
- `thin_lto_enable_cache = false` avoids retaining a local ThinLTO cache.
- `chrome_pgo_phase = 0` disables PGO for these local debugging builds.
- `init_stack_vars_zero = false` is an explicit Thorium build-policy choice and
  has security implications; do not copy it into unrelated builds casually.
- `optimize_webui = false` favors inspectable WebUI output. The macOS debug
  examples currently keep optimized WebUI resources.

WebRTC's `rtc_enable_avx2` is intentionally not pinned here. Chromium enables
the optional AVX2 implementation with Clang and selects suitable code at
runtime; that setting does not define Thorium's process-wide minimum ISA.

## Media and DRM

The media arguments enable Thorium's supported codec and WebRTC features,
including FFmpeg, proprietary codec branding, HLS, HEVC, Dolby-related parser
support, DTS, MPEG-H, and MPEG-TS parsing. Availability still depends on the
target platform and the corresponding Thorium patches.

`enable_library_cdms` and `enable_widevine` enable the library CDM integration.
`bundle_widevine_cdm` controls whether a prebuilt payload is included:

- Linux debug examples leave bundling disabled so externally installed
  Widevine remains possible.
- macOS debug examples bundle the repository's matching prebuilt payload.
- Windows debug examples currently leave bundling disabled.

These settings do not grant Widevine redistribution rights and must remain
consistent with the files available for the selected architecture.

## Platform-specific notes

- `use_system_xcode = true` is required for normal public macOS builds.
- `use_vaapi = true` is used by the Linux examples.
- `rtc_build_with_neon = true` is used by the macOS ARM64 example.
- `enable_linux_installer` is enabled only by the Linux Release DCHECK build.
  Debug installer outputs are not supported as distributable packages.
- `enable_updater` and `enable_update_notifications` are disabled by the macOS
  debug examples.

## Maintenance rule

Keep only intentional overrides in these files. When updating Chromium, run GN
against every maintained args file and remove arguments that have disappeared
or simply duplicate a changed upstream default without representing a Thorium
policy.
