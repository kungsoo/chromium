## Thorium for ARM CPUs <img src="https://github.com/Alex313031/thorium/blob/main/logos/STAGING/arm_logo.png" width="128">

This directory contains build argument files for Android ARM, Raspberry Pi
ARM64, and Windows on ARM64. ARM ABI selection remains owned by Chromium's
central build configuration; these files only select the target and applicable
product settings.

Run `python3 setup.py --help` from the root of this repository for more information.
Use `--raspi` for a Raspberry Pi build or `--woa` for a Windows on ARM build.
macOS ARM64 argument files are located in [`other/Mac`](../other/Mac).

- Windows on ARM64 builds: use [`win_ARM_args.gn`](win_ARM_args.gn) as the
  basis for `args.gn`.

After running the appropriate `setup.py` profile, change to the Chromium `src`
directory and create or edit the output configuration with:

```shell
gn args out/thorium
```

Use [`raspi/raspi_args.gn`](raspi/raspi_args.gn) for Raspberry Pi ARM64 and
[`win_ARM_args.gn`](win_ARM_args.gn) for Windows on ARM64.

### Common checkout and GN commands

```shell
git fetch --tags
git rebase-update
gclient runhooks
gn ls out/thorium
git show-ref
```

Use `python3 version.py` with the profile appropriate to the selected ARM
target. Destructive synchronization commands are documented in the main
[building guide](../docs/BUILDING.md#common-checkout-and-gn-commands).

## Raspberry Pi Builds &nbsp;<img src="https://github.com/Alex313031/thorium/blob/main/logos/STAGING/Raspberry_Pi_Logo.svg" width="28">

Thorium Raspberry Pi builds support ARM64 only. Use them on a Raspberry Pi 3B,
3B+, 4, or 400 running a 64-bit operating system. See Raspberry Pi's
[64-bit OS announcement](https://www.raspberrypi.com/news/raspberry-pi-os-64-bit/)
for additional background.
