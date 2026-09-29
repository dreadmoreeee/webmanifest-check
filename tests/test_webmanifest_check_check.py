import copy
import json

import pytest
from wmc_helpers import GOOD_HTML, GOOD_MANIFEST, ico, make_good_site, png

from webmanifest_check.checks import CheckError, check_site
from webmanifest_check.cli import main
from webmanifest_check.http import Fetcher


def run(site, **kw):
    return check_site(site.url + "/", Fetcher(delay=0), **kw)


def codes(rep, level):
    return {f.code for f in rep.findings if f.level == level}


def test_good_site_has_no_errors_or_warnings(site):
    rep = run(make_good_site(site))
    assert codes(rep, "error") == set()
    assert codes(rep, "warning") == set()
    assert rep.missing == []
    assert rep.exit_code("warning") == 0
    assert len(rep.icons) == 3 and all(i["status"] == "ok" for i in rep.icons)


def test_no_manifest_link(site):
    site.add("/", "<html><head></head></html>")
    rep = run(site)
    assert "manifest-link" in codes(rep, "error")
    assert {"manifest", "icon-192", "icon-512", "icon-maskable", "apple-touch-icon", "favicon.ico"} <= set(rep.missing)
    assert rep.exit_code() == 1


def test_manifest_404_and_bad_json(site):
    site.add("/", '<link rel="manifest" href="/m.json">')
    assert "manifest-fetch" in codes(run(site), "error")
    site.add("/m.json", "{not json", "application/json")
    assert "manifest-json" in codes(run(site), "error")
    site.add("/m.json", "[1]", "application/json")
    assert "manifest-json" in codes(run(site), "error")


def test_declared_512_but_really_256(site):
    make_good_site(site)
    site.add("/i512.png", png(256), "image/png")
    rep = run(site)
    msgs = [f.message for f in rep.findings if f.code == "icon-size"]
    assert msgs and "real size is 256x256" in msgs[0]
    assert any(i["status"] == "size-mismatch" for i in rep.icons)
    assert rep.exit_code() == 1


def test_declared_png_but_really_jpeg(site):
    make_good_site(site)
    site.add("/i192.png", png(192, fmt="JPEG"), "image/png")
    rep = run(site)
    assert "icon-type" in codes(rep, "warning")
    assert "icon-mime" in codes(rep, "warning")


def test_icon_404_and_corrupt(site):
    make_good_site(site)
    site.routes.pop("/i192.png")
    site.add("/i512.png", b"this is not an image", "image/png")
    rep = run(site)
    assert {"icon-fetch", "icon-image"} <= codes(rep, "error")


def test_missing_sizes_maskable_id_and_short_name(site):
    m = copy.deepcopy(GOOD_MANIFEST)
    m["icons"] = [{"src": "/i192.png", "sizes": "192x192", "type": "image/png"}]
    m["short_name"] = "A very long short name"
    del m["id"]
    rep = run(make_good_site(site, m))
    assert "icon-512" in codes(rep, "error")
    assert {"icon-maskable", "id", "short-name"} <= codes(rep, "warning")
    assert {"icon-512", "icon-maskable"} <= set(rep.missing)


def test_start_url_outside_scope_and_bad_display_and_colours(site):
    m = copy.deepcopy(GOOD_MANIFEST)
    m.update(scope="/app/", start_url="/", display="windowed", theme_color="notacolour", background_color="#12")
    rep = run(make_good_site(site, m))
    assert {"start-url-scope", "display", "theme-color", "background-color"} <= codes(rep, "error")


def test_start_url_other_origin(site):
    m = copy.deepcopy(GOOD_MANIFEST)
    m["start_url"] = "https://elsewhere.example/"
    assert "start-url" in codes(run(make_good_site(site, m)), "error")


def test_relative_manifest_start_url_resolves_against_manifest(site):
    m = copy.deepcopy(GOOD_MANIFEST)
    m.update(start_url="./?utm=pwa", scope="/")
    assert "start-url-scope" not in codes(run(make_good_site(site, m)), "error")


def test_missing_optional_fields_warn(site):
    m = {"name": "X", "icons": GOOD_MANIFEST["icons"]}
    w = codes(run(make_good_site(site, m)), "warning")
    assert {"short-name", "start-url", "display", "theme-color", "background-color", "id"} <= w


