"""Laporan kalibrasi: keputusan terbaru dan hasil nyata per tingkat confidence (HTML Telegram)."""
import datetime as dt
from collections import Counter

from .config import NY
from .notify import esc, fmt_wib
from .tracker import stats_by_confidence


def decisions_by_day(store, now_ts, days=10):
    """{tanggal_NY: {'analyzed','wait','signal','final': Counter}} untuk hari-hari sebelum hari ini."""
    today = dt.datetime.fromtimestamp(now_ts, NY).date()
    out = {}
    for d in store.decisions_since(now_ts - days * 86400):
        day = dt.datetime.fromtimestamp(d["ts"], NY).date()
        if day >= today:
            continue
        o = out.setdefault(day, {"analyzed": 0, "wait": 0, "signal": 0, "final": Counter()})
        o["final"][d["final"]] += 1
        if d["final"] in ("WAIT", "DITOLAK", "BAWAH_AMBANG", "SIGNAL"):          # hanya yang benar-benar dianalisis AI
            o["analyzed"] += 1
            o["wait"] += 1 if d["final"] == "WAIT" else 0
            o["signal"] += 1 if d["final"] == "SIGNAL" else 0
    return dict(sorted(out.items()))


def build_report(store, now_ts):
    L = ["<b>📈 LAPORAN LAB-GOLD</b>", f"<i>{fmt_wib(now_ts)}</i>", ""]
    docs = store.decisions_since(now_ts - 7 * 86400)
    c = Counter(d["final"] for d in docs)
    L.append("<b>Keputusan 7 hari</b>: " + (" · ".join(f"{k} {v}" for k, v in c.most_common()) or "belum ada"))
    rej = Counter(r for d in docs if d["final"] == "DITOLAK" for r in d.get("validator", []))
    if rej:
        L += ["", "<b>Alasan ditolak validator (terbanyak)</b>"] + [f"• {esc(k[:90])} — {v}x" for k, v in rej.most_common(4)]
    skip = Counter(d.get("reason", "")[:60] for d in docs if d["final"] == "SKIP")
    if skip:
        L += ["", "<b>Dilewati sebelum AI</b>"] + [f"• {esc(k)} — {v}x" for k, v in skip.most_common(3)]
    fk = Counter(f for d in docs if d["final"] == "SIGNAL" for f in d.get("faktor_kunci", []))
    if fk:
        L += ["", "<b>Faktor kunci pada sinyal</b>"] + [f"• {esc(k)} — {v}x" for k, v in fk.most_common(5)]
    for kind, title in (("SIGNAL", "Hasil sinyal terkirim"), ("SHADOW", "Hasil 'bayangan' (di bawah ambang, tidak dikirim)")):
        st = stats_by_confidence(store, kind)
        L += ["", f"<b>{title}</b> <i>(R bersih biaya, per confidence)</i>"]
        L += [f"• conf {k}: n={o['n']} · menang {o['win']} · rata-rata <b>{o['sum_r'] / o['n']:+.2f}R</b>" for k, o in st.items()] or ["• belum ada hasil"]
    L += ["", "<i>Sampel kecil belum bermakna: tunggu puluhan hasil per kelompok sebelum mengubah ambang. Bukan nasihat keuangan.</i>"]
    return "\n".join(L)
