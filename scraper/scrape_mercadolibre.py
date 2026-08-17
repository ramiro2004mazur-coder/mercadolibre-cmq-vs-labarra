"""
Scraper de MercadoLibre para las tiendas oficiales CMQ y La Barra.

Dos fuentes, en orden de preferencia:

1. Listado completo de categoria ("Cervezas"), que requiere una sesion
   autenticada (cookies). Este script NUNCA envia usuario/contrasena ni
   intenta resolver captchas/verificaciones: si el acceso esta bloqueado
   (login, captcha), lo detecta, lo loguea, y pasa a la fuente 2.
2. Home publica de la tienda (sin login), que muestra los carruseles que el
   vendedor decide destacar (Productos recomendados, Mas vendidos, etc.).
   Cobertura parcial, pero siempre disponible sin credenciales.

Cookies: se leen de la variable de entorno ML_SESSION_COOKIES_JSON (JSON
crudo), o del archivo indicado por ML_COOKIES_FILE, o de
scraper/.cookies.local.json (gitignored) si existe. Si no hay cookies
disponibles, se usa directamente la fuente 2 para ambas tiendas.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from config import STORES
from parse import es_cerveza, parse_producto

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
HISTORICO_PATH = DATA_DIR / "historico.json"
LOCAL_COOKIES_PATH = Path(__file__).resolve().parent / ".cookies.local.json"

TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")
MAX_PAGINAS = 25

ITEM_ID_RE = re.compile(r"item_id%3A(MLA\d+)|/(MLA\d+)-")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

EXTRACT_JS = """
() => {
  const cards = document.querySelectorAll('.poly-card, li.ui-search-layout__item');
  const seen = new Set();
  const out = [];
  cards.forEach(card => {
    const titleEl = card.querySelector('.poly-component__title, h2.ui-search-item__title');
    if (!titleEl) return;
    const titulo = (titleEl.textContent || '').trim();
    const anchor = titleEl.tagName === 'A' ? titleEl : titleEl.closest('a');
    const href = anchor ? anchor.href : '';
    if (!titulo || !href || seen.has(href)) return;
    seen.add(href);

    const prevEl = card.querySelector('.poly-price__previous .andes-money-amount__fraction, s .andes-money-amount__fraction');
    const curEl = card.querySelector('.poly-price__current .andes-money-amount__fraction, .price-tag-fraction');
    const discEl = card.querySelector('.poly-price__disc-label, .ui-search-price__discount, .andes-money-amount__discount');
    const instEl = card.querySelector('.poly-price__installments, .ui-search-installments');
    const instFracEl = instEl ? instEl.querySelector('.andes-money-amount__fraction') : null;

    out.push({
      titulo,
      url: href,
      fleje_raw: prevEl ? prevEl.textContent : null,
      ptc_raw: curEl ? curEl.textContent : null,
      disc_raw: discEl ? discEl.textContent : null,
      inst_raw: instFracEl ? instFracEl.textContent : null,
    });
  });
  return out;
}
"""


def log(msg: str) -> None:
    print(f"[{datetime.now(TZ_AR).isoformat(timespec='seconds')}] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Cookies (opcionales)
# ---------------------------------------------------------------------------

_DOMAIN_RE = re.compile(r"[\w.-]+\.[a-zA-Z]{2,}")
_SAMESITE_MAP = {
    "no_restriction": "None",
    "unspecified": "Lax",
    "lax": "Lax",
    "strict": "Strict",
}


def normalizar_cookie(c: dict) -> dict | None:
    """Traduce un export tipo Cookie-Editor/DevTools al formato que espera Playwright."""
    if not c.get("name") or "value" not in c:
        return None

    dominio_crudo = str(c.get("domain", ""))
    match = _DOMAIN_RE.search(dominio_crudo)
    if not match:
        return None
    host = match.group(0)
    if not c.get("hostOnly", False) and not host.startswith("."):
        host = "." + host

    same_site_raw = str(c.get("sameSite", "")).lower()
    same_site = _SAMESITE_MAP.get(same_site_raw, "Lax")

    expira = c.get("expirationDate")
    return {
        "name": c["name"],
        "value": c["value"],
        "domain": host,
        "path": c.get("path") or "/",
        "httpOnly": bool(c.get("httpOnly", False)),
        "secure": bool(c.get("secure", True)),
        "sameSite": same_site,
        "expires": float(expira) if expira else -1,
    }


def cargar_cookies() -> list[dict] | None:
    raw = os.environ.get("ML_SESSION_COOKIES_JSON")
    if not raw:
        cookies_file = os.environ.get("ML_COOKIES_FILE")
        path = Path(cookies_file).expanduser() if cookies_file else LOCAL_COOKIES_PATH
        if path.exists():
            raw = path.read_text(encoding="utf-8")
    if not raw:
        return None

    crudas = json.loads(raw)
    cookies = []
    for c in crudas:
        normalizada = normalizar_cookie(c)
        if normalizada is None:
            log(f"cookie descartada (formato irreconocible): {c.get('name', '<sin nombre>')}")
            continue
        cookies.append(normalizada)
    return cookies or None


# ---------------------------------------------------------------------------
# Parseo de precios
# ---------------------------------------------------------------------------


def parse_money(texto: str | None) -> float | None:
    if not texto:
        return None
    limpio = texto.strip().replace(".", "").replace(",", ".")
    limpio = re.sub(r"[^\d.]", "", limpio)
    if not limpio:
        return None
    try:
        return float(limpio)
    except ValueError:
        return None


def parse_descuento(texto: str | None) -> float | None:
    if not texto:
        return None
    match = re.search(r"(\d+)\s*%", texto)
    return int(match.group(1)) / 100 if match else None


def extraer_item_id(url: str) -> str | None:
    match = ITEM_ID_RE.search(url)
    if not match:
        return None
    return match.group(1) or match.group(2)


def hay_muro(page) -> bool:
    return "account-verification" in page.url or "captcha" in page.url or "/gz/" in page.url


def items_desde_cards(crudos: list[dict], tienda_key: str, errores: list[str]) -> list[dict]:
    productos = []
    for item in crudos:
        try:
            titulo = item["titulo"]
            if not es_cerveza(titulo):
                continue

            item_id = extraer_item_id(item["url"])
            if not item_id:
                errores.append(f"[{tienda_key}] no se pudo extraer item_id de: {item['url']}")
                continue

            ptc = parse_money(item["ptc_raw"])
            fleje = parse_money(item["fleje_raw"]) or ptc
            dinamica = parse_descuento(item["disc_raw"])
            if dinamica is None and fleje and ptc and fleje > 0:
                dinamica = round(1 - (ptc / fleje), 4)
            cuotas = parse_money(item["inst_raw"])

            if ptc is None:
                errores.append(f"[{tienda_key}] sin precio final parseable: {titulo!r}")
                continue

            atributos = parse_producto(titulo)
            productos.append(
                {
                    "tienda": tienda_key,
                    "sku": item_id,
                    "titulo": titulo,
                    "url": item["url"].split("#")[0],
                    "fleje": fleje,
                    "ptc": ptc,
                    "dinamica": dinamica or 0,
                    "cuotas": cuotas,
                    **atributos,
                }
            )
        except Exception as exc:  # noqa: BLE001 - un item roto no debe tumbar la corrida
            errores.append(f"[{tienda_key}] error parseando item ({item.get('url')}): {exc}")
    return productos


# ---------------------------------------------------------------------------
# Fuente 1: listado completo de categoria (requiere cookies)
# ---------------------------------------------------------------------------


def scrapear_listado(page, tienda_key: str, store: dict, errores: list[str]) -> list[dict] | None:
    """Devuelve la lista de productos, o None si el listado esta bloqueado (para caer al fallback)."""
    log(f"[{tienda_key}] (listado autenticado) navegando a {store['cervezas_url']}")
    try:
        page.goto(store["cervezas_url"], wait_until="domcontentloaded", timeout=30000)
    except PWTimeout:
        errores.append(f"[{tienda_key}] timeout al cargar el listado de categoria")
        return None

    if hay_muro(page):
        errores.append(
            f"[{tienda_key}] listado bloqueado ({page.url}) - cookies vencidas o captcha; uso home publica"
        )
        return None

    productos: list[dict] = []
    vistos_urls: set[str] = set()
    for pagina in range(1, MAX_PAGINAS + 1):
        try:
            page.wait_for_selector(".poly-card, li.ui-search-layout__item", timeout=15000)
        except PWTimeout:
            if pagina == 1:
                errores.append(f"[{tienda_key}] listado sin productos en la pagina 1 (posible cambio de layout)")
                return None
            break

        crudos = page.evaluate(EXTRACT_JS)
        nuevos = [c for c in crudos if c["url"] not in vistos_urls]
        for c in nuevos:
            vistos_urls.add(c["url"])
        productos.extend(items_desde_cards(nuevos, tienda_key, errores))

        log(f"[{tienda_key}] listado pagina {pagina}: {len(nuevos)} items nuevos, {len(productos)} cervezas acumuladas")
        if not nuevos:
            break

        siguiente = page.query_selector(
            "a.andes-pagination__link[title='Siguiente'], li.andes-pagination__button--next a"
        )
        if not siguiente:
            break
        try:
            siguiente.click()
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except PWTimeout:
            errores.append(f"[{tienda_key}] timeout al pasar de pagina en el listado, corto paginacion")
            break

        if hay_muro(page):
            errores.append(f"[{tienda_key}] listado se bloqueo a mitad de la paginacion (pagina {pagina + 1})")
            break

    return productos


# ---------------------------------------------------------------------------
# Fuente 2: home publica de la tienda (fallback, sin login)
# ---------------------------------------------------------------------------


def scrapear_home(page, tienda_key: str, store: dict, errores: list[str]) -> list[dict]:
    log(f"[{tienda_key}] (home publica) navegando a {store['home_url']}")
    try:
        page.goto(store["home_url"], wait_until="domcontentloaded", timeout=30000)
    except PWTimeout:
        errores.append(f"[{tienda_key}] timeout al cargar la home de la tienda")
        return []

    if hay_muro(page):
        errores.append(f"[{tienda_key}] la home publica devolvio un muro inesperado ({page.url})")
        return []

    try:
        page.wait_for_selector(".poly-card, li.ui-search-layout__item", timeout=15000)
    except PWTimeout:
        errores.append(f"[{tienda_key}] no se encontraron productos en la home (posible cambio de layout)")
        return []

    try:
        alto_previo = -1
        for _ in range(6):
            alto = page.evaluate("document.body.scrollHeight")
            if alto == alto_previo:
                break
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(400)
            alto_previo = alto
    except Exception:  # noqa: BLE001 - el scroll es best-effort, no critico
        pass

    crudos = page.evaluate(EXTRACT_JS)
    productos = items_desde_cards(crudos, tienda_key, errores)
    log(f"[{tienda_key}] {len(productos)} cervezas encontradas en la home publica")
    return productos


def scrapear_tienda(page, tienda_key: str, store: dict, hay_cookies: bool, errores: list[str]) -> list[dict]:
    if hay_cookies:
        productos = scrapear_listado(page, tienda_key, store, errores)
        if productos is not None:
            return productos
    return scrapear_home(page, tienda_key, store, errores)


def determinar_turno(turno_arg: str | None) -> str:
    if turno_arg:
        return turno_arg
    hora_ar = datetime.now(TZ_AR).hour
    return "AM" if hora_ar < 15 else "PM"


def cargar_historico() -> dict:
    if HISTORICO_PATH.exists():
        return json.loads(HISTORICO_PATH.read_text(encoding="utf-8"))
    return {"runs": [], "productos": []}


def consolidar_historico(historico: dict, run_label: str, productos_run: list[dict]) -> dict:
    if run_label not in historico["runs"]:
        historico["runs"].append(run_label)

    index = {(p["tienda"], p["sku"]): p for p in historico["productos"]}

    for prod in productos_run:
        clave = (prod["tienda"], prod["sku"])
        entrada = index.get(clave)
        if entrada is None:
            entrada = {
                "tienda": prod["tienda"],
                "sku": prod["sku"],
                "titulo": prod["titulo"],
                "url": prod["url"],
                "marca": prod["marca"],
                "grupo": prod["grupo"],
                "calibre": prod["calibre"],
                "segmento": prod["segmento"],
                "runs": {},
            }
            historico["productos"].append(entrada)
            index[clave] = entrada
        else:
            entrada.update(
                {
                    "titulo": prod["titulo"],
                    "url": prod["url"],
                    "marca": prod["marca"],
                    "grupo": prod["grupo"],
                    "calibre": prod["calibre"],
                    "segmento": prod["segmento"],
                }
            )

        entrada["runs"][run_label] = {
            "fleje": prod["fleje"],
            "ptc": prod["ptc"],
            "dinamica": prod["dinamica"],
            "cuotas": prod["cuotas"],
        }

    return historico


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--turno", choices=["AM", "PM"], default=None)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    fecha = datetime.now(TZ_AR).strftime("%Y-%m-%d")
    turno = determinar_turno(args.turno)
    run_label = f"{fecha} {turno}"
    log(f"Corrida: {run_label}")

    errores: list[str] = []
    todos_productos: list[dict] = []

    cookies = cargar_cookies()
    log(f"Cookies disponibles: {'si (' + str(len(cookies)) + ')' if cookies else 'no -> uso solo home publica'}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
        )
        if cookies:
            context.add_cookies(cookies)
        page = context.new_page()

        for tienda_key, store in STORES.items():
            try:
                productos = scrapear_tienda(page, tienda_key, store, bool(cookies), errores)
                todos_productos.extend(productos)
            except Exception as exc:  # noqa: BLE001 - una tienda rota no debe tumbar la otra
                errores.append(f"[{tienda_key}] fallo inesperado: {exc}")
                log(f"[{tienda_key}] ERROR: {exc}")

        browser.close()

    raw_path = RAW_DIR / f"{fecha}_{turno}.json"
    raw_path.write_text(
        json.dumps({"run": run_label, "productos": todos_productos, "errores": errores}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log(f"Guardado raw: {raw_path} ({len(todos_productos)} productos, {len(errores)} errores)")

    if errores:
        for e in errores:
            log(f"ERROR: {e}")

    historico = cargar_historico()
    historico = consolidar_historico(historico, run_label, todos_productos)
    HISTORICO_PATH.write_text(json.dumps(historico, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Historico actualizado: {HISTORICO_PATH} ({len(historico['productos'])} productos, {len(historico['runs'])} corridas)")

    if not todos_productos:
        log("La corrida no trajo NINGUN producto de ninguna tienda.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
