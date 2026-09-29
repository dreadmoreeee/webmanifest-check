"""The `check` logic: page -> manifest -> icons -> other icon/theme signals."""

import io
import json
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit

from PIL import Image

from .colors import is_css_color
from .htmlscan import scan
from .http import Fetcher

DISPLAYS = ("fullscreen", "standalone", "minimal-ui", "browser")
MIME_BY_FORMAT = {
    "PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp",
    "ICO": "image/x-icon", "BMP": "image/bmp",
}
ICO_MIMES = {"image/x-icon", "image/vnd.microsoft.icon", "image/ico"}
LEVELS = ("error", "warning", "info", "ok")
MAX_ICONS = 12


class CheckError(Exception):
    """The page itself could not be fetched (exit code 2)."""


@dataclass
class Finding:
    level: str
    code: str
    message: str
    url: str = ""


@dataclass
class Report:
    url: str
    findings: list = field(default_factory=list)
    icons: list = field(default_factory=list)      # per-icon verification rows
    missing: list = field(default_factory=list)    # icon roles not found
    manifest_url: str = ""
    browser: dict | None = None
    requests: int = 0

    def add(self, level, code, message, url=""):
        self.findings.append(Finding(level, code, message, url))

    def count(self, level) -> int:
        return sum(1 for f in self.findings if f.level == level)

    def exit_code(self, fail_on: str = "error") -> int:
        if self.count("error"):
            return 1
        return 1 if fail_on == "warning" and self.count("warning") else 0


def _sizes(value) -> list[tuple[int, int]] | None:
    """Parse a sizes string. Returns None when it has no WxH token (empty or only 'any')."""
    out = []
    for tok in str(value or "").lower().split():
        w, sep, h = tok.partition("x")
        if sep and w.isdigit() and h.isdigit():
            out.append((int(w), int(h)))
    return out or None


def inspect_image(body: bytes):
    """Return (format, (w, h)) or raise ValueError. For ICO the largest entry is reported."""
    try:
        with Image.open(io.BytesIO(body)) as im:
            fmt = im.format
            size = im.size
            if fmt == "ICO":
                sizes = sorted(im.info.get("sizes", {size}))
                size = sizes[-1]
            return fmt, size
    except Exception as e:  # Pillow raises many types for broken data
        raise ValueError(str(e) or type(e).__name__) from None


def _origin(u: str):
    p = urlsplit(u)
    return (p.scheme, p.netloc.lower())


def _fail(r) -> str:
    return r.error or "HTTP %d" % r.status


def check_site(url: str, fetcher: Fetcher, browser: bool = False) -> Report:
    if "://" not in url:
        url = "https://" + url
    rep = Report(url)
    page = fetcher.get(url)
    if not page.ok:
        raise CheckError(f"cannot fetch {url}: {_fail(page)}")
    base = page.url
    origin = urlunsplit(urlsplit(base)[:2] + ("", "", ""))
    tags = scan(page.body.decode("utf-8", "replace"))

    manifest = _check_manifest(rep, fetcher, tags, base)
    _check_other_icons(rep, fetcher, tags, base, origin, manifest)
    if browser:
        from .browser import check_browser
        check_browser(rep, base)
    rep.requests = fetcher.count
    return rep


def _no_icons(rep):
    rep.missing.extend(["icon-192", "icon-512", "icon-maskable"])


