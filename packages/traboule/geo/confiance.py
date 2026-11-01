"""Indice de confiance de zone (ADR-0006).

- faible : qualité `12`, `22`, `33` (position aléatoire) ou inconnue ; distance au polygone
  d'une autre zone < 10 m ; zones différentes selon la source (géolocalisation / stock) ;
- haute : qualité `11` seulement, distance ≥ 25 m, même zone avec les deux sources ;
- moyenne sinon, notamment qualité `21` (« moyenne au mieux ») et coordonnées du stock
  absentes (accord non vérifiable, « moyenne au mieux »).

La règle est écrite une fois en Python (`confiance`) et traduite en SQL (`confiance_sql`) ;
un test vérifie qu'elles concordent. Une distance absente vaut « au-delà du rayon de
recherche » (aucune autre zone dans le rayon).
"""

from traboule.config import FAR_LIMIT_M, NEAR_LIMIT_M, SEARCH_RADIUS_M
from traboule.contracts.zone import Confiance

RANDOM_POSITION = ("12", "22", "33")


def confiance(
    *,
    zone: str | None,
    qualite_xy: str | None,
    dist_autre_zone_m: float | None,
    stock_present: bool,
    zone_stock: str | None,
) -> Confiance | None:
    """Indice de confiance d'un établissement rattaché à `zone` (None si aucune zone)."""
    if zone is None:
        return None
    distance = SEARCH_RADIUS_M if dist_autre_zone_m is None else dist_autre_zone_m
    if (
        qualite_xy is None
        or qualite_xy in RANDOM_POSITION
        or distance < NEAR_LIMIT_M
        or (stock_present and zone_stock != zone)
    ):
        return "faible"
    if qualite_xy == "11" and distance >= FAR_LIMIT_M and stock_present:
        return "haute"
    return "moyenne"


def confiance_sql(
    zone: str = "zone",
    qualite_xy: str = "qualite_xy",
    dist_autre_zone_m: str = "dist_autre_zone_m",
    stock_present: str = "stock_present",
    zone_stock: str = "zone_stock",
) -> str:
    """Expression SQL DuckDB équivalente à `confiance`, sur les colonnes nommées."""
    distance = f"coalesce({dist_autre_zone_m}, {SEARCH_RADIUS_M})"
    random = ", ".join(f"'{q}'" for q in RANDOM_POSITION)
    return f"""case
        when {zone} is null then null
        when {qualite_xy} is null or {qualite_xy} in ({random})
             or {distance} < {NEAR_LIMIT_M}
             or ({stock_present} and {zone_stock} is distinct from {zone}) then 'faible'
        when {qualite_xy} = '11' and {distance} >= {FAR_LIMIT_M} and {stock_present}
             then 'haute'
        else 'moyenne'
    end"""
