import json
import os
import re
import requests
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CANAL_ID = "@topmusiciangear"
DESCUENTO_MINIMO = 5

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

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def extract_price_amazon(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        html = resp.text
        patterns = [
            r'"price":\s*"(\d+\.?\d*)"',
            r'"displayAmount":\s*"(\d+\.?\d*)"',
            r'<span class="a-price"[^>]*>.*?<span[^>]*>\$?€?(\d+\.?\d*)',
            r'a-price-whole[^>]*>(\d+)<',
        ]
        for p in patterns:
            m = re.search(p, html, re.DOTALL)
            if m:
                val = m.group(1).replace(",", "")
                return float(val)
        return None
    except:
        return None

def extract_price_musicstore(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        html = resp.text
        patterns = [
            r'<meta itemprop="price"[^>]*content="(\d+\.?\d*)"',
            r'"price":\s*"(\d+\.?\d*)"',
            r'<span class="price"[^>]*>.*?\$?€?(\d+\.?\d*)',
            r'our-price[^>]*>.*?\$?€?(\d+\.?\d*)',
        ]
        for p in patterns:
            m = re.search(p, html, re.DOTALL)
            if m:
                return float(m.group(1).replace(",", "."))
        return None
    except:
        return None

def extract_price_andertons(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        html = resp.text
        patterns = [
            r'"price":\s*"(\d+\.?\d*)"',
            r'<meta itemprop="price"[^>]*content="(\d+\.?\d*)"',
            r'<span class="price"[^>]*>.*?\$?€?£?(\d+\.?\d*)',
            r'product-price[^>]*>.*?\$?€?£?(\d+\.?\d*)',
        ]
        for p in patterns:
            m = re.search(p, html, re.DOTALL)
            if m:
                return float(m.group(1).replace(",", "."))
        return None
    except:
        return None

def extract_price_gear4music(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        html = resp.text
        patterns = [
            r'"price":\s*"(\d+\.?\d*)"',
            r'<meta itemprop="price"[^>]*content="(\d+\.?\d*)"',
            r'<span class="price"[^>]*>.*?\$?€?£?(\d+\.?\d*)',
            r'data-price="(\d+\.?\d*)"',
        ]
        for p in patterns:
            m = re.search(p, html, re.DOTALL)
            if m:
                return float(m.group(1).replace(",", "."))
        return None
    except:
        return None

def extract_price_pluginboutique(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        html = resp.text
        patterns = [
            r'"price":\s*"(\d+\.?\d*)"',
            r'<meta itemprop="price"[^>]*content="(\d+\.?\d*)"',
            r'\$?€?(\d+\.?\d*)\s*</span>\s*<span[^>]*class="[^"]*price',
            r'class="price"[^>]*>.*?\$?€?(\d+\.?\d*)',
        ]
        for p in patterns:
            m = re.search(p, html, re.DOTALL)
            if m:
                return float(m.group(1).replace(",", "."))
        return None
    except:
        return None

def get_precio(url):
    if not url:
        return None
    if "amazon" in url:
        return extract_price_amazon(url)
    elif "musicstore" in url:
        return extract_price_musicstore(url)
    elif "andertons" in url:
        return extract_price_andertons(url)
    elif "gear4music" in url:
        return extract_price_gear4music(url)
    elif "pluginboutique" in url:
        return extract_price_pluginboutique(url)
    return None

TIENDA_NOMBRES = {
    "amazon": "🇪🇸 Amazon",
    "musicstore": "🇩🇪 Music Store",
    "andertons": "🇬🇧 Andertons",
    "gear4music": "🇪🇺 Gear4Music",
    "pluginboutique": "🔌 Plugin Boutique",
}

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN:
        print("No TELEGRAM_TOKEN")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CANAL_ID,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        print(f"Telegram: {resp.status_code}")
    except Exception as e:
        print(f"Telegram error: {e}")

def formatear_oferta(prod, tienda_key, precio_viejo, precio_nuevo, url):
    icono = PRICE_CATEGORIES.get(prod["categoria"], "🛒")
    nombre = prod["nombre"]
    tienda_nombre = TIENDA_NOMBRES.get(tienda_key, tienda_key)
    descuento = round((1 - precio_nuevo / precio_viejo) * 100)
    moneda = prod.get("moneda", "$")

    msg = f"{icono} <b>{nombre}</b>\n"
    msg += f"📍 {tienda_nombre}\n"
    msg += f"💵 Was: {moneda}{precio_viejo:.0f} → Now: {moneda}{precio_nuevo:.0f}  <b>(-{descuento}%)</b>\n"
    msg += f"🔗 <a href='{url}'>Buy here</a>\n"
    msg += f"🔍 topmusiciangear.com"

    return msg

def main():
    data = load_json("productos.json")
    precios_guardados = load_json("precios.json")
    productos = data.get("productos", [])
    config = data.get("config", {})
    descuento_min = config.get("descuento_minimo", DESCUENTO_MINIMO)
    canal = config.get("canal_id", CANAL_ID)

    global CANAL_ID
    CANAL_ID = canal

    cambios = []

    for prod in productos:
        nombre = prod["nombre"]
        tiendas = prod.get("tiendas", {})
        prev = precios_guardados.get(nombre, {})

        for tienda_key, url in tiendas.items():
            if not url:
                continue
            precio_nuevo = get_precio(url)
            if precio_nuevo is None:
                continue

            precio_viejo = prev.get(tienda_key)
            if precio_viejo is None:
                precio_viejo = precio_nuevo

            if precio_viejo > 0 and precio_nuevo < precio_viejo:
                diff_pct = round((1 - precio_nuevo / precio_viejo) * 100)
                if diff_pct >= descuento_min:
                    cambios.append({
                        "producto": prod,
                        "tienda": tienda_key,
                        "precio_viejo": precio_viejo,
                        "precio_nuevo": precio_nuevo,
                        "url": url,
                    })

            if nombre not in precios_guardados:
                precios_guardados[nombre] = {}
            precios_guardados[nombre][tienda_key] = precio_nuevo

    save_json("precios.json", precios_guardados)

    for c in cambios:
        msg = formatear_oferta(
            c["producto"], c["tienda"],
            c["precio_viejo"], c["precio_nuevo"], c["url"]
        )
        enviar_telegram(msg)
        print(f"Oferta: {c['producto']['nombre']} - {c['tienda']} - {c['precio_viejo']}->{c['precio_nuevo']}")

    if not cambios:
        print(f"No hay ofertas nuevas. ({datetime.now().isoformat()})")

if __name__ == "__main__":
    main()
