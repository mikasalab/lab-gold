"""Analisis gambar oleh AI: Gemini 3.5 Flash-Lite -> Gemini 3.1 Flash-Lite -> Groq Qwen3.8 (cadangan)."""
import base64
import json
import re
import time
from pathlib import Path

import requests

from .config import env

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompts" / "system_prompt.md"


class AIError(Exception):
    pass


class QuotaError(AIError):
    """429: kuota habis -> langsung pindah ke model berikutnya."""


def load_prompt():
    """PROMPT_TEXT (secret) menimpa file di repo, bila prompt ingin dirahasiakan dari repo publik."""
    return env("PROMPT_TEXT") or PROMPT_FILE.read_text(encoding="utf-8")


def model_chain():
    """[(provider, model)] berurutan. Nama model bisa diganti lewat Variables GitHub saat model lama dimatikan."""
    chain = [("gemini", env("GEMINI_MODEL", "gemini-3.5-flash-lite")),
             ("gemini", env("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")),
             ("groq", env("GROQ_MODEL", "qwen/qwen3.8-27b"))]
    return [(p, m) for p, m in chain if m]


# ------------------------------------------------------------------ parsing
def _num(x):
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _txt(x, n):
    return " ".join(str(x or "").split())[:n]


def _lst(x, k, n=80):
    return [_txt(i, n) for i in (x if isinstance(x, list) else [])[:k] if str(i).strip()]


def parse_result(text):
    """Ambil objek JSON dari jawaban model dan rapikan. Melempar AIError bila tidak bisa dipakai."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise AIError("jawaban bukan JSON")
    try:
        d = json.loads(m.group(0))
    except ValueError:
        raise AIError("JSON tidak valid")
    status = str(d.get("status", "")).strip().upper()
    status = {"BUY": "LONG", "SELL": "SHORT"}.get(status, status)
    if status not in ("LONG", "SHORT", "WAIT"):
        raise AIError(f"status tidak dikenal: {status[:20]}")
    conf = _num(d.get("confidence"))
    r = {"status": status, "pola_visual": _txt(d.get("pola_visual"), 40),
         "confidence": int(max(1, min(10, round(conf)))) if conf is not None else 1,
         "tipe_entry": "LIMIT" if str(d.get("tipe_entry", "")).upper() == "LIMIT" else "MARKET",
         "entry": _num(d.get("entry")), "stop_loss": _num(d.get("stop_loss")), "take_profit": _num(d.get("take_profit")),
         "analisa_gambar": _txt(d.get("analisa_gambar"), 300), "faktor_kunci": _lst(d.get("faktor_kunci"), 4),
         "jebakan_terdeteksi": _lst(d.get("jebakan_terdeteksi"), 3)}
    if status == "WAIT":
        r["entry"] = r["stop_loss"] = r["take_profit"] = None
    return r


# ------------------------------------------------------------------ penyedia
def call_gemini(model, system, table, png, key, session=None, timeout=60):
    if not key:
        raise AIError("GEMINI_API_KEY belum diisi")
    s = session or requests
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}},
                {"text": "TABEL ANGKA PENDUKUNG:\n" + table + "\n\nBerikan keputusan dalam JSON sesuai format."}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1500, "responseMimeType": "application/json"}}
    level = env("GEMINI_THINKING", "low")
    if level and level.lower() != "off":
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": level.lower()}
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    for attempt in range(3):
        try:
            r = s.post(GEMINI_URL.format(model=model), headers=headers, json=body, timeout=timeout)
        except requests.RequestException as e:
            if attempt < 1:
                time.sleep(3)
                continue
            raise AIError(f"koneksi gagal: {type(e).__name__}")
        if r.status_code == 429:
            raise QuotaError("kuota habis (429)")
        if r.status_code == 400 and "thinkingConfig" in body["generationConfig"]:
            body["generationConfig"].pop("thinkingConfig")      # model tidak mendukung level berpikir ini -> ulangi tanpa itu
            continue
        if r.status_code >= 500 and attempt < 2:
            time.sleep(3)
            continue
        if r.status_code != 200:
            raise AIError(f"HTTP {r.status_code}")
        try:
            j = r.json()
            parts = j["candidates"][0]["content"]["parts"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise AIError("respons kosong/diblokir")
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return parse_result(text)
    raise AIError("gagal setelah beberapa percobaan")


def call_groq(model, system, table, png, key, session=None, timeout=60):
    if not key:
        raise AIError("GROQ_API_KEY belum diisi")
    s = session or requests
    uri = "data:image/png;base64," + base64.b64encode(png).decode()
    body = {"model": model, "temperature": 0.3, "max_tokens": 1500,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": [
                             {"type": "text", "text": "TABEL ANGKA PENDUKUNG:\n" + table + "\n\nBerikan keputusan dalam JSON sesuai format."},
                             {"type": "image_url", "image_url": {"url": uri}}]}],
            "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(2):
        try:
            r = s.post(GROQ_URL, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as e:
            raise AIError(f"koneksi gagal: {type(e).__name__}")
        if r.status_code == 429:
            raise QuotaError("kuota habis (429)")
        if r.status_code == 400 and "response_format" in body:
            body.pop("response_format")
            continue
        if r.status_code != 200:
            raise AIError(f"HTTP {r.status_code}")
        try:
            return parse_result(r.json()["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError, TypeError):
            raise AIError("respons kosong")
    raise AIError("gagal setelah beberapa percobaan")


def analyze(png, table, session=None, chain=None):
    """Coba model berurutan. Kembalikan (hasil, meta). Semua gagal -> AIError berisi ringkasan percobaan."""
    system = load_prompt()
    attempts = []
    for provider, model in (chain or model_chain()):
        t0 = time.time()
        try:
            if provider == "gemini":
                res = call_gemini(model, system, table, png, env("GEMINI_API_KEY"), session)
            else:
                res = call_groq(model, system, table, png, env("GROQ_API_KEY"), session)
            return res, {"provider": provider, "model": model, "latency_ms": int((time.time() - t0) * 1000),
                         "attempts": attempts, "fallback": bool(attempts)}
        except AIError as e:
            attempts.append(f"{model}: {e}")
            print(f"[ai] {model} gagal: {e}")
    raise AIError("; ".join(attempts))
