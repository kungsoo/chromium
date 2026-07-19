# Android args.gn files

`debug_args.gn` targets ARM64. Use the other argument files as references when
creating an x86, x64, or ARM32 debug configuration; do not duplicate Chromium's
ARM ABI or microarchitecture settings in these files.

`android_full_debug = true` can be used for a more complete debug build.

`chromium_x64_release_args.gn` is for an official, non-debug vanilla Chromium
x64 build. It is separate from Thorium's architecture-specific release
configurations.

API keys enable location-related features but do not provide desktop-style
Google Sync in Android Chromium because access is subject to additional Google
service restrictions.

Run `python3 setup.py --android` from the Thorium checkout. Then change to the
Chromium `src` directory and create or edit the Android output configuration:

```shell
gn args out/thorium
```

Paste the appropriate `arm32_args.gn`, `arm64_args.gn`, `x86_args.gn`, or
`x64_args.gn` contents into the editor for the selected Android architecture.

### Common checkout and GN commands

```shell
git fetch --tags
git rebase-update
gclient runhooks
gn ls out/thorium
git show-ref
```

Use `python3 version.py` from the Thorium checkout for revision and profile
preparation. Destructive synchronization commands are documented in the main
[building guide](../../docs/BUILDING.md#common-checkout-and-gn-commands).
