# MercadoLibre · CMQ vs La Barra

Tracker de precios de cerveza en las tiendas oficiales de MercadoLibre Argentina:

- **CMQ** — Cervecería y Maltería Quilmes: https://www.mercadolibre.com.ar/tienda/cerveceria-y-malteria-quilmes
- **La Barra (CCU)**: https://www.mercadolibre.com.ar/tienda/la-barra

Dos corridas por día (10:15 y 19:00 hora Argentina), histórico consolidado AM/PM, y un dashboard con la misma estética que los proyectos de PedidosYa/Rappi.

## Cómo funciona (y por qué no cubre el 100% del catálogo)

MercadoLibre pone el listado completo de la categoría "Cervezas" y las fichas de producto individuales **detrás de un login**. Probamos además que, incluso con una sesión ya autenticada, acceder a ese listado desde un browser automatizado dispara un captcha de MercadoLibre — y eso no lo vamos a intentar resolver ni evadir.

Lo que sí es público y estable: la **home de cada tienda** (`/tienda/{slug}`), que muestra varios carruseles curados por el vendedor (Productos recomendados, Más vendidos, Elegidos para vos) con precio de lista, % OFF, precio final y cuotas sin interés. El scraper lee esa home, sin login, sin cookies, sin nada que viole los Términos de Servicio de MercadoLibre.

**Consecuencia real:** esto trae entre 15 y 25 SKUs de cerveza por tienda (los que cada vendedor destaca), no necesariamente el catálogo completo publicado. Es la mejor cobertura posible sin cruzar la línea de evadir verificaciones/captchas.

## Estructura

```
scraper/
  config.py       # URLs de tiendas + diccionarios de marca/segmento
  parse.py        # parseo de marca/calibre/segmento desde el titulo
  scrape_mercadolibre.py   # scraper Playwright (home publica, sin login)
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
cd ..
python scraper/scrape_mercadolibre.py        # auto-detecta AM/PM segun la hora
python scraper/scrape_mercadolibre.py --turno AM   # o forzar el turno
python scripts/build_dashboard_data.py
```

Para ver el dashboard local:

```bash
python -m http.server 8792 --directory docs
```

## Setup en GitHub

1. El repo ya está creado y pusheado: https://github.com/ramiro2004mazur-coder/mercadolibre-cmq-vs-labarra
2. Settings → Pages → Source: **GitHub Actions** (ya configurado).
3. Corré el workflow una vez manualmente (Actions → Scrape MercadoLibre CMQ vs La Barra → Run workflow) para confirmar que trae datos antes de confiar en el cron.

No hace falta ningún secret: el scraper no usa credenciales.

## Datos que captura por producto

- **fleje**: precio de lista (tachado en la ficha de MercadoLibre).
- **ptc**: precio final que paga el comprador.
- **dinamica**: % de descuento vigente.
- **cuotas**: valor de la cuota sin interés, si la tienda la ofrece (dato nuevo, no existía en el dashboard de PedidosYa).

Productos sin la palabra "cerveza" en el título, o que sean combos/surtidos multi-marca, se excluyen (mismo criterio que PedidosYa).
