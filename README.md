# lab-gold

Bot sinyal **XAUUSD (emas spot)** pribadi untuk paper trading. Data harga digambar menjadi satu kolase chart 3 timeframe,
dibaca oleh AI vision bersama tabel angka pendukung, divalidasi oleh kode, lalu sinyal **LONG/SHORT** dikirim ke Telegram
sebagai foto. Default keputusan adalah **WAIT**.

> Hanya untuk edukasi dan paper trading. Bukan nasihat keuangan. Kinerja AI belum terbukti; kalibrasi dari hasil nyata dulu.

## Alur satu run (tiap 5 menit, sesi New York 08:00-16:00)

1. cron-job.org memicu GitHub Actions (`workflow_dispatch`).
2. Ambil candle XAU/USD (Twelve Data, memakai cache) lalu perbarui hasil sinyal yang masih terbuka.
3. Hanya bila ada **candle M15 baru yang tertutup**: hitung indikator dan level, gambar kolase, bentuk tabel angka.
4. Pemeriksaan awal (sesi, berita USD HIGH, sinyal terbuka, cooldown, batas harian); bila gagal, AI tidak dipanggil.
5. AI menjawab JSON: status, pola visual, confidence 1-10, entry/SL/TP, analisa, `faktor_kunci`.
6. Validator kode memeriksa risiko. Lolos dan confidence >= ambang (awal 6) => kirim foto ke Telegram.
   Confidence di bawah ambang dilacak diam-diam sebagai sinyal "bayangan" untuk kalibrasi.
7. Semua keputusan dicatat di MongoDB.

## Struktur

```
.github/workflows/trade.yml   workflow (dipicu cron-job.org)
src/labgold/                  kode: config, data, snapshot, chart, ai, validator, tracker, notify, alerts, report, main
prompts/system_prompt.md      prompt AI (70% trader profesional, 30% Expert Advisor)
scripts/alert_fail.py         alert Telegram bila run GitHub gagal
tests/                        uji unit dan end-to-end (tanpa internet)
```

## Pengaturan awal (ringkas)

1. **Secrets** (repo > Settings > Secrets and variables > Actions > Secrets):
   `TWELVE_DATA_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ALERT_BOT_TOKEN`,
   `ALERT_CHAT_ID`, `MONGO_URL`, `DB_NAME` (mis. `xauv3`), `GH_TOKEN_EXPIRY` (YYYY-MM-DD). Opsional: `PROMPT_TEXT`.
2. **Variables** (opsional, tab Variables): `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`, `GROQ_MODEL`, `MIN_CONFIDENCE`,
   `MAX_SIGNALS_DAY`, `SEND_RESULTS`.
3. **Uji berurutan** (Actions > trade > Run workflow > pilih mode): `check` > `telegram_test` > `ai_test` > `force`.
4. **cron-job.org**: buat pekerjaan (zona waktu **UTC**):
   - URL: `https://api.github.com/repos/<USERNAME>/lab-gold/actions/workflows/trade.yml/dispatches`, metode POST, body `{"ref":"main"}`
   - Header: `Authorization: Bearer <token fine-grained>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`
   - Jadwal (zona waktu job: **UTC**). Crontab: `1-59/5 12-20 * * 1-5`. Bila editor memakai pilihan per kolom: menit `1,6,11,16,21,26,31,36,41,46,51,56`, jam `12` sampai `20`, hari Senin-Jumat, tanggal dan bulan semua. "Test run" harus 204.
   - Cek: geser toggle riwayat ke *Job time zone*; run pertama Senin harus 12:01 UTC (19:01 WIB), selang tiap run 5 menit.
   - Jam UTC 12-21 = 19:00-04:00 WIB; kode memutuskan jendela NY 08:00-16:00 sehingga otomatis benar di musim dingin/panas.

## Mode workflow

| Mode | Fungsi |
|---|---|
| `run` | normal (dipakai cron) |
| `check` | uji data, kalender, makro, dan gambar (tanpa AI/Telegram/database) |
| `ai_test` | seperti `check` ditambah satu panggilan AI (hanya status dicetak ke log) |
| `telegram_test` | kirim foto contoh (data sintetis) ke bot sinyal dan pesan tes ke bot alert |
| `report` | kirim laporan kalibrasi ke bot alert |
| `force` | analisis di luar jam sesi (uji) |

## Validator risiko (nilai awal, ubah di `src/labgold/config.py`)

- SL >= 0,8 ATR M15 dan <= 2 ATR H1; RR >= 1,5 dan <= 8; biaya (spread+slip) <= 0,15R.
- Entry MARKET maksimal 0,6 ATR M15 dari harga; entry LIMIT maksimal 2 ATR di sisi yang benar.
- Satu sinyal terbuka; jeda 60 menit setelah sinyal dan 3 jam setelah SL; sinyal searah dengan entry mirip ditolak.
- Maksimal 3 sinyal per hari; tidak ada sinyal di 60 menit terakhir sesi, Jumat setelah 14:00 NY, libur AS, dan +-30 menit berita USD HIGH.

## Keamanan repo publik

- Tidak ada rahasia di kode: semua lewat GitHub Secrets. `.env` dan `*.png` ada di `.gitignore`.
- Log Actions bersifat publik: bot hanya mencetak status singkat, bukan analisa, harga sinyal, atau ID chat.
- Aktifkan *Secret scanning* dan *Push protection* (Settings > Code security).
- Prompt di `prompts/system_prompt.md` ikut publik; isi secret `PROMPT_TEXT` bila ingin merahasiakannya.
- Data tier gratis Gemini dapat dipakai Google untuk memperbaiki produknya: jangan kirim data pribadi.

## Uji lokal

```
pip install -r requirements.txt
cd tests && PYTHONPATH=../src python -m unittest test_all -v
```

## Batas layanan gratis (diperiksa 27 Nov 2026; bisa berubah)

- Twelve Data Basic: 800 kredit/hari, 8/menit; bot memakai sekitar 40-60 kredit per hari berkat cache.
- Gemini 3.5/3.1 Flash-Lite gratis: batas harian dan per menit yang berlaku lihat di Google AI Studio (halaman rate limit); bot memakai sekitar 32 request per hari.
  Gemini 3.1 Flash-Lite dijadwalkan mati paling cepat 7 Mei 2027: ganti lewat `GEMINI_FALLBACK_MODEL`.
- Groq gratis: 8.000 token/menit; satu gambar = 2.048 token (cukup untuk cadangan).
- MongoDB Atlas M0: 512 MB. GitHub Actions: gratis untuk repo publik (runner standar).
