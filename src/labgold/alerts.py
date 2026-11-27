"""System alert lab-gold: format seragam dan pencegah pesan berulang. Dikirim lewat bot alert terpisah."""
from .notify import esc, fmt_wib

LABEL = {"🟢": "Abaikan", "🟡": "Pantau", "🔴": "Perlu tindakan"}
FOOTER = "\n\n<i>lab-gold</i>"

ALERTS = {
    "data_sesaat": ("🟢", "Gangguan data sesaat", "Analisis candle ini dilewati; run berikutnya mencoba lagi.",
                    ["Tidak perlu melakukan apa-apa."], "Jika pesan merah menyusul, ikuti langkahnya."),
    "data_beruntun": ("🔴", "Data gagal berulang", "Sinyal baru diblokir sampai data pulih.",
                      ["Buka twelvedata.com → Dashboard: cek API key aktif dan sisa kredit hari ini.",
                       "Jika key tidak valid: buat key baru, ganti secret TWELVE_DATA_KEY di GitHub.",
                       "Uji: Actions → trade → Run workflow → mode check."], "Pesan 'pulih' datang otomatis."),
    "ai_gagal": ("🔴", "Semua model AI gagal", "Candle ini tidak dianalisis; bot mencoba lagi di run berikutnya.",
                 ["Cek kuota dan API key di aistudio.google.com (Gemini) dan console.groq.com (Groq).",
                  "Cek nama model di Variables GitHub (GEMINI_MODEL, GEMINI_FALLBACK_MODEL, GROQ_MODEL); model lama bisa dimatikan.",
                  "Uji: Actions → trade → Run workflow → mode ai_test."], "Pesan 'pulih' datang otomatis."),
    "ai_cadangan": ("🟡", "Model utama gagal, memakai cadangan", "Analisis tetap berjalan dengan model cadangan.",
                    ["Cek log run (nama model tertera) dan kuota Gemini.",
                     "Jika berulang tiap hari, periksa apakah nama model utama berubah."], "Tidak perlu tindakan bila hanya sesekali."),
    "wait_tinggi": ("🟡", "Bot nyaris selalu WAIT", "Sinyal sangat jarang; prompt atau filter mungkin terlalu ketat.",
                    ["Buka laporan (Actions → trade → mode report) dan lihat alasan WAIT/ditolak terbanyak.",
                     "Pertimbangkan melonggarkan prompt (bukan validator risiko) atau turunkan MIN_CONFIDENCE.",
                     "Jangan ubah banyak hal sekaligus; ubah satu lalu amati beberapa hari."], "Peringatan ini hanya saran untuk dianalisis."),
    "crash": ("🔴", "Skrip bot error", "Run tersebut gagal; run berikutnya tetap mencoba.",
              ["Buka GitHub → Actions → run merah → langkah 'Jalankan bot'.",
               "Salin 10-15 baris terakhir log (jangan sertakan key atau token) dan kirim ke Claude."],
              "Jika hanya sekali dan run berikutnya hijau, abaikan."),
    "github_gagal": ("🔴", "Run GitHub gagal", "Run tersebut tidak berjalan; run berikutnya tetap mencoba.",
                     ["Buka GitHub → Actions → run merah → lihat langkah yang gagal.",
                      "Jika 'pip install' yang gagal: klik 'Re-run all jobs' (biasanya gangguan sesaat).",
                      "Jika berulang, kirim 10-15 baris terakhir log ke Claude."], "Jika run berikutnya hijau, abaikan."),
    "atlas": ("🔴", "Database tidak bisa dihubungi", "Bot tidak bisa membaca/menyimpan data; run gagal sampai pulih.",
              ["Buka cloud.mongodb.com → pastikan cluster 'Running' (tekan Resume bila Paused).",
               "Network Access → pastikan 0.0.0.0/0 aktif.",
               "Database Access → cek user/password; jika diganti, perbarui secret MONGO_URL."],
              "Alert ini diulang paling sering sekali per jam."),
    "kalender": ("🟡", "Kalender berita tidak diperbarui", "Filter berita memakai data lama atau tidak aktif.",
                 ["Tidak perlu tindakan segera; bot mencoba lagi tiap 6 jam."], "Bot tetap berjalan."),
    "storage": ("🟡", "Ruang database hampir penuh", "Jika penuh, penyimpanan berhenti dan bot gagal.",
                ["Atlas → Browse Collections → hapus database contoh (mis. 'sample_mflix').",
                 "Keputusan lama otomatis dihapus setelah 180 hari."], "Paket gratis Atlas M0 dibatasi 512 MB."),
    "token": ("🟡", "Token GitHub segera kedaluwarsa", "Jika kedaluwarsa, cron-job.org gagal memicu bot.",
              ["GitHub → Settings → Developer settings → Fine-grained tokens → buat token baru (hanya repo lab-gold, Actions: Read and write).",
               "cron-job.org → tiap pekerjaan → header Authorization: ganti 'Bearer <token baru>', lalu 'Test run' (harus 204).",
               "Perbarui secret GH_TOKEN_EXPIRY dengan tanggal baru (YYYY-MM-DD)."], "Lakukan sebelum tanggal kedaluwarsa."),
    "pulih": ("🟢", "Sistem pulih", "Masalah sebelumnya sudah teratasi.", ["Tidak perlu melakukan apa-apa."], ""),
}


def fmt_alert(code, kejadian, now_ts, title=None):
    icon, ttl, dampak, steps, note = ALERTS[code]
    L = [f"<b>{icon} SYSTEM ALERT · {esc(title or ttl)}</b>", f"<i>{LABEL[icon]} · {fmt_wib(now_ts)}</i>", "",
         f"<b>Kejadian</b> : {esc(kejadian)}", f"<b>Dampak</b> : {esc(dampak)}"]
    if len(steps) == 1:
        L.append(f"<b>Yang perlu dilakukan</b> : {esc(steps[0])}")
    else:
        L.append("<b>Yang perlu dilakukan</b>")
        L += [f"{i}. {esc(s)}" for i, s in enumerate(steps, 1)]
    if note:
        L += ["", f"<i>{esc(note)}</i>"]
    return "\n".join(L) + FOOTER


class Alerts:
    """Pengirim alert. store=None (mis. database mati) = kirim tanpa pencegah duplikat."""

    def __init__(self, store, tg):
        self.store, self.tg = store, tg

    def fire(self, code, kejadian, now_ts, key=None, ttl=0, title=None):
        k = f"alert:{key or code}"
        if self.store is not None and ttl:
            last = self.store.get(k)
            if last and now_ts - last.get("ts", 0) < ttl:
                return False
        ok = self.tg.send(fmt_alert(code, kejadian, now_ts, title), html=True)
        if self.store is not None:
            self.store.set(k, {"ts": now_ts})
            if ALERTS[code][0] != "🟢":
                act = self.store.get("alerts_active") or {}
                act[code] = {"ts": now_ts, "kejadian": kejadian[:140]}
                self.store.set("alerts_active", act)
        return ok

    def resolve(self, code, now_ts, kejadian="Kembali normal.", notify=True):
        if self.store is None:
            return False
        act = self.store.get("alerts_active") or {}
        if code not in act:
            return False
        del act[code]
        self.store.set("alerts_active", act)
        if notify:
            self.tg.send(fmt_alert("pulih", kejadian, now_ts, title=f"Pulih: {ALERTS[code][1]}"), html=True)
        return True
