# Thorium UI Debug Shell <img src="https://raw.githubusercontent.com/Alex313031/Thorium/main/logos/NEW/thorium_debug_shell/icon_256.png" width="36">

## Summary:
This is a special program, built on top of views_examples & content_shell and incorporating a multitude of options for testing, viewing, and debugging UI resources in Thorium. It builds views_examples_with_content, and renames it to thorium_ui_debug_shell. Building views_examples builds the program, but without content_shell linked in (which can be accessed via the *"WebView"* option in the dropdown menu).

## Linux Use
Run the Thorium_Debug_Shell.sh, and you can select from the dropdown menu. Some things are interactive, some load internal resources, and some require loading external resources like viewing .icon files. In that case, you can load a file using its full path in the box towards the bottom.

## Windows Use
Run the thorium_ui_debug_shell.exe, and you can select from the dropdown menu. Some things are interactive, some load internal resources, and some require loading external resources like viewing .icon files. In that case, you can load a file using its full path in the box towards the bottom.

## Use in Thorium
I built this to view and test native Chromium UI icons in the *.icon* format.
These paths are relative to the Chromium `src` directory:

- `ui/views/vector_icons/` — native Views UI icons.
- `ui/views/window/vector_icons/` — window and top-bar icons.
- `components/vector_icons/` — icons shared by multiple components.
- `chrome/app/vector_icons/` — browser-specific icons.
- `ash/resources/vector_icons/` — Ash and ChromiumOS icons.
- `chromeos/ui/vector_icons/` — ChromiumOS-specific UI icons.
- `chromecast/ui/vector_icons/` — Chromecast-specific icons.

*More info can be found at > https://chromium.googlesource.com/chromium/src.git/+/refs/heads/main/components/vector_icons/README.md*

## Building <img src="https://github.com/Alex313031/thorium/blob/main/logos/NEW/build_light.svg#gh-dark-mode-only"> <img src="https://github.com/Alex313031/thorium/blob/main/logos/NEW/build_dark.svg#gh-light-mode-only">

From the Thorium repository root, build the complete debug product set and UI
Debug Shell with:

```shell
python3 infra/DEBUG/build_debug.py --target-os linux --mode full
```

Use `--target-os win` for Windows. To build and archive only the standalone UI
Debug Shell, replace `--mode full` with `--mode shell`. Pass `-j N` to limit
parallel jobs. macOS currently supports build-only operation because its Debug
Shell package layout has not yet been defined and verified.
