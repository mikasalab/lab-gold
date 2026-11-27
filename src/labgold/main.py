"""Titik masuk lab-gold:  python -m labgold.main   (dipicu cron-job.org -> GitHub Actions).
Opsi: --check (data+gambar, tanpa AI/Telegram) --ai-test (plus panggilan AI) --telegram-test --report --force"""
import argparse
import datetime as dt
import sys
import time
import traceback

from . import ai as ai_mod
from .alerts import Alerts, fmt_alert
from .chart import render
from .config import TF_ORDER, TOKEN_EXPIRY, VERSION_RULES, env, load_settings
from .data import DataError, TwelveData, get_candles, get_macro, is_fresh
from .econ_calendar import blackout_event, known, refresh_calendar, table_lines
from .notify import Telegram, esc, fmt_caption, fmt_wib
from .report import build_report, decisions_by_day
from .session import ny_day_start, ny_now, session_state
from .snapshot import build_table, compute_levels, frames_from_rows
from .store import MemoryStore, MongoStore
from .tracker import OPEN, create_signal, update_signals
from .validator import precheck, validate


def log_decision(store, now_ts, candle_ts, final, reason="", res=None, meta=None, bad=None, table="", price=None):
    doc = {"ts": now_ts, "candle_ts": candle_ts, "final": final, "reason": reason[:200], "price": price,
           "rules": VERSION_RULES, "validator": bad or [], "table": table}
    if res:
        doc.update({k: res[k] for k in ("status", "confidence", "pola_visual", "tipe_entry", "entry", "stop_loss", "take_profit",
                                        "analisa_gambar", "faktor_kunci", "jebakan_terdeteksi")})
    if meta:
        doc.update({k: meta[k] for k in ("provider", "model", "latency_ms", "fallback")})
        doc["attempts"] = meta["attempts"]
    store.add_decision(doc)


def daily_checks(store, now_ts, cfg, alerts):
    """Sekali per hari New York, di run pertama dalam sesi: kalender, ruang database, token, dan alert WAIT tinggi."""
    key = f"daily:{ny_now(now_ts).date()}"
    if store.get(key):
        return
    store.set(key, {"at": now_ts})
    cal = store.get("calendar") or {}
    if cal.get("fails", 0) >= 2:
        alerts.fire("kalender", f"Gagal {cal['fails']}x: {cal.get('error', '')}"[:200], now_ts, key="kalender", ttl=86400)
    ratio = getattr(store, "storage_ratio", lambda: None)()
    if ratio is not None and ratio >= 0.8:
        alerts.fire("storage", f"Pemakaian ruang sekitar {round(100 * ratio)}% dari 512 MB", now_ts, key="storage", ttl=86400)
    try:
        left = (dt.date.fromisoformat(TOKEN_EXPIRY) - ny_now(now_ts).date()).days
        if left <= 14:
            alerts.fire("token", f"Token GitHub kedaluwarsa {TOKEN_EXPIRY} ({left} hari lagi)", now_ts, key="token", ttl=86400)
    except ValueError:
        pass
    days = [(d, o) for d, o in decisions_by_day(store, now_ts).items() if o["analyzed"] >= cfg["min_analyses_day"]]
    n_need = max(cfg["wait_alert_days"], cfg["zero_signal_days"])
    last = days[-n_need:]
    msgs = []
    if len(last) >= cfg["wait_alert_days"]:
        w = last[-cfg["wait_alert_days"]:]
        if all(o["wait"] / o["analyzed"] > cfg["wait_alert_ratio"] for _, o in w):
            msgs.append(f"AI menjawab WAIT di atas {cfg['wait_alert_ratio'] * 100:g}% selama {len(w)} hari bursa berturut-turut")
    if len(last) >= cfg["zero_signal_days"]:
        z = last[-cfg["zero_signal_days"]:]
        if all(o["signal"] == 0 for _, o in z):
            msgs.append(f"Nol sinyal selama {len(z)} hari bursa berturut-turut")
    if msgs:
        alerts.fire("wait_tinggi", "; ".join(msgs), now_ts, key="wait_tinggi", ttl=86400)
    else:
        alerts.resolve("wait_tinggi", now_ts, "Aktivitas sinyal kembali normal.", notify=False)


