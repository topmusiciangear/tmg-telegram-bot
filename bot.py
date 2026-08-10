import json
import os
import re
import socket
import sys
import time
import requests
from datetime import datetime, timedelta

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

BLOCKED_STORES = ["amazon", "musicstore", "andertons", "pluginboutique", "gear4music"]

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

def parse_num(s):
    if s is None:
        return None
    s = str(s).strip()
    s = s.replace("\u00a0", " ").replace("\u20ac", "").replace("\u00a3", "").replace("$", "").replace("\ufffd", "").replace("EUR", "").replace("GBP", "").replace("USD", "").replace("RON", "").replace("&euro;", "").replace("&amp;", "")
    s = s.replace(",", "").replace(" ", "")
    try:
        f = float(s)
        return f if f > 0 else None
    except:
        return None

def find_price_in_html(html, patterns):
    for p in patterns:
        m = re.search(p, html, re.DOTALL)
        if m:
            v = parse_num(m.group(1))
            if v:
                return v
    return None

# Generic "was / compare-at / RRP" price detection used by stores that don't
# expose it in JSON-LD. Returns the reference price or None.
WAS_PATTERNS = [
    r'was-price[^>]*>\s*[£€$]?\s*([\d.,\s]+)',
    r'wasPrice"\s*:\s*"?([\d.,]+)',
    r'"was_price"\s*:\s*"?([\d.,]+)',
    r'data-was-price[^>]*>\s*[£€$]?\s*([\d.,\s]+)',
    r'Was:\s*[£€$]\s*([\d.,]+)',
    r'RRP:\s*[£€$]\s*([\d.,]+)',
    r'List Price[^<]{0,20}[£€$]\s*([\d.,]+)',
    r'"originalPrice"\s*:\s*"?([\d.,]+)',
    r'"compareAtPrice"\s*:\s*"?([\d.,]+)',
    r'<s[^>]*>\s*[£€$]\s*([\d.,]+)\s*</s>',
    r'<del[^>]*>\s*[£€$]\s*([\d.,]+)\s*</del>',
    r'line-through[^>]*>\s*[£€$]?\s*([\d.,]+)',
    r'text-decoration:line-through[^>]*>[^<]*[£€$]\s*([\d.,]+)',
]

def find_was_price(html):
    for p in WAS_PATTERNS:
        m = re.search(p, html, re.DOTALL)
        if m:
            v = parse_num(m.group(1))
            if v:
                return v
    return None

# ---------- Amazon ----------
def extract_price_amazon(html):
    # Only look at the buybox region: cut off before "related products" start,
    # otherwise we match prices of other products on the page.
    cut = html.find("pd_rd_i=")
    if cut > 0:
        html = html[:cut]

    current = None
    was = None
    # Main price: a-price-whole + a-price-fraction
    m = re.search(r'class="a-price-whole">\s*([\d.,]+)\s*<span class="a-price-decimal"[^>]*>[^<]*</span>\s*</span>\s*<span class="a-price-fraction">\s*(\d+)', html)
    if m:
        whole = parse_num(m.group(1))
        frac = int(m.group(2))
        if whole:
            current = whole + frac / 100.0
    if current is None:
        current = find_price_in_html(html, [
            r'class="a-offscreen">\s*[A-Z]{0,4}\s*([\d.,]+)',
            r'"priceAmount"\s*:\s*([\d.]+)',
        ])
    # Was price: struck-through RRP block in the buybox
    m = re.search(r'data-a-strike="true"[^>]*>\s*<span class="a-offscreen">\s*[A-Z]{0,4}\s*([\d.,]+)', html)
    if m:
        was = parse_num(m.group(1))
    if was is None:
        was = find_price_in_html(html, [
            r'a-text-price[^>]*data-a-strike="true"[^>]*>\s*<span class="a-offscreen">\s*[A-Z]{0,4}\s*([\d.,]+)',
            r'"listPrice"\s*:\s*\{[^}]*?"amount"\s*:\s*([\d.]+)',
        ])
    return current, was

