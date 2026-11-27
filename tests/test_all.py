import json
import unittest

from helpers import CFG, NOW, FakeTG, OfflineSession, Resp

from labgold import ai, main as lg_main
from labgold.chart import render
from labgold.data import DataError, clean_candles, get_candles
from labgold.demo import FakeTD, make_rows
from labgold.indicators import adx, atr, rsi, swings, to_df
from labgold.notify import fmt_caption
from labgold.session import session_state
from labgold.snapshot import build_table, compute_levels, frames_from_rows
from labgold.store import MemoryStore
from labgold.tracker import create_signal, process, update_signals
from labgold.validator import precheck, validate

CTX = {"price": 4030.0, "atr_m15": 3.0, "atr_h1": 8.0}


def res(status="LONG", entry=4030.0, sl=4024.0, tp=4042.0, conf=7, tipe="MARKET"):
    return {"status": status, "pola_visual": "uji", "confidence": conf, "tipe_entry": tipe, "entry": entry, "stop_loss": sl,
            "take_profit": tp, "analisa_gambar": "uji analisa", "faktor_kunci": ["a", "b"], "jebakan_terdeteksi": []}


class TestData(unittest.TestCase):
    def test_clean_drops_forming_and_dups(self):
        rows = [[0, 1, 2, 0.5, 1.5], [900, 1, 2, 0.5, 1.5], [900, 1, 2, 0.5, 1.6], [1800, 1, 2, 0.5, 1.5]]
        out = clean_candles(rows, "M15", 2700)
        self.assertEqual([r[0] for r in out], [0, 900, 1800])           # 1800 + 900 <= 2700 -> tertutup
        out = clean_candles(rows, "M15", 2000)
        self.assertEqual([r[0] for r in out], [0, 900])
        self.assertEqual(out[1][4], 1.6)                                # duplikat: versi terakhir dipakai

    def test_invalid_ohlc(self):
        with self.assertRaises(DataError):
            clean_candles([[0, 1, 0.5, 2, 1]], "M15", 10_000)

    def test_cache_saves_credits(self):
        store, td = MemoryStore(), FakeTD(NOW)
        get_candles(store, td, "M15", NOW)
        get_candles(store, td, "M15", NOW + 60)
        self.assertEqual(td.calls, 1)
        get_candles(store, td, "M15", NOW + 1000)                       # candle baru seharusnya sudah ada
        self.assertEqual(td.calls, 2)


class TestIndicators(unittest.TestCase):
    def test_basic(self):
        df = to_df(make_rows(NOW)["H1"])
        self.assertTrue(0 <= rsi(df.close).iloc[-1] <= 100)
        self.assertGreater(atr(df).iloc[-1], 0)
        self.assertTrue(0 <= adx(df).iloc[-1] <= 100)
        sw = swings(df.tail(100).reset_index(drop=True), 3)
        self.assertTrue(any(s["kind"] == "H" for s in sw) and any(s["kind"] == "L" for s in sw))


def pipeline():
    rows = make_rows(NOW)
    rows = {tf: [r for r in rows[tf] if r[0] + {"M15": 900, "H1": 3600, "H4": 14400}[tf] <= NOW] for tf in rows}
    frames = frames_from_rows(rows)
    levels = compute_levels(frames, NOW)
    return frames, levels


class TestChart(unittest.TestCase):
    def test_render_and_table(self):
        frames, levels = pipeline()
        png = render(frames, levels)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertLess(len(png), 3_000_000)
        from PIL import Image
        import io
        self.assertEqual(Image.open(io.BytesIO(png)).size, (1600, 2100))
        table, ctx = build_table(frames, levels, {}, ["Berita USD HIGH: tidak ada"], NOW, CFG)
        for k in ("[H4]", "[H1]", "[M15]", "Level di atas harga", "Makro:", "WIB"):
            self.assertIn(k, table)
        self.assertLess(len(table), 4000)


