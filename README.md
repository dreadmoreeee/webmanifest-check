# webmanifest-check

Checks the **web app manifest and icons** of a site the way browsers and phones use them, and generates the icon files that turn out to be missing.

```
python -m webmanifest_check check https://example.com
python -m webmanifest_check icons logo.png -o icons
```

Most manifest linters read the JSON and stop. This one also **downloads every icon** and opens it with Pillow, because the classic bug is an icon declared `512x512` that is really 256 pixels, or a `.png` that is a JPEG.

## What `check` looks at

- `<link rel=manifest>` in the HTML (stdlib `html.parser`), then the manifest: valid JSON, `name`, `short_name` (warns over 12 characters), `start_url` (resolves, same origin, inside `scope`), `scope`, `display`, `theme_color` and `background_color` (valid CSS colours), `id`.
- `icons`: a 192x192 and a 512x512 icon, a `maskable` one. Every declared icon is fetched and compared with its declared `sizes` and `type` (real pixel size, real format, served MIME type).
- `apple-touch-icon` (the `<link>`, or `/apple-touch-icon.png` as fallback, 180x180 expected), `/favicon.ico`, an SVG favicon (`<link rel=icon type=image/svg+xml>`), `<meta name=theme-color>`.
- The report ends with the list of **missing icons** (`icon-192`, `icon-512`, `icon-maskable`, `apple-touch-icon`, `favicon.ico`, `favicon.svg`).
- `--browser` loads the page once in headless Chromium (Playwright) and reports whether a service worker is registered (`navigator.serviceWorker.getRegistrations()`, `controller`) and whether `beforeinstallprompt` fired. It never clicks or types.

```
python -m webmanifest_check check <url> [--format markdown|json] [--fail-on error|warning] [--browser] [--delay 1.0]
```

Exit codes: `0` nothing at the failing level, `1` errors found (or warnings too with `--fail-on warning`), `2` usage error or the page could not be fetched. Fine to run in CI after a deploy.

Requests are plain `GET`s with the User-Agent `webmanifest-check/1.0`, at least `--delay` seconds apart (1 s by default), about 8 to 20 per site. It does not crawl.

## What `icons` does

```
python -m webmanifest_check icons logo.png -o icons --url-prefix /icons/ [--background "#0f1720"] [--maskable-padding 0.2] [--force]
```

From one source image (square PNG, 512 px or more is best; other shapes are centred on a transparent square, never stretched) it writes `icon-192.png`, `icon-512.png`, `icon-maskable-512.png` (artwork shrunk inside a 20% safe-zone margin on a solid background), `apple-touch-icon.png` (180x180, opaque, because iOS paints transparency black) and a multi-size `favicon.ico` (16, 32, 48). Existing files are kept unless you pass `--force`. It prints the `icons` JSON snippet for the manifest ([examples/manifest.json](examples/manifest.json) shows the result; [examples/source-icon.png](examples/source-icon.png) is a source to try).

## Measured result

Run against my own three sites (GET only, one request per second, no forms, no clicks). Exit code was `1` on all three.

`https://demarkstudio.ca` has a manifest; the tool found two real gaps in it:

```
$ python -m webmanifest_check check https://demarkstudio.ca
Manifest: https://demarkstudio.ca/static/site.webmanifest
Result: 2 error(s), 2 warning(s), 1 info, 5 ok (8 HTTP requests)

ERROR  icon-192       no 192x192 icon declared (needed for installability)
ERROR  icon-512       no 512x512 icon declared (needed for installability)
WARN   id             id is missing; browsers fall back to start_url as the app identity
WARN   icon-maskable  no icon with "purpose": "maskable"; Android will shrink icons onto a white circle
INFO   favicon-ico    /favicon.ico not found (HTTP 404); a <link rel=icon> is declared
OK     start-url, apple-touch-icon (PNG 180x180), favicon-svg, meta-theme-color (#f8fbfd)

| src                                                     | declared | real  | format | status |
|---------------------------------------------------------|----------|-------|--------|--------|
| https://demarkstudio.ca/static/img/favicon.svg          | any      | -     | SVG    | ok     |
| https://demarkstudio.ca/static/img/favicon-32.png       | 32x32    | 32x32 | PNG    | ok     |
| https://demarkstudio.ca/static/img/apple-touch-icon.png | 180x180  | 180x180 | PNG  | ok     |

Missing icons: icon-192, icon-512, icon-maskable, favicon.ico
```