def handle_data_error(store, alerts, e, now_ts, cfg):
    inc = store.get("inc:data") or {"n": 0}
    inc["n"] = inc.get("n", 0) + 1
    store.set("inc:data", inc)
    print(f"DATA ERROR: {e}")
    if inc["n"] == 1:
        alerts.fire("data_sesaat", str(e)[:250], now_ts)
    elif inc["n"] == cfg["data_escalate_runs"]:
        alerts.fire("data_beruntun", str(e)[:250], now_ts)


def run(store, td, tg, atg, now_ts, cfg, force=False, session=None, ai_fn=None):
    alerts = Alerts(store, atg)
    ai_fn = ai_fn or ai_mod.analyze
    if not store.acquire_lock(now_ts):
        print("Run lain sedang berjalan. Keluar.")
        return {"skipped": "lock"}
    out = {"result": None}
    try:
        in_sess, new_ok, detail = session_state(now_ts, cfg)
        if force:
            in_sess, new_ok, detail = True, True, "dipaksa (uji)"
        open_sigs = store.signals(OPEN)
        if not in_sess and not open_sigs:
            print(f"Di luar sesi ({detail}) dan tidak ada sinyal terbuka. Selesai.")
            return {"skipped": detail}
        try:
            m15 = get_candles(store, td, "M15", now_ts)
        except DataError as e:
            handle_data_error(store, alerts, e, now_ts, cfg)
            return {"error": str(e)}
        for s in update_signals(store, m15, now_ts, cfg):
            print(f"[hasil] {s['kind']} {s['status']} {s['r']}")
            if cfg["send_results"] and s["kind"] == "SIGNAL" and s.get("r") is not None:
                tg.send(f"<b>Hasil {esc(s['direction'])} XAUUSD</b>: {s['status']} · <b>{s['r']:+.2f}R</b> · {fmt_wib(s['closed_ts'])}", html=True)
        if not in_sess:
            print(f"Di luar sesi ({detail}); hanya pelacakan hasil.")
            return {"skipped": detail, "tracked": True}
        daily_checks(store, now_ts, cfg, alerts)
        cal = refresh_calendar(store, now_ts, session)
        macro = get_macro(store, now_ts, session)
        try:
            rows = {"M15": m15, "H1": get_candles(store, td, "H1", now_ts), "H4": get_candles(store, td, "H4", now_ts)}
            for tf in TF_ORDER:
                if not is_fresh(rows[tf], tf, now_ts):
                    raise DataError(f"data {tf} tidak segar (candle terakhir terlalu lama)")
            frames = frames_from_rows(rows)
        except DataError as e:
            handle_data_error(store, alerts, e, now_ts, cfg)
            return {"error": str(e)}
        if (store.get("inc:data") or {}).get("n"):
            alerts.resolve("data_beruntun", now_ts, "Pengambilan data kembali normal.", notify=(store.get("inc:data") or {}).get("n", 0) >= cfg["data_escalate_runs"])
            store.set("inc:data", {"n": 0})
        candle_ts = int(m15[-1][0])
        if store.get("last_analyzed") == candle_ts and not force:
            print(f"Candle {candle_ts} sudah dianalisis. Selesai.")
            return {"skipped": "sudah dianalisis"}
        levels = compute_levels(frames, now_ts)
        table, ctx = build_table(frames, levels, macro, table_lines(cal, now_ts), now_ts, cfg)
        news = blackout_event(cal, now_ts, cfg["news_blackout_min"]) if known(cal, now_ts) else None
        why = precheck(store, now_ts, cfg, new_ok, news, ny_day_start(now_ts))
        if why:
            log_decision(store, now_ts, candle_ts, "SKIP", why, table=table, price=ctx["price"])
            store.set("last_analyzed", candle_ts)
            print(f"[SKIP] {why}")
            return {"result": "SKIP", "reason": why}
        png = render(frames, levels)
        try:
            res, meta = ai_fn(png, table, session)
        except ai_mod.AIError as e:
            fail = store.get("ai_fail") or {}
            n = fail.get("n", 0) + 1 if fail.get("candle") == candle_ts else 1
            store.set("ai_fail", {"candle": candle_ts, "n": n})
            alerts.fire("ai_gagal", str(e)[:250], now_ts, key="ai_gagal", ttl=3600)
            print(f"[AI GAGAL] percobaan {n}")
            if n >= 3:
                log_decision(store, now_ts, candle_ts, "ERROR", str(e), table=table, price=ctx["price"])
                store.set("last_analyzed", candle_ts)
            return {"result": "ERROR"}
        alerts.resolve("ai_gagal", now_ts, "Analisis AI kembali normal.", notify=False)
        if meta.get("fallback"):
            alerts.fire("ai_cadangan", f"Memakai {meta['model']}; gagal: {'; '.join(meta['attempts'])}"[:250], now_ts, key="ai_cadangan", ttl=6 * 3600)
        bad, final = [], "WAIT"
        if res["status"] in ("LONG", "SHORT"):
            bad = validate(res, ctx, cfg, store.signals(kinds=("SIGNAL",)), now_ts)
            if bad:
                final = "DITOLAK"
            elif res["confidence"] < cfg["min_confidence"]:
                final = "BAWAH_AMBANG"
            else:
                final = "SIGNAL"
        reason = "; ".join(bad) if bad else (f"confidence {res['confidence']} < {cfg['min_confidence']}" if final == "BAWAH_AMBANG" else "")
        log_decision(store, now_ts, candle_ts, final, reason, res, meta, bad, table, ctx["price"])
        store.set("last_analyzed", candle_ts)
        if final == "SIGNAL":
            sig = create_signal(store, res, ctx, candle_ts, now_ts, "SIGNAL", {"provider": meta["provider"], "model": meta["model"]})
            if sig and not tg.send_photo(png, fmt_caption(sig, now_ts)):
                alerts.fire("crash", "Sinyal tercatat tetapi pengiriman Telegram gagal (cek token/chat ID bot sinyal)", now_ts, key="tg_gagal", ttl=3600)
        elif final == "BAWAH_AMBANG":
            create_signal(store, res, ctx, candle_ts, now_ts, "SHADOW", {"provider": meta["provider"], "model": meta["model"]})
        print(f"[{final}] {res['status']} conf {res['confidence']} via {meta['model']} ({meta['latency_ms']} ms){' · ' + reason[:80] if reason else ''}")
        out = {"result": final}
        credits = store.get(f"credits:{ny_day_start(now_ts)}") or 0
        store.set(f"credits:{ny_day_start(now_ts)}", credits + td.calls)
        return out
    finally:
        store.release_lock()


