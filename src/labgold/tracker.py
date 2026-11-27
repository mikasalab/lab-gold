"""Pelacak hasil nyata sinyal (dan sinyal 'bayangan' di bawah ambang confidence) dari candle M15 tertutup.
Konservatif: bila SL dan TP tersentuh di candle yang sama, SL dianggap lebih dulu. Hasil dalam R (kelipatan jarak SL), bersih biaya."""
import datetime as dt

from .config import VERSION_RULES

OPEN = ("PENDING", "ACTIVE")
KINDS = ("SIGNAL", "SHADOW")


def create_signal(store, res, ctx, candle_ts, now_ts, kind="SIGNAL", meta=None):
    sid = f"{'S-' if kind == 'SHADOW' else ''}XAUUSD-{candle_ts}"
    if any(s["id"] == sid for s in store.signals()):
        return None
    dist = abs(res["entry"] - res["stop_loss"])
    sig = {"id": sid, "kind": kind, "rules_version": VERSION_RULES, "symbol": "XAUUSD", "direction": res["status"],
           "entry": res["entry"], "sl": res["stop_loss"], "tp": res["take_profit"], "entry_type": res["tipe_entry"],
           "confidence": res["confidence"], "pola": res["pola_visual"], "analisa": res["analisa_gambar"],
           "faktor_kunci": res["faktor_kunci"], "jebakan": res["jebakan_terdeteksi"],
           "sl_dist": dist, "rr": round(abs(res["take_profit"] - res["entry"]) / dist, 2),
           "atr_m15": ctx["atr_m15"], "price_at_signal": ctx["price"], "created_ts": now_ts, "candle_ts": candle_ts,
           "status": "PENDING", "last_ts": candle_ts, "last_close": None, "filled_ts": None, "mfe": 0.0, "mae": 0.0,
           "r": None, "closed_ts": None, "note": "", "bars": 0}
    sig.update(meta or {})
    store.add_signal(sig)
    return sig


def _close(s, status, ts, note, r):
    s.update(status=status, closed_ts=int(ts), note=note, r=None if r is None else round(r, 3))


def _r(s, px, cost):
    d = 1 if s["direction"] == "LONG" else -1
    return d * (px - s["entry"]) / s["sl_dist"] - cost / s["sl_dist"]


def process(s, rows, now_ts, cfg):
    """Putar ulang candle M15 tertutup sejak pengecekan terakhir. Mengembalikan True bila sinyal selesai."""
    buy = s["direction"] == "LONG"
    cost = cfg["spread"] + cfg["slip"]
    entry, sl, tp, dist = s["entry"], s["sl"], s["tp"], s["sl_dist"]
    for c in rows:
        if s["status"] not in OPEN:
            break
        ts, o, h, l, cl = c
        if ts <= s["last_ts"]:
            continue
        just_filled = False
        if s["status"] == "PENDING":
            if s["entry_type"] == "MARKET":
                beyond = o <= sl if buy else o >= sl
                far = abs(o - entry) > cfg["fill_max_atr"] * s["atr_m15"]
                if beyond or far:
                    _close(s, "EXPIRED", ts + 900, "harga sudah jauh dari entry / melewati SL, tidak terisi", None)
                    s["last_ts"], s["last_close"] = ts, cl
                    break
                s["status"], s["filled_ts"] = "ACTIVE", ts
            else:
                if ts - s["candle_ts"] > cfg["limit_valid_candles"] * 900:
                    _close(s, "EXPIRED", ts, "order limit kedaluwarsa", None)
                    break
                touched = (l <= entry) if buy else (h >= entry)
                if not touched:
                    if (cl <= sl) if buy else (cl >= sl):
                        _close(s, "EXPIRED", ts + 900, "harga menembus SL sebelum entry terisi", None)
                        s["last_ts"], s["last_close"] = ts, cl
                        break
                    s["last_ts"], s["last_close"] = ts, cl
                    continue
                s["status"], s["filled_ts"], just_filled = "ACTIVE", ts, True
        fav = ((h - entry) if buy else (entry - l)) / dist
        adv = ((entry - l) if buy else (h - entry)) / dist
        s["mfe"], s["mae"] = max(s["mfe"], fav), max(s["mae"], adv)
        s["bars"] += 1
        hit_sl = (l <= sl) if buy else (h >= sl)
        hit_tp = (h >= tp) if buy else (l <= tp)
        if hit_sl:
            gap = (o < sl) if buy else (o > sl)
            _close(s, "HIT_SL", ts + 900, "SL tersentuh", _r(s, o if gap else sl, cost))
        elif hit_tp and not just_filled:
            _close(s, "HIT_TP", ts + 900, "TP tersentuh", _r(s, tp, cost))
        else:
            d = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
            if d.weekday() == 4 and d.hour * 60 + d.minute >= 20 * 60 + 45:
                _close(s, "CLOSED_TIME", ts + 900, "ditutup sebelum akhir pekan", _r(s, cl, cost))
            elif s["bars"] >= cfg["max_hold_candles"]:
                _close(s, "CLOSED_TIME", ts + 900, "batas waktu tahan terlampaui", _r(s, cl, cost))
        s["last_ts"], s["last_close"] = ts, cl
    return s["status"] not in OPEN


def update_signals(store, m15_rows, now_ts, cfg):
    """Perbarui semua sinyal terbuka (SIGNAL dan SHADOW). Mengembalikan daftar sinyal yang baru selesai."""
    done = []
    for s in store.signals(OPEN):
        before = (s["status"], s["last_ts"])
        finished = process(s, m15_rows, now_ts, cfg)
        if (s["status"], s["last_ts"]) != before:
            store.update_signal(s)
        if finished:
            done.append(s)
    return done


def stats_by_confidence(store, kind="SIGNAL"):
    """{confidence: {'n','win','sum_r'}} dari sinyal yang punya hasil (bukan EXPIRED)."""
    out = {}
    for s in store.signals(kinds=(kind,)):
        if s.get("r") is None:
            continue
        o = out.setdefault(int(s["confidence"]), {"n": 0, "win": 0, "sum_r": 0.0})
        o["n"] += 1
        o["win"] += 1 if s["r"] > 0 else 0
        o["sum_r"] += s["r"]
    return dict(sorted(out.items()))
