"""Test 1 du spike : référentiel géographique et rattachement Sirene à la Métropole de Lyon.

Script jetable. Construit dans data/interim/ :
- ref_communes_ml.parquet, ref_arrondissements_lyon.parquet, passage_communes.parquet ;
- sirene_ml.parquet (stock filtré en streaming DuckDB + géolocalisation epsg 2154).
Écrit toutes les mesures dans spikes/output/test1/metrics.json. Aucun code commune en dur :
seul l'EPCI est lu dans configs/sources.yaml. Les données Sirene ne quittent pas data/interim/.
"""

import json
import platform
import shutil
import sys
import threading
import time
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import duckdb
import httpx
import psutil
import typer
import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
SOURCES_DIR = INTERIM / "sources"
OUTPUT_DIR = ROOT / "spikes" / "output" / "test1"
RAW_DATE = "2026-10-28"
STOCK_DATE = "2026-10-01"
SRC007_DATE = "2026-08-04"

STOCK = RAW / f"SRC-001a/{RAW_DATE}/stock_etablissement/stock-stocketablissement-parquet.parquet"
GEOLOC = (
    RAW / f"SRC-001b/{RAW_DATE}/geolocalisation/"
    "geoloc-geolocalisationetablissement-sirene-pour-etudes-statistiques-parquet.parquet"
)
SRC007 = RAW / f"SRC-007/{RAW_DATE}/sirene_metropole/sirene_metropole.csv"
SRC003 = RAW / f"SRC-003/{RAW_DATE}/catalogue/catalogue.geojson"
SRC002 = RAW / f"SRC-002/{RAW_DATE}/zonage/zonage.geojson"
REF_COMMUNES = RAW / f"REF-COMMUNES-ML-2024/{RAW_DATE}/communes/communes.geojson"
GPU_PIECES = RAW / f"SRC-005/{RAW_DATE}/liste_pieces/liste_pieces.json"
ARCHIVES = {
    "SRC-004a": RAW / f"SRC-004a/{RAW_DATE}/cog_ensemble/cog_ensemble_2026_csv.zip",
    "SRC-004b": RAW
    / f"SRC-004b/{RAW_DATE}/table_appartenance/table-appartenance-geo-communes-2026.zip",
    "SRC-004c": RAW
    / f"SRC-004c/{RAW_DATE}/table_passage_2003_2026/table_passage_geo2003_geo2026.zip",
}
OUTPUTS = ["ref_communes_ml", "ref_arrondissements_lyon", "passage_communes", "sirene_ml"]

app = typer.Typer(add_completion=False, help=__doc__.splitlines()[0])


class CheckError(RuntimeError):
    """Contrôle bloquant non satisfait."""


@contextmanager
def measured(name: str, steps: dict):
    """Chronomètre une étape et échantillonne le pic RSS du processus toutes les 100 ms."""
    proc, peak, stop = psutil.Process(), [0], threading.Event()

    def sample() -> None:
        while not stop.is_set():
            peak[0] = max(peak[0], proc.memory_info().rss)
            stop.wait(0.1)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    start = time.perf_counter()
    try:
        yield
    finally:
        stop.set()
        thread.join()
        peak[0] = max(peak[0], proc.memory_info().rss)
        steps[name] = {
            "seconds": round(time.perf_counter() - start, 2),
            "peak_rss_mb": round(peak[0] / 1e6),
        }
        typer.echo(
            f"  {name} : {steps[name]['seconds']} s, pic RSS {steps[name]['peak_rss_mb']} Mo"
        )


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def scalar(con: duckdb.DuckDBPyConnection, sql: str):
    return con.execute(sql).fetchone()[0]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)
    typer.echo(f"    ✓ {message}")


def xlsx(path: Path, sheet: str, cols: str = "Z") -> str:
    return (
        f"read_xlsx('{path}', sheet='{sheet}', range='A6:{cols}200000', "
        "header=true, all_varchar=true)"
    )


def extract_archives() -> dict[str, Path]:
    extracted = {}
    for source_id, archive in ARCHIVES.items():
        dest = SOURCES_DIR / source_id
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
        extracted[source_id] = dest
    return extracted


