"""Ubah candle menjadi frame berindikator, daftar level kunci, dan tabel angka untuk AI."""
import datetime as dt

import pandas as pd

from .config import TF, TF_ORDER, WIB
from .data import DataError
from .indicators import swings, to_df, with_indicators
from .session import ny_now


def frames_from_rows(rows_by_tf):
    out = {}
    for tf in TF_ORDER:
        rows = rows_by_tf[tf]
        if len(rows) < TF[tf]["show"] + 20:
            raise DataError(f"{tf}: candle kurang ({len(rows)})")
        out[tf] = with_indicators(to_df(rows))
    return out


def _wib(ts, fmt="%d %b %H:%M"):
    return dt.datetime.fromtimestamp(int(ts), WIB).strftime(fmt)


def _srv_date(ts_values):
    """Hari trading emas: bergulir pada 17:00 New York (= 00:00 waktu server)."""
    s = pd.to_datetime(pd.Series(ts_values), unit="s", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    return (s + pd.Timedelta(hours=7)).dt.normalize()


def structure(df, n):
    """Struktur dari dua swing high/low terakhir: naik (HH+HL), turun (LH+LL), atau campuran."""
    sw = swings(df.tail(300).reset_index(drop=True), n)
    hs = [s["price"] for s in sw if s["kind"] == "H"][-2:]
    ls = [s["price"] for s in sw if s["kind"] == "L"][-2:]
    if len(hs) == 2 and len(ls) == 2:
        if hs[1] > hs[0] and ls[1] > ls[0]:
            return "naik (HH+HL)"
        if hs[1] < hs[0] and ls[1] < ls[0]:
            return "turun (LH+LL)"
    return "campuran"


def compute_levels(frames, now_ts):
    """Level kunci: kemarin, sesi Asia/London, swing H1/H4 terakhir, angka bulat. [{'name','price','group'}]"""
    out = []
    h1, m15 = frames["H1"], frames["M15"]
    dates = _srv_date(h1.ts.values)
    cur = _srv_date([now_ts]).iloc[0]
    prev = sorted({d for d in dates if d < cur})
    if prev:
        sub = h1[(dates == prev[-1]).values]
        out += [{"name": "PDH", "price": float(sub.high.max()), "group": "hari"},
                {"name": "PDL", "price": float(sub.low.min()), "group": "hari"}]
    day0 = now_ts - now_ts % 86400
    for nm, a, b in (("Asia", 0, 7), ("London", 7, 12)):
        if now_ts < day0 + a * 3600:
            continue
        sub = m15[(m15.ts >= day0 + a * 3600) & (m15.ts < day0 + b * 3600)]
        if len(sub) >= 4:
            part = "" if now_ts >= day0 + b * 3600 else " (berjalan)"
            out += [{"name": f"{nm} H{part}", "price": float(sub.high.max()), "group": "sesi"},
                    {"name": f"{nm} L{part}", "price": float(sub.low.min()), "group": "sesi"}]
    for tf in ("H4", "H1"):
        df = frames[tf].tail(300).reset_index(drop=True)
        sw = swings(df, TF[tf]["swing_n"])
        for kind, tag in (("H", "SwH"), ("L", "SwL")):
            pts = [s for s in sw if s["kind"] == kind][-2:]
            for k, s in enumerate(reversed(pts), 1):
                out.append({"name": f"{tf} {tag}{k}", "price": s["price"], "group": "swing"})
    last = float(m15.close.iloc[-1])
    base = int(last // 50) * 50
    for k, p in enumerate((base, base + 50, base - 50, base + 100)):
        out.append({"name": "angka bulat", "price": float(p), "group": "bulat"})
    return out


def _candle_line(r):
    rng = max(r.high - r.low, 1e-9)
    body = abs(r.close - r.open) / rng * 100
    up = (r.high - max(r.open, r.close)) / rng * 100
    lo = (min(r.open, r.close) - r.low) / rng * 100
    return (f"  {_wib(r.ts)} O{r.open:.2f} H{r.high:.2f} L{r.low:.2f} C{r.close:.2f} | badan {body:.0f}% sumbu atas {up:.0f}% bawah {lo:.0f}%"
            f"{' (hijau)' if r.close >= r.open else ' (merah)'}")


def build_table(frames, levels, macro, cal_lines, now_ts, cfg):
    m15, h1, h4 = frames["M15"], frames["H1"], frames["H4"]
    price = float(m15.close.iloc[-1])
    a15, a1 = float(m15.atr.iloc[-1]), float(h1.atr.iloc[-1])
    n = ny_now(now_ts)
    mins_open = max(0, round((n.hour + n.minute / 60 - cfg["session_start_ny"]) * 60))
    mins_left = max(0, round((cfg["session_end_ny"] - n.hour - n.minute / 60) * 60))
    cost = cfg["spread"] + cfg["slip"]
    L = [f"XAUUSD spot | sekarang {_wib(now_ts, '%d %b %Y %H:%M')} WIB ({n:%H:%M} New York)",
         f"Harga terakhir (close M15 {_wib(m15.ts.iloc[-1] + 900, '%H:%M')} WIB): {price:.2f}",
         f"Sesi New York: {mins_open} menit sejak open, sisa {mins_left} menit | biaya masuk (spread+slip) sekitar ${cost:.2f} (= {cost / a15:.2f} ATR M15)"]
    for tf, df, emas in (("H4", h4, (50, 200)), ("H1", h1, (50, 200)), ("M15", m15, (20, 50))):
        r = df.iloc[-1]
        e1, e2 = (float(r[f"ema{e}"]) for e in emas)
        L.append(f"[{tf}] close {r.close:.2f} | EMA{emas[0]} {e1:.2f} | EMA{emas[1]} {e2:.2f} | RSI {r.rsi:.0f} | ATR {r.atr:.2f} | "
                 f"ADX {r.adx:.0f} | MACD hist {r.macdh:+.2f} | struktur {structure(df, TF[tf]['swing_n'])}")
    L.append("[M15] 6 candle tertutup terakhir (WIB):")
    L += [_candle_line(r) for r in m15.tail(6).itertuples()]
    above = sorted((l for l in levels if l["price"] > price), key=lambda l: l["price"])
    below = sorted((l for l in levels if l["price"] <= price), key=lambda l: -l["price"])

    def lv(l):
        d = abs(l["price"] - price)
        return f"{l['name']} {l['price']:.2f} (${d:.2f} = {d / a15:.1f} ATR M15)"
    L.append("Level di atas harga: " + (" | ".join(lv(l) for l in above[:5]) or "-"))
    L.append("Level di bawah harga: " + (" | ".join(lv(l) for l in below[:5]) or "-"))
    if macro:
        parts = []
        for k, v in macro.items():
            chg = "" if v.get("chg_pct") is None else f" ({v['chg_pct']:+.2f}% harian)"
            parts.append(f"{k} {v['price']:.2f}{chg} [data {_wib(v['ts'], '%H:%M') if v.get('ts') else '?'} WIB]")
        L.append("Makro: " + " | ".join(parts) + " (konteks; bisa tertunda)")
    else:
        L.append("Makro: DXY/US10Y tidak tersedia saat ini (abaikan)")
    L += cal_lines
    return "\n".join(L), {"price": price, "atr_m15": a15, "atr_h1": a1}
