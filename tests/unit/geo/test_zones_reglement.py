"""Correspondance code de zone → chapitre du règlement : une branche par règle."""

import pytest

from traboule.config import RAW_DIR, ROOT
from traboule.geo import zones_reglement as zr

V = "PLU-H – MODIFICATION N° 4 – APPROBATION 2024"
PAGES = {
    1: "SOMMAIRE 0.1 - Champ d’application du PLU-H 0.2 - Nomenclature des zones et des secteurs "
    "de zones 0.3 - Règles applicables",
    2: f"{V} 0.1 - Champ d’application du PLU-H Le présent PLU-H s’applique sur tout le "
    "territoire, à l’exception de la partie couverte par le plan de sauvegarde et de mise en "
    "valeur (PSMV) du vieux Lyon. Suite.",
    3: f"{V} 0.2 - Nomenclature des zones et des secteurs de zones La zone comprend les secteurs "
    "UCe1a et UCe1b. Cette zone correspond à des tissus anciens très denses. Les STECAL "
    "concernent des activités spécifiques (A2s1, A2s2, etc.) régies "
    "par la partie III du règlement.",
    4: f"{V} 0.3 - Règles applicables aux destinations",
    10: f"{V} Zone UCe1 Centre ancien CARACTÈRE DE LA ZONE Cette zone correspond à des tissus "
    "anciens très denses. Le secteur UCe1a a une bande.",
    11: f"{V} Zone UCe1 suite du chapitre.",
    20: f"{V} Zone UPp Zone de paysage CARACTÈRE DE LA ZONE La zone comprend un secteur UPpa de "
    "protection forte.",
    30: f"{V} Zone AUs.co Zone à urbaniser CARACTÈRE DE LA ZONE Dès lors que les conditions "
    "d’ouverture à l’urbanisation sont réunies, le règlement de la zone U correspondante "
    "s’applique.",
    40: f"{V} Zone AU Zone différée CARACTÈRE DE LA ZONE La zone comprend trois secteurs (AU1 : "
    "mixte ; AU2 : habitat ; AU3 : activité).",
    50: f"{V} Zone A 2 Zone agricole CARACTÈRE DE LA ZONE Texte.",
    60: f"{V} Zone URm1 Zone composite CARACTÈRE DE LA ZONE Le secteur URm1c est particulier.",
    70: "Annexe",
}
TOC = [
    (1, "Partie I", 1),
    (2, "Zone UCe1 ", 10),
    (2, "Zone UPp", 20),
    (2, "Zone AUs.co ", 30),
    (2, "Zone AU ", 40),
    (2, "Zone A 2 ", 50),
    (2, "Zone URm1", 60),
    (1, "Annexe", 70),
]
CHAPS = zr.chapters(TOC, max(PAGES))


def match(code: str) -> zr.Rattachement:
    return zr.match_code(code, CHAPS, PAGES)


def test_chapters_ignore_spaces_and_end_before_next_entry():
    assert CHAPS["A2"] == (50, 59) and CHAPS["UCe1"] == (10, 19) and "AUs.co" in CHAPS


def test_exact_cites_chapter_title_and_label():
    r = match("A2")
    assert (r.methode, r.chapitre, r.citation, r.citation_page_pdf) == (
        "exact",
        "Zone A2",
        "Zone A 2 Zone agricole",
        50,
    )
    assert r.secteur == "" and r.version_piece == "MODIFICATION N° 4 – APPROBATION 2024"
    assert (r.source_citation, r.document, r.abstention_motif) == (
        "titre",
        "règlement écrit, partie II",
        "",
    )


def test_suffix_cites_nomenclature_and_checks_sector_provisions():
    a, b = match("UCe1a"), match("UCe1b")
    assert (a.methode, a.chapitre, a.citation_page_pdf) == ("suffixe", "Zone UCe1", 3)
    assert "UCe1a" in a.citation
    assert (a.secteur, a.dispositions_secteur, a.pages_dispositions_secteur) == (
        "UCe1a",
        "oui",
        "10",
    )
    assert (b.dispositions_secteur, b.pages_dispositions_secteur) == ("non", "")
    assert a.source_citation == "§0.2"


