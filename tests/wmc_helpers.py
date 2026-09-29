import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image


def png(size, color=(10, 60, 120, 255), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGBA", (size, size), color).convert("RGB" if fmt == "JPEG" else "RGBA").save(buf, format=fmt)
    return buf.getvalue()


def ico(sizes=(16, 32, 48)):
    buf = io.BytesIO()
    Image.new("RGBA", (48, 48), (1, 2, 3, 255)).save(buf, format="ICO", sizes=[(s, s) for s in sizes])
    return buf.getvalue()


class Site:
    """Local test server. routes: path -> (status, content_type, body_bytes)."""

    def __init__(self):
        self.routes = {}
        self.hits = []
        site = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                site.hits.append(self.path)
                status, ctype, body = site.routes.get(self.path.split("?")[0], (404, "text/plain", b"nope"))
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def add(self, path, body, ctype="text/html", status=200):
        if isinstance(body, str):
            body = body.encode()
        self.routes[path] = (status, ctype, body)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


GOOD_HTML = """<!doctype html><html><head>
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#0a3d62">
</head><body>hi</body></html>"""

GOOD_MANIFEST = {
    "id": "/",
    "name": "Good App",
    "short_name": "Good",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "theme_color": "#0a3d62",
    "background_color": "white",
    "icons": [
        {"src": "/i192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/i512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "/m512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}


def make_good_site(site, manifest=None, html=GOOD_HTML):
    site.add("/", html)
    site.add("/manifest.webmanifest", json.dumps(manifest or GOOD_MANIFEST), "application/manifest+json")
    site.add("/i192.png", png(192), "image/png")
    site.add("/i512.png", png(512), "image/png")
    site.add("/m512.png", png(512), "image/png")
    site.add("/apple-touch-icon.png", png(180), "image/png")
    site.add("/favicon.ico", ico(), "image/x-icon")
    site.add("/favicon.svg", "<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")
    return site