# ---------- Music Store ----------
def extract_price_musicstore(html):
    # Music Store embeds the main product price in JS like:
    #   listPrices['REC0016331-000'] = 199.00;  salePrices['REC0016331-000'] = 149.00;
    # The "salePriceTransfer"/"listPriceTransfer" divs belong to related products,
    # so we must use the main product's own JS prices.
    current = None
    was = None
    m = re.search(r"listPrices\['([^']+)'\]\s*=\s*([\d.]+)\s*;", html)
    sale = re.search(r"salePrices\['([^']+)'\]\s*=\s*([\d.]+)\s*;", html)
    if m:
        current = parse_num(m.group(2))
        # if a sale price exists for the same product, use it as current
        if sale and sale.group(1) == m.group(1):
            current = parse_num(sale.group(2))
    if current is None:
        current = find_price_in_html(html, [
            r'<meta property="og:price:amount"[^>]*content="([\d.,]+)"',
            r'<meta itemprop="price"[^>]*content="([\d.,]+)"',
            r'product-sale-price-value[^>]*>\s*([^<]+)',
        ])
    if m:
        # List price is the "was" reference for this product
        was = parse_num(m.group(2))
        if sale and sale.group(1) == m.group(1):
            sale_v = parse_num(sale.group(2))
            if sale_v and sale_v < was:
                current = sale_v
    return current, was

# ---------- Andertons ----------
def extract_price_andertons(html):
    current = find_price_in_html(html, [
        r'data-testid="pdp-price"[^>]*>\s*£?\s*([\d.,]+)',
        r'"price":\s*"?([\d.,]+)"?[^}]*"priceCurrency"',
        r'<meta itemprop="price"[^>]*content="([\d.,]+)"',
        r'data-price[=]["\']([\d.,]+)["\']',
    ])
    if current is None:
        # JSON-LD Offer price
        m = re.search(r'"offers"\s*:\s*\{[^}]*?"price"\s*:\s*"?([\d.,]+)', html)
        if m:
            current = parse_num(m.group(1))
    was = find_was_price(html)
    return current, was

# ---------- Gear4Music ----------
def extract_price_gear4music(html):
    current = None
    m = re.search(r'"offers"\s*:\s*\{[^}]*?"price"\s*:\s*"?([\d.,]+)', html)
    if m:
        current = parse_num(m.group(1))
    if current is None:
        current = find_price_in_html(html, [
            r'<meta itemprop="price"[^>]*content="([\d.,]+)"',
            r'class="[^"]*price[^"]*"[^>]*>\s*[£€$]\s*([\d.,]+)',
            r'data-price[=]["\']([\d.,]+)["\']',
        ])
    was = find_was_price(html)
    return current, was

# ---------- Plugin Boutique ----------
def extract_price_pluginboutique(html):
    current = find_price_in_html(html, [
        r'data-product-purchase-options-target="otpPrice"[^>]*>\s*<div class="flex">\s*<span class="block text-gray-800[^>]*">\s*[€$£\ufffd]?\s*([\d.,]+)',
        r'text-gray-800 text-xl font-semibold[^>]*>\s*[€$£\ufffd]?\s*([\d.,]+)',
        r'<meta itemprop="price"[^>]*content="([\d.,]+)"',
        r'"price"\s*:\s*"?([\d.,]+)"?',
    ])
    was = find_was_price(html)
    return current, was

# ---------- Plugin Boutique ----------

IMPERSONATES = ["chrome124", "chrome110", "safari15_5", "safari17_0", "edge99"]

def amazon_currency_cookie(url):
    # Amazon shows prices in the visitor's local currency (geo-based). Force the
    # store's native currency via the i18n-prefs cookie so prices are stable.
    if "amazon.co.uk" in url:
        return "GBP"
    if "amazon.de" in url:
        return "EUR"
    if "amazon.it" in url:
        return "EUR"
    if "amazon.fr" in url:
        return "EUR"
    if "amazon.es" in url:
        return "EUR"
    if "amazon.com" in url:
        return "USD"
    return None

