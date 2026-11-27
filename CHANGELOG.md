# Changelog

Format mengikuti [Keep a Changelog](https://keepachangelog.com/id/1.1.0/). Versi memakai Semantic Versioning.

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
