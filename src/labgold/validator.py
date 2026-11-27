"""Validator kode: menjaga risiko. AI memberi usulan; angka yang melanggar batas dibuang di sini."""


def validate(res, ctx, cfg, prev_signals=(), now_ts=0):
    """res: hasil AI (LONG/SHORT). ctx: price, atr_m15, atr_h1. Kembalikan daftar alasan penolakan ([] = lolos)."""
    bad = []
    e, sl, tp = res.get("entry"), res.get("stop_loss"), res.get("take_profit")
    if res["status"] not in ("LONG", "SHORT") or None in (e, sl, tp):
        return ["angka entry/SL/TP tidak lengkap"]
    price, a15, a1 = ctx["price"], ctx["atr_m15"], ctx["atr_h1"]
    long_ = res["status"] == "LONG"
    if long_ and not (sl < e < tp):
        return ["urutan harga salah untuk LONG (harus SL < entry < TP)"]
    if not long_ and not (tp < e < sl):
        return ["urutan harga salah untuk SHORT (harus TP < entry < SL)"]
    dist, reward = abs(e - sl), abs(tp - e)
    # ---- lokasi entry
    if res["tipe_entry"] == "MARKET":
        if abs(e - price) > cfg["market_max_atr"] * a15:
            bad.append(f"entry MARKET {abs(e - price):.2f} dari harga ({abs(e - price) / a15:.1f} ATR) melebihi {cfg['market_max_atr']:g} ATR M15")
    else:
        away = (price - e) if long_ else (e - price)           # LIMIT harus lebih baik dari harga sekarang
        if away < -0.1 * a15:
            bad.append("entry LIMIT berada di sisi yang salah terhadap harga sekarang")
        elif away > cfg["limit_max_atr"] * a15:
            bad.append(f"entry LIMIT terlalu jauh ({away / a15:.1f} ATR M15, maks {cfg['limit_max_atr']:g})")
    # ---- SL, RR, biaya
    if dist < cfg["sl_min_atr_m15"] * a15:
        bad.append(f"SL terlalu dekat ({dist:.2f} < {cfg['sl_min_atr_m15']:g} ATR M15)")
    if dist > cfg["sl_max_atr_h1"] * a1:
        bad.append(f"SL terlalu lebar ({dist:.2f} > {cfg['sl_max_atr_h1']:g} ATR H1)")
    rr = reward / dist if dist else 0
    if rr < cfg["min_rr"]:
        bad.append(f"RR {rr:.2f} di bawah minimum {cfg['min_rr']:g}")
    if rr > cfg["max_rr"]:
        bad.append(f"RR {rr:.1f} tidak realistis (maks {cfg['max_rr']:g})")
    cost_r = (cfg["spread"] + cfg["slip"]) / dist if dist else 9
    if cost_r > cfg["cost_max_r"]:
        bad.append(f"biaya {cost_r:.2f}R melebihi {cfg['cost_max_r']:g}R")
    # ---- duplikat
    for s in prev_signals:
        if s.get("kind") == "SIGNAL" and s["direction"] == res["status"] and now_ts - s["created_ts"] <= cfg["dup_window_h"] * 3600 \
                and abs(s["entry"] - e) <= cfg["dup_entry_atr"] * a15:
            bad.append("duplikat sinyal sebelumnya (arah dan entry hampir sama)")
            break
    return bad


def precheck(store, now_ts, cfg, session_ok, news_event, day_start_ts):
    """Pemeriksaan sebelum memanggil AI (hemat kuota). Kembalikan alasan blokir atau None."""
    if not session_ok:
        return "sesi: sinyal baru tidak diizinkan"
    if news_event:
        return f"berita: {news_event['title']} dalam +-{cfg['news_blackout_min']} menit"
    sigs = [s for s in store.signals(kinds=("SIGNAL",))]
    if any(s["status"] in ("PENDING", "ACTIVE") for s in sigs):
        return "masih ada sinyal terbuka"
    today = [s for s in sigs if s["created_ts"] >= day_start_ts]
    if len(today) >= cfg["max_signals_day"]:
        return f"batas sinyal harian tercapai ({len(today)}/{cfg['max_signals_day']})"
    if sigs:
        last = max(sigs, key=lambda s: s["created_ts"])
        if now_ts - last["created_ts"] < cfg["cooldown_signal_min"] * 60:
            return "cooldown setelah sinyal terakhir"
        if last.get("status") == "HIT_SL" and last.get("closed_ts") and now_ts - last["closed_ts"] < cfg["cooldown_sl_min"] * 60:
            return "cooldown setelah SL"
    return None
