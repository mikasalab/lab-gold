# Changelog

Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/1.1.0/). Versi memakai Semantic Versioning.

## [0.1.1] - 2026-11-28

### Diubah
- Chart: label swing diganti `SwH`/`SwL` (sebelumnya `SH`/`SL`, mudah tertukar dengan stop loss); garis level berhenti di candle terakhir
  sehingga tidak menembus teks label; label diberi latar putih; level yang berdekatan digabung (prioritas: kemarin/sesi, swing HTF, swing panel, angka bulat);
  sumbu waktu memakai jam bulat WIB (M15 tiap 3 jam, H1 tiap 6 jam, H4 jam 07:00); legenda dipindah ke luar area plot; font harga swing diperbesar.
- Prompt AI: menjelaskan arti label `SwH/SwL`, `PDH/PDL`, `Asia/London H/L`.
- Workflow: `actions/checkout@v6` dan `actions/setup-python@v6` (Node 24; menghilangkan peringatan deprecation Node 20).
- Jadwal cron-job.org: tiap 5 menit, crontab UTC `1-59/5 12-20 * * 1-5`.
- Data sintetis (`demo.py`): candle H1/H4 disejajarkan dengan jam UTC seperti data asli, sehingga foto contoh Telegram menampilkan sumbu waktu yang sama dengan data nyata.

## [0.1.0] - 2026-11-27

Rilis pertama bot XAUUSD berbasis analisis gambar (menggantikan seluruh bot aturan `sinyalfx` lama).

### Ditambahkan
- Kolase 3 timeframe dalam satu gambar (matplotlib): M15 96 candle, H1 72 candle, H4 42 candle, lengkap dengan EMA,
  swing high/low (harga berlabel), level kunci (kemarin, sesi Asia/London, swing H1/H4, angka bulat), dan garis harga terakhir.
- Tabel angka pendukung yang dikirim bersama gambar (indikator, 6 candle M15 terakhir, jarak level dalam ATR, makro, berita).
- Analisis AI bergantian: Gemini 3.5 Flash-Lite, lalu Gemini 3.1 Flash-Lite, lalu Groq `qwen/qwen3.8-27b` (cadangan).
  Nama model dapat diganti lewat Variables GitHub tanpa mengubah kode.
- Prompt "70% trader profesional, 30% Expert Advisor" di `prompts/system_prompt.md` (opsional dirahasiakan lewat secret `PROMPT_TEXT`).
- Validator risiko berbasis kode, cooldown, batas sinyal harian, filter berita USD HIGH, dan jendela sesi New York (08:00-16:00 NY).
- Notifikasi Telegram `sendPhoto` hanya untuk sinyal LONG/SHORT (caption maks 1024 karakter).
- Pelacak hasil nyata (TP/SL, MFE/MAE) termasuk sinyal "bayangan" di bawah ambang confidence untuk kalibrasi.
- Semua keputusan dicatat di MongoDB Atlas (disimpan 180 hari) dan laporan kalibrasi (`mode report`).
- Alert sistem: data gagal, AI gagal, model cadangan terpakai, WAIT tinggi (>98% per hari atau nol sinyal beberapa hari), dan lainnya.
- Workflow `trade.yml` (dipicu cron-job.org), dengan mode uji: `check`, `ai_test`, `telegram_test`, `report`, `force`.

### Diubah
- Sumber harga: Twelve Data XAU/USD (spot). Yahoo Finance hanya untuk DXY dan ^TNX, maksimal sekali per jam, gagal-lunak.

### Dihapus
- Mesin aturan lama (`engine.py`), paper mode H4 `xau_*`, ringkasan harian/mingguan, dan perintah Telegram lama.