def build_references(con, epci: str, src: dict[str, Path]) -> dict:
    cog = src["SRC-004a"] / "v_commune_2026.csv"
    mvt = src["SRC-004a"] / "v_mvt_commune_2026.csv"
    appart = next(src["SRC-004b"].glob("*.xlsx"))
    passage = next(src["SRC-004c"].glob("*.xlsx"))
    con.execute(f"create or replace view cog as select * from read_csv('{cog}', all_varchar=true)")
    con.execute(f"create or replace view mvt as select * from read_csv('{mvt}', all_varchar=true)")

    # Étape 1 — communes de l'EPCI au COG 2026
    con.execute(f"""
        create or replace table ref_communes_ml as
        select a.CODGEO as code_commune, c.LIBELLE as libelle, a.EPCI as epci,
               2026 as cog_millesime, 'commune' as niveau
        from {xlsx(appart, "COM")} a
        join cog c on c.TYPECOM = 'COM' and c.COM = a.CODGEO
        where a.EPCI = '{epci}'
        order by 1""")
    n = scalar(con, "select count(*) from ref_communes_ml")
    check(n == 58, f"{n} communes dans l'EPCI {epci} au COG 2026 (attendu 58)")
    lyon = scalar(con, "select COM from cog where TYPECOM='COM' and NCC='LYON'")
    check(
        scalar(con, f"select count(*) from ref_communes_ml where code_commune='{lyon}'") == 1,
        f"Lyon ({lyon}) présente comme commune",
    )

    # Étape 2 — arrondissements de Lyon
    con.execute(f"""
        create or replace table ref_arrondissements_lyon as
        select c.COM as code_arrondissement, c.LIBELLE as libelle,
               c.COMPARENT as code_commune_parent, 2026 as cog_millesime,
               'arrondissement_municipal' as niveau
        from cog c where c.TYPECOM = 'ARM' and c.COMPARENT = '{lyon}' order by 1""")
    n_arm = scalar(con, "select count(*) from ref_arrondissements_lyon")
    check(n_arm == 9, f"{n_arm} arrondissements municipaux de Lyon (attendu 9)")
    arm_appart = scalar(
        con,
        f"""select count(*) from {xlsx(appart, "ARM")} a
            join ref_arrondissements_lyon r on r.code_arrondissement = a.CODGEO
            where a.COM = '{lyon}' and a.EPCI = '{epci}'""",
    )
    check(arm_appart == 9, "les 9 arrondissements concordent avec l'onglet ARM (EPCI, parent)")

    # Étape 3 — passage des codes historiques vers le COG 2026
    con.execute(f"""
        create or replace table passage_communes as
        with p as (
            select CODGEO_INI as code_source, CODGEO_2026 as code_cog_2026
            from {xlsx(passage, "Table de passage", "C")}
            where CODGEO_2026 in (select code_commune from ref_communes_ml)
        ),
        m as (
            select COM_AV, COM_AP, min(DATE_EFF) as date_effet, string_agg(distinct MOD, ',') as mod
            from mvt where TYPECOM_AV = 'COM' and TYPECOM_AP = 'COM'
            group by all
        )
        select p.code_source, 'commune' as niveau_source, p.code_cog_2026,
               null::varchar as code_arrondissement_2026,
               m.date_effet, m.mod as type_mouvement, 'SRC-004c + v_mvt_commune_2026' as source
        from p left join m on m.COM_AV = p.code_source and m.COM_AP = p.code_cog_2026
                          and p.code_source <> p.code_cog_2026
        union all
        select code_arrondissement, 'arrondissement_municipal', code_commune_parent,
               code_arrondissement, null, null, 'SRC-004a (ARM)'
        from ref_arrondissements_lyon
        order by 1""")
    ambiguous = rows(
        con,
        """select code_source, list(distinct code_cog_2026) cibles from passage_communes
           group by 1 having count(distinct code_cog_2026) > 1""",
    )
    check(not ambiguous, f"aucun code source ambigu ({ambiguous})")
    historical = rows(
        con,
        """select code_source, code_cog_2026, date_effet, type_mouvement from passage_communes
           where niveau_source='commune' and code_source <> code_cog_2026""",
    )
    check(
        all(r["date_effet"] for r in historical),
        f"date d'effet lue pour les {len(historical)} code(s) historique(s)",
    )

    ref_layer = json.loads(REF_COMMUNES.read_text())
    ref_props = [f["properties"] for f in ref_layer["features"]]
    return {
        "lyon_code": lyon,
        "communes_count": n,
        "arrondissements_count": n_arm,
        "historical_codes": historical,
        "passage_rows": scalar(con, "select count(*) from passage_communes"),
        "ref_communes_ml_2024_properties_sample": ref_props[0] if ref_props else None,
        "ref_communes_ml_2024_count": len(ref_props),
    }


