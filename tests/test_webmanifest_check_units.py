import json

import pytest
from wmc_helpers import png
from PIL import Image

from webmanifest_check.cli import main
from webmanifest_check.colors import is_css_color
from webmanifest_check.htmlscan import scan
from webmanifest_check.icons import generate


@pytest.mark.parametrize("v", ["#fff", "#FFFF", "#0a3d62", "#0a3d62cc", "red", "RebeccaPurple", "transparent",
                               "rgb(1, 2, 3)", "rgb(1 2 3 / 50%)", "rgba(0,0,0,.5)", "hsl(120deg 50% 50%)",
                               "oklch(0.7 0.1 200)", "color(display-p3 1 0 0)"])
def test_valid_colors(v):
    assert is_css_color(v)


@pytest.mark.parametrize("v", ["", "#12", "#ggg", "#12345", "notacolour", "rgb(1,2)", "rgb()", "0a3d62"])
def test_invalid_colors(v):
    assert not is_css_color(v)


def test_html_scan():
    t = scan('<LINK REL="Shortcut Icon" href=/f.ico><link rel=manifest href="/m.json"><meta name=Theme-Color content=" #fff ">'
             "<link rel=icon>")
    assert t.links_with("manifest")[0]["href"] == "/m.json"
    assert t.links_with("icon")[0]["href"] == "/f.ico"
    assert len(t.links_with("icon")) == 1  # the href-less one is ignored
    assert t.meta("theme-color") == "#fff"


def test_generate_full_set(tmp_path):
    src = tmp_path / "src.png"
    src.write_bytes(png(600, (200, 30, 30, 255)))
    res = generate(src, tmp_path / "out", url_prefix="/img")
    out = tmp_path / "out"
    assert sorted(res["written"]) == ["apple-touch-icon.png", "favicon.ico", "icon-192.png",
                                      "icon-512.png", "icon-maskable-512.png"]
    assert Image.open(out / "icon-192.png").size == (192, 192)
    assert Image.open(out / "icon-512.png").size == (512, 512)
    assert Image.open(out / "apple-touch-icon.png").size == (180, 180)
    assert Image.open(out / "apple-touch-icon.png").mode == "RGB"
    with Image.open(out / "favicon.ico") as ic:
        assert sorted(ic.info["sizes"]) == [(16, 16), (32, 32), (48, 48)]
    assert res["manifest_icons"][2]["purpose"] == "maskable"
    assert res["manifest_icons"][0]["src"] == "/img/icon-192.png"


def test_maskable_has_safe_zone_padding(tmp_path):
    src = tmp_path / "s.png"
    Image.new("RGBA", (512, 512), (255, 0, 0, 255)).save(src)
    generate(src, tmp_path / "o", background="#0000ff")
    im = Image.open(tmp_path / "o" / "icon-maskable-512.png").convert("RGBA")
    assert im.getpixel((5, 5)) == (0, 0, 255, 255)          # padding uses the background
    assert im.getpixel((256, 256)) == (255, 0, 0, 255)      # artwork in the centre
    assert im.getpixel((100, 256)) == (0, 0, 255, 255)      # inside 20% margin (~102 px)
    assert im.getpixel((110, 256)) == (255, 0, 0, 255)


def test_non_square_source_is_padded_not_stretched(tmp_path):
    src = tmp_path / "wide.png"
    Image.new("RGBA", (400, 200), (0, 255, 0, 255)).save(src)
    generate(src, tmp_path / "o")
    im = Image.open(tmp_path / "o" / "icon-512.png")
    assert im.size == (512, 512)
    assert im.getpixel((256, 5))[3] == 0      # transparent band above the artwork
    assert im.getpixel((256, 256))[3] == 255


def test_existing_files_kept_unless_force(tmp_path):
    src = tmp_path / "s.png"
    src.write_bytes(png(512))
    out = tmp_path / "o"
    out.mkdir()
    (out / "icon-192.png").write_bytes(b"mine")
    res = generate(src, out)
    assert res["skipped"] == ["icon-192.png"] and (out / "icon-192.png").read_bytes() == b"mine"
    res = generate(src, out, force=True)
    assert res["skipped"] == [] and Image.open(out / "icon-192.png").size == (192, 192)


def test_bad_background_and_padding(tmp_path):
    src = tmp_path / "s.png"
    src.write_bytes(png(512))
    with pytest.raises(ValueError):
        generate(src, tmp_path / "o", background="blue")
    with pytest.raises(ValueError):
        generate(src, tmp_path / "o", maskable_padding=0.6)


def test_cli_icons(tmp_path, capsys):
    src = tmp_path / "s.png"
    src.write_bytes(png(512))
    assert main(["icons", str(src), "-o", str(tmp_path / "o")]) == 0
    out = capsys.readouterr().out
    assert '"purpose": "maskable"' in out and "wrote icon-192.png" in out
    assert main(["icons", str(src), "-o", str(tmp_path / "o"), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["skipped"]


def test_cli_icons_missing_source(tmp_path, capsys):
    assert main(["icons", str(tmp_path / "nope.png"), "-o", str(tmp_path / "o")]) == 2
    assert "webmanifest-check:" in capsys.readouterr().err


def test_generated_icons_pass_check(tmp_path, site):
    """Round trip: icons made by `icons` satisfy `check`."""
    from wmc_helpers import GOOD_HTML, make_good_site
    from webmanifest_check.checks import check_site
    from webmanifest_check.http import Fetcher

    src = tmp_path / "s.png"
    src.write_bytes(png(512))
    res = generate(src, tmp_path / "o")
    manifest = {"id": "/", "name": "RT", "short_name": "RT", "start_url": "/", "scope": "/", "display": "standalone",
                "theme_color": "#fff", "background_color": "#fff", "icons": res["manifest_icons"]}
    make_good_site(site, manifest, GOOD_HTML.replace("#0a3d62", "#fff"))
    for n in ("icon-192", "icon-512", "icon-maskable-512"):
        site.add(f"/icons/{n}.png", (tmp_path / "o" / f"{n}.png").read_bytes(), "image/png")
    rep = check_site(site.url + "/", Fetcher(delay=0))
    assert rep.count("error") == 0, [f.message for f in rep.findings if f.level == "error"]