def test_apple_touch_fallback_and_missing(site):
    make_good_site(site, html=GOOD_HTML.replace('<link rel="apple-touch-icon" href="/apple-touch-icon.png">', ""))
    rep = run(site)
    assert "apple-touch-icon" not in codes(rep, "warning")
    site.routes.pop("/apple-touch-icon.png")
    rep = run(site)
    assert "apple-touch-icon" in codes(rep, "warning")
    assert "apple-touch-icon" in rep.missing


def test_apple_touch_wrong_size_warns(site):
    make_good_site(site)
    site.add("/apple-touch-icon.png", png(152), "image/png")
    assert "apple-touch-icon" in codes(run(site), "warning")


def test_favicon_ico_missing_and_svg_missing(site):
    make_good_site(site, html=GOOD_HTML.replace('<link rel="icon" type="image/svg+xml" href="/favicon.svg">', ""))
    site.routes.pop("/favicon.ico")
    rep = run(site)
    assert "favicon-ico" in codes(rep, "warning")
    assert "favicon-svg" in codes(rep, "info")
    assert {"favicon.ico", "favicon.svg"} <= set(rep.missing)


def test_svg_favicon_wrong_content_is_error(site):
    make_good_site(site)
    site.add("/favicon.svg", "<html>oops</html>", "image/svg+xml")
    assert "favicon-svg" in codes(run(site), "error")


def test_meta_theme_color(site):
    make_good_site(site, html=GOOD_HTML.replace('content="#0a3d62"', 'content="banana"'))
    assert "meta-theme-color" in codes(run(site), "error")
    make_good_site(site, html=GOOD_HTML.replace('<meta name="theme-color" content="#0a3d62">', ""))
    assert "meta-theme-color" in codes(run(site), "warning")
    make_good_site(site, html=GOOD_HTML.replace('content="#0a3d62"', 'content="#ffffff"'))
    assert "meta-theme-color" in codes(run(site), "info")


def test_ico_bad_data_is_error(site):
    make_good_site(site)
    site.add("/favicon.ico", b"garbage", "image/x-icon")
    assert "favicon-ico" in codes(run(site), "error")


def test_unreachable_page_raises(site):
    with pytest.raises(CheckError):
        check_site(site.url + "/missing", Fetcher(delay=0))


def test_request_count_is_bounded(site):
    rep = run(make_good_site(site))
    assert rep.requests == 8
    assert len(site.hits) == 8


def test_cli_exit_codes_and_formats(site, capsys):
    make_good_site(site)
    assert main(["check", site.url, "--delay", "0"]) == 0
    assert "# Web manifest check" in capsys.readouterr().out
    assert main(["check", site.url, "--delay", "0", "--format", "json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["exit_code"] == 0 and d["summary"]["error"] == 0

    m = copy.deepcopy(GOOD_MANIFEST)
    del m["id"]
    make_good_site(site, m)
    assert main(["check", site.url, "--delay", "0"]) == 0
    assert main(["check", site.url, "--delay", "0", "--fail-on", "warning"]) == 1

    site.add("/i512.png", png(100), "image/png")
    assert main(["check", site.url, "--delay", "0"]) == 1


def test_cli_network_error_is_2(site, capsys):
    assert main(["check", site.url + "/nothing", "--delay", "0"]) == 2
    assert "cannot fetch" in capsys.readouterr().err


def test_cli_usage_error_is_2():
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2


def test_ico_helper_roundtrip():
    from webmanifest_check.checks import inspect_image
    assert inspect_image(ico()) == ("ICO", (48, 48))


def _chromium_ok():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _chromium_ok(), reason="Chromium not available")
def test_browser_detects_service_worker(site):
    make_good_site(site, html=GOOD_HTML + "<script>navigator.serviceWorker.register('/sw.js')</script>")
    site.add("/sw.js", "self.addEventListener('fetch', () => {});", "text/javascript")
    rep = run(site, browser=True)
    assert rep.browser["registrations"], rep.browser
    assert "browser-sw" in codes(rep, "ok")


@pytest.mark.skipif(not _chromium_ok(), reason="Chromium not available")
def test_browser_no_service_worker(site):
    rep = run(make_good_site(site), browser=True)
    assert rep.browser["registrations"] == []
    assert "browser-sw" in codes(rep, "warning")