def compare_ref_communes(con, props_key: str | None) -> dict:
    """Compare les 58 codes COG avec la couche REF-COMMUNES-ML-2024 (champ code détecté)."""
    layer = json.loads(REF_COMMUNES.read_text())
    codes_cog = {r[0] for r in con.execute("select code_commune from ref_communes_ml").fetchall()}
    props = layer["features"][0]["properties"]
    key = props_key or next(
        (k for k, v in props.items() if isinstance(v, str) and v in codes_cog), None
    )
    if key is None:
        return {"field": None, "note": "aucun champ de code INSEE reconnu dans la couche"}
    codes_ref = {f["properties"][key] for f in layer["features"]}
    return {
        "field": key,
        "only_in_cog": sorted(codes_cog - codes_ref),
        "only_in_ref_layer": sorted(codes_ref - codes_cog),
    }


def build_sirene(con) -> dict:
    con.execute(f"""
        copy (
            with g as (
                select siret, x, y, qualite_xy, plg_code_commune, plg_iris, distance_precision
                from read_parquet('{GEOLOC}') where epsg = '2154'
            )
            select s.siret, s.siren, s.nic, s.etablissementSiege, s.statutDiffusionEtablissement,
                   s.etatAdministratifEtablissement, s.dateCreationEtablissement, s.dateDebut,
                   s.dateDernierTraitementEtablissement, s.activitePrincipaleEtablissement,
                   s.nomenclatureActivitePrincipaleEtablissement,
                   s.activitePrincipaleNAF25Etablissement, s.trancheEffectifsEtablissement,
                   s.caractereEmployeurEtablissement, s.codeCommuneEtablissement,
                   s.coordonneeLambertAbscisseEtablissement,
                   s.coordonneeLambertOrdonneeEtablissement,
                   p.code_cog_2026 as code_commune_cog2026,
                   p.code_arrondissement_2026 as code_arrondissement,
                   g.x, g.y, g.qualite_xy, g.plg_code_commune, g.plg_iris, g.distance_precision,
                   g.siret is not null as geoloc_present
            from read_parquet('{STOCK}') s
            join passage_communes p on p.code_source = s.codeCommuneEtablissement
            left join g using (siret)
        ) to '{INTERIM / "sirene_ml.parquet"}' (format parquet, compression zstd)""")
    con.execute(
        "create or replace view sirene_ml as "
        f"select * from read_parquet('{INTERIM / 'sirene_ml.parquet'}')"
    )
    n = scalar(con, "select count(*) from sirene_ml")
    check(
        scalar(con, "select count(*) from sirene_ml where code_commune_cog2026 is null") == 0,
        f"{n:,} établissements, tous rattachés à une commune COG 2026",
    )
    check(
        scalar(con, "select count(*) - count(distinct siret) from sirene_ml") == 0,
        "aucun SIRET en double",
    )
    return {"rows": n}