# ------------------------------------------------------------------ mode uji (tanpa database)
def _fetch_all(td, store, now_ts):
    rows = {tf: get_candles(store, td, tf, now_ts) for tf in TF_ORDER}
    frames = frames_from_rows(rows)
    levels = compute_levels(frames, now_ts)
    return frames, levels


def check(now_ts, cfg, with_ai=False):
    store, td = MemoryStore(), TwelveData(env("TWELVE_DATA_KEY"))
    try:
        frames, levels = _fetch_all(td, store, now_ts)
    except DataError as e:
        print(f"DATA ERROR: {e}")
        return 1
    cal, macro = refresh_calendar(store, now_ts), get_macro(store, now_ts)
    table, ctx = build_table(frames, levels, macro, table_lines(cal, now_ts), now_ts, cfg)
    png = render(frames, levels)
    print(f"Data OK: kredit Twelve Data {td.calls} · harga {ctx['price']:.2f} · ATR M15 {ctx['atr_m15']:.2f} · level {len(levels)}")
    print(f"Kalender: {'OK ' + str(len(cal.get('events', []))) + ' event' if known(cal, now_ts) else 'TIDAK TERSEDIA (' + str(cal.get('error')) + ')'}")
    print(f"Makro Yahoo: {', '.join(macro) if macro else 'TIDAK TERSEDIA (bot tetap jalan)'}")
    print(f"Gambar: {len(png) // 1024} KB · tabel: {len(table)} karakter · sesi: {session_state(now_ts, cfg)[2]}")
    if with_ai:
        try:
            res, meta = ai_mod.analyze(png, table)
        except ai_mod.AIError as e:
            print(f"AI GAGAL: {e}")
            return 1
        print(f"AI OK: {meta['model']} · {meta['latency_ms']} ms · status {res['status']} · confidence {res['confidence']} · "
              f"gagal sebelumnya: {meta['attempts'] or 'tidak ada'}")
    return 0


