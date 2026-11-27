"""Dipanggil workflow saat run GAGAL (hanya pustaka standar, tetap jalan walau 'pip install' gagal)."""
import datetime as dt
import html
import os
import urllib.parse
import urllib.request

WIB = dt.timezone(dt.timedelta(hours=7))
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def main():
    token = (os.environ.get("ALERT_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("ALERT_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        print("token alert belum diisi")
        return
    n = dt.datetime.now(WIB)
    url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    text = "\n".join([
        "<b>🔴 SYSTEM ALERT · Run GitHub gagal</b>", f"<i>Perlu tindakan · {n.day} {BULAN[n.month - 1]} {n:%H:%M} WIB</i>", "",
        "<b>Kejadian</b> : run workflow berakhir gagal sebelum atau saat dijalankan",
        "<b>Dampak</b> : analisis pada run tersebut tidak berjalan; run berikutnya tetap mencoba",
        "<b>Yang perlu dilakukan</b>",
        f"1. Buka run ini dan lihat langkah yang berwarna merah: {html.escape(url)}",
        "2. Jika 'pip install' yang gagal: klik 'Re-run all jobs' (biasanya gangguan sesaat).",
        "3. Jika berulang, kirim 10-15 baris terakhir log ke Claude (tanpa key atau token).", "",
        "<i>Jika run berikutnya hijau, tidak perlu melakukan apa-apa.</i>", "", "<i>lab-gold</i>"])
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data), timeout=20)
        print("alert terkirim")
    except Exception as e:  # noqa: BLE001
        print("alert gagal:", type(e).__name__)


if __name__ == "__main__":
    main()