def measures(con, lyon: str) -> dict:
    m: dict = {}
    ml_codes = "(select code_source from passage_communes)"
    m["etat_par_commune"] = rows(
        con,
        """select r.code_commune, r.libelle,
              count(*) filter (where s.etatAdministratifEtablissement='A') actifs,
              count(*) filter (where s.etatAdministratifEtablissement='F') fermes,
              count(s.siret) total
           from ref_communes_ml r left join sirene_ml s on s.code_commune_cog2026 = r.code_commune
           group by all order by 1""",
    )
    m["etat_par_arrondissement"] = rows(
        con,
        """select r.code_arrondissement, r.libelle,
              count(*) filter (where s.etatAdministratifEtablissement='A') actifs,
              count(*) filter (where s.etatAdministratifEtablissement='F') fermes,
              count(s.siret) total
           from ref_arrondissements_lyon r
           left join sirene_ml s on s.code_arrondissement = r.code_arrondissement
           group by all order by 1""",
    )
    m["totaux"] = rows(
        con,
        """select count(*) total,
              count(*) filter (where etatAdministratifEtablissement='A') actifs,
              count(*) filter (where etatAdministratifEtablissement='F') fermes
           from sirene_ml""",
    )[0]
    m["niveau_lyon_dans_stock"] = rows(
        con,
        f"""select case when codeCommuneEtablissement = '{lyon}' then 'commune {lyon}'
                        else 'arrondissement' end niveau, count(*) n
            from sirene_ml where code_commune_cog2026 = '{lyon}' group by 1 order by 1""",
    )
    m["codes_historiques_et_lyon_commune"] = rows(
        con,
        f"""select codeCommuneEtablissement code, etatAdministratifEtablissement etat,
               year(dateDernierTraitementEtablissement) annee_dernier_traitement,
               count(*) n
            from sirene_ml
            where codeCommuneEtablissement = '{lyon}'
               or codeCommuneEtablissement in (
                   select code_source from passage_communes
                   where niveau_source='commune' and code_source <> code_cog_2026)
            group by all order by 1, 2, 3""",
    )
    m["jointure_geoloc"] = rows(
        con,
        """select etatAdministratifEtablissement etat, statutDiffusionEtablissement diffusion,
              count(*) n, count(*) filter (where geoloc_present) geoloc,
              round(100.0 * count(*) filter (where geoloc_present) / count(*), 2) pct
           from sirene_ml group by all order by 1, 2""",
    )
    m["actifs_sans_coordonnees_par_diffusion"] = rows(
        con,
        """select statutDiffusionEtablissement diffusion, count(*) actifs,
              count(*) filter (where not geoloc_present) sans_geoloc,
              round(100.0 * count(*) filter (where not geoloc_present) / count(*), 2) pct
           from sirene_ml where etatAdministratifEtablissement='A' group by 1 order by 1""",
    )
    m["qualite_xy"] = rows(
        con,
        """select qualite_xy, count(*) n, round(100.0*count(*)/sum(count(*)) over (), 2) pct,
              round(median(distance_precision), 1) distance_precision_mediane
           from sirene_ml where geoloc_present group by 1 order by 2 desc""",
    )
    m["geoloc_hors_2154_dans_perimetre"] = scalar(
        con,
        f"""select count(*) from read_parquet('{GEOLOC}')
            where epsg <> '2154' and plg_code_commune in {ml_codes}""",
    )
    # Codes 2024 de la géolocalisation contre le référentiel 2026
    m["plg_code_commune_hors_referentiel"] = rows(
        con,
        f"""select plg_code_commune, count(*) n from sirene_ml
            where geoloc_present and plg_code_commune not in {ml_codes}
            group by 1 order by 2 desc""",
    )
    m["plg_vs_stock_desaccords"] = rows(
        con,
        """select codeCommuneEtablissement code_stock, plg_code_commune code_geoloc,
              etatAdministratifEtablissement etat, count(*) n
           from sirene_ml where geoloc_present and plg_code_commune <> codeCommuneEtablissement
           group by all order by n desc limit 50""",
    )
    m["plg_vs_stock_desaccords_total"] = scalar(
        con,
        """select count(*) from sirene_ml
           where geoloc_present and plg_code_commune <> codeCommuneEtablissement""",
    )
    # Perte dans l'autre sens : géolocalisé dans la Métropole, codé ailleurs dans le stock
    m["perte_inverse"] = rows(
        con,
        f"""with g as (
                select siret, plg_code_commune from read_parquet('{GEOLOC}')
                where epsg = '2154' and plg_code_commune in {ml_codes}
            )
            select s.etatAdministratifEtablissement etat,
                   count(*) n,
                   count(*) filter (where s.codeCommuneEtablissement like '69%') dont_rhone
            from g join read_parquet('{STOCK}') s using (siret)
            where s.codeCommuneEtablissement not in {ml_codes}
               or s.codeCommuneEtablissement is null
            group by 1 order by 1""",
    )
    m["perte_inverse_codes_stock"] = rows(
        con,
        f"""with g as (
                select siret, plg_code_commune from read_parquet('{GEOLOC}')
                where epsg = '2154' and plg_code_commune in {ml_codes}
            )
            select s.codeCommuneEtablissement code_stock, g.plg_code_commune code_geoloc,
                   s.etatAdministratifEtablissement etat, count(*) n
            from g join read_parquet('{STOCK}') s using (siret)
            where s.codeCommuneEtablissement not in {ml_codes}
               or s.codeCommuneEtablissement is null
            group by all order by n desc limit 30""",
    )
    m["geoloc_ml_absents_du_stock"] = scalar(
        con,
        f"""select count(*) from read_parquet('{GEOLOC}') g
            anti join read_parquet('{STOCK}') s using (siret)
            where g.epsg = '2154' and g.plg_code_commune in {ml_codes}""",
    )
    # Dates de création hors plage : deux comptages séparés, rien n'est filtré
    m["dates_creation"] = rows(
        con,
        f"""select
              count(*) filter (where d > date '{STOCK_DATE}'
                               and d <= date '{STOCK_DATE}' + interval 1 year)
                  posterieures_moins_1_an,
              count(*) filter (where d > date '{STOCK_DATE}' + interval 1 year)
                  posterieures_plus_1_an,
              count(*) filter (where d < date '1900-01-01') anterieures_1900,
              count(*) filter (where d is null) nulles,
              count(*) total
           from (select dateCreationEtablissement d from sirene_ml)""",
    )[0]
    # Coordonnées stock vs géolocalisation
    con.execute("""
        create or replace temp view coords as
        select siret, x, y, geoloc_present,
               try_cast(coordonneeLambertAbscisseEtablissement as double) sx,
               try_cast(coordonneeLambertOrdonneeEtablissement as double) sy
        from sirene_ml""")
    m["coords_couverture"] = rows(
        con,
        """select geoloc_present, (sx is not null and sy is not null) stock_coords, count(*) n
           from coords group by all order by all""",
    )
    m["coords_ecart_m"] = rows(
        con,
        """with d as (select sqrt((sx - x)^2 + (sy - y)^2) dist from coords
                    where geoloc_present and sx is not null and sy is not null)
           select count(*) n, round(quantile_cont(dist, 0.5), 2) p50,
                  round(quantile_cont(dist, 0.9), 2) p90, round(quantile_cont(dist, 0.99), 2) p99,
                  round(max(dist), 1) max, count(*) filter (where dist > 50) sup_50m,
                  round(100.0 * count(*) filter (where dist > 50) / count(*), 3) pct_sup_50m,
                  count(*) filter (where dist < 1) inf_1m
           from d""",
    )[0]
    return m


