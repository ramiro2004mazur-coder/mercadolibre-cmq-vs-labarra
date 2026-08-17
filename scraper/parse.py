"""Parseo de marca / calibre (presentacion) / segmento a partir del titulo de un producto ML."""
import re

from config import MARCAS, SEGMENTOS, KEYWORD_CERVEZA, EXCLUIR_KEYWORDS

_VOL_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s?(ml|cc|l)\b", re.IGNORECASE)
_PACK_RE = re.compile(r"pack\s?(?:de\s?)?[xX]?\s?(\d+)\b|[xX]\s?(\d+)\b")
_FORMATOS = [
    ("Lata", ["lata"]),
    ("Porrón", ["porron", "porrón"]),
    ("Botella", ["botella"]),
    ("Barril", ["barril"]),
]


def es_cerveza(titulo: str) -> bool:
    t = titulo.lower()
    if KEYWORD_CERVEZA not in t:
        return False
    if any(k in t for k in EXCLUIR_KEYWORDS):
        return False
    return True


def detectar_marca(titulo: str) -> str | None:
    t = titulo.lower()
    for marca in MARCAS:
        if marca.lower() in t:
            return marca
    return None


def detectar_segmento(titulo: str) -> str:
    t = titulo.lower()
    for nombre, keywords in SEGMENTOS:
        if any(k in t for k in keywords):
            return nombre
    return "Cerveza"


def detectar_calibre(titulo: str) -> str:
    t = titulo.lower()
    partes = []

    vol = _VOL_RE.search(t)
    if vol:
        cantidad, unidad = vol.groups()
        partes.append(f"{cantidad}{unidad.lower()}")

    pack = _PACK_RE.search(t)
    if pack:
        cantidad_pack = pack.group(1) or pack.group(2)
        partes.append(f"x{cantidad_pack}")

    formato = None
    for nombre, keywords in _FORMATOS:
        if any(k in t for k in keywords):
            formato = nombre
            break
    if formato:
        partes.append(formato)

    return " ".join(partes) if partes else "Sin especificar"


def parse_producto(titulo: str) -> dict:
    marca = detectar_marca(titulo)
    return {
        "marca": marca or "Otra",
        "grupo": marca or "Otros",
        "calibre": detectar_calibre(titulo),
        "segmento": detectar_segmento(titulo),
    }
