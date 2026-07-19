# Checking out and building Thorium on Linux &nbsp;<img src="https://github.com/Alex313031/thorium/blob/main/logos/NEW/build_light.svg#gh-dark-mode-only" width="48"> <img src="https://github.com/Alex313031/thorium/blob/main/logos/NEW/build_dark.svg#gh-light-mode-only" width="48">

There are instructions for other platforms here in the Thorium Docs directory.
You can also read the [old building instructions](https://github.com/Alex313031/thorium/blob/main/infra/BUILDING.md).

#### Windows
For Windows and Windows [AVX2](https://en.wikipedia.org/wiki/Advanced_Vector_Extensions#Advanced_Vector_Extensions_2), I made new dedicated instructions. If you are building on Windows use [BUILDING_WIN.md](https://github.com/Alex313031/thorium/blob/main/docs/BUILDING_WIN.md) and if you are building for Windows on Linux, use [WIN_CROSS_BUILD_INSTRUCTIONS](https://github.com/Alex313031/thorium/blob/main/docs/WIN_CROSS_BUILD_INSTRUCTIONS.txt)

## System Requirements

*   A x64 machine with at least 8GB of RAM. 16GB or more is highly
    recommended.
*   At least 75GB of free disk space.
*   You must have Git and Python v3.8+ installed already (and `python3` must point
    to a Python v3.8+ binary, i.e. in your path or as default python install). 
    Depot_tools bundles an appropriate version of Python in `$depot_tools/python-bin`, 
    if you don't have an appropriate version already on your system.

### Open-file limit

Large Chromium builds may need more simultaneously open files than the shell's
default limit permits. On Linux, inspect the current soft and hard limits with:

```shell
ulimit -Sn
ulimit -Hn
```

When the system hard limit permits it, raise both limits for the current shell
before building:

```shell
ulimit -Hn 1048576
ulimit -Sn 1048576
ulimit -n
```

These settings affect only the current shell and its child processes. If the
hard-limit command fails, configure the distribution's PAM/systemd resource
limits first instead of running the build as root.

Most development is done on Ubuntu 22.04, Jammy Jellyfish (This is what Chromium's build infrastructure currently runs). 
Ubuntu 16.04/18.04 no longer works. 20.04 and Debian 10/11/12 will work.
There are some instructions for other distros below, but they are mostly unsupported.

__The scripts to build Thorium assume that depot_tools, thorium and chromium are both in $HOME!__

## Install `depot_tools` <a name="depot-tools"></a>

Clone the `depot_tools` repository:

```shell
$ git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git
```

Add *depot_tools* to the end of your *$PATH* (you will probably want to put this
in your `~/.bashrc` or `~/.zshrc`). When setting the path after cloning *depot_tools* to your home directory 
**do not** use `~` in the PATH, otherwise `gclient runhooks` will fail to run. Rather, you should use either
`$HOME` or the absolute path. So, assuming you cloned *depot_tools* to *$HOME*:

```shell
$ export PATH="${HOME}/depot_tools:$PATH" or $ export PATH="/home/alex/depot_tools:$PATH"
```

## Get the code <a name="get-the-code"></a>

### Thorium Code

Clone the Thorium repo into *$HOME*

```shell
$ git clone --recursive https://github.com/Alex313031/thorium.git
```

### Chromium Code

Create a *chromium* directory for the checkout and change to it.

```shell
$ mkdir ~/chromium && cd ~/chromium
```

Run the *fetch* tool from depot_tools to check out the code and its
dependencies.

```shell
$ fetch --nohooks chromium
```

The `--nohooks` flag is omitted on other platforms, we just use it on linux to explicitly run the hooks
later, after installing the prerequisites.
`fetch` and `repo` are used to download, rebase, and sync all Google repositories, including Chromium, ChromiumOS, 
Android, Fuchsia, Infra, Monorail, GN, etc.

If you don't want the full repo history, you can save a lot of time by
adding the `--no-history` flag to `fetch`. This is equivalent to a shallow git clone with a depth of 1.

Expect the command to take 20 minutes on a fast (150mbps+) connection, and many
hours on slower ones.

If you've already installed the build dependencies on the machine (from another
checkout, for example), you can omit the `--nohooks` flag and *fetch*
will automatically execute `gclient runhooks` at the end.

When *fetch* completes, it will have created a hidden `.gclient` file and a
directory called `src` in the *chromium* directory. The remaining instructions
assume you have switched to the `src` directory, so:

```shell
$ cd src
```

### Install additional build dependencies

Once you have checked out the code, and assuming you're using Ubuntu, run the
[*`install-build-deps.sh`*](https://chromium.googlesource.com/chromium/src/+/main/build/install-build-deps.sh) script.

```shell
$ ./build/install-build-deps.sh --no-nacl
```

You can run it with the flag `--help` to see arguments. For example, you would want `--lib32` if building for 32 bit Linux, `--arm` for building
a Raspberry Pi release, `--chromeos-fonts` for building Thorium for ThoriumOS, and `--quick-check` just to verify needed libraries are installed.

You may need to adjust the build dependencies for other distros. There are
some [notes](#notes) at the end of this document, but we make no guarantees
for their accuracy, as distros get updated over time.

### Run the hooks

Once you've run `install-build-deps` at least once, you can now run the
Chromium-specific hooks, which will download additional binaries and other
things like LLVM and a Debian Sysroot.:

```shell
$ gclient runhooks
```

*Optional:* You can also [build with API
keys](https://www.chromium.org/developers/how-tos/api-keys) if you want your
build to talk to some Google services like Google Sync, Translate, and GeoLocation.&nbsp;<img src="https://github.com/Alex313031/thorium/blob/main/logos/NEW/Key_Light.svg#gh-dark-mode-only" width="26"> <img src="https://github.com/Alex313031/thorium/blob/main/logos/NEW/Key_Dark.svg#gh-light-mode-only" width="26">&nbsp;Thorium has its own keys in a private repository, if you are a builder or would like access to them, contact me. Otherwise, for personal or development builds, 
you can create your own keys and add yourself to [google-browser-signin-testaccounts](https://groups.google.com/u/1/a/chromium.org/g/google-browser-signin-testaccounts)
to enable Sync.

## Setting up the build <a name="setup"></a>

First, we need to run `python3 ./trunk.py` (in the root of the Thorium repo.) This will Rebase/Sync the Chromium repo, and revert it to stock Chromium.
It will also fetch all the tags/branches, which is needed for the version.py script.
It should be used before every separate build. See the [Updating](#updating) section.

__IMPORTANT__
This will update and sync the sources to the latest revision (tip of tree) and ensure you have all the version tags.

- Then, to check out the current Chromium revision that Thorium is using, run `python3 ./version.py`. At the end it will download the [PGO profiles](https://chromium.googlesource.com/chromium/src.git/+/refs/heads/main/docs/pgo.md) used by the platform workflow. The file will be downloaded to *//chromium/src/chrome/build/pgo_profiles/&#42;.profdata* with the actual file name looking something like 'chrome-linux-6167-1706004111-41f78c57fb3a1fe49a5c549b16f0221465339af9.profdata', which should be added to the end of args.gn as per below.
Take note of this, as we will be using it in the `args.gn` below.
- Then, (from where you cloned this repo) run `python3 ./setup.py`. This will copy all the files and patches to the needed locations.
- NOTE: To build for MacOS, use `python3 ./setup.py --mac`. To build for Raspberry Pi, use `python3 ./setup.py --raspi`. Use `python3 ./setup.py --help` to see all options/platforms.

Chromium and Thorium use [Ninja](https://ninja-build.org) as their main build tool, along with
a tool called [GN](https://gn.googlesource.com/gn/+/refs/heads/main/README.md)
to generate `.ninja` files in the build output directory. You can create any number of *build directories*
with different configurations. From the Chromium `src` directory, run
`gn args out/thorium` directly for Linux, Windows, macOS, Android, ChromeOS,
and supported cross-builds. Copy the contents
of '[args.gn](https://github.com/Alex313031/thorium/blob/main/args.gn)' in the root of this repo into the editor. Note that for Windows, Mac, ChromiumOS, or Android there are separate &#42;_args.gn files for those platforms. *--Include your api keys here at the top or leave blank, and edit the last line to point to the actual path and file name of '&#42;.profdata'*
- For more info about args.gn, read the [ABOUT_GN_ARGS.md](https://github.com/Alex313031/thorium/blob/main/infra/DEBUG/ABOUT_GN_ARGS.md) file.
- '[infra/args.list](https://github.com/Alex313031/thorium/blob/main/infra/args.list)' contains an alphabetical list with descriptions of all possible build arguments; [gn_args.list](https://github.com/Alex313031/thorium/blob/main/infra/gn_args.list) gives a similar list but with the flags in args.gn added.

You can list all the possible build arguments and pipe it to a text file by running:

```shell
$ gn args out/thorium --list >> /path/to/ARGS.list
```

* You only have to run this once for each new build directory, Ninja will
  update the build files as needed.
* You can replace *thorium* with another output directory name and pass it to
  `build.py` with `--out-dir`.
* For information on the args.gn that Thorium uses, see [ABOUT_GN_ARGS.md](https://github.com/Alex313031/thorium/blob/main/docs/ABOUT_GN_ARGS.md).  
* For other build arguments, including release settings, see [GN build
  configuration](https://www.chromium.org/developers/gn-build-configuration).
  The default will be a vanilla Chromium debug component build matching the current host
  operating system and CPU.
* For more info on GN, run `gn help` on the command line or read the
  [quick start guide](https://gn.googlesource.com/gn/+/main/docs/quick_start.md).

#### ccache

You can use [ccache](https://ccache.dev) to speed up local builds.

Increase your ccache hit rate by setting `CCACHE_BASEDIR` to a parent directory
that the working directories all have in common (e.g.,
`/home/yourusername/development`). Consider using
`CCACHE_SLOPPINESS=include_file_mtime` (since if you are using multiple working
directories, header times in svn sync'ed portions of your trees will be
different - see
[the ccache troubleshooting section](https://ccache.dev/manual/latest.html#_troubleshooting)
for additional information). If you use symbolic links from your home directory
to get to the local physical disk directory where you keep those working
development directories, consider putting

    alias cd="cd -P"

in your `.bashrc` so that `$PWD` or `cwd` always refers to a physical, not
logical directory (and make sure `CCACHE_BASEDIR` also refers to a physical
parent).

If you tune ccache correctly, a second working directory that uses a branch
tracking trunk and is up to date with trunk and was gclient sync'ed at about the
same time should build chrome in about 1/3 the time, and the cache misses as
reported by `ccache -s` should barely increase.

This is especially useful if you use
[git-worktree](http://git-scm.com/docs/git-worktree) and keep multiple local
working directories going at once.

## Build Thorium <a name="build"></a>

Build Thorium and its platform installer or packages with `build.py`. The
script reads the actual `target_os` and `target_cpu` from the generated GN
output directory, so native and cross-builds use the same entry point. Release
products are built in sequential phases: the main product must complete before
each installer or package target starts. Pass `--single-pass` to combine all
selected targets into one `autoninja` invocation.

```shell
$ python3 build.py -j 8
```

You could also manually issue the command (where -j is the number of jobs):

```shell
$ autoninja -C ~/chromium/src/out/thorium thorium chrome_sandbox chromedriver thorium_shell -j8
```

`autoninja` is a wrapper from depot_tools that automatically provides optimal
values for the arguments passed to `ninja`.

You can get a list of all of the other build targets from GN by running `gn ls
out/thorium` from the command line. To compile one, pass the GN label to Ninja
with no preceding "//" (so, for `//chrome/test:unit_tests` use `autoninja -C
out/thorium chrome/test:unit_tests`).

## Run Thorium

Once it is built, you can simply run the browser:

```shell
$ out/thorium/thorium
```
To completely discard `out/thorium` and its downloaded Chromium PGO profiles,
run `python3 clean.py` from the Thorium repository. This is a full reset and
does not preserve the built browser or installer files.

## Installing Thorium

The default Linux build also creates the DEB and RPM packages. To build without
the installer or packages, use:

```shell
$ python3 build.py --no-installer -j 8
```
To make an appimage, copy the .deb to `//thorium/infra/APPIMAGE/`
and follow the [Instructions](https://github.com/Alex313031/thorium/blob/main/infra/APPIMAGE/README.md#instructions) therein.

### Tests

See the [Debugging](#debugging) section below, as well as
[Thorium UI Debug Shell](https://github.com/Alex313031/thorium/blob/main/infra/DEBUG/DEBUG_SHELL_README.md).

Learn about [how to use Chromedriver](https://chromedriver.chromium.org/getting-started) and Google Test at its
[GitHub page](https://github.com/google/googletest).

## Update your checkout and revert to latest vanilla tip-o-tree Chromium. <a name="updating"></a>

Simply run `trunk.py` in the root of the Thorium repo or execute the commands inside.

```shell
$ python3 ./trunk.py
```

### Common checkout and GN commands

The former `aliases.txt` file only defined optional shell aliases and was never
loaded automatically. Use the underlying commands directly so that the same
workflow remains clear across shells and platforms:

```shell
# Fetch Chromium tags.
git fetch --tags

# Update the current Chromium branch using depot_tools.
git rebase-update

# Run Chromium hooks.
gclient runhooks

# List targets generated in the default Thorium output directory.
gn ls out/thorium

# Display local and remote Git references.
git show-ref
```

Use `python3 version.py` from the Thorium checkout to download the appropriate
PGO profiles instead of invoking `tools/update_pgo_profiles.py` through
platform-specific aliases.

For a routine forced synchronization and cleanup, prefer `python3 trunk.py`.
The equivalent low-level command is destructive: it resets managed checkouts
and deletes unversioned trees.

```shell
gclient sync --with_branch_heads --with_tags --force --reset --nohooks --delete_unversioned_trees
```

The former `origin` alias ran `git checkout -f origin/main`. Run that command
only when intentionally discarding tracked working-tree changes; it is not a
normal update command.

## Running test targets

Tests are split into multiple test targets based on their type and where they
exist in the directory structure. To see what target a given unit test or
browser test file corresponds to, the following command can be used:

```shell
$ gn refs out/Default --testonly=true --type=executable --all chrome/browser/ui/browser_list_unittest.cc
//chrome/test:unit_tests
```

In the example above, the target is unit_tests. The unit_tests binary can be
built by running the following command:

```shell
$ autoninja -C out/Default unit_tests
```

## Tips, tricks, and troubleshooting

### More links

*   Information about [building with Clang](https://chromium.googlesource.com/chromium/src.git/+/refs/heads/main/docs/clang.md).
*   You may want to [use a chroot](https://chromium.googlesource.com/chromium/src.git/+/refs/heads/main/docs/linux/using_a_chroot.md) to
    isolate yourself from versioning or packaging conflicts.
*   Cross-compiling for ARM? (Raspberry Pi) See the [Thorium ARM](https://github.com/Alex313031/thorium/tree/main/arm#readme) dir and [chromium_arm.md](https://chromium.googlesource.com/chromium/src.git/+/refs/heads/main/docs/linux/chromium_arm.md).
*   [Atom](https://thorium.rocks/atom-ng/) and [Geany](https://www.geany.org/) are recommended IDEs for working on Thorium.

### Debugging <a name="debugging"></a>
*   See the [Thorium DEBUG](https://github.com/Alex313031/thorium/tree/main/infra/DEBUG#readme) dir, including the [More Info](https://github.com/Alex313031/thorium/blob/main/infra/DEBUG/README.md#more-info-) section, and [DEBUGGING.md](https://github.com/Alex313031/thorium/blob/main/infra/DEBUG/DEBUGGING.md).

If you have problems building, join us in the Thorium IRC Channel at 
`#thorium` on `irc.libera.chat` and ask there.

## Notes for other distros <a name="notes"></a>

### Arch Linux

Instead of running Debian's `install-build-deps.sh`, update the system and
install the Arch package set used by Thorium:

```shell
$ sudo pacman -Syu --needed \
    autoconf autoconf-archive automake base-devel beep bluez-libs cabextract \
    cmake curl dkms dosfstools exfatprogs exo ffmpeg gcc git go gperf gtk2 \
    gtk3 hwdata i2c-tools java-runtime-common java-runtime-headless kdialog \
    libcbor libdrm libnet libpulse libsecret libudev0-shim libva libva-utils \
    libva-vdpau-driver libwebp libxss lm_sensors lsb-release make man-db \
    mesa-utils minizip mtools nano nasm ncurses nodejs nss ntfs-3g numlockx \
    openjpeg2 opus org.freedesktop.secrets p7zip pciutils pipewire polkit \
    python python-docutils python-oauth2client python-oauthlib \
    python-pkgconfig python-pkginfo python-protobuf python-setuptools \
    python-virtualenv qt5-base re2 read-edid tar libtar tk tree ttf-font \
    ttf-liberation unrar unzip vulkan-extra-layers vulkan-headers \
    vulkan-tools wget xdg-utils xsensors xz yasm zenity
```

This is a broad historical Thorium package set covering Chromium compilation,
runtime libraries, media support, ChromiumOS image tools, debugging utilities,
and optional desktop integration. It is not a minimal Chromium dependency
list. Package names and repository availability can change on Arch and its
derivatives; remove unavailable optional packages or install their current
replacement as appropriate. `-Syu` is intentional because Arch does not
support partial upgrades. Do not replace it with `-Syyuu`: forced database
refreshes and package downgrades are unnecessary here.

For the optional packages on Arch Linux:

*   `php-cgi` is provided with `pacman`
*   `wdiff` is not in the main repository but `dwdiff` is. You can get `wdiff`
    in AUR/`yaourt`

### Crostini on ChromiumOS/ThoriumOS (Debian based)

First install the `file` and `lsb-release` commands for the script to run properly:

```shell
$ sudo apt-get install file lsb-release
```

Then invoke install-build-deps.sh with the `--no-arm` argument,
because the ARM toolchain doesn't exist for this configuration:

```shell
$ sudo build/install-build-deps.sh --no-arm
```

### Fedora

Instead of running `build/install-build-deps.sh`, run:

```shell
su -c 'yum install git python bzip2 tar pkgconfig atk-devel alsa-lib-devel \
bison binutils brlapi-devel bluez-libs-devel bzip2-devel cairo-devel \
cups-devel dbus-devel dbus-glib-devel expat-devel fontconfig-devel \
freetype-devel gcc-c++ glib2-devel glibc.i686 gperf glib2-devel \
gtk3-devel java-1.*.0-openjdk-devel libatomic libcap-devel libffi-devel \
libgcc.i686 libjpeg-devel libstdc++.i686 libX11-devel \
libXScrnSaver-devel libXtst-devel libxkbcommon-x11-devel ncurses-compat-libs \
nspr-devel nss-devel pam-devel pango-devel pciutils-devel \
pulseaudio-libs-devel zlib.i686 httpd mod_ssl php php-cli python-psutil wdiff \
xorg-x11-server-Xvfb'
```

The fonts needed by Blink's web tests can be obtained by following [these
instructions](https://gist.github.com/pwnall/32a3b11c2b10f6ae5c6a6de66c1e12ae).
For the optional packages:

* `php-cgi` is provided by the `php-cli` package.
* `sun-java6-fonts` is covered by the instructions linked above.

### Gentoo

You can install the deps by doing a dry run of `emerge www-client/chromium`.

### Optimized LLVM toolchain

After applying `other/llvm-optimized-toolchain-build.patch`, Linux users can
build Thorium's LLVM/Clang, LLD and Polly toolchain with:

```shell
python3 infra/build_llvm.py
```

The wrapper validates the Chromium checkout and then runs the equivalent of:

```shell
python3 tools/clang/scripts/build.py --bootstrap --without-android \
  --without-fuchsia --disable-asserts --thinlto --pgo --bolt \
  --llvm-force-head-revision
```

Set `CR_DIR` or `CR_SRC_DIR` to the Chromium `src` directory, or pass
`--chromium-src`. Without an override it uses `~/chromium/src`. Use
`--dry-run` to validate and print the command without starting the build.

This is an expensive Linux-only toolchain build. The
`--llvm-force-head-revision` option intentionally builds LLVM HEAD instead of
Chromium's pinned revision, so reproducibility and compatibility should be
revalidated when the toolchain is updated.

---------------------------------
*Happy Thorium Building!*

<img src="https://github.com/Alex313031/thorium/blob/main/logos/STAGING/Thorium90_504.jpg" width="200">