def cross_check_src007(con) -> dict:
    con.execute(f"""
        create or replace table src007 as
        select siret, insee, datecreation, datemaj,
               ST_Transform(
                   ST_GeomFromText(the_geom), 'EPSG:4326', 'EPSG:2154', always_xy := true
               ) g
        from read_csv('{SRC007}', all_varchar=true)""")
    r: dict = {"rows": scalar(con, "select count(*) from src007")}
    r["codes_hors_perimetre"] = rows(
        con,
        """select insee, count(*) n from src007
           where insee not in (select code_source from passage_communes) group by 1""",
    )
    r["siret_doublons"] = scalar(con, "select count(*) - count(distinct siret) from src007")
    con.execute("""
        create or replace temp view a1 as
        select siret, codeCommuneEtablissement code, statutDiffusionEtablissement diffusion,
               dateCreationEtablissement, dateDebut, x, y
        from sirene_ml where etatAdministratifEtablissement = 'A' and geoloc_present""")
    r["par_code"] = rows(
        con,
        """with a as (select code, count(*) n1 from a1 group by 1),
                b as (select insee code, count(*) n7 from src007 group by 1)
           select code, coalesce(n1,0) src001_actifs_geoloc, coalesce(n7,0) src007,
                  coalesce(n1,0) - coalesce(n7,0) ecart
           from a full join b using (code) order by code""",
    )
    r["recouvrement"] = rows(
        con,
        """select (a1.siret is not null) dans_src001_actifs_geoloc,
                  (s.siret is not null) dans_src007, count(*) n
           from a1 full join src007 s using (siret) group by all order by all""",
    )
    # Explication des écarts : SRC-007 seul → état dans le stock ; SRC-001 seul → dates
    r["src007_seul_etat_stock"] = rows(
        con,
        f"""select coalesce(st.etatAdministratifEtablissement, 'absent du stock ML') etat,
                  case when st.dateDebut > date '{SRC007_DATE}'
                       then 'changement après {SRC007_DATE}'
                       when st.siret is null then '-' else 'changement avant' end quand,
                  coalesce(st.geoloc_present::varchar, '-') geoloc_src001,
                  coalesce(st.statutDiffusionEtablissement, '-') diffusion, count(*) n
           from src007 s anti join a1 using (siret)
           left join sirene_ml st using (siret)
           group by all order by n desc""",
    )
    r["src001_seul_creation"] = rows(
        con,
        f"""select case when dateCreationEtablissement > date '{SRC007_DATE}'
                       then 'créé après {SRC007_DATE}'
                       when dateDebut > date '{SRC007_DATE}'
                       then 'période ouverte après {SRC007_DATE}'
                       else 'antérieur' end motif,
                  diffusion, count(*) n
           from a1 anti join src007 using (siret) group by all order by n desc""",
    )
    r["ecart_coordonnees_m"] = rows(
        con,
        """with d as (select sqrt((ST_X(s.g) - a1.x)^2 + (ST_Y(s.g) - a1.y)^2) dist
                     from a1 join src007 s using (siret))
           select count(*) n, round(quantile_cont(dist, 0.5), 2) p50,
                  round(quantile_cont(dist, 0.9), 2) p90, round(quantile_cont(dist, 0.99), 2) p99,
                  round(100.0 * count(*) filter (where dist > 50) / count(*), 3) pct_sup_50m
           from d""",
    )[0]
    return r


