"""Configuracion de tiendas y diccionarios de parseo para el scraper de MercadoLibre."""

STORES = {
    "CMQ": {
        "nombre": "Cervecería y Maltería Quilmes",
        "slug": "cerveceria-y-malteria-quilmes",
        "home_url": "https://www.mercadolibre.com.ar/tienda/cerveceria-y-malteria-quilmes",
        "cervezas_url": (
            "https://listado.mercadolibre.com.ar/tienda/cerveceria-y-malteria-quilmes"
            "/listado/alimentos-bebidas/bebidas/cervezas/"
        ),
    },
    "LA_BARRA": {
        "nombre": "La Barra (CCU)",
        "slug": "la-barra",
        "home_url": "https://www.mercadolibre.com.ar/tienda/la-barra",
        "cervezas_url": (
            "https://listado.mercadolibre.com.ar/tienda/la-barra"
            "/listado/alimentos-bebidas/bebidas/cervezas/"
        ),
    },
}

# Orden importa: las marcas mas especificas / mas largas van primero para evitar
# matches parciales (ej. "Andes Origen" antes que "Andes", "Corona Cero" antes que "Corona").
MARCAS = [
    "Andes Origen",
    "Corona Cero",
    "Corona",
    "Stella Artois",
    "Quilmes",
    "Brahma",
    "Patagonia",
    "Michelob",
    "Budweiser",
    "Blue Moon",
    "Imperial",
    "Heineken",
    "Amstel",
    "Schneider",
    "Miller",
    "Santa Fe",
    "Warsteiner",
    "Norte",
]

# Keywords de estilo/segmento, buscadas en el titulo (case-insensitive).
SEGMENTOS = [
    ("Sin Alcohol", ["sin alcohol"]),
    ("IPA", ["ipa"]),
    ("Golden", ["golden"]),
    ("Lager", ["lager"]),
    ("Stout", ["stout", "negra"]),
    ("Roja", ["roja", "red ale"]),
    ("Rubia", ["rubia"]),
    ("Ale", [" ale"]),
    ("Trigo", ["trigo", "weiss", "weizen"]),
    ("Pilsner", ["pilsner", "pilsen"]),
]

# Titulo debe contener alguna de estas palabras para considerarse "cerveza".
KEYWORD_CERVEZA = "cerveza"

# Palabras que indican combos/packs mixtos multi-marca a excluir (mismo criterio que PedidosYa).
EXCLUIR_KEYWORDS = ["combo", "surtido", "mix ", "variado"]