def telegram_test(now_ts, cfg, tg, atg):
    from .demo import make_rows
    store = MemoryStore()
    rows = make_rows(now_ts)
    rows = {tf: [r for r in rows[tf] if r[0] + {"M15": 900, "H1": 3600, "H4": 14400}[tf] <= now_ts] for tf in rows}
    frames = frames_from_rows(rows)
    levels = compute_levels(frames, now_ts)
    p = float(frames["M15"].close.iloc[-1])
    sig = {"direction": "LONG", "pola": "CONTOH: pin bar di PDL", "confidence": 7, "entry_type": "LIMIT", "entry": round(p - 1, 2),
           "sl": round(p - 7, 2), "sl_dist": 6.0, "tp": round(p + 8, 2), "rr": 1.67, "faktor_kunci": ["contoh data sintetis"],
           "analisa": "INI PESAN TES dengan data sintetis (bukan harga asli). Memastikan sendPhoto dan caption berfungsi."}
    ok1 = tg.send_photo(render(frames, levels), fmt_caption(sig, now_ts))
    ok2 = atg.send(fmt_alert("pulih", "Tes koneksi bot alert", now_ts, title="Tes bot alert"), html=True)
    print(f"Bot sinyal (foto): {'OK' if ok1 else 'GAGAL'} · bot alert: {'OK' if ok2 else 'GAGAL'}"
          + ("" if ok1 and ok2 else " (cek token dan chat ID, dan pastikan sudah menekan Start di bot)"))
    return 0 if ok1 and ok2 else 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    for f in ("--check", "--ai-test", "--telegram-test", "--report", "--force"):
        ap.add_argument(f, action="store_true")
    args = ap.parse_args(argv)
    now, cfg = int(time.time()), load_settings()
    tg = Telegram(env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID"))
    atg = Telegram(env("ALERT_BOT_TOKEN") or env("TELEGRAM_BOT_TOKEN"), env("ALERT_CHAT_ID") or env("TELEGRAM_CHAT_ID"))
    if args.telegram_test:
        return telegram_test(now, cfg, tg, atg)
    if args.check or args.ai_test:
        return check(now, cfg, with_ai=args.ai_test)
    url = env("MONGO_URL")
    if not url:
        print("MONGO_URL belum diisi.")
        return 1
    try:
        store = MongoStore(url, env("DB_NAME", "xauv3"))
    except Exception as e:  # noqa: BLE001
        print(f"Koneksi database gagal: {type(e).__name__}")
        if (now // 300) % 12 == 0:                                   # tanpa database tidak ada pencegah duplikat: sekali per jam
            Alerts(None, atg).fire("atlas", f"{type(e).__name__}: tidak bisa terhubung ke MongoDB Atlas", now)
        return 1
    if args.report:
        return 0 if atg.send(build_report(store, now), html=True) else 1
    try:
        run(store, TwelveData(env("TWELVE_DATA_KEY")), tg, atg, now, cfg, force=args.force)
        return 0
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        try:
            Alerts(store, atg).fire("crash", f"{type(e).__name__}: {str(e)[:150]}", now, key="crash", ttl=3600)
        except Exception:  # noqa: BLE001
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