def vigilance() -> dict:
    v: dict = {}
    catalogue = json.loads(SRC003.read_text())["features"]
    v["src003"] = {
        "objets": len(catalogue),
        "uids": sorted(f["properties"].get("uid") for f in catalogue),
        "last_update_max": max(f["properties"].get("last_update") or "" for f in catalogue),
    }
    pieces = list(json.loads(GPU_PIECES.read_text())["writingMaterials"])
    cahiers = [p for p in pieces if "_cahier_" in p]
    kinds: dict[str, int] = {}
    for p in cahiers:
        kind = p.split("_cahier_")[1].split("_")[0]
        kinds[kind] = kinds.get(kind, 0) + 1
    v["gpu_cahiers"] = {"total": len(cahiers), "par_type": kinds, "noms": sorted(cahiers)}
    zonage = json.loads(SRC002.read_text())["features"]
    v["src002_last_update_max"] = max(f["properties"].get("last_update") or "" for f in zonage)
    v["src002_last_update_fme_max"] = max(
        f["properties"].get("last_update_fme") or "" for f in zonage
    )
    try:
        resp = httpx.get(
            "https://apicarto.ign.fr/api/gpu/document",
            params={"partition": "DU_200046977"},
            timeout=60,
        )
        resp.raise_for_status()
        v["gpu_documents_partition"] = [f["properties"] for f in resp.json().get("features", [])]
    except httpx.HTTPError as exc:
        v["gpu_documents_partition"] = f"échec de la requête : {exc}"
    return v


@app.command()
def main(
    force: Annotated[bool, typer.Option(help="Écraser les Parquet existants")] = False,
) -> None:
    """Construit les référentiels, filtre Sirene et écrit les mesures du Test 1."""
    existing = [n for n in OUTPUTS if (INTERIM / f"{n}.parquet").exists()]
    if existing and not force:
        typer.echo(f"Sorties existantes {existing} : relancer avec --force.", err=True)
        sys.exit(1)
    config = yaml.safe_load((ROOT / "configs" / "sources.yaml").read_text())
    epci = config["metadata"]["territory"]["epci_code"]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (INTERIM / ".duckdb_tmp").mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("set memory_limit = '6GB'")
    con.execute(f"set temp_directory = '{INTERIM / '.duckdb_tmp'}'")
    con.load_extension("excel")
    con.load_extension("spatial")

    steps: dict = {}
    result: dict = {"started_at": datetime.now(UTC).isoformat(), "epci": epci, "steps": steps}
    try:
        with measured("0_extraction", steps):
            src = extract_archives()
        with measured("1-3_referentiels", steps):
            result["referentiels"] = build_references(con, epci, src)
            result["referentiels"]["comparaison_ref_communes_ml_2024"] = compare_ref_communes(
                con, None
            )
            for name in OUTPUTS[:3]:
                con.execute(f"copy {name} to '{INTERIM / name}.parquet' (format parquet)")
        with measured("4_sirene_ml", steps):
            result["sirene_ml"] = build_sirene(con)
        with measured("5_mesures", steps):
            result["mesures"] = measures(con, result["referentiels"]["lyon_code"])
        with measured("5.9_controle_src007", steps):
            result["controle_src007"] = cross_check_src007(con)
        with measured("6_vigilance", steps):
            result["vigilance"] = vigilance()
    except CheckError as exc:
        typer.echo(f"CONTRÔLE BLOQUANT : {exc}", err=True)
        result["erreur"] = str(exc)
        sys.exit(1)
    finally:
        result["environment"] = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "versions": {p: version(p) for p in ("duckdb", "psutil", "httpx", "typer")},
            "sources_sha256": {
                str(p.parent.relative_to(RAW)): json.loads(p.read_text())["sha256"]
                for p in sorted(RAW.glob(f"*/{RAW_DATE}/*/manifest.json"))
            },
        }
        out = OUTPUT_DIR / "metrics.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n")
        typer.echo(f"Mesures : {out}")


if __name__ == "__main__":
    app()
