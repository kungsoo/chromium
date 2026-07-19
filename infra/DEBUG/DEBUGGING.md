# Debugging Thorium

Thorium uses Chromium's debugging facilities. The generated build directory is
`out/thorium` unless another directory is passed to the build tools.

## Generate a debug build

Choose the matching args file in this directory and copy its contents into the
GN arguments for the Chromium checkout. For example:

```shell
gn args out/thorium
```

The output must have `is_debug = true` before it can be used by
`build_debug.py`. Build and package the Linux Debug Shell with:

```shell
python3 infra/DEBUG/build_debug.py --target-os linux --mode shell
```

Use `--target-os win` on Windows. macOS currently supports build-only mode:

```shell
python3 infra/DEBUG/build_debug.py --target-os mac --mode shell --build-only
```

Run `python3 infra/DEBUG/build_debug.py --help` for all supported options.

## Runtime logging

Useful Chromium switches include:

```text
--enable-logging=stderr
--v=1
--vmodule=source_file=2
```

Thorium's debug-mode support also recognizes the `THORIUM_DEBUG` environment
variable where the corresponding patch is enabled.

## Current upstream documentation

Debugging behavior changes frequently, so this repository does not duplicate
the complete Chromium debugging manuals. Use the current upstream documents:

- [Linux debugging](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/linux/debugging.md)
- [macOS debugging](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/mac/debugging.md)
- [Cross-platform debugging overview](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/debugging.md)
- [Android debugging](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/android_debugging_instructions.md)
- [Logging](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/logging.md)
- [Profiling](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/profiling.md)

Follow the documentation matching the Chromium revision used by the current
Thorium branch when behavior differs from `HEAD`.
