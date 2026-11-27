"""Data harga XAU/USD dari Twelve Data (cache di database) dan konteks makro dari Yahoo (opsional, gagal-lunak)."""
import datetime as dt
import time

import requests

from .config import MAX_STALE, MIN_REFETCH_AGE, TD_SYMBOL, TF

URL = "https://api.twelvedata.com/time_series"


class DataError(Exception):
    """Data pasar tidak valid / gagal diambil -> bot tidak boleh memberi sinyal."""


def parse_dt(s):
    s = str(s).strip()
    fmt = "%Y-%m-%d %H:%M:%S" if " " in s else "%Y-%m-%d"
    return int(dt.datetime.strptime(s, fmt).replace(tzinfo=dt.timezone.utc).timestamp())


class TwelveData:
    def __init__(self, key, session=None, sleeper=time.sleep, clock=time.monotonic, max_per_min=7):
        self.key, self.session = key, session or requests.Session()
        self.sleeper, self.clock, self.max_per_min = sleeper, clock, max_per_min
        self._stamps, self.calls = [], 0

    def _throttle(self):
        """Paket Basic: 8 kredit/menit -> pakai maksimal 7 per 60 detik."""
        for _ in range(10):
            now = self.clock()
            self._stamps = [t for t in self._stamps if now - t < 60.0]
            if len(self._stamps) < self.max_per_min:
                return
            self.sleeper(60.0 - (now - self._stamps[0]) + 0.3)

    def fetch(self, tf):
        if not self.key:
            raise DataError("TWELVE_DATA_KEY belum diisi")
        self._throttle()
        self._stamps.append(self.clock())
        self.calls += 1
        params = {"symbol": TD_SYMBOL, "interval": TF[tf]["td"], "outputsize": TF[tf]["fetch"],
                  "timezone": "UTC", "order": "ASC", "apikey": self.key}
        try:
            r = self.session.get(URL, params=params, timeout=30)
        except requests.RequestException as e:
            raise DataError(f"koneksi Twelve Data gagal: {type(e).__name__}")
        try:
            j = r.json()
        except ValueError:
            raise DataError(f"respons Twelve Data bukan JSON (HTTP {r.status_code})")
        if j.get("status") == "error" or "values" not in j:
            raise DataError(f"Twelve Data: {j.get('message') or j.get('code') or 'error'}")
        rows = []
        for v in j["values"]:
            try:
                rows.append([parse_dt(v["datetime"]), float(v["open"]), float(v["high"]), float(v["low"]), float(v["close"])])
            except (KeyError, ValueError, TypeError):
                raise DataError("format candle dari provider tidak dikenali")
        return rows


def clean_candles(rows, tf, now_ts):
    """Urutkan, buang duplikat timestamp, validasi OHLC, buang candle yang masih berjalan."""
    if not rows:
        raise DataError("provider tidak mengembalikan candle")
    out, dups = [], 0
    for r in sorted(rows, key=lambda x: x[0]):
        if out and out[-1][0] == r[0]:
            out[-1], dups = r, dups + 1
        else:
            out.append(r)
    if dups > 3:
        raise DataError(f"{tf}: terlalu banyak duplikat timestamp ({dups})")
    for ts, o, h, l, c in out:
        if any(v != v or v <= 0 for v in (o, h, l, c)):
            raise DataError(f"{tf}: nilai OHLC kosong/nol pada {ts}")
        if h < max(o, c) - 1e-9 or l > min(o, c) + 1e-9 or h < l:
            raise DataError(f"{tf}: OHLC tidak valid pada {ts}")
    sec = TF[tf]["sec"]
    closed = [r for r in out if r[0] + sec <= now_ts]
    if not closed:
        raise DataError(f"{tf}: tidak ada candle yang sudah close")
    return closed


def _weekend_gap(a, b):
    return dt.datetime.fromtimestamp(a, dt.timezone.utc).weekday() in (4, 5, 6) and (b - a) >= 12 * 3600


def check_gaps(rows, tf, window=60):
    """Celah besar di tengah data (di luar akhir pekan) = data tidak dapat dipercaya."""
    sec = TF[tf]["sec"]
    seg = rows[-(window if tf != "H4" else 30):]
    for a, b in zip(seg, seg[1:]):
        if (b[0] - a[0]) > sec * 6 and not _weekend_gap(a[0], b[0]):
            raise DataError(f"{tf}: ada celah data {a[0]} -> {b[0]}")


def is_fresh(rows, tf, now_ts):
    return (now_ts - (rows[-1][0] + TF[tf]["sec"])) <= MAX_STALE[tf]


def get_candles(store, client, tf, now_ts):
    """Candle tertutup dari cache; ambil ulang hanya bila candle baru seharusnya sudah ada (tidak tergantung zona waktu bar)."""
    key = f"candles:{tf}"
    cache = store.get(key) or {}
    rows = cache.get("rows") or []
    sec = TF[tf]["sec"]
    age = now_ts - cache.get("fetched_at", 0)
    need = (not rows) or (now_ts >= rows[-1][0] + 2 * sec and age >= MIN_REFETCH_AGE[tf])
    if need:
        rows = clean_candles(client.fetch(tf), tf, now_ts)
        check_gaps(rows, tf)
        store.set(key, {"rows": rows[-TF[tf]["fetch"]:], "fetched_at": now_ts})
    else:
        rows = [r for r in rows if r[0] + sec <= now_ts]
        if not rows:
            raise DataError(f"{tf}: cache kosong")
    return rows


# ------------------------------------------------------------------ makro (Yahoo, hanya konteks)
MACRO = {"DXY": "DX-Y.NYB", "US10Y": "^TNX"}
MACRO_TTL, MACRO_BACKOFF = 3600, 1800


def _yahoo_one(symbol, session):
    r = session.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                    params={"interval": "1d", "range": "5d"}, timeout=15,
                    headers={"User-Agent": "Mozilla/5.0 lab-gold-bot"})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    res = r.json()["chart"]["result"][0]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    price = res["meta"].get("regularMarketPrice") or closes[-1]
    prev = closes[-2] if len(closes) >= 2 else None
    return {"price": float(price), "chg_pct": None if not prev else round(100 * (price - prev) / prev, 2),
            "ts": int(res["meta"].get("regularMarketTime") or 0)}


def get_macro(store, now_ts, session=None):
    """Maksimal sekali per jam. Gagal -> kembalikan cache lama (bila ada) tanpa mengganggu bot."""
    m = store.get("macro") or {}
    if m.get("data") and now_ts - m.get("fetched_at", 0) < MACRO_TTL:
        return m["data"]
    if now_ts < m.get("next_try", 0):
        return m.get("data") or {}
    s, data, err = session or requests, {}, None
    for name, sym in MACRO.items():
        try:
            data[name] = _yahoo_one(sym, s)
        except Exception as e:  # noqa: BLE001 - makro hanya konteks
            err = f"{name}: {type(e).__name__}: {e}"
    if data:
        store.set("macro", {"data": data, "fetched_at": now_ts, "next_try": 0, "error": err})
        return data
    store.set("macro", {"data": m.get("data") or {}, "fetched_at": m.get("fetched_at", 0),
                        "next_try": now_ts + MACRO_BACKOFF, "error": err})
    return m.get("data") or {}
