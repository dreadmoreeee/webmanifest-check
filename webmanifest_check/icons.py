"""The `icons` logic: generate the icon set a PWA needs from one source image."""

import json
from pathlib import Path

from PIL import Image

FAVICON_SIZES = (16, 32, 48)


def _square(im: Image.Image) -> Image.Image:
    """Centre the image on a transparent square canvas (no cropping, no stretching)."""
    im = im.convert("RGBA")
    side = max(im.size)
    if im.size == (side, side):
        return im
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    return canvas


def _parse_bg(value: str | None, src: Image.Image) -> tuple[int, int, int, int]:
    if value:
        v = value.lstrip("#")
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        if len(v) != 6 or any(c not in "0123456789abcdefABCDEF" for c in v):
            raise ValueError(f"background must be a hex colour like #0a3d62, got {value!r}")
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16), 255)
    corner = src.getpixel((0, 0))
    return corner if corner[3] == 255 else (255, 255, 255, 255)


def _resize(im: Image.Image, size: int) -> Image.Image:
    return im.resize((size, size), Image.Resampling.LANCZOS)


def _padded(src: Image.Image, size: int, padding: float, bg) -> Image.Image:
    """Opaque `size` square with the artwork shrunk inside a `padding` margin on every side."""
    inner = max(1, round(size * (1 - 2 * padding)))
    canvas = Image.new("RGBA", (size, size), bg)
    art = _resize(src, inner)
    canvas.alpha_composite(art, ((size - inner) // 2, (size - inner) // 2))
    return canvas


def generate(source: str | Path, outdir: str | Path, url_prefix: str = "/icons/",
             background: str | None = None, maskable_padding: float = 0.2,
             force: bool = False) -> dict:
    """Write the icons into outdir. Existing files are kept unless force=True.

    Returns {"written": [...], "skipped": [...], "manifest_icons": [...]}.
    """
    if not 0 <= maskable_padding < 0.5:
        raise ValueError("maskable padding must be from 0 up to (not including) 0.5")
    with Image.open(source) as im:
        src = _square(im)
    if src.width < 512:
        note_small = True
    else:
        note_small = False
    bg = _parse_bg(background, src)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    written, skipped = [], []

    def save(name, image, **kw):
        path = out / name
        if path.exists() and not force:
            skipped.append(name)
            return
        image.save(path, **kw)
        written.append(name)

    save("icon-192.png", _resize(src, 192), format="PNG")
    save("icon-512.png", _resize(src, 512), format="PNG")
    save("icon-maskable-512.png", _padded(src, 512, maskable_padding, bg), format="PNG")
    save("apple-touch-icon.png", _padded(src, 180, 0.0, bg).convert("RGB"), format="PNG")
    ico_base = _resize(src, max(FAVICON_SIZES))
    save("favicon.ico", ico_base, format="ICO", sizes=[(s, s) for s in FAVICON_SIZES])

    prefix = url_prefix if url_prefix.endswith("/") else url_prefix + "/"
    snippet = [
        {"src": prefix + "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": prefix + "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": prefix + "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ]
    return {"written": written, "skipped": skipped, "manifest_icons": snippet, "small_source": note_small}


def snippet_json(icons: list) -> str:
    return json.dumps({"icons": icons}, indent=2)
