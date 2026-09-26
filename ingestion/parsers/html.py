from html.parser import HTMLParser


class Snapshot(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.text = [], []
        self.in_title, self.hidden = False, 0

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if not self.hidden and data.strip():
            self.text.append(data.strip())


def parse_html(data):
    parser = Snapshot()
    parser.feed(data.decode("utf-8", errors="replace"))
    return {"format": "html", "title": "".join(parser.title), "text": "\n".join(parser.text),
            "decoding": "utf-8 with replacement; original bytes retained"}
