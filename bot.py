import json
import os
import re
import socket
import sys
import time
import requests
from datetime import datetime

socket.setdefaulttimeout(15)

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL = True
except ImportError:
    HAS_CURL = False

def log(msg):
    print(msg, flush=True)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

BLOCKED_STORES = ["amazon", "musicstore", "andertons"]

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
            val = m.group(1).replace(" ", "").replace("\u20ac", "").replace("$", "").replace("\u00a3", "")
            try:
                f = float(val)
                if f > 0:
                    return f
            except:
                pass
            try:
                f = float(val.replace(",", ""))
                if f > 0:
                    return f
            except:
                pass
    return None

def extract_price_amazon(html):
    patterns = [
        r'"price":\s*"(\d+\.?\d*)"',
        r'"displayAmount":\s*"(\d+\.?\d*)"',
        r'corePrice_desktop.*?a-offscreen[^>]*>[^<]*[£$]\s*(\d+\.?\d*)',
        r'data-a-size="xl"[^>]*>.*?a-offscreen[^>]*>[^<]*[£$]\s*(\d+\.?\d*)',
        r'a-offscreen[^>]*>[^<]*[£$]\s*(\d+\.?\d*)',
    ]
    return find_price_in_html(html, patterns)

def extract_price_musicstore(html):
    patterns = [
        r'meta\.setAttribute\(.*?content.*?[€€]\s*(\d+[.,]?\d*)',
        r'<[^>]*class="[^"]*price[^"]*"[^>]*>[^<]*[€€]\s*(\d+[.,]?\d*)',
        r'<meta itemprop="price"[^>]*content="(\d+\.?\d*)"',
        r'"price":\s*"(\d+\.?\d*)"',
        r'our-price[^>]*>[^<]*€\s*(\d+[.,]?\d*)',
        r'<span[^>]*price[^>]*>[^<]*€\s*(\d+[.,]?\d*)',
        r'topbar-price[^>]*>[^<]*€\s*(\d+[.,]?\d*)',
        r'data-price[=]["\'](\d+\.?\d*)["\']',
    ]
    return find_price_in_html(html, patterns)

def extract_price_andertons(html):
    patterns = [
        r'price:amount"\s*content="(\d+\.?\d*)"',
        r'data-testid="pdp-price"[^>]*>[^<]*£\s*(\d+[.,]?\d*)',
        r'<meta itemprop="price"[^>]*content="(\d+\.?\d*)"',
        r'"price":\s*"(\d+\.?\d*)"',
        r'<span[^>]*price[^>]*>[^<]*£\s*(\d+[.,]?\d*)',
        r'class="[^"]*price[^"]*"[^>]*>£\s*(\d+[.,]?\d*)',
        r'data-price[=]["\'](\d+\.?\d*)["\']',
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
        r'<meta itemprop="price"[^>]*content="(\d+\.?\d*)"',
        r'"price":\s*"(\d+\.?\d*)"',
        r'class="[^"]*price[^"]*"[^>]*>[^<]*[€$]\s*(\d+[.,]?\d*)',
        r'[€$]\s*(\d+[.,]?\d*)',
    ]
    return find_price_in_html(html, patterns)

IMPERSONATES = ["chrome124", "safari17_0"]

def fetch_page(url):
    for store in BLOCKED_STORES:
        if store not in url:
            continue
        if not HAS_CURL:
            break
        for imp in IMPERSONATES:
            try:
                resp = curl_requests.get(url, headers=HEADERS, timeout=10, impersonate=imp)
                log(f"  [{store}] curl_cffi/{imp}: HTTP {resp.status_code}, {len(resp.content)} bytes")
                if resp.status_code == 200 and len(resp.content) > 10000:
                    return resp.text
            except Exception as e:
                log(f"  [{store}] curl_cffi/{imp} error: {e}")
                continue
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        log(f"  [requests] HTTP {resp.status_code}, {len(resp.content)} bytes")
        return resp.text
    except Exception as e:
        log(f"  [requests] failed: {e}")
        return None

def extract_price(url, nombre_producto=""):
    if not url:
        return None
    try:
        html = fetch_page(url)
        if html is None:
            return None
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
    import os as _os
    log(f"CWD: {_os.getcwd()}")
    log(f"productos.json exists: {_os.path.exists('productos.json')}")
    log(f"Files in CWD: {[f for f in _os.listdir('.') if f.endswith('.json')]}")

    data = load_json("productos.json")
    productos = data.get("productos", [])
    config = data.get("config", {})
    descuento_min = config.get("descuento_minimo", 5)

    log(f"Loaded {len(productos)} products, min discount: {descuento_min}%")

    cambios = []

    for prod in productos:
        nombre = prod["nombre"]
        precio_base = prod.get("precio_base", 0)
        tiendas = prod.get("tiendas", {})

        for tienda_key, url in tiendas.items():
            if not url or precio_base <= 0:
                continue
            log(f"Checking {nombre} @ {tienda_key}...")
            precio_actual = extract_price(url, nombre)
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
