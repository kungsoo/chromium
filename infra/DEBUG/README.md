## Thorium Debugging Infra <img src="https://github.com/Alex313031/thorium/blob/main/logos/STAGING/bug.svg" width="28">

 - This contains [*.gn files*](https://gn.googlesource.com/gn/) and scripts for generating DEBUG builds of Thorium for debugging, testing, and inspection.
 - The [ABOUT_GN_ARGS.md](https://github.com/Alex313031/thorium/blob/main/infra/DEBUG/ABOUT_GN_ARGS.md) describes what each line in the args &#42;.gn files do, also useful for the regular build args &#42;.gn files. \
&nbsp;&nbsp; __NOTE:__ Debug outputs are not supported as distributable installers. Windows full mode still builds the `setup` and `mini_installer` targets so those binaries can be debugged. Run `python3 clean.py` from the repository root only when you want to delete the entire `out/thorium` directory and downloaded Chromium PGO profiles.
 - `build_debug.py` replaces the former platform-specific build scripts. It validates the generated GN target OS and debug mode before building each target in a separate `autoninja` phase.
 - To build Thorium and the UI Debug Shell on Linux, run `python3 infra/DEBUG/build_debug.py --target-os linux --mode full` from the repository root. Use `--target-os win` for a Windows build and add `-j N` to limit parallel jobs.
 - To build and archive only the standalone UI Debug Shell, use `--mode shell`. Linux and Windows packages are assembled in `out/thorium/Thorium_UI_Debug_Shell`; shell-only mode also creates `out/thorium/Thorium_UI_Debug_Shell.zip`.
 - macOS debug targets can be built with `--target-os mac --mode full --build-only` or `--mode shell --build-only`. macOS packaging is intentionally disabled until its payload layout is defined and verified.
 - `--package-only` rebuilds a Linux or Windows package from existing artifacts, while `--build-only` skips packaging. Use `--single-pass` only when intentionally building all selected targets in one `autoninja` invocation.
 - For more information, read the [DEBUG_SHELL_README.md](https://github.com/Alex313031/thorium/blob/main/infra/DEBUG/DEBUG_SHELL_README.md) file.
 
### More Info <a name="moreinfo"></a>
See [DEBUGGING.md](https://github.com/Alex313031/thorium/blob/main/infra/DEBUG/DEBUGGING.md) for Thorium-specific guidance and links to the current upstream Chromium debugging documentation.

<img src="https://github.com/Alex313031/thorium/blob/main/logos/NEW/thorium_infra_256.png" width="200">