def _check_manifest(rep, fetcher, tags, base):
    links = tags.links_with("manifest")
    if not links:
        rep.add("error", "manifest-link", "no <link rel=manifest> in the page HTML")
        rep.missing.append("manifest")
        _no_icons(rep)
        return None
    murl = urljoin(base, links[0]["href"])
    rep.manifest_url = murl
    if len(links) > 1:
        rep.add("warning", "manifest-link", "more than one <link rel=manifest>; only the first is used")
    r = fetcher.get(murl)
    if not r.ok:
        rep.add("error", "manifest-fetch", f"manifest not fetched: {_fail(r)}", murl)
        _no_icons(rep)
        return None
    if r.content_type and "json" not in r.content_type:
        rep.add("warning", "manifest-mime", f"manifest served as {r.content_type}; expected application/manifest+json", murl)
    try:
        m = json.loads(r.body.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as e:
        rep.add("error", "manifest-json", f"manifest is not valid JSON: {e}", murl)
        _no_icons(rep)
        return None
    if not isinstance(m, dict):
        rep.add("error", "manifest-json", "manifest JSON must be an object", murl)
        _no_icons(rep)
        return None
    rep.add("ok", "manifest", "manifest found and parsed", murl)

    name, short = m.get("name"), m.get("short_name")
    if not isinstance(name, str) or not name.strip():
        rep.add("error", "name", "name is missing or empty")
    if not isinstance(short, str) or not short.strip():
        rep.add("warning", "short-name", "short_name is missing; launchers may truncate name")
    elif len(short) > 12:
        rep.add("warning", "short-name", f"short_name is {len(short)} characters (over 12); it may be truncated under the icon")

    doc_origin = _origin(base)
    start = m.get("start_url")
    if start is None:
        rep.add("warning", "start-url", "start_url is missing; the page URL is used as the start")
        start_abs = base
    elif not isinstance(start, str):
        rep.add("error", "start-url", "start_url must be a string")
        start_abs = base
    else:
        start_abs = urljoin(murl, start)
        if _origin(start_abs) != doc_origin:
            rep.add("error", "start-url", f"start_url {start_abs} is on a different origin than the page")
    scope = m.get("scope")
    if scope is None:
        scope_abs = urljoin(start_abs, ".")
        rep.add("info", "scope", f"scope not set; defaults to {scope_abs}")
    elif not isinstance(scope, str):
        rep.add("error", "scope", "scope must be a string")
        scope_abs = urljoin(start_abs, ".")
    else:
        scope_abs = urljoin(murl, scope)
        if _origin(scope_abs) != doc_origin:
            rep.add("error", "scope", f"scope {scope_abs} is on a different origin than the page")
    sp, tp = urlsplit(scope_abs).path or "/", urlsplit(start_abs).path or "/"
    if _origin(start_abs) == _origin(scope_abs) and not tp.startswith(sp):
        rep.add("error", "start-url-scope", f"start_url {start_abs} is outside scope {scope_abs}")
    elif start is not None:
        rep.add("ok", "start-url", f"start_url resolves to {start_abs}, within scope")

    disp = m.get("display")
    if disp is None:
        rep.add("warning", "display", "display is missing; defaults to 'browser', so the app opens as a normal tab")
    elif disp not in DISPLAYS:
        rep.add("error", "display", f"display {disp!r} is not one of {', '.join(DISPLAYS)}")

    for key in ("theme_color", "background_color"):
        v = m.get(key)
        code = key.replace("_", "-")
        if v is None:
            rep.add("warning", code, f"{key} is missing")
        elif not isinstance(v, str) or not is_css_color(v):
            rep.add("error", code, f"{key} {v!r} is not a valid CSS colour")

    if not isinstance(m.get("id"), str) or not m.get("id"):
        rep.add("warning", "id", "id is missing; browsers fall back to start_url as the app identity")

    _check_manifest_icons(rep, fetcher, m, murl)
    return m


def _check_manifest_icons(rep, fetcher, m, murl):
    icons = m.get("icons")
    if not isinstance(icons, list) or not icons:
        rep.add("error", "icons", "icons is missing or empty")
        _no_icons(rep)
        return
    declared = set()
    maskable = False
    rows = {}
    for i, ic in enumerate(icons):
        if not isinstance(ic, dict) or not isinstance(ic.get("src"), str) or not ic["src"]:
            rep.add("error", "icon-src", f"icons[{i}] has no src")
            continue
        if "maskable" in str(ic.get("purpose", "any")).lower().split():
            maskable = True
        sz = _sizes(ic.get("sizes"))
        if sz:
            declared.update(sz)
        src = urljoin(murl, ic["src"])
        if src in rows:
            continue
        if len(rows) >= MAX_ICONS:
            rep.add("info", "icon-limit", f"only the first {MAX_ICONS} distinct icons are fetched")
            continue
        rows[src] = _verify_icon(rep, fetcher, src, ic, sz)
    rep.icons.extend(rows.values())
    for n in (192, 512):
        if (n, n) in declared:
            rep.add("ok", f"icon-{n}", f"{n}x{n} icon declared")
        else:
            rep.add("error", f"icon-{n}", f"no {n}x{n} icon declared (needed for installability)")
            rep.missing.append(f"icon-{n}")
    if maskable:
        rep.add("ok", "icon-maskable", "a maskable icon is declared")
    else:
        rep.add("warning", "icon-maskable", 'no icon with "purpose": "maskable"; Android will shrink icons onto a white circle')
        rep.missing.append("icon-maskable")


def _verify_icon(rep, fetcher, src, ic, sz):
    row = {"src": src, "declared_sizes": ic.get("sizes", ""), "declared_type": ic.get("type", ""),
           "purpose": ic.get("purpose", "any"), "actual": None, "format": "", "status": "ok"}
    r = fetcher.get(src)
    if not r.ok:
        row["status"] = "missing"
        rep.add("error", "icon-fetch", f"icon not fetched: {_fail(r)}", src)
        return row
    if r.content_type == "image/svg+xml" or src.lower().split("?")[0].endswith(".svg"):
        row["format"] = "SVG"
        if ic.get("type") and ic["type"] != "image/svg+xml":
            rep.add("warning", "icon-type", f"declared type {ic['type']} but the file is SVG", src)
        return row
    try:
        fmt, size = inspect_image(r.body)
    except ValueError as e:
        row["status"] = "invalid"
        rep.add("error", "icon-image", f"not a readable image: {e}", src)
        return row
    row["actual"], row["format"] = list(size), fmt
    if sz and size not in sz:
        row["status"] = "size-mismatch"
        want = " ".join(f"{w}x{h}" for w, h in sz)
        rep.add("error", "icon-size", f"declared {want} but the real size is {size[0]}x{size[1]}", src)
    elif sz is None and "any" not in str(ic.get("sizes", "")).lower():
        rep.add("warning", "icon-sizes", f"no sizes declared (real size is {size[0]}x{size[1]})", src)
    if size[0] != size[1]:
        rep.add("warning", "icon-square", f"icon is not square ({size[0]}x{size[1]})", src)
    real_mime = MIME_BY_FORMAT.get(fmt, "")
    decl = ic.get("type")
    if decl and real_mime and decl != real_mime and not (real_mime == "image/x-icon" and decl in ICO_MIMES):
        rep.add("warning", "icon-type", f"declared type {decl} but the image is {fmt} ({real_mime})", src)
        if row["status"] == "ok":
            row["status"] = "type-mismatch"
    if r.content_type and real_mime and r.content_type != real_mime and not (
            real_mime == "image/x-icon" and r.content_type in ICO_MIMES):
        rep.add("warning", "icon-mime", f"served as {r.content_type} but the image is {fmt}", src)
    return row


def _check_other_icons(rep, fetcher, tags, base, origin, manifest):
    # apple-touch-icon: declared link first, /apple-touch-icon.png as fallback
    apple = tags.links_with("apple-touch-icon") + tags.links_with("apple-touch-icon-precomposed")
    aurl = urljoin(base, apple[0]["href"]) if apple else origin + "/apple-touch-icon.png"
    r = fetcher.get(aurl)
    if r.ok:
        try:
            fmt, size = inspect_image(r.body)
            note = f"{'link' if apple else 'fallback'}: {aurl} is {fmt} {size[0]}x{size[1]}"
            if size != (180, 180):
                rep.add("warning", "apple-touch-icon", note + "; iOS expects 180x180", aurl)
            else:
                rep.add("ok", "apple-touch-icon", note, aurl)
        except ValueError as e:
            rep.add("error", "apple-touch-icon", f"{aurl} is not a readable image: {e}", aurl)
    else:
        rep.missing.append("apple-touch-icon")
        if apple:
            rep.add("error", "apple-touch-icon", f"declared apple-touch-icon not fetched: {_fail(r)}", aurl)
        else:
            rep.add("warning", "apple-touch-icon", "no <link rel=apple-touch-icon> and /apple-touch-icon.png is missing (iOS home-screen icon)")

    # /favicon.ico
    icon_links = tags.links_with("icon")
    furl = origin + "/favicon.ico"
    r = fetcher.get(furl)
    if r.ok:
        try:
            fmt, size = inspect_image(r.body)
            rep.add("ok", "favicon-ico", f"/favicon.ico is {fmt}, largest {size[0]}x{size[1]}", furl)
        except ValueError as e:
            rep.add("error", "favicon-ico", f"/favicon.ico is not a readable image: {e}", furl)
    else:
        rep.missing.append("favicon.ico")
        rep.add("info" if icon_links else "warning", "favicon-ico",
                f"/favicon.ico not found ({_fail(r)})" + ("; a <link rel=icon> is declared" if icon_links else ""), furl)

    # SVG favicon
    svg = [x for x in icon_links if x.get("type", "").lower() == "image/svg+xml"]
    if not svg:
        rep.add("info", "favicon-svg", "no <link rel=icon type=image/svg+xml> (optional; scales and supports dark mode)")
        rep.missing.append("favicon.svg")
    else:
        surl = urljoin(base, svg[0]["href"])
        r = fetcher.get(surl)
        if not r.ok:
            rep.add("error", "favicon-svg", f"SVG favicon not fetched: {_fail(r)}", surl)
        elif b"<svg" not in r.body[:4096].lower():
            rep.add("error", "favicon-svg", "SVG favicon does not look like SVG", surl)
        elif r.content_type != "image/svg+xml":
            rep.add("warning", "favicon-svg", f"SVG favicon served as {r.content_type or 'unknown'}, not image/svg+xml", surl)
        else:
            rep.add("ok", "favicon-svg", "SVG favicon found", surl)

    # <meta name=theme-color>
    tc = tags.meta("theme-color")
    if tc is None:
        rep.add("warning", "meta-theme-color", "no <meta name=theme-color>")
    elif not is_css_color(tc):
        rep.add("error", "meta-theme-color", f"<meta name=theme-color> {tc!r} is not a valid CSS colour")
    else:
        mt = manifest.get("theme_color") if isinstance(manifest, dict) else None
        if isinstance(mt, str) and mt.strip().lower() != tc.lower():
            rep.add("info", "meta-theme-color", f"meta theme-color {tc} differs from manifest theme_color {mt}")
        else:
            rep.add("ok", "meta-theme-color", f"<meta name=theme-color> is {tc}")
