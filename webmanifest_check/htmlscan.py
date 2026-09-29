"""Pull the <link> and <meta> tags we care about out of an HTML page."""

from html.parser import HTMLParser


class PageTags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[dict] = []
        self.metas: list[dict] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "link":
            a["rel"] = a.get("rel", "").lower()
            self.links.append(a)
        elif tag == "meta":
            self.metas.append(a)

    def links_with(self, rel: str) -> list[dict]:
        return [link for link in self.links if rel in link["rel"].split() and link.get("href")]

    def meta(self, name: str) -> str | None:
        for m in self.metas:
            if m.get("name", "").lower() == name and "content" in m:
                return m["content"].strip()
        return None


def scan(html: str) -> PageTags:
    p = PageTags()
    p.feed(html)
    p.close()
    return p
