"""Transforma data/historico.json (append-only) en docs/data.json (formato pivot para el dashboard)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORICO_PATH = ROOT / "data" / "historico.json"
OUT_PATH = ROOT / "docs" / "data.json"

TIENDA_LABEL = {"CMQ": "CMQ", "LA_BARRA": "La Barra"}


def run_sort_key(run_label: str):
    fecha, turno = run_label.rsplit(" ", 1)
    dt = datetime.strptime(fecha, "%Y-%m-%d")
    return (dt, 0 if turno == "AM" else 1)


def construir_pivot(historico: dict) -> list[dict]:
    pivot = []
    for prod in historico["productos"]:
        pivot.append(
            {
                "tienda": prod["tienda"],
                "tienda_label": TIENDA_LABEL.get(prod["tienda"], prod["tienda"]),
                "sku": prod["sku"],
                "titulo": prod.get("titulo", ""),
                "url": prod.get("url", ""),
                "marca": prod["marca"],
                "grupo": prod["grupo"],
                "calibre": prod["calibre"],
                "segmento": prod["segmento"],
                "dates": prod["runs"],
            }
        )
    return pivot


def construir_stats(pivot: list[dict], dates: list[str]) -> list[dict]:
    stats = []
    for row in pivot:
        valores = [row["dates"][d] for d in dates if d in row["dates"]]
        dinamicas = [v["dinamica"] for v in valores if v.get("dinamica") is not None]
        ptcs = [v["ptc"] for v in valores if v.get("ptc") is not None]
        dias_dinamica = sum(1 for v in dinamicas if v and v > 0)
        stats.append(
            {
                "tienda": row["tienda_label"],
                "marca": row["marca"],
                "grupo": row["grupo"],
                "segmento": row["segmento"],
                "calibre": row["calibre"],
                "dias": len(valores),
                "dias_dinamica": dias_dinamica,
                "max_dinamica": max(dinamicas) if dinamicas else 0,
                "avg_dinamica": (sum(dinamicas) / len(dinamicas)) if dinamicas else 0,
                "avg_ptc": (sum(ptcs) / len(ptcs)) if ptcs else 0,
            }
        )
    return stats


def construir_fights() -> list[dict]:
    # Comparacion tienda vs tienda (no marca vs marca): CMQ y La Barra son
    # portfolios de marcas distintos, se comparan por calibre/presentacion.
    return [
        {
            "name": "CMQ vs La Barra",
            "seg": "Todas las marcas de cada tienda, agrupadas por presentacion",
            "cmq": "CMQ",
            "comp": "LA_BARRA",
        }
    ]


def main() -> None:
    if not HISTORICO_PATH.exists():
        raise SystemExit(f"No existe {HISTORICO_PATH}. Corre el scraper primero.")

    historico = json.loads(HISTORICO_PATH.read_text(encoding="utf-8"))
    dates = sorted(historico.get("runs", []), key=run_sort_key)
    pivot = construir_pivot(historico)
    stats = construir_stats(pivot, dates)
    fights = construir_fights()

    tiendas_count = {}
    for row in pivot:
        tiendas_count[row["tienda_label"]] = tiendas_count.get(row["tienda_label"], 0) + 1

    data = {
        "pivot": pivot,
        "dates": dates,
        "stats": stats,
        "fights": fights,
        "meta": {
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_productos": len(pivot),
            "productos_por_tienda": tiendas_count,
            "corridas": len(dates),
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escrito {OUT_PATH}: {len(pivot)} productos, {len(dates)} corridas")


if __name__ == "__main__":
    main()
