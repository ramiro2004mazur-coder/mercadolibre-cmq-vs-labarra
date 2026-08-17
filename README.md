# MercadoLibre · CMQ vs La Barra

Tracker de precios de cerveza en las tiendas oficiales de MercadoLibre Argentina:

- **CMQ** — Cervecería y Maltería Quilmes: https://www.mercadolibre.com.ar/tienda/cerveceria-y-malteria-quilmes
- **La Barra (CCU)**: https://www.mercadolibre.com.ar/tienda/la-barra

Dos corridas por día (10:15 y 19:00 hora Argentina), histórico consolidado AM/PM, y un dashboard con la misma estética que los proyectos de PedidosYa/Rappi.

## ⚠️ Antes de usarlo: el tema de la sesión autenticada

MercadoLibre pone el listado completo de la categoría "Cervezas" y las fichas de producto **detrás de un login** ("account-verification"). No hay forma pública/anónima de ver el catálogo completo de estas tiendas.

Este scraper **no automatiza el login** (no maneja usuario/contraseña, no resuelve captchas ni verificaciones). En cambio, usa cookies de sesión que vos exportás manualmente desde tu propia cuenta ya logueada:

1. Iniciá sesión en `mercadolibre.com.ar` en tu navegador normal (Chrome/Firefox), con la cuenta que quieras usar para esto.
2. Exportá las cookies del dominio `mercadolibre.com.ar` como JSON. Opciones:
   - Extensión de navegador tipo "Get cookies.txt LOCALLY" / "Cookie-Editor" (exportar como JSON, no como Netscape).
   - DevTools → pestaña Application/Storage → Cookies → copiar manualmente.
3. El JSON debe ser una lista de objetos `{"name": ..., "value": ..., "domain": ".mercadolibre.com.ar", "path": "/"}` (formato estándar que exportan esas extensiones).
4. Pegá ese JSON completo como el secret **`ML_SESSION_COOKIES_JSON`** en GitHub (Settings → Secrets and variables → Actions → New repository secret).

**Riesgos que tenés que aceptar vos, no yo:**
- Usar una cuenta real para scraping automatizado va contra los Términos de Servicio de MercadoLibre. Existe riesgo de suspensión de esa cuenta.
- Las cookies expiran (inactividad, logout en otro dispositivo, cambio de IP). Cuando eso pase, el scraper lo va a detectar y loguear como error (no rompe la corrida ni corrompe el histórico), pero **no se va a re-loguear solo** — vas a tener que repetir el proceso de arriba y actualizar el secret. Recomendación: revisarlo cada 2-3 semanas.

## Estructura

```
scraper/
  config.py       # URLs de tiendas + diccionarios de marca/segmento
  parse.py        # parseo de marca/calibre/segmento desde el titulo
  scrape_mercadolibre.py   # scraper Playwright
scripts/
  build_dashboard_data.py  # data/historico.json -> docs/data.json (pivot)
data/
  raw/            # 1 archivo crudo por corrida (auditoria/debug)
  historico.json  # consolidado append-only, fuente de verdad
docs/
  index.html      # dashboard (GitHub Pages sirve desde aca)
  data.json       # generado por build_dashboard_data.py
.github/workflows/scrape.yml   # cron 10:15 y 19:00 ART + commit + deploy Pages
```

## Correr localmente

```bash
cd scraper
pip install -r requirements.txt
playwright install chromium
```

Pegá el JSON de cookies en `scraper/.cookies.local.json` (gitignored, nunca se commitea), y corré:

```bash
python scraper/scrape_mercadolibre.py        # auto-detecta AM/PM segun la hora
python scraper/scrape_mercadolibre.py --turno AM   # o forzar el turno
python scripts/build_dashboard_data.py
```

Para ver el dashboard local:

```bash
python -m http.server 8792 --directory docs
```

## Setup en GitHub

1. Creá el repo en GitHub y pusheá este proyecto.
2. Settings → Secrets and variables → Actions → agregá `ML_SESSION_COOKIES_JSON`.
3. Settings → Pages → Source: **GitHub Actions**.
4. Corré el workflow una vez manualmente (Actions → Scrape MercadoLibre CMQ vs La Barra → Run workflow) para validar que todo funcione antes de confiar en el cron.

## Datos que captura por producto

- **fleje**: precio de lista (tachado en la ficha de MercadoLibre).
- **ptc**: precio final que paga el comprador.
- **dinamica**: % de descuento vigente.
- **cuotas**: valor de la cuota sin interés, si la tienda la ofrece (dato nuevo, no existía en el dashboard de PedidosYa).

Productos sin la palabra "cerveza" en el título, o que sean combos/surtidos multi-marca, se excluyen (mismo criterio que PedidosYa).
