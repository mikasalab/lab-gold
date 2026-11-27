"""Konfigurasi lab-gold. Semua angka penting ada di sini supaya mudah diubah."""
import datetime as dt
import os
from zoneinfo import ZoneInfo

WIB = dt.timezone(dt.timedelta(hours=7))
NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc

SYMBOL = "XAUUSD"
TD_SYMBOL = "XAU/USD"
VERSION_RULES = "v0.1"

# show = jumlah candle di gambar; fetch = jumlah candle yang diambil (lebih banyak agar EMA200 sudah stabil)
TF = {
    "M15": dict(td="15min", sec=900, fetch=400, show=96, swing_n=3),
    "H1": dict(td="1h", sec=3600, fetch=400, show=72, swing_n=3),
    "H4": dict(td="4h", sec=14400, fetch=300, show=42, swing_n=2),
}
TF_ORDER = ("M15", "H1", "H4")                 # urutan panel di gambar: atas -> bawah
MIN_REFETCH_AGE = {"M15": 240, "H1": 600, "H4": 1200}     # detik; hemat kredit Twelve Data
MAX_STALE = {"M15": 2700, "H1": 10800, "H4": 32400}       # umur maksimal candle terakhir (detik sejak close)


def env(name, default=None):
    """Baca environment variable. Nilai kosong dianggap tidak ada (Secrets yang belum dibuat terbaca kosong)."""
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip()


def env_float(name, default):
    try:
        return float(env(name, default))
    except (TypeError, ValueError):
        return float(default)


def env_int(name, default):
    return int(env_float(name, default))


def load_settings():
    return dict(
        # ---- keputusan ----
        min_confidence=env_int("MIN_CONFIDENCE", 6),       # ambang awal; dikalibrasi dari hasil nyata
        max_signals_day=env_int("MAX_SIGNALS_DAY", 3),     # batas sinyal per hari (tanggal New York)
        # ---- sesi (waktu New York; cron boleh lebih lebar, kode yang memutuskan) ----
        session_start_ny=8.0, session_end_ny=16.0,
        no_new_last_min=60,                                # tidak ada sinyal baru di 60 menit terakhir sesi
        friday_cutoff_ny=14.0,                             # Jumat: tidak ada sinyal baru setelah jam ini (NY)
        news_blackout_min=30,                              # berita USD HIGH +- 30 menit -> tidak dianalisis
        # ---- cooldown ----
        cooldown_signal_min=60, cooldown_sl_min=180, dup_entry_atr=0.5, dup_window_h=6,
        # ---- validator risiko ----
        min_rr=1.5, max_rr=8.0,
        sl_min_atr_m15=0.8,                                # jarak SL minimum = 0.8 x ATR M15
        sl_max_atr_h1=2.0,                                 # jarak SL maksimum = 2.0 x ATR H1
        market_max_atr=0.6,                                # entry MARKET maksimal 0.6 ATR M15 dari harga terakhir
        limit_max_atr=2.0,                                 # entry LIMIT maksimal 2 ATR M15 di sisi yang benar
        spread=env_float("XAU_SPREAD", 0.25), slip=env_float("XAU_SLIP", 0.05),   # dolar per 1 oz
        cost_max_r=0.15,
        # ---- pelacak hasil ----
        fill_max_atr=1.0, limit_valid_candles=8, max_hold_candles=96,
        # ---- alert ----
        wait_alert_ratio=0.98, wait_alert_days=3, zero_signal_days=3, min_analyses_day=10,
        data_escalate_runs=3,
        send_results=env("SEND_RESULTS", "0") == "1",      # kirim pesan hasil TP/SL ke bot sinyal (default mati)
    )


TOKEN_EXPIRY = env("GH_TOKEN_EXPIRY", "2027-10-25")