def test_suffix_cited_only_in_chapter():
    pages = PAGES | {3: PAGES[3].replace("UCe1a et ", "")}  # UCe1a absent de la nomenclature
    r = zr.match_code("UCe1a", CHAPS, pages)
    assert (r.methode, r.source_citation, r.citation_page_pdf) == ("suffixe", "chapitre", 10)


def test_stecal_has_no_chapter_and_abstains_on_part_iii():
    r = match("A2s")
    assert (r.methode, r.chapitre, r.page_chapitre, r.secteur) == ("stecal", "", None, "A2s")
    assert (r.document, r.abstention_motif) == ("partie III, non ingérée", "document_non_ingere")
    assert (r.source_citation, r.citation_page_pdf) == ("§0.2", 3)
    assert "A2s1, A2s2" in r.citation


def test_deferred_au():
    r = match("AU2")
    assert (r.methode, r.chapitre, r.secteur, r.citation_page_pdf) == (
        "au_differee",
        "Zone AU",
        "AU2",
        40,
    )


def test_au_reference_points_to_u_zone_with_suffix():
    r = match("AURm1c")
    assert (r.methode, r.chapitre, r.zone_u_reference, r.chapitre_u) == (
        "au_reference",
        "Zone AUs.co",
        "URm1c",
        "Zone URm1",
    )
    assert (r.page_chapitre_u, r.secteur, r.dispositions_secteur) == (60, "URm1c", "oui")
    assert r.citation.startswith("Dès lors que") and r.source_citation == "page dédiée"


def test_named_sector():
    r = match("UPpa")
    assert (r.methode, r.chapitre, r.citation_page_pdf) == ("secteur", "Zone UPp", 20)
    assert "secteur UPpa" in r.citation and r.source_citation == "chapitre"


def test_safeguarded_sector_is_governed_by_another_document():
    r = match("SECTSAUV")
    assert (r.methode, r.chapitre, r.citation_page_pdf) == ("autre_document", "", 2)
    assert r.citation.startswith("Le présent PLU-H") and "(PSMV)" in r.citation
    assert (r.document, r.abstention_motif) == ("PSMV du Vieux-Lyon, non ingéré", "autre_document")


@pytest.mark.parametrize("code", ["UXx9", "A2sk", "UPpz", "AUZz1"])
def test_codes_are_never_guessed(code):
    r = match(code)
    assert (r.methode, r.chapitre, r.citation, r.source_citation) == ("non_rattache", "", "", "")


def test_stecal_numbers_are_listed_only_for_stecal_codes():
    rows = zr.build(["A2s", "UCe1"], TOC, PAGES, {"A2s": ["1", "2", "3"]})
    assert [(r.code_zone, r.numeros_stecal) for r in rows] == [("A2s", "1 2 3"), ("UCe1", "")]
    with pytest.raises(zr.CorrespondanceError, match="UCe1"):
        zr.build(["A2s", "UCe1"], TOC, PAGES, {"UCe1": ["1"]})


def test_build_fails_on_any_unmatched_code():
    with pytest.raises(zr.CorrespondanceError, match="UXx9"):
        zr.build(["UCe1", "UXx9"], TOC, PAGES)
    with pytest.raises(zr.CorrespondanceError, match="UCe3-p"):
        zr.build(["UCe1", "UCe3-p"], TOC, PAGES)


def evidence(
    code="UCe1-x", libelle=None, libelong="Cette zone correspond a des tissus anciens tres denses"
):
    zone = {"libelle": libelle or code, "libelong": libelong, "typezone": "U",
            "idurba": zr.VERSION_GPU.upper(), "partition": "DU_200046977", "datvalid": "20260326",
            "nomfic": "200046977_reglement_20260326.pdf"}  # fmt: skip
    record = {"code_zonage": code, "chapitre_candidat": "UCe1", "requete_le": "2026-11-01T10:00",
              "fichier": f"configs/preuves_gpu/{code}.json",
              "points": [{"lon": 4.8, "lat": 45.7, "zones": [zone]}] * 3}  # fmt: skip
    return {code: record}


ALIAS = {"UCe1-x": {"code_zonage": "UCe1-x", "code_reglement": "UCe1a", "statut": "probable"}}


