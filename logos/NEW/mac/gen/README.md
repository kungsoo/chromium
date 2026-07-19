## macOS application icon generation <img src="https://github.com/Alex313031/thorium/blob/main/logos/NEW/mac/icon_2048px.png" width="48">

Thorium uses Apple's macOS 26 layered icon format. The authoritative layered
sources live in `src/chrome/app/theme/chromium/mac/AppIcon.icon`; the legacy
`app.icns` is a generated compatibility artifact, not a separately maintained
icon design.

Generate both `Assets.car` and `app.icns` on macOS with Python 3.11, Xcode 26,
`iconutil`, ImageMagick, and `rsvg-convert` from librsvg:

```shell
brew install imagemagick librsvg
python3 logos/NEW/mac/gen/build_app_icon.py
```

The script writes both build inputs directly to:

```text
src/chrome/app/theme/chromium/mac/Assets.car
src/chrome/app/theme/chromium/mac/app.icns
```

The `Icon` entry in `Assets.car` is the document badge used by macOS for
Thorium-associated file types. Its checked-in catalog inputs are synchronized
byte-for-byte with:

```text
logos/NEW/product_logo_256.png
logos/NEW/product_logo_512.png
```

The generator rejects stale or mismatched catalog copies so a Chromium badge
cannot be reintroduced silently.

`Assets.car` provides the layered icon on macOS 26 and later. `app.icns`
remains necessary for macOS 12–25 and Chromium components that still consume
an ICNS file. Its temporary PNG sizes are composed directly from the same
layered SVG files used by `AppIcon.icon` and are never checked in.

Without a Mac, manually run the `Generate macOS app icon` GitHub Actions
workflow. Download its `thorium-macos-app-icon` artifact. It contains both
generated resources, extracted ICNS PNGs, an `assetutil` catalog inventory,
hashes, file-type diagnostics, and the exact tool versions used. Copy
`Assets.car` and `app.icns` to `src/chrome/app/theme/chromium/mac/`, then review
and commit them together with their sources.

The workflow pins the M150 deployment target to macOS 12.0 because it does not
check out Chromium. When updating the Chromium branch, synchronize the
workflow's `MACOSX_DEPLOYMENT_TARGET` value with
`build/config/mac/mac_sdk.gni`.

Review `Thorium.iconset` for the compatibility application icon and
`DocumentBadge.iconset` for the document badge. The latter should contain only
the transparent Thorium roundel, not a complete paper-shaped document icon.

<img src="https://github.com/Alex313031/thorium/blob/main/logos/NEW/mac/apple.png" width="200">
