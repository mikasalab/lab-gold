import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import requests  # noqa: E402

from labgold.config import load_settings  # noqa: E402

CFG = load_settings()
NOW = int(dt.datetime(2026, 12, 2, 15, 1, tzinfo=dt.timezone.utc).timestamp())      # Rabu 10:01 New York (dalam sesi)


class FakeTG:
    enabled = True

    def __init__(self):
        self.texts, self.photos = [], []

    def send(self, text, html=False):
        self.texts.append(text)
        return True

    def send_photo(self, png, caption, html=True):
        self.photos.append((png, caption))
        return True


class OfflineSession:
    """Pengganti requests: semua permintaan gagal (kalender/makro harus gagal-lunak)."""
    def get(self, *a, **k):
        raise requests.ConnectionError("offline")

    post = get


class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code, self._p = status, payload

    def json(self):
        if self._p is None:
            raise ValueError("no json")
        return self._p
