# Cross-Compiling Thorium for Windows on Linux &nbsp;<img src="https://github.com/Alex313031/thorium/blob/main/logos/NEW/build_light.svg#gh-dark-mode-only" width="48"> <img src="https://github.com/Alex313031/thorium/blob/main/logos/NEW/build_dark.svg#gh-light-mode-only" width="48">

As many Thorium developers are on Linux/Mac, cross-compiling Thorium for
Windows targets facilitates development for Windows targets on non-Windows
machines.

It's possible to build most parts of the codebase on a Linux or Mac host while
targeting Windows. It's also possible to run the locally-built binaries on
swarming.  This document describes how to set that up, and current restrictions.

## Limitations

What does *not* work:

* `js2gtest` tests are omitted from the build ([bug](https://crbug.com/1010561))
* on Mac hosts, 32-bit builds don't work ([bug](https://crbug.com/794838) has
  more information, and this is unlikely to ever change)

All other targets build fine (including `chrome`, `thorium_shell`, etc...).

Uses of `.asm` files have been stubbed out.  As a result, Crashpad cannot
report crashes, and NaCl defaults to disabled and cannot be enabled in cross
builds ([.asm bug](https://crbug.com/762167)).

## Setup
First make sure you've followed the instructions for getting the Chromium and Thorium code from [HERE](https://github.com/Alex313031/thorium/blob/main/docs/BUILDING.md#get-the-code).

__IMPORTANT__
Also make sure you have run `python3 ./trunk.py`, `python3 ./version.py --pgo-target win64`, and `python3 ./setup.py` to setup and copy the Thorium code over the Chromium tree as per [HERE](https://github.com/Alex313031/thorium/blob/main/docs/BUILDING.md#setting-up-the-build).

## *.gclient* setup

1. Tell gclient that you need Windows build dependencies by adding
   `target_os = ['win']` to the end of your `.gclient` file present in *~/chromium/*.  (If you already
   have a `target_os` line in there, just add `'win'` to the list.) e.g.

       solutions = [
         {
           ...
         }
       ]
       target_os = ['linux', 'win']

2. Run `python3 ./trunk.py`, and follow the instructions on screen.

### Installing the MSVS Artifacts Archive

Download the latest MSVS Artifacts Archive from [HERE](https://github.com/Alex313031/Snippets/releases/latest). \
Then, make a subdir in *chromium* called win, i.e. `mkdir ~/chromium/win`, and then place the .zip file in there.

Then, to use the
generated file on a Linux or Mac host, the following environment variables
need to be set, so add these lines to your `.bashrc` or `.zshrc`.

    export DEPOT_TOOLS_WIN_TOOLCHAIN_BASE_URL=<base url>
    export GYP_MSVS_HASH_<toolchain hash>=<hash value>

`<base url>` is the full path of the directory containing the .zip file, i.e. */home/alex/chromium/win/80909eccbb.zip*

`<toolchain hash>` is hardcoded in `src/build/vs_toolchain.py` and can be found by
setting `DEPOT_TOOLS_WIN_TOOLCHAIN_BASE_URL` and running `gclient runhooks`:

    gclient runhooks
    ...
    Running hooks:  17% (11/64) win_toolchain
    ________ running '/usr/bin/python src/build/vs_toolchain.py update --force' in <chromium dir>
    Windows toolchain out of date or doesn't exist, updating (Pro)...
    current_hashes:
    desired_hash: <toolchain hash>

`<hash value>` is the name of the .zip, without .zip at the end, i.e. `80909eccbb`

### Generating a MSVS Artifacts Archive yourself

Use Chromium's current Windows cross-build documentation and the scripts from a
real depot_tools checkout when generating MSVS artifacts. Thorium no longer
ships a local depot_tools overlay for this helper.

## Building
Follow [Setting up the build](https://github.com/Alex313031/thorium/blob/main/docs/BUILDING.md#setting-up-the-build), except instead of using the Linux `args.gn`, use [`win_args.gn`](https://github.com/Alex313031/thorium/blob/main/win_args.gn) from the root of the Thorium checkout.

From the Chromium `src` directory, create or edit the cross-build output
configuration with:

```shell
gn args out/thorium
```

Paste the cross-build `win_args.gn` contents into the editor before starting
the build.

Run the useful commands from the former alias file directly:

```shell
git fetch --tags
git rebase-update
gclient runhooks
gn ls out/thorium
git show-ref
```

Use `python3 version.py --pgo-target win64` from the Thorium checkout to update
the Windows PGO profile. Destructive synchronization commands are documented
in the [common maintenance section](BUILDING.md#common-checkout-and-gn-commands).

Then run `python3 build.py --expect-os win`. The script reads the generated GN target configuration, so it also works for a Windows cross-build from Linux. See > [Here](https://github.com/Alex313031/thorium/blob/main/docs/BUILDING.md#build-thorium-).

*Happy Thorium Building!*

<img src="https://github.com/Alex313031/thorium/blob/main/logos/STAGING/Thorium90_504.jpg" width="200">