def fetch_page(url):
    for store in BLOCKED_STORES:
        if store not in url:
            continue
        if not HAS_CURL:
            break
        headers = dict(HEADERS)
        amz = amazon_currency_cookie(url)
        if amz:
            headers["Cookie"] = f"i18n-prefs={amz}"
        for imp in IMPERSONATES:
            try:
                resp = curl_requests.get(url, headers=headers, timeout=10, impersonate=imp, allow_redirects=True)
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
        if resp.status_code == 200 and len(resp.content) > 10000:
            return resp.text
        return None
    except Exception as e:
        log(f"  [requests] failed: {e}")
        return None

CURRENCY_SYMBOLS = {
    "EUR": "€", "GBP": "£", "USD": "$", "RON": "lei", "CAD": "C$", "AUD": "A$",
}

def detect_moneda(url, html=""):
    # Prefer the page's own currency (meta og:price:currency / JSON-LD priceCurrency)
    if html:
        m = re.search(r'<meta property="og:price:currency"[^>]*content="([A-Z]{3})"', html)
        if not m:
            m = re.search(r'"priceCurrency"\s*:\s*"([A-Z]{3})"', html)
        if m:
            iso = m.group(1).upper()
            return CURRENCY_SYMBOLS.get(iso, iso)
        # Plugin Boutique: currency sits right before the price in the otpPrice block,
        # often as \ufffd (undecodable euro) — treat that as EUR.
        if "pluginboutique" in url:
            m = re.search(r'otpPrice[^>]*>\s*<div class="flex">[^€£$]*?([€£$\ufffd])\s*[\d.,]+', html)
            if m:
                sym = m.group(1)
                return "€" if sym == "\ufffd" else sym
        # Amazon encodes currency as a prefix like "RON953.25" or "$953.25"
        m = re.search(r'class="a-price-symbol"[^>]*>\s*([A-Z$£€]{1,4})', html)
        if not m:
            m = re.search(r'class="a-offscreen">\s*([A-Z$£€]{1,4})\s*[\d.,]+', html)
        if m:
            sym = m.group(1).strip()
            if sym in ("$", "£", "€"):
                return sym
            return CURRENCY_SYMBOLS.get(sym.upper(), sym)
        # Generic: what symbol appears right before a price in the page
        m = re.search(r'[£€$]\s*[\d.,]+', html)
        if m:
            return m.group(0)[0]
    if "amazon.co.uk" in url:
        return "£"
    if "amazon.de" in url:
        return "€"
    if "amazon" in url:
        return "$"
    if "musicstore" in url:
        return "€"
    if "andertons" in url:
        return "£"
    if "gear4music" in url:
        return "£"
    return "$"

def extract_price(url, nombre_producto=""):
    if not url:
        return None
    try:
        html = fetch_page(url)
        if html is None:
            return None
        moneda = detect_moneda(url, html)
        if "amazon" in url:
            current, was = extract_price_amazon(html)
        elif "musicstore" in url:
            current, was = extract_price_musicstore(html)
        elif "andertons" in url:
            current, was = extract_price_andertons(html)
        elif "gear4music" in url:
            current, was = extract_price_gear4music(html)
        elif "pluginboutique" in url:
            current, was = extract_price_pluginboutique(html)
        else:
            return None
        if not current:
            return None
        return (current, was, moneda)
    except:
        return None

def enviar_telegram(mensaje):
    if not TELEGRAM_TOKEN:
        log("No TELEGRAM_TOKEN set")
        return False
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
        if resp.status_code == 200:
            return True
        log(f"Telegram response: {resp.text[:200]}")
    except Exception as e:
        log(f"Telegram error: {e}")
    return False

