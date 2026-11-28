"""Gambar kolase 3 timeframe dengan matplotlib (garis swing, level, EMA, label harga dikendalikan penuh).
Panel atas M15 (96 candle), tengah H1 (72), bawah H4 (42). Satu gambar PNG, dibaca AI bersama tabel angka."""
import datetime as dt
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from .config import SYMBOL, TF, TF_ORDER, WIB  # noqa: E402
from .indicators import swings  # noqa: E402

UP, DOWN = "#1b9e77", "#d62728"
EMA_SPEC = {"M15": [("ema20", "EMA20", "#1f77b4"), ("ema50", "EMA50", "#ff7f0e")],
            "H1": [("ema50", "EMA50", "#ff7f0e"), ("ema200", "EMA200", "#7b1fa2")],
            "H4": [("ema50", "EMA50", "#ff7f0e"), ("ema200", "EMA200", "#7b1fa2")]}
GROUP_COLOR = {"hari": "#0b6e99", "sesi": "#8d6e00", "swing": "#555555", "bulat": "#9e9e9e"}
RIGHT_PAD = 17          # ruang di kanan untuk label harga (jumlah candle)
TICK_HOURS = {"M15": (0, 3, 6, 9, 12, 15, 18, 21), "H1": (0, 6, 12, 18), "H4": (7,)}   # jam WIB (H4 dibuka 07:00 WIB = 00:00 UTC)
LEVEL_PRIO = {"hari": 0, "sesi": 0, "swing": 1, "bulat": 3}                              # prioritas label bila dua level saling berdekatan


def _wib(ts, fmt):
    return dt.datetime.fromtimestamp(int(ts), WIB).strftime(fmt)


def _spread_labels(items, gap, ymin, ymax):
    """Atur posisi label agar tidak bertumpuk. items: [(y, text, color, special)] -> [(y_asli, y_label, text, color, special)]."""
    items = sorted(items, key=lambda t: t[0])
    ys = [it[0] for it in items]
    for i in range(1, len(ys)):                       # dorong ke atas bila terlalu rapat
        ys[i] = max(ys[i], ys[i - 1] + gap)
    if ys and ys[-1] > ymax - gap * 0.5:              # melewati batas atas -> tarik turun dari atas
        ys[-1] = ymax - gap * 0.5
        for i in range(len(ys) - 2, -1, -1):
            ys[i] = min(ys[i], ys[i + 1] - gap)
    return [(it[0], ys[i], it[1], it[2], it[3]) for i, it in enumerate(items)]


LEVEL_GROUPS = {"M15": {"hari", "sesi", "swing", "bulat"}, "H1": {"hari", "swing", "bulat"}, "H4": {"hari", "swing", "bulat"}}