class TestValidator(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(validate(res(), CTX, CFG, (), NOW), [])

    def test_geometry(self):
        self.assertTrue(validate(res(sl=4035), CTX, CFG))                          # SL di atas entry untuk LONG
        self.assertTrue(validate(res("SHORT", sl=4024, tp=4042), CTX, CFG))

    def test_rr_and_sl_bounds(self):
        self.assertTrue(any("RR" in r for r in validate(res(tp=4033), CTX, CFG)))
        self.assertTrue(any("terlalu dekat" in r for r in validate(res(sl=4029, tp=4034), CTX, CFG)))
        self.assertTrue(any("terlalu lebar" in r for r in validate(res(sl=4000, tp=4100), CTX, CFG)))

    def test_entry_location(self):
        self.assertTrue(any("MARKET" in r for r in validate(res(entry=4040, sl=4034, tp=4052), CTX, CFG)))
        self.assertTrue(any("sisi yang salah" in r for r in validate(res(tipe="LIMIT", entry=4033, sl=4027, tp=4045), CTX, CFG)))
        self.assertEqual(validate(res(tipe="LIMIT", entry=4027, sl=4021, tp=4039), CTX, CFG), [])

    def test_duplicate(self):
        prev = [{"kind": "SIGNAL", "direction": "LONG", "entry": 4029.5, "created_ts": NOW - 1800}]
        self.assertTrue(any("duplikat" in r for r in validate(res(), CTX, CFG, prev, NOW)))

    def test_precheck(self):
        st = MemoryStore()
        self.assertIsNone(precheck(st, NOW, CFG, True, None, NOW - 36000))
        self.assertIn("sesi", precheck(st, NOW, CFG, False, None, NOW - 36000))
        self.assertIn("berita", precheck(st, NOW, CFG, True, {"title": "CPI"}, NOW - 36000))
        create_signal(st, res(), CTX, NOW - 600, NOW - 600)
        self.assertIn("terbuka", precheck(st, NOW, CFG, True, None, NOW - 36000))


class TestTracker(unittest.TestCase):
    def sig(self, **kw):
        st = MemoryStore()
        return create_signal(st, res(**kw), CTX, 1000, 1000)

    def test_tp(self):
        s = self.sig()
        process(s, [[1000, 4030, 4031, 4029, 4030.5], [1900, 4030.5, 4043, 4030, 4042]], 5000, CFG)
        self.assertEqual(s["status"], "HIT_TP")
        self.assertAlmostEqual(s["r"], 2 - 0.30 / 6, places=2)

    def test_sl_first_when_both(self):
        s = self.sig()
        process(s, [[1900, 4030, 4045, 4020, 4030]], 5000, CFG)
        self.assertEqual(s["status"], "HIT_SL")
        self.assertLess(s["r"], -1)

    def test_market_expired_far(self):
        s = self.sig()
        process(s, [[1900, 4040, 4041, 4039, 4040]], 5000, CFG)
        self.assertEqual(s["status"], "EXPIRED")

    def test_limit_fill_then_tp(self):
        s = self.sig(tipe="LIMIT", entry=4027, sl=4021, tp=4039)
        process(s, [[1900, 4030, 4031, 4029, 4030]], 5000, CFG)
        self.assertEqual(s["status"], "PENDING")
        process(s, [[2800, 4030, 4030.5, 4026.5, 4029], [3700, 4029, 4040, 4028, 4039]], 5000, CFG)
        self.assertEqual(s["status"], "HIT_TP")

    def test_update_signals_persists(self):
        st = MemoryStore()
        create_signal(st, res(), CTX, 1000, 1000)
        done = update_signals(st, [[1900, 4030, 4043, 4030, 4042]], 5000, CFG)
        self.assertEqual(len(done), 1)
        self.assertEqual(st.signals()[0]["status"], "HIT_TP")


class TestNotify(unittest.TestCase):
    def test_caption_limit(self):
        st = MemoryStore()
        s = create_signal(st, res(), CTX, 1000, 1000)
        s["analisa"] = "x" * 300
        s["faktor_kunci"] = ["faktor panjang " * 5] * 4
        cap = fmt_caption(s, NOW)
        import re
        plain = re.sub(r"</?[a-z]+>", "", cap)
        self.assertLessEqual(len(plain), 1000)
        for k in ("LONG", "Pola", "Confidence", "Entry", "SL", "TP", "Analisa", "WIB"):
            self.assertIn(k, cap)


class TestSession(unittest.TestCase):
    def test_states(self):
        import datetime as dt
        u = lambda y, m, d, h, mi=0: int(dt.datetime(y, m, d, h, mi, tzinfo=dt.timezone.utc).timestamp())
        self.assertEqual(session_state(NOW, CFG)[:2], (True, True))
        self.assertEqual(session_state(u(2026, 12, 2, 12), CFG)[:2], (False, False))             # 07:00 NY
        self.assertEqual(session_state(u(2026, 12, 2, 20, 30), CFG)[:2], (True, False))          # 15:30 NY: akhir sesi
        self.assertEqual(session_state(u(2026, 12, 5, 15), CFG)[:2], (False, False))             # Sabtu
        self.assertEqual(session_state(u(2026, 11, 26, 15), CFG)[2], "libur pasar AS")           # Thanksgiving
        self.assertEqual(session_state(u(2026, 7, 1, 13), CFG)[:2], (True, True))                # musim panas 09:00 NY
        self.assertFalse(session_state(u(2026, 12, 4, 19, 30), CFG)[1])                          # Jumat 14:30 NY: tutup lebih awal


class FakeSession:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def post(self, url, **kw):
        self.calls.append(url)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


GOOD = {"status": "LONG", "pola_visual": "pin bar", "confidence": 7, "tipe_entry": "LIMIT", "entry": 1, "stop_loss": 0.5, "take_profit": 2.5,
        "analisa_gambar": "ok", "faktor_kunci": ["EMA"], "jebakan_terdeteksi": []}


def gem(payload):
    return Resp(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]})


