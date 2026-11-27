"""Kalender ekonomi (feed gratis ForexFactory). Hanya berita USD yang relevan untuk emas."""
import datetime as dt

import requests

from .config import WIB

CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CAL_REFRESH, CAL_MAX_AGE = 6 * 3600, 7 * 86400


def parse_events(raw):
    events = []
    for e in raw:
        try:
            ts = dt.datetime.fromisoformat(e["date"]).timestamp()
        except (KeyError, ValueError, TypeError):
            continue
        events.append({"ts": int(ts), "ccy": str(e.get("country", "")).upper(),
                       "impact": str(e.get("impact", "")).upper(), "title": e.get("title", "")})
    return events


def refresh_calendar(store, now_ts, session=None):
    """Ambil paling sering tiap 6 jam; bila gagal (mis. HTTP 429), tunggu lebih lama."""
    cal = store.get("calendar") or {}
    due = (not cal.get("events")) or (now_ts - cal.get("fetched_at", 0) >= CAL_REFRESH)
    if not due or now_ts < cal.get("next_try", 0):
        return cal
    try:
        r = (session or requests).get(CAL_URL, timeout=20, headers={"User-Agent": "Mozilla/5.0 lab-gold-bot"})
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        events = parse_events(r.json())
        if not events:
            raise RuntimeError("feed kosong")
        cal = {"events": events, "fetched_at": now_ts, "fails": 0, "next_try": 0, "error": None}
    except Exception as e:  # noqa: BLE001 - kegagalan kalender tidak boleh menghentikan bot
        fails = cal.get("fails", 0) + 1
        cal.update(fails=fails, error=f"{type(e).__name__}: {e}", next_try=now_ts + min(900 * 2 ** (fails - 1), 6 * 3600))
    store.set("calendar", cal)
    return cal


def known(cal, now_ts):
    return bool(cal.get("events")) and (now_ts - cal.get("fetched_at", 0)) < CAL_MAX_AGE


def _usd_high(cal):
    return [e for e in cal.get("events", []) if e["impact"] == "HIGH" and e["ccy"] == "USD"]


def blackout_event(cal, now_ts, minutes=30):
    for e in _usd_high(cal):
        if abs(e["ts"] - now_ts) <= minutes * 60:
            return e
    return None


def table_lines(cal, now_ts, ahead_h=4, back_min=60):
    """Baris teks berita USD HIGH untuk tabel AI (waktu WIB)."""
    if not known(cal, now_ts):
        return ["Berita USD HIGH: kalender tidak tersedia (anggap ada risiko berita tak terduga)"]
    ev = sorted((e for e in _usd_high(cal) if now_ts - back_min * 60 <= e["ts"] <= now_ts + ahead_h * 3600), key=lambda e: e["ts"])
    if not ev:
        return [f"Berita USD HIGH: tidak ada dalam {ahead_h} jam ke depan / {back_min} menit terakhir"]
    out = []
    for e in ev:
        m = round((e["ts"] - now_ts) / 60)
        t = dt.datetime.fromtimestamp(e["ts"], WIB).strftime("%d %b %H:%M")
        out.append(f"Berita USD HIGH: {e['title']} {t} WIB ({'+' if m >= 0 else ''}{m} menit)")
    return out
