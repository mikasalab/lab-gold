"""Telegram (HTTP API): kirim foto + caption (maks 1024 karakter), teks, dan dokumen. Waktu selalu WIB."""
import datetime as dt
import html as _html
import re

import requests

from .config import WIB

BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
CAPTION_MAX = 1000          # batas Telegram 1024; sisakan ruang aman


def esc(x):
    return _html.escape(str(x), quote=False)


def fmt_wib(ts):
    d = dt.datetime.fromtimestamp(ts, WIB)
    return f"{d.day} {BULAN[d.month - 1]} {d:%H:%M} WIB"


def _plain(text):
    return _html.unescape(re.sub(r"</?[a-zA-Z]+>", "", text))


class Telegram:
    def __init__(self, token, chat_id, session=None):
        self.token, self.chat_id, self.session = token, chat_id, session or requests
        self.enabled = bool(token and chat_id)

    def _url(self, method):
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def send(self, text, html=False):
        if not self.enabled:
            print("[telegram] belum dikonfigurasi, pesan tidak dikirim")
            return False
        try:
            payload = {"chat_id": self.chat_id, "text": text}
            if html:
                payload.update(parse_mode="HTML", disable_web_page_preview=True)
            r = self.session.post(self._url("sendMessage"), json=payload, timeout=20)
            if html and r.status_code == 400:      # format ditolak -> kirim ulang sebagai teks polos
                r = self.session.post(self._url("sendMessage"), json={"chat_id": self.chat_id, "text": _plain(text)}, timeout=20)
            if r.status_code != 200:
                print(f"[telegram] gagal HTTP {r.status_code}")
            return r.status_code == 200
        except requests.RequestException as e:
            print(f"[telegram] gagal: {type(e).__name__}")
            return False

    def send_photo(self, png, caption, html=True):
        """sendPhoto: foto <= 10 MB, caption <= 1024 karakter."""
        if not self.enabled:
            print("[telegram] belum dikonfigurasi, foto tidak dikirim")
            return False
        data = {"chat_id": self.chat_id, "caption": caption[:1024]}
        if html:
            data["parse_mode"] = "HTML"
        try:
            r = self.session.post(self._url("sendPhoto"), data=data, files={"photo": ("chart.png", png, "image/png")}, timeout=60)
            if html and r.status_code == 400:
                data.pop("parse_mode")
                data["caption"] = _plain(caption)[:1024]
                r = self.session.post(self._url("sendPhoto"), data=data, files={"photo": ("chart.png", png, "image/png")}, timeout=60)
            if r.status_code != 200:
                print(f"[telegram] foto gagal HTTP {r.status_code}")
            return r.status_code == 200
        except requests.RequestException as e:
            print(f"[telegram] foto gagal: {type(e).__name__}")
            return False

    def send_document(self, name, data, caption=None):
        if not self.enabled:
            return False
        try:
            payload = {"chat_id": self.chat_id}
            if caption:
                payload["caption"] = caption[:1024]
            r = self.session.post(self._url("sendDocument"), data=payload, files={"document": (name, data)}, timeout=60)
            return r.status_code == 200
        except requests.RequestException:
            return False


def fmt_caption(sig, now_ts):
    """Caption sinyal. Isi: status, pola visual, confidence, entry, SL, TP, analisa gambar (+ faktor kunci). Maks ~1000 karakter."""
    long_ = sig["direction"] == "LONG"
    rr = sig["rr"]
    head = [f"<b>{'🟢 LONG' if long_ else '🔴 SHORT'} XAUUSD</b> · PAPER",
            f"<b>Pola</b>: {esc(sig['pola'])}",
            f"<b>Confidence</b>: {sig['confidence']}/10",
            f"<b>Entry</b> ({sig['entry_type']}): <code>{sig['entry']:.2f}</code>",
            f"<b>SL</b>: <code>{sig['sl']:.2f}</code> (risiko ${sig['sl_dist']:.2f})",
            f"<b>TP</b>: <code>{sig['tp']:.2f}</code> (RR 1:{rr:g})"]
    tail = [f"<i>{fmt_wib(now_ts)} · berlaku selama harga masih dekat entry. Bukan nasihat keuangan.</i>"]
    fk = ", ".join(sig.get("faktor_kunci") or [])
    mid_fk = [f"<b>Faktor kunci</b>: {esc(fk)}"] if fk else []
    analisa = sig.get("analisa") or ""

    def build(a, with_fk):
        mid = ([f"<b>Analisa</b>: {esc(a)}"] if a else []) + (mid_fk if with_fk else [])
        return "\n".join(head + mid + tail)

    text = build(analisa, True)
    if len(_plain(text)) > CAPTION_MAX:
        text = build(analisa, False)
    while len(_plain(text)) > CAPTION_MAX and analisa:
        analisa = analisa[:max(0, len(analisa) - 20)].rstrip()
        text = build(analisa + ("…" if analisa else ""), False)
    return text