The two other sites have **no `<link rel=manifest>`** at all, so they are not installable PWAs (they are not meant to be):

```
$ python -m webmanifest_check check https://demo.demarkstudio.ca
Result: 1 error(s), 2 warning(s), 1 info, 1 ok (4 HTTP requests)
ERROR  manifest-link      no <link rel=manifest> in the page HTML
WARN   apple-touch-icon   no <link rel=apple-touch-icon> and /apple-touch-icon.png is missing
WARN   meta-theme-color   no <meta name=theme-color>
INFO   favicon-ico        /favicon.ico not found (HTTP 404); a <link rel=icon> is declared
OK     favicon-svg
Missing icons: manifest, icon-192, icon-512, icon-maskable, apple-touch-icon, favicon.ico

$ python -m webmanifest_check check https://marvin.demarkstudio.ca
Result: 1 error(s), 1 warning(s), 1 info, 2 ok (4 HTTP requests)
ERROR  manifest-link      no <link rel=manifest> in the page HTML
WARN   apple-touch-icon   no <link rel=apple-touch-icon> and /apple-touch-icon.png is missing
INFO   favicon-ico        /favicon.ico not found (HTTP 404); a <link rel=icon> is declared
OK     favicon-svg, meta-theme-color (#0f1720)
Missing icons: manifest, icon-192, icon-512, icon-maskable, apple-touch-icon, favicon.ico
```

(The tool prints each finding as a Markdown list item; the blocks above are condensed to one line each.)

With `--browser` on all three sites (browser lines only), the same result on each: no service worker is registered, and Chromium did not fire `beforeinstallprompt` within 3 seconds.

```
$ python -m webmanifest_check check https://demarkstudio.ca --browser
- `browser-sw` no service worker registered (needed for offline support; Chrome no longer requires one to install)
- `browser-install` beforeinstallprompt not observed within 3 s (headless Chromium may not fire it; not proof of failure)
```

Then I used the tool on my own portfolio: rendered its SVG favicon to a 512 px PNG, ran `icons` on it, and published the `apple-touch-icon.png` and `favicon.ico` it wrote. The same check afterwards:

```
$ python -m webmanifest_check check https://marvin.demarkstudio.ca
Manifest: not found
Result: 1 error(s), 0 warning(s), 0 info, 4 ok (4 HTTP requests)
- `manifest-link` no <link rel=manifest> in the page HTML
- `apple-touch-icon` link: https://marvin.demarkstudio.ca/apple-touch-icon.png is PNG 180x180
```

The remaining error is deliberate: a portfolio does not need to install as an app.

The `icons` command on [examples/source-icon.png](examples/source-icon.png) wrote `icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, `apple-touch-icon.png` and `favicon.ico` and printed the manifest snippet.

```
$ python -m pytest -q -p no:cacheprovider --import-mode=importlib webmanifest-check
.......................................................                  [100%]
55 passed in 21.95s
```

The tests use local HTTP servers on random ports (no internet) and generate their fixture images with Pillow, including an icon declared 512 that is really 256. Two of them start headless Chromium against a local page and are skipped when it is not installed.

## Install

```
pip install .                 # Pillow only
pip install ".[browser]"      # adds Playwright for --browser
playwright install chromium
```

Console script: `webmanifest-check`. Python 3.10+.

## Limitations

- Colours are checked by **syntax** (hex, named, `rgb()`, `hsl()`, `hwb()`, `lab()`, `lch()`, `oklab()`, `oklch()`, `color()`), not by full CSS parsing.
- Only the first `<link rel=manifest>` is read, at most 12 distinct icons are fetched, and `shortcuts`, `screenshots` and `display_override` are not checked.
- `--browser` does not prove a site is installable: headless Chromium does not always fire `beforeinstallprompt`, and installability rules change between browser versions.
- Icon contents are not judged (a maskable icon may still have artwork outside the safe zone); only presence, size and format are.

## Author

Marvin Palencia, founder of [DeMark Studio](https://demarkstudio.ca), Miramichi, New Brunswick, Canada. Portfolio: [marvin.demarkstudio.ca](https://marvin.demarkstudio.ca)

MIT License.
