"""Data sintetis untuk uji (tes Telegram, uji unit). BUKAN harga asli."""
import numpy as np

from .config import TF


def make_rows(now_ts, seed=1, base=4030.0):
    """Kembalikan {tf: rows} bergaya Twelve Data (termasuk candle yang masih berjalan di akhir)."""
    rng = np.random.default_rng(seed)
    n15 = 4800 + 8
    last_open = now_ts - now_ts % 900                      # candle M15 yang sedang berjalan
    ts = last_open - 900 * np.arange(n15 - 1, -1, -1)
    drift = np.sin(np.arange(n15) / 220.0) * 0.35
    ret = rng.normal(drift, 1.3, n15)
    close = base + np.cumsum(ret) - np.cumsum(ret)[-1]
    open_ = np.r_[close[0] - ret[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0.2, 1.6, n15)
    low = np.minimum(open_, close) - rng.uniform(0.2, 1.6, n15)
    m15 = [[int(t), float(o), float(h), float(l), float(c)] for t, o, h, l, c in zip(ts, open_, high, low, close)]

    def agg(k, size):
        out = []
        end = len(m15) - (len(m15) % k) if False else len(m15)
        i = end
        while i - k >= 0 and len(out) < size:
            chunk = m15[i - k:i]
            out.append([chunk[0][0], chunk[0][1], max(c[2] for c in chunk), min(c[3] for c in chunk), chunk[-1][4]])
            i -= k
        return out[::-1]
    return {"M15": m15[-TF["M15"]["fetch"]:], "H1": agg(4, TF["H1"]["fetch"]), "H4": agg(16, TF["H4"]["fetch"])}


class FakeTD:
    """Pengganti klien Twelve Data untuk uji tanpa internet."""
    def __init__(self, now_ts, seed=1):
        self.rows, self.calls = make_rows(now_ts, seed), 0

    def fetch(self, tf):
        self.calls += 1
        return [list(r) for r in self.rows[tf]]
