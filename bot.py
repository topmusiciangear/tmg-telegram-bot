import json
import os
import re
import sys
import time
import requests
from datetime import datetime

def log(msg):
    print(msg, flush=True)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

PRICE_CATEGORIES = {
    "auriculares": "🎧",
    "interfaces": "🎸",
    "microfonos": "🎤",
    "monitores": "🔊",
    "guitarras": "🎸",
    "teclados": "🎹",
    "bateria": "🥁",
    "plugins": "🔌",
    "pa": "🔊",
    "accesorios": "🔧",
}

TIENDA_NOMBRES = {
    "amazon": "🇪🇸 Amazon",
    "musicstore": "🇩🇪 Music Store",
    "andertons": "🇬🇧 Andertons",
    "gear4music": "🇪🇺 Gear4Music",
    "pluginboutique": "🔌 Plugin Boutique",
}

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def find_price_in_html(html, patterns):
    for p in patterns:
        m = re.search(p, html, re.DOTALL)
        if m:
            val = m.group(1).replace(",", ".").replace(" ", "").replace("€", "").replace("$", "").replace("£", "")
            try:
                return float(val)
            except:
                continue
    return None

def extract_price_amazon(html):
    patterns = [
        r'"price":\s*"(\d+\.?\d*)"',
        r'"displayAmount":\s*"(\d+\.?\d*)"',
        r'a-price-whole[^>]*>(\d+)<',
        r'<span class="a-price"[^>]*>.*?\$(\d+\.?\d*)',
    ]
    return find_price_in_html(html, patterns)

def extract_price_musicstore(html):
    patterns = [
        r'<meta itemprop="price"[^>]*content="(\d+\.?\d*)"',
        r'"price":\s*"(\d+\.?\d*)"',
        r'our-price[^>]*>[^<]*€\s*(\d+[.,]?\d*)',
        r'<span[^>]*price[^>]*>[^<]*€\s*(\d+[.,]?\d*)',
    ]
    return find_price_in_html(html, patterns)

def extract_price_andertons(html):
    patterns = [
        r'<meta itemprop="price"[^>]*content="(\d+\.?\d*)"',
        r'"price":\s*"(\d+\.?\d*)"',
        r'<span[^>]*price[^>]*>[^<]*£\s*(\d+[.,]?\d*)',
        r'class="[^"]*price[^"]*"[^>]*>£\s*(\d+[.,]?\d*)',
    ]
    return find_price_in_html(html, patterns)

def extract_price_gear4music(html):
    patterns = [
        r'"price":\s*"(\d+\.?\d*)"',
        r'<meta itemprop="price"[^>]*content="(\d+\.?\d*)"',
        r'<span[^>]*class="[^"]*price[^"]*"[^>]*>.*?[€$£]\s*(\d+[.,]?\d*)',
        r'class="[^"]*price[^"]*"[^>]*>.*?[€$£]\s*(\d+[.,]?\d*)',
        r'data-price[=]["\'](\d+\.?\d*)["\']',
    ]
    return find_price_in_html(html, patterns)

def extract_price_pluginboutique(html):
    patterns = [
        r'"price":\s*"(\d+\.?\d*)"',
        r'<meta itemprop="price"[^>]*content="(\d+\.?\d*)"',
        r'class="price"[^>]*>.*?\$(\d+\.?\d*)',
        r'\$(\d+\.?\d*)\s*</span>',
    ]
    return find_price_in_html(html, patterns)

def extract_price(url):
    if not url:
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        html = resp.text
        if "amazon" in url:
            return extract_price_amazon(html)
        elif "musicstore" in url:
            return extract_price_musicstore(html)
        elif "andertons" in url:
            return extract_price_andertons(html)
        elif "gear4music" in url:
            return extract_price_gear4music(html)
        elif "pluginboutique" in url:
            return extract_price_pluginboutique(html)
        return None
    except:
        return None

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN:
        log("No TELEGRAM_TOKEN set")
        return
    data = load_json("productos.json")
    canal = data.get("config", {}).get("canal_id", "@topmusiciangear")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": canal,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        log(f"Telegram status: {resp.status_code}")
        if resp.status_code != 200:
            log(f"Telegram response: {resp.text[:200]}")
    except Exception as e:
        log(f"Telegram error: {e}")

def formatear_oferta(prod, tienda_key, precio_base, precio_actual, url):
    icono = PRICE_CATEGORIES.get(prod.get("categoria", ""), "🛒")
    nombre = prod["nombre"]
    tienda_nombre = TIENDA_NOMBRES.get(tienda_key, tienda_key)
    descuento = round((1 - precio_actual / precio_base) * 100)
    moneda = prod.get("moneda", "$")

    msg = f"{icono} <b>{nombre}</b>\n"
    msg += f"📍 {tienda_nombre}\n"
    msg += f"💵 Was: {moneda}{precio_base:.0f} → Now: {moneda}{precio_actual:.0f}  <b>(-{descuento}%)</b>\n"
    if url:
        msg += f"🔗 <a href='{url}'>Buy here</a>\n"
    msg += f"🔍 topmusiciangear.com"
    return msg

def precio_es_realista(precio, base):
    if precio <= 0:
        return False
    ratio = precio / base
    return 0.4 <= ratio <= 2.0

def main():
    data = load_json("productos.json")
    productos = data.get("productos", [])
    config = data.get("config", {})
    descuento_min = config.get("descuento_minimo", 5)

    cambios = []

    for prod in productos:
        nombre = prod["nombre"]
        precio_base = prod.get("precio_base", 0)
        tiendas = prod.get("tiendas", {})

        for tienda_key, url in tiendas.items():
            if not url or precio_base <= 0:
                continue
            log(f"Checking {nombre} @ {tienda_key}...")
            precio_actual = extract_price(url)
            if precio_actual is None:
                log(f"  Could not get price")
                continue

            if not precio_es_realista(precio_actual, precio_base):
                log(f"  Unrealistic price: {precio_actual} (base: {precio_base}) - skipped")
                continue

            diff_pct = round((1 - precio_actual / precio_base) * 100)
            log(f"  Base: {precio_base} Current: {precio_actual} Diff: {diff_pct}%")

            if diff_pct >= descuento_min:
                cambios.append({
                    "producto": prod,
                    "tienda": tienda_key,
                    "precio_base": precio_base,
                    "precio_actual": precio_actual,
                    "url": url,
                })

    for i, c in enumerate(cambios):
        if i > 0:
            time.sleep(3)
        msg = formatear_oferta(
            c["producto"], c["tienda"],
            c["precio_base"], c["precio_actual"], c["url"]
        )
        log(f"DEAL: {c['producto']['nombre']} @ {c['tienda']} - {c['precio_base']} -> {c['precio_actual']}")
        enviar_telegram(msg)

    if not cambios:
        log(f"No deals found. ({datetime.now().isoformat()})")

if __name__ == "__main__":
    main()
