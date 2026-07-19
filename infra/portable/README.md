# Thorium portable packaging

`portable.py` creates portable ZIP archives from a Thorium Linux `.deb` package
or Windows mini installer. It requires Python 3.11 or newer.

## Linux

Install `dpkg-deb`, then run from the Thorium repository root:

```shell
python3 infra/portable/portable.py \
  --platform linux \
  --input /path/to/thorium-browser.deb
```

The generated archive contains transparent Bash launchers whose executable bits
are stored in the ZIP. Linux packaging must run on a system with `dpkg-deb`.
Extract the result with a tool that preserves Unix symbolic links, such as:

```shell
unzip Thorium_Linux_ARCH_VERSION_portable.zip
```

## Windows

Install [7-Zip](https://www.7-zip.org/) and add `7z.exe` to `PATH`, or pass its
location explicitly:

```powershell
python infra/portable/portable.py `
  --platform windows `
  --input C:\path\to\thorium_AVX2_mini_installer.exe `
  --seven-zip "C:\Program Files\7-Zip\7z.exe"
```

The platform can normally be inferred from `.deb` or `.exe`, so `--platform`
is optional. Use `--output PATH` to choose the archive name and `--force` to
replace an existing archive. If a renamed Windows installer no longer contains
its SIMD profile in the filename, pass `--profile NAME` to retain that profile
in the output archive name. Use `--expected-version VERSION` in release
automation to reject an unexpected package version.

Packaging takes place in an isolated temporary directory. The input package is
never modified, and the final ZIP replaces its destination only after it has
been written successfully. A same-directory lock prevents concurrent packaging
processes from writing the same output. Locks left by a process that no longer
exists are recovered automatically.

## Security and portability

The browser launchers pass `--disable-encryption` and `--disable-machine-id` so
the profile can move between machines. This weakens protection for cookies,
passwords, and other profile data. Treat the extracted directory as sensitive
and do not use this mode when OS-bound credential protection is preferred.

Linux `.desktop` files are included as `.desktop.example` templates. Replace
every `@PORTABLE_ROOT@` placeholder with the absolute extracted directory
before installing them into `~/.local/share/applications`. Executable paths are
quoted so ordinary spaces are supported; paths containing desktop-entry escape
characters such as `"`, `` ` ``, `$`, or `\\` require specification-compliant
escaping.
