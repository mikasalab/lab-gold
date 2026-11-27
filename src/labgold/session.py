"""Jendela sesi New York (08:00-16:00 NY). Cron memicu lebih lebar; kode inilah yang memutuskan."""
import datetime as dt

from dateutil.easter import easter

from .config import NY

ONE = dt.timedelta(days=1)


def _nth_weekday(y, m, wd, n):
    d = dt.date(y, m, 1)
    return d + dt.timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(y, m, wd):
    d = dt.date(y + (m == 12), m % 12 + 1, 1) - ONE
    return d - dt.timedelta(days=(d.weekday() - wd) % 7)


def us_holidays(y):
    """Libur pasar AS (diamati) + Jumat Agung: likuiditas tipis, tidak ada sinyal."""
    items = [dt.date(y, 1, 1), _nth_weekday(y, 1, 0, 3), _nth_weekday(y, 2, 0, 3), _last_weekday(y, 5, 0),
             dt.date(y, 6, 19), dt.date(y, 7, 4), _nth_weekday(y, 9, 0, 1), _nth_weekday(y, 11, 3, 4), dt.date(y, 12, 25)]
    out = {easter(y) - 2 * ONE}
    for d in items:
        out.add(d - ONE if d.weekday() == 5 else d + ONE if d.weekday() == 6 else d)
    return out


def ny_now(now_ts):
    return dt.datetime.fromtimestamp(now_ts, NY)


def session_state(now_ts, cfg):
    """(dalam_sesi, sinyal_baru_boleh, keterangan). Dalam sesi = dianalisis; sinyal baru dilarang di akhir sesi."""
    n = ny_now(now_ts)
    h = n.hour + n.minute / 60
    if n.weekday() >= 5:
        return False, False, "akhir pekan"
    if n.date() in us_holidays(n.year):
        return False, False, "libur pasar AS"
    if not (cfg["session_start_ny"] <= h < cfg["session_end_ny"]):
        return False, False, f"di luar sesi NY {cfg['session_start_ny']:g}-{cfg['session_end_ny']:g}"
    cutoff = cfg["session_end_ny"] - cfg["no_new_last_min"] / 60
    if n.weekday() == 4:
        cutoff = min(cutoff, cfg["friday_cutoff_ny"])
    if h >= cutoff:
        return True, False, "akhir sesi (tidak ada sinyal baru)"
    return True, True, "dalam sesi"


def ny_day_start(now_ts):
    """Timestamp UTC untuk 00:00 tanggal New York saat ini (untuk batas sinyal harian)."""
    n = ny_now(now_ts)
    return int(dt.datetime(n.year, n.month, n.day, tzinfo=NY).timestamp())