def formatear_oferta(prod, tienda_key, precio_base, precio_actual, url, moneda="£"):
    icono = PRICE_CATEGORIES.get(prod.get("categoria", ""), "🛒")
    nombre = prod["nombre"]
    tienda_nombre = TIENDA_NOMBRES.get(tienda_key, tienda_key)
    descuento = round((1 - precio_actual / precio_base) * 100)

    msg = f"{icono} <b>{nombre}</b>\n"
    msg += f"📍 {tienda_nombre}\n"
    msg += f"💵 Was: {moneda}{precio_base:.0f} → Now: {moneda}{precio_actual:.0f}  <b>(-{descuento}%)</b>\n"
    if url:
        msg += f"🔗 <a href='{url}'>Buy here</a>\n"
    msg += f"🔍 topmusiciangear.com"
    return msg

def precio_es_plausible(current, was):
    if not current or current <= 0 or current > 100000:
        return False
    if not was or was <= 0:
        return False
    ratio = current / was
    # A real sale: current must be lower than was but not absurdly so
    return 0.05 < ratio < 0.99

ESTADO_FILE = "estado.json"

def load_estado():
    try:
        with open(ESTADO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_estado(estado):
    try:
        with open(ESTADO_FILE, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Could not save estado.json: {e}")

def ya_publicado(estado, nombre, tienda, precio_actual):
    key = f"{nombre}|{tienda}"
    entry = estado.get(key)
    if not entry:
        return False
    last_price = entry.get("precio_actual")
    last_time = entry.get("ts", 0)
    if precio_actual < last_price - 0.01:
        return False
    if time.time() - last_time >= 86400:
        return False
    return True

def main():
    import os as _os
    log(f"CWD: {_os.getcwd()}")
    log(f"productos.json exists: {_os.path.exists('productos.json')}")
    log(f"Files in CWD: {[f for f in _os.listdir('.') if f.endswith('.json')]}")

    if HAS_CURL:
        try:
            curl_requests.get("https://www.amazon.co.uk", headers=HEADERS, timeout=8, impersonate="chrome124")
            log("Warmed Amazon session")
        except:
            pass

    data = load_json("productos.json")
    productos = data.get("productos", [])
    config = data.get("config", {})
    descuento_min = config.get("descuento_minimo", 5)

    estado = load_estado()

    log(f"Loaded {len(productos)} products, min discount: {descuento_min}%")

    cambios = []

    for prod in productos:
        nombre = prod["nombre"]
        tiendas = prod.get("tiendas", {})

        for tienda_key, url in tiendas.items():
            if not url:
                continue
            log(f"Checking {nombre} @ {tienda_key}...")
            info = extract_price(url, nombre)
            if info is None:
                log(f"  Could not get price")
                continue
            precio_actual, precio_was, moneda = info

            if not precio_was or precio_was <= 0:
                log(f"  No sale/was price on page (not on sale) - skipped")
                continue

            if not precio_es_plausible(precio_actual, precio_was):
                log(f"  Not a plausible discount (current: {precio_actual}, was: {precio_was}) - skipped")
                continue

            diff_pct = round((1 - precio_actual / precio_was) * 100)
            log(f"  Was: {precio_was} Current: {precio_actual} Diff: {diff_pct}%")

            if diff_pct >= descuento_min and not ya_publicado(estado, nombre, tienda_key, precio_actual):
                cambios.append({
                    "producto": prod,
                    "tienda": tienda_key,
                    "precio_base": precio_was,
                    "precio_actual": precio_actual,
                    "url": url,
                    "moneda": moneda,
                })

    for i, c in enumerate(cambios):
        if i > 0:
            time.sleep(3)
        msg = formatear_oferta(
            c["producto"], c["tienda"],
            c["precio_base"], c["precio_actual"], c["url"], c["moneda"]
        )
        log(f"DEAL: {c['producto']['nombre']} @ {c['tienda']} - {c['precio_base']} -> {c['precio_actual']}")
        ok = enviar_telegram(msg)
        if ok:
            key = f"{c['producto']['nombre']}|{c['tienda']}"
            estado[key] = {
                "precio_actual": c["precio_actual"],
                "precio_base": c["precio_base"],
                "ts": int(time.time()),
            }

    save_estado(estado)

    if not cambios:
        log(f"No deals found. ({datetime.now().isoformat()})")

if __name__ == "__main__":
    main()