def _panel(ax, tf, df, levels, last_price):
    show = TF[tf]["show"]
    start = len(df) - show
    v = df.iloc[start:]
    x = np.arange(show)
    o, h, l, c = (v[k].values for k in ("open", "high", "low", "close"))
    lo, hi = float(l.min()), float(h.max())
    pad = (hi - lo) * 0.06
    ymin, ymax = lo - pad, hi + pad
    rng = ymax - ymin
    colors = np.where(c >= o, UP, DOWN)
    ax.vlines(x, l, h, colors=colors, linewidth=1.1, zorder=3)
    ax.bar(x, np.maximum(np.abs(c - o), rng * 0.0006), bottom=np.minimum(o, c), width=0.7, color=colors, zorder=4)
    handles = []
    for col, name, color in EMA_SPEC[tf]:
        ax.plot(x, v[col].values, color=color, linewidth=1.6, zorder=5)
        handles.append(Line2D([0], [0], color=color, lw=2, label=name))
    # ---- swing: segitiga + harga, zigzag tipis, garis horizontal untuk swing yang belum ditembus
    sw = swings(df, TF[tf]["swing_n"])
    vis = [s for s in sw if s["i"] >= start]
    if len(vis) >= 2:
        ax.plot([s["i"] - start for s in vis], [s["price"] for s in vis], color="#9e9e9e", linewidth=0.9, linestyle="-", alpha=0.7, zorder=2)
    for s in vis:
        xi = s["i"] - start
        up = s["kind"] == "H"
        ax.plot(xi, s["price"] + (rng * 0.012 if up else -rng * 0.012), marker="v" if up else "^",
                color=DOWN if up else UP, markersize=6, zorder=6)
        ax.text(xi, s["price"] + (rng * 0.026 if up else -rng * 0.026), f"{s['price']:.2f}", fontsize=8.5, ha="center",
                va="bottom" if up else "top", color="#333333", zorder=7)
    cand = []                                          # (harga, teks, warna, prioritas, x_mulai, gaya garis)
    for kind in ("H", "L"):
        keep = []
        for s in [s for s in sw if s["kind"] == kind][-4:]:
            after = df.high.values[s["i"] + 1:] if kind == "H" else df.low.values[s["i"] + 1:]
            broken = len(after) and ((after.max() >= s["price"]) if kind == "H" else (after.min() <= s["price"]))
            if not broken and ymin <= s["price"] <= ymax:
                keep.append(s)
        for s in keep[-2:]:                            # "Sw" = swing (supaya tidak tertukar dengan SL = stop loss)
            cand.append((s["price"], f"{'SwH' if kind == 'H' else 'SwL'} {s['price']:.2f}", "#444444", 2, max(0, s["i"] - start), ":"))
    # ---- level kunci (kemarin, sesi, swing HTF, angka bulat)
    for lv in levels:
        p = lv["price"]
        if not (ymin <= p <= ymax) or lv["name"].startswith(tf + " S") \
                or lv["group"] not in LEVEL_GROUPS[tf] or (tf == "H4" and lv["name"].startswith("H1 ")):
            continue
        cand.append((p, f"{lv['name']} {p:.2f}", GROUP_COLOR.get(lv["group"], "#777777"), LEVEL_PRIO.get(lv["group"], 2), 0, "--"))
    labels, kept = [], []
    line_end = show - 0.3                              # garis berhenti di candle terakhir, tidak menembus teks label
    for p, text, col, _, x0, ls in sorted(cand, key=lambda c: c[3]):
        if any(abs(p - q) < rng * 0.012 for q in kept):   # dua level hampir sama: pakai yang prioritasnya lebih tinggi
            continue
        kept.append(p)
        ax.hlines(p, x0, line_end, colors="#666666" if ls == ":" else col, linestyles=ls, linewidth=1.1 if ls == ":" else 1.2, zorder=2)
        labels.append((p, text, col, False))
    labels.append((last_price, f" {last_price:.2f} ", "white", True))
    ax.axhline(last_price, color="black", linewidth=1.0, linestyle="-", alpha=0.85, zorder=6)
    xl = show - 0.2 + 0.4
    for y, yl, text, color, special in _spread_labels(labels, rng * 0.032, ymin, ymax):
        if abs(yl - y) > rng * 0.004:                 # penghubung kecil bila label bergeser
            ax.plot([xl - 0.4, xl], [y, yl], color="#999999", linewidth=0.7, zorder=7)
        if special:
            ax.text(xl, yl, text, fontsize=9.5, color="white", va="center", ha="left", zorder=9, fontweight="bold",
                    bbox=dict(facecolor="black", edgecolor="black", boxstyle="square,pad=0.2"))
        else:
            ax.text(xl, yl, text, fontsize=8.6, color=color, va="center", ha="left", zorder=8, fontweight="bold",
                    bbox=dict(facecolor="white", edgecolor="none", pad=0.8, alpha=0.9))
    # ---- sumbu waktu (WIB) dan pemisah hari
    ts = v.ts.values
    days = [_wib(t, "%d %b") for t in ts]
    for i in range(1, show):
        if days[i] != days[i - 1]:
            ax.axvline(i - 0.5, color="#bdbdbd", linewidth=0.9, linestyle="-.", zorder=1)
            ax.text(i - 0.4, ymax - rng * 0.012, days[i], fontsize=8, color="#757575", va="top", ha="left")
    ticks = [i for i, t in enumerate(ts) if int(_wib(t, "%H")) in TICK_HOURS[tf] and _wib(t, "%M") == "00"]
    if len(ticks) < 3:                                 # cadangan bila data tidak rata (mis. akhir pekan)
        ticks = list(range(0, show, max(1, show // 8)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([_wib(ts[i], "%d/%m\n%H:%M") for i in ticks], fontsize=8.5)
    ax.set_xlim(-1, show + RIGHT_PAD)
    ax.set_ylim(ymin, ymax)
    ax.yaxis.tick_right()
    ax.tick_params(axis="y", labelsize=9)
    ax.grid(True, color="#eeeeee", linewidth=0.8, zorder=0)
    for sp in ("top", "left"):
        ax.spines[sp].set_visible(False)
    handles += [Line2D([0], [0], marker="v", color="w", markerfacecolor=DOWN, markersize=8, label="swing high"),
                Line2D([0], [0], marker="^", color="w", markerfacecolor=UP, markersize=8, label="swing low")]
    ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.01), fontsize=8.5, ncol=4, frameon=False)
    ax.set_title(f"{SYMBOL} · {tf} · {show} candle · candle tertutup terakhir {_wib(ts[-1] + TF[tf]['sec'], '%d %b %H:%M')} WIB",
                 fontsize=12.5, fontweight="bold", loc="left")


def render(frames, levels, dpi=100):
    """frames: {'M15','H1','H4'} DataFrame berindikator. Kembalikan bytes PNG (16x21 inci -> 1600x2100 px)."""
    fig, axes = plt.subplots(3, 1, figsize=(16, 21), dpi=dpi, gridspec_kw={"height_ratios": [1.1, 1, 1]})
    last = float(frames["M15"].close.iloc[-1])
    for ax, tf in zip(axes, TF_ORDER):
        _panel(ax, tf, frames[tf], levels, last)
    fig.subplots_adjust(left=0.025, right=0.955, top=0.965, bottom=0.04, hspace=0.20)
    fig.text(0.025, 0.012, "Waktu = WIB (UTC+7) · garis putus-putus = level kunci · titik-titik = swing yang belum ditembus · "
                          "garis hitam = harga terakhir", fontsize=9, color="#555555")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor="white")
    plt.close(fig)
    return buf.getvalue()