class TestAI(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(ai.parse_result('<think>x</think>```json\n{"status":"buy","confidence":15,"entry":"1.5"}\n```')["status"], "LONG")
        r = ai.parse_result('{"status":"WAIT","entry":5,"confidence":0}')
        self.assertEqual((r["entry"], r["confidence"]), (None, 1))
        with self.assertRaises(ai.AIError):
            ai.parse_result("tidak ada json")
        with self.assertRaises(ai.AIError):
            ai.parse_result('{"status":"MAYBE"}')

    def test_chain_fallback(self):
        s = FakeSession([Resp(429, {}), Resp(500, {}), Resp(500, {}), Resp(500, {}), Resp(200, {"choices": [{"message": {"content": json.dumps(GOOD)}}]})])
        import labgold.ai as m
        m.time.sleep = lambda *_: None
        import os
        os.environ.update(GEMINI_API_KEY="k", GROQ_API_KEY="k")
        out, meta = ai.analyze(b"png", "tabel", s)
        self.assertEqual(meta["provider"], "groq")
        self.assertTrue(meta["fallback"])
        self.assertEqual(len(meta["attempts"]), 2)
        self.assertEqual(out["status"], "LONG")

    def test_all_fail(self):
        import os
        os.environ.update(GEMINI_API_KEY="k", GROQ_API_KEY="k")
        s = FakeSession([Resp(429, {})] * 3)
        with self.assertRaises(ai.AIError):
            ai.analyze(b"png", "t", s)


class TestRun(unittest.TestCase):
    def setUp(self):
        self.store, self.td, self.tg, self.atg = MemoryStore(), FakeTD(NOW), FakeTG(), FakeTG()
        frames, levels = pipeline()
        _, self.ctx = build_table(frames, levels, {}, [], NOW, CFG)

    def ai_long(self, conf=7):
        c = self.ctx
        d = 1.5 * c["atr_m15"]

        def fn(png, table, session=None):
            self.assertEqual(png[:4], b"\x89PNG")
            self.assertIn("[H4]", table)
            r = res("LONG", c["price"], c["price"] - d, c["price"] + 2 * d, conf)
            return r, {"provider": "gemini", "model": "m", "latency_ms": 5, "attempts": [], "fallback": False}
        return fn

    def go(self, now=NOW, fn=None, **kw):
        return lg_main.run(self.store, self.td, self.tg, self.atg, now, CFG, session=OfflineSession(), ai_fn=fn or self.ai_long(), **kw)

    def test_signal_flow(self):
        out = self.go()
        self.assertEqual(out["result"], "SIGNAL")
        self.assertEqual(len(self.tg.photos), 1)
        self.assertLessEqual(len(self.tg.photos[0][1]), 1024)
        self.assertEqual(len(self.store.signals(kinds=("SIGNAL",))), 1)
        d = self.store.decisions_since(0)
        self.assertEqual((len(d), d[0]["final"]), (1, "SIGNAL"))
        self.assertIn("[H4]", d[0]["table"])
        self.assertEqual(self.go().get("skipped"), "sudah dianalisis")
        self.assertEqual(len(self.tg.photos), 1)

    def test_next_candle_blocked_by_open_signal(self):
        self.go()
        out = self.go(NOW + 900)
        self.assertEqual(out["result"], "SKIP")
        self.assertEqual(len(self.tg.photos), 1)

    def test_below_threshold_is_shadow(self):
        out = self.go(fn=self.ai_long(conf=4))
        self.assertEqual(out["result"], "BAWAH_AMBANG")
        self.assertEqual(self.tg.photos, [])
        self.assertEqual(len(self.store.signals(kinds=("SHADOW",))), 1)

    def test_rejected_and_wait(self):
        def bad(png, table, session=None):
            r = res("LONG", self.ctx["price"], self.ctx["price"] + 1, self.ctx["price"] + 2)
            return r, {"provider": "g", "model": "m", "latency_ms": 1, "attempts": [], "fallback": False}
        self.assertEqual(self.go(fn=bad)["result"], "DITOLAK")
        w = lambda png, table, session=None: ({**res("WAIT"), "entry": None, "stop_loss": None, "take_profit": None},
                                               {"provider": "g", "model": "m", "latency_ms": 1, "attempts": [], "fallback": False})
        self.assertEqual(self.go(NOW + 900, fn=w)["result"], "WAIT")

    def test_ai_failure_retries_then_gives_up(self):
        def boom(png, table, session=None):
            raise ai.AIError("semua gagal")
        for k in range(3):
            self.assertEqual(self.go(NOW + 60 * k, fn=boom)["result"], "ERROR")
        self.assertEqual(self.store.decisions_since(0)[-1]["final"], "ERROR")
        self.assertTrue(any("Semua model AI gagal" in t for t in self.atg.texts))

    def test_outside_session_does_nothing(self):
        out = self.go(NOW - 4 * 3600)                                  # 06:01 NY
        self.assertIn("skipped", out)
        self.assertEqual(self.td.calls, 0)

    def test_daily_wait_alert(self):
        import datetime as dt
        for day in (29, 30, 1):                                        # hari-hari sebelumnya, semua WAIT
            ts = int(dt.datetime(2026, 11 if day > 20 else 12, day, 15, tzinfo=dt.timezone.utc).timestamp())
            for k in range(12):
                self.store.add_decision({"ts": ts + k * 900, "final": "WAIT", "candle_ts": ts})
        self.go()
        self.assertTrue(any("nyaris selalu WAIT" in t for t in self.atg.texts))


if __name__ == "__main__":
    unittest.main()
