"""Command line: `check` and `icons`. Exit codes: 0 ok, 1 findings, 2 usage/network error."""

import argparse
import sys

from . import __version__
from .checks import CheckError, check_site
from .http import Fetcher
from .icons import generate, snippet_json
from .report import to_json, to_markdown


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="webmanifest-check", description="Check a site's web app manifest and icons.")
    p.add_argument("--version", action="version", version=f"webmanifest-check {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=_Parser)

    c = sub.add_parser("check", help="validate the manifest and icons of a site")
    c.add_argument("url")
    c.add_argument("--format", choices=("markdown", "json"), default="markdown")
    c.add_argument("--fail-on", choices=("warning", "error"), default="error",
                   help="exit 1 on warnings too, or only on errors (default)")
    c.add_argument("--browser", action="store_true",
                   help="also load the page in headless Chromium (needs playwright)")
    c.add_argument("--delay", type=float, default=1.0, help="seconds between HTTP requests (default 1.0)")
    c.add_argument("--timeout", type=float, default=15.0, help="per-request timeout in seconds")

    i = sub.add_parser("icons", help="generate icons from a source image")
    i.add_argument("source", help="source image, ideally a square PNG of 512x512 or more")
    i.add_argument("-o", "--out", default="icons", help="output directory (default: icons)")
    i.add_argument("--url-prefix", default="/icons/", help="URL prefix used in the manifest snippet")
    i.add_argument("--background", help="hex colour behind maskable/apple icons (default: source corner or white)")
    i.add_argument("--maskable-padding", type=float, default=0.2,
                   help="safe-zone margin per side as a fraction of the icon (default 0.2)")
    i.add_argument("--force", action="store_true", help="overwrite files that already exist")
    i.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return p


def _run_check(a) -> int:
    fetcher = Fetcher(delay=a.delay, timeout=a.timeout)
    try:
        rep = check_site(a.url, fetcher, browser=a.browser)
    except (CheckError, RuntimeError) as e:
        print(f"webmanifest-check: {e}", file=sys.stderr)
        return 2
    print(to_json(rep, a.fail_on) if a.format == "json" else to_markdown(rep))
    return rep.exit_code(a.fail_on)


def _run_icons(a) -> int:
    import json
    try:
        res = generate(a.source, a.out, a.url_prefix, a.background, a.maskable_padding, a.force)
    except (OSError, ValueError) as e:
        print(f"webmanifest-check: {e}", file=sys.stderr)
        return 2
    if a.format == "json":
        print(json.dumps(res, indent=2))
        return 0
    print(f"# Icons written to {a.out}\n")
    for n in res["written"]:
        print(f"- wrote {n}")
    for n in res["skipped"]:
        print(f"- kept existing {n} (use --force to overwrite)")
    if res["small_source"]:
        print("\nNote: the source is smaller than 512 px, so the large icons are upscaled and will look soft.")
    print("\nManifest snippet:\n\n```json\n" + snippet_json(res["manifest_icons"]) + "\n```")
    print('\nHTML:\n\n```html\n<link rel="apple-touch-icon" href="' + a.url_prefix.rstrip("/") + '/apple-touch-icon.png">\n'
          '<link rel="icon" href="/favicon.ico" sizes="48x48">\n```\n'
          'Serve favicon.ico from the site root (browsers also request /favicon.ico by default).')
    return 0


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    return _run_check(a) if a.cmd == "check" else _run_icons(a)


if __name__ == "__main__":
    sys.exit(main())
