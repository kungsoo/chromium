# Thorium for ThoriumOS

This directory contains build config files for compiling Thorium for [ThoriumOS](https://github.com/Alex313031/ThoriumOS) (a fork of [ChromiumOS](https://www.chromium.org/chromium-os/)).

Run `python3 setup.py --cros` from the Thorium checkout. Then change to the
Chromium `src` directory and create or edit the output configuration:

```shell
gn args out/thorium
```

Use [`cros_args.gn`](cros_args.gn) as the basis for the generated `args.gn`.

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

### CrOS

<img src="https://github.com/Alex313031/ThoriumOS/blob/main/images/ChromiumBook_Black.png" width="192">