def test_gpu_long_label_proves_the_parent_zone():
    r = zr.match_code("UCe1-x", CHAPS, PAGES, evidence())
    assert (r.methode, r.chapitre, r.citation_page_pdf, r.source_citation) == (
        "libelong_gpu", "Zone UCe1", 3, "§0.2")  # fmt: skip
    assert "tissus anciens très denses" in r.citation
    assert "API Carto GPU zone-urba, 2026-11-01 : 3 points" in r.preuve
    assert (r.secteur, r.alias_statut) == ("", "")  # sans alias, aucun secteur rapproché


def test_alias_table_gives_the_sector_with_its_status():
    r = zr.match_code("UCe1-x", CHAPS, PAGES, evidence(), ALIAS)
    assert (r.secteur, r.dispositions_secteur, r.pages_dispositions_secteur, r.alias_statut) == (
        "UCe1a", "oui", "10", "probable")  # fmt: skip


@pytest.mark.parametrize("code", ["UCe1-y", "UCe1y", "UCe1-a"])
def test_code_absent_from_alias_table_is_never_matched(code):
    assert zr.match_code(code, CHAPS, PAGES, evidence(), ALIAS).methode == "non_rattache"


def test_inconsistent_gpu_evidence_is_rejected():
    with pytest.raises(zr.CorrespondanceError, match="autre libellé"):
        zr.match_code("UCe1-x", CHAPS, PAGES, evidence(libelle="UCe1"))
    absent = evidence(libelong="texte absent du règlement")
    assert zr.match_code("UCe1-x", CHAPS, PAGES, absent).methode == "non_rattache"


def test_alias_must_be_applied_and_meaningful():
    with pytest.raises(zr.CorrespondanceError, match="non appliqués"):
        zr.build(["UCe1"], TOC, PAGES, aliases=ALIAS)
    with pytest.raises(zr.CorrespondanceError, match="figure dans le règlement"):
        pages = PAGES | {11: PAGES[11] + " UCe1-x"}
        zr.match_code("UCe1-x", CHAPS, pages, evidence(), ALIAS)


def test_alias_status_is_closed(tmp_path):
    path = tmp_path / "alias.csv"
    path.write_text("code_zonage,code_reglement,statut,preuve\nUCe1-x,UCe1a,certain,p\n")
    with pytest.raises(zr.CorrespondanceError, match="statut"):
        zr.load_aliases(path)


def test_query_gpu_keeps_the_documented_fields():
    import httpx

    feature = {"properties": {"libelle": "UCe3-p", "libelong": "Tissus", "idurba": "X", "autre": 1}}
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"features": [feature]})))  # fmt: skip
    (point,) = zr.query_gpu(client, [{"ogc_fid": 1, "lon": 4.8, "lat": 45.7}])
    assert point["zones"][0]["libelle"] == "UCe3-p" and "autre" not in point["zones"][0]
    assert set(point["zones"][0]) == set(zr.GPU_FIELDS)


REGLEMENT = RAW_DIR / zr.REGLEMENT
ZONAGE = RAW_DIR / zr.ZONAGE


@pytest.mark.skipif(not (REGLEMENT.exists() and ZONAGE.exists()), reason="données brutes absentes")
def test_real_reglement_matches_versioned_csv():
    pytest.importorskip("pymupdf")
    toc, pages = zr.read_reglement(REGLEMENT)
    assert len(zr.chapters(toc, max(pages))) == zr.EXPECTED_CHAPTERS
    rows = zr.build(
        zr.zone_codes(ZONAGE),
        toc,
        pages,
        zr.stecal_numbers(ZONAGE),
        zr.load_evidence(),
        zr.load_aliases(),
    )
    assert len(rows) == 93
    assert not [r.code_zone for r in rows if r.methode == "non_rattache"]
    ucep = next(r for r in rows if r.code_zone == "UCe3-p")
    assert (ucep.methode, ucep.chapitre, ucep.secteur, ucep.alias_statut) == (
        "libelong_gpu", "Zone UCe3", "UCe3p", "probable")  # fmt: skip
    assert zr.to_csv(rows) == (ROOT / "configs" / "zones_reglement.csv").read_text(encoding="utf-8")
