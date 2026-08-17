# MercadoLibre · CMQ vs La Barra

Tracker de precios de cerveza en las tiendas oficiales de MercadoLibre Argentina:

- **CMQ** — Cervecería y Maltería Quilmes: https://www.mercadolibre.com.ar/tienda/cerveceria-y-malteria-quilmes
- **La Barra (CCU)**: https://www.mercadolibre.com.ar/tienda/la-barra

Dos corridas por día (10:15 y 19:00 hora Argentina), histórico consolidado AM/PM, y un dashboard con la misma estética que los proyectos de PedidosYa/Rappi.

## Cómo funciona

El scraper intenta dos fuentes, en este orden:

1. **Listado completo de categoría "Cervezas"** de cada tienda — el catálogo real. Requiere una sesión autenticada (cookies). Probamos que acceder a esto desde una IP de datacenter (GitHub-hosted runner) dispara un captcha de MercadoLibre incluso con sesión válida, así que **este workflow corre en un runner self-hosted instalado en tu Mac**: al usar la misma IP/máquina con la que te logueaste, es mucho menos probable (no garantizado) que MercadoLibre lo bloquee.
2. **Home pública de la tienda** (sin login) — fallback automático si el listado está bloqueado (cookies vencidas, captcha, lo que sea). Cubre solo lo que cada vendedor destaca en su home (5-20+ SKUs según la tienda), pero siempre funciona sin credenciales.

El scraper nunca automatiza login ni resuelve captchas/verificaciones — si el listado está bloqueado, lo detecta, lo loguea, y cae al fallback público sin romper la corrida.

## Setup del runner self-hosted (ya hecho una vez, dejar como referencia)

```bash
mkdir ~/actions-runner && cd ~/actions-runner
curl -o runner.tar.gz -L https://github.com/actions/runner/releases/latest/download/actions-runner-osx-arm64-<version>.tar.gz
tar xzf runner.tar.gz
TOKEN=$(gh api -X POST repos/ramiro2004mazur-coder/mercadolibre-cmq-vs-labarra/actions/runners/registration-token --jq .token)
./config.sh --url https://github.com/ramiro2004mazur-coder/mercadolibre-cmq-vs-labarra --token $TOKEN --unattended --name "ramiro-mac" --labels self-hosted --work _work
./svc.sh install
./svc.sh start
```

**Importante:** el runner solo reacciona a `schedule` y `workflow_dispatch` (nunca a `pull_request`), justamente porque el repo es público y un self-hosted runner en un repo público es sensible a workflows de terceros vía PR. No lo cambies sin pensarlo dos veces.

Para que el cron de las 10:15/19:00 funcione, **tu Mac tiene que estar prendida y conectada** a esa hora. Si está apagada, esa corrida se pierde (no hay reintento automático).

Chequear que el servicio esté corriendo:
```bash
cd ~/actions-runner && ./svc.sh status
```

## Cookies (para la fuente 1, el listado completo)

Se guardan **solo en tu Mac**, nunca en GitHub ni en ningún chat:

1. Iniciá sesión en `mercadolibre.com.ar` en tu navegador normal, en esta misma Mac.
2. Instalá la extensión "Cookie-Editor" (Chrome/Firefox), exportá las cookies del dominio como JSON.
3. Guardá ese JSON en: `~/.config/ml-scraper/cookies.json` (la carpeta ya existe, permisos 700).

Si ese archivo no existe o las cookies vencieron, el scraper cae automáticamente al fallback público — no rompe nada, simplemente trae menos productos ese día. Repetí este proceso cada vez que quieras refrescar la sesión (cada 2-3 semanas es razonable).

**Recordatorio del riesgo:** usar una cuenta real para esto sigue yendo contra los Términos de Servicio de MercadoLibre. Correrlo desde tu propia Mac reduce el riesgo de que el captcha se dispare, pero no lo elimina ni te exime de esa violación de ToS — es una decisión tuya, no mía.

## Estructura

```
scraper/
  config.py       # URLs de tiendas + diccionarios de marca/segmento
  parse.py        # parseo de marca/calibre/segmento desde el titulo
  scrape_mercadolibre.py   # listado autenticado -> fallback home publica
scripts/
  build_dashboard_data.py  # data/historico.json -> docs/data.json (pivot)
data/
  raw/            # 1 archivo crudo por corrida (auditoria/debug)
  historico.json  # consolidado append-only, fuente de verdad
docs/
  index.html      # dashboard (GitHub Pages sirve desde aca)
  data.json       # generado por build_dashboard_data.py
.github/workflows/scrape.yml   # cron 10:15 y 19:00 ART, corre en el runner de tu Mac
```

## Correr localmente (fuera del workflow)

```bash
cd scraper
pip install -r requirements.txt
playwright install chromium
cd ..
python scraper/scrape_mercadolibre.py        # auto-detecta AM/PM segun la hora
python scraper/scrape_mercadolibre.py --turno AM   # o forzar el turno
python scripts/build_dashboard_data.py
python -m http.server 8792 --directory docs   # ver el dashboard local
```

## Datos que captura por producto

- **fleje**: precio de lista (tachado en la ficha de MercadoLibre).
- **ptc**: precio final que paga el comprador.
- **dinamica**: % de descuento vigente.
- **cuotas**: valor de la cuota sin interés, si la tienda la ofrece.

Productos sin la palabra "cerveza" en el título, o que sean combos/surtidos multi-marca, se excluyen (mismo criterio que PedidosYa).
