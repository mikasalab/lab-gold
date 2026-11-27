"""Indikator teknikal (dihitung dari candle yang sudah close)."""
import numpy as np
import pandas as pd


def to_df(rows):
    return pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"]).reset_index(drop=True)


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(close, n=14):
    d = close.diff()
    up, dn = d.clip(lower=0), (-d).clip(lower=0)
    au, ad = up.ewm(alpha=1 / n, adjust=False).mean(), dn.ewm(alpha=1 / n, adjust=False).mean()
    out = 100 - 100 / (1 + au / ad.replace(0, np.nan))
    return out.where(ad != 0, 100.0).fillna(50.0)


def true_range(df):
    pc = df.close.shift(1)
    return pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)


def atr(df, n=14):
    return true_range(df).ewm(alpha=1 / n, adjust=False).mean()


def adx(df, n=14):
    up, dn = df.high.diff(), -df.low.diff()
    plus = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    minus = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    a = true_range(df).ewm(alpha=1 / n, adjust=False).mean().replace(0, np.nan)
    pdi = 100 * plus.ewm(alpha=1 / n, adjust=False).mean() / a
    mdi = 100 * minus.ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean().fillna(0.0)


def macd_hist(close, fast=12, slow=26, sig=9):
    line = ema(close, fast) - ema(close, slow)
    return line - ema(line, sig)


def swings(df, n=3):
    """Swing high/low terkonfirmasi (n candle di kiri dan kanan). Hasil: [{'i','price','kind'}] urut indeks."""
    h, l = df.high.values, df.low.values
    out = []
    for i in range(n, len(df) - n):
        if h[i] == h[i - n:i + n + 1].max() and h[i] > h[i - 1]:
            out.append({"i": i, "price": float(h[i]), "kind": "H"})
        if l[i] == l[i - n:i + n + 1].min() and l[i] < l[i - 1]:
            out.append({"i": i, "price": float(l[i]), "kind": "L"})
    return sorted(out, key=lambda x: x["i"])


def with_indicators(df):
    """Tambahkan kolom EMA20/50/200, RSI, ATR, ADX, MACD histogram."""
    df = df.copy()
    for n in (20, 50, 200):
        df[f"ema{n}"] = ema(df.close, n)
    df["rsi"], df["atr"], df["adx"], df["macdh"] = rsi(df.close), atr(df), adx(df), macd_hist(df.close)
    return df
