"""
Scraper de MercadoLibre para las tiendas oficiales CMQ y La Barra.

No usa login ni cookies de sesion. Se probo que el listado completo de categoria
("Cervezas") y las fichas de producto individuales estan detras de un muro de
verificacion de cuenta, y que incluso con una sesion autenticada valida, acceder
a ese listado desde un browser automatizado dispara un captcha de MercadoLibre
("captcha/wall/logged"). No vamos a intentar resolver ni evadir eso.

En cambio, este scraper lee la home publica de cada tienda (sin login, sin
captcha, confirmado en vivo), que muestra varios carruseles curados por el
vendedor (Productos recomendados, Mas vendidos, Elegidos para vos, etc.) con
precio de lista, % OFF, precio final y cuotas. No es garantia de cubrir el 100%
del catalogo de cada tienda, pero es la unica via que no viola verificaciones
ni requiere credenciales.
"""
from __future__ import annotations

import argparse
import json
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

TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")

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


def scrapear_tienda(page, tienda_key: str, store: dict, errores: list[str]) -> list[dict]:
    productos: list[dict] = []
    log(f"[{tienda_key}] navegando a {store['home_url']}")
    try:
        page.goto(store["home_url"], wait_until="domcontentloaded", timeout=30000)
    except PWTimeout:
        errores.append(f"[{tienda_key}] timeout al cargar la home de la tienda")
        return productos

    if hay_muro(page):
        errores.append(f"[{tienda_key}] la home publica devolvio un muro inesperado ({page.url})")
        return productos

    try:
        page.wait_for_selector(".poly-card, li.ui-search-layout__item", timeout=15000)
    except PWTimeout:
        errores.append(f"[{tienda_key}] no se encontraron productos en la home (posible cambio de layout)")
        return productos

    # Los carruseles de abajo (mas vendidos, elegidos para vos) a veces cargan
    # perezosamente al hacer scroll; forzamos un scroll completo antes de leer el DOM.
    try:
        alto_previo = -1
        for _ in range(6):
            alto = page.evaluate("document.body.scrollHeight")
            if alto == alto_previo:
                break
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(400)
            alto_previo = alto
    except Exception:  # noqa: BLE001 - el scroll es best-effort, no crítico
        pass

    crudos = page.evaluate(EXTRACT_JS)
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

    log(f"[{tienda_key}] {len(productos)} cervezas encontradas en la home publica")
    return productos


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
            # Refrescamos metadata por si el titulo/atributos cambiaron.
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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
        )
        page = context.new_page()

        for tienda_key, store in STORES.items():
            try:
                productos = scrapear_tienda(page, tienda_key, store, errores)
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
