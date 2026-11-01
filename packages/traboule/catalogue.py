"""Catalogue des tables DuckDB (conventions §3, règles 5 et 6) : source unique.

Chaque table déclare son niveau géographique, son millésime, ses sources (`source_id` du
registre) et la commande qui la produit ; chaque colonne a une description. La base
(`traboule.ingestion.database`) en tire ses commentaires `COMMENT ON`, et la documentation
`docs/architecture/donnees.md` en est générée (`scripts/generate_data_doc.py`).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    description: str


@dataclass(frozen=True)
class Table:
    name: str
    description: str
    niveau: str
    millesime: str
    sources: tuple[str, ...]
    produite_par: str
    columns: tuple[Column, ...]
    exemple_sql: str
    avertissement: str = ""


def _cols(*pairs: tuple[str, str]) -> tuple[Column, ...]:
    return tuple(Column(n, d) for n, d in pairs)


STATUT_P = (
    "Contient des établissements en statut P : aucune vue exposée au routeur ne renvoie de ligne "
    "individuelle en statut P (règle à appliquer aux vues en liste blanche, semaines 4–5)."
)

TABLES: tuple[Table, ...] = (
    Table(
        name="communes",
        description="Communes de la Métropole de Lyon au COG 2026 (EPCI 200046977).",
        niveau="commune",
        millesime="COG 2026",
        sources=("SRC-004a", "SRC-004b"),
        produite_par="uv run python -m traboule.geo.referentiel",
        columns=_cols(
            ("code_commune", "Code commune INSEE (COG 2026) ; Lyon = 69123"),
            ("libelle", "Nom de la commune (COG 2026)"),
            ("epci", "Code SIREN de l'EPCI d'appartenance"),
            ("cog_millesime", "Millésime du code officiel géographique"),
            ("niveau", "Niveau géographique de la ligne (commune)"),
        ),
        exemple_sql="select code_commune, libelle from communes order by code_commune limit 5",
    ),
    Table(
        name="arrondissements",
        description=(
            "Arrondissements municipaux de Lyon au COG 2026 : subdivisions de Lyon, jamais des "
            "communes supplémentaires (règle 5)."
        ),
        niveau="arrondissement municipal",
        millesime="COG 2026",
        sources=("SRC-004a", "SRC-004b"),
        produite_par="uv run python -m traboule.geo.referentiel",
        columns=_cols(
            ("code_arrondissement", "Code INSEE de l'arrondissement (69381 à 69389)"),
            ("libelle", "Nom de l'arrondissement (COG 2026)"),
            ("code_commune_parent", "Code de la commune parente (69123, Lyon)"),
            ("cog_millesime", "Millésime du code officiel géographique"),
            ("niveau", "Niveau géographique de la ligne (arrondissement municipal)"),
        ),
        exemple_sql="select code_arrondissement, libelle from arrondissements order by 1",
    ),
    Table(
        name="passage_communes",
        description=(
            "Passage des codes géographiques du stock Sirene (communes historiques et "
            "arrondissements) vers le COG 2026."
        ),
        niveau="correspondance de codes (commune ou arrondissement → COG 2026)",
        millesime="codes de 2003 à 2026 → COG 2026",
        sources=("SRC-004a", "SRC-004c"),
        produite_par="uv run python -m traboule.geo.referentiel",
        columns=_cols(
            ("code_source", "Code tel qu'il figure dans la source (commune ou arrondissement)"),
            ("niveau_source", "Niveau du code source : commune ou arrondissement_municipal"),
            ("code_cog_2026", "Code commune au COG 2026"),
            ("code_arrondissement_2026", "Code d'arrondissement au COG 2026 (Lyon seulement)"),
            ("date_effet", "Date d'effet du mouvement de commune (codes historiques)"),
            ("type_mouvement", "Code du type de mouvement INSEE (ex. 32 : commune nouvelle)"),
            ("source", "Fichiers INSEE à l'origine de la ligne"),
        ),
        exemple_sql=(
            "select code_source, code_cog_2026, date_effet from passage_communes "
            "where code_source <> code_cog_2026 and niveau_source = 'commune'"
        ),
    ),
    Table(
        name="etablissements",
        description=(
            "Établissements Sirene rattachés à la Métropole : stock filtré, géolocalisation "
            "INSEE en EPSG:2154. Aucune adresse. Un statut P n'a aucune position (règle 10)."
        ),
        niveau="établissement",
        millesime=(
            "stock Sirene du 2026-10-01 ; géolocalisation d'octobre 2026 ; communes au COG 2026"
        ),
        sources=("SRC-001a", "SRC-001b", "SRC-004a", "SRC-004c"),
        produite_par="uv run python -m traboule.ingestion.sirene",
        avertissement=STATUT_P,
        columns=_cols(
            ("siret", "Identifiant de l'établissement (SIRET, 14 chiffres)"),
            ("siren", "Identifiant de l'unité légale (SIREN)"),
            ("nic", "Numéro interne de classement de l'établissement"),
            ("etablissementSiege", "Vrai si l'établissement est le siège de l'unité légale"),
            (
                "statutDiffusionEtablissement",
                "Statut de diffusion : O (diffusible) ou P (partielle)",
            ),
            ("etatAdministratifEtablissement", "État administratif : A (actif) ou F (fermé)"),
            ("dateCreationEtablissement", "Date de création de l'établissement"),
            ("dateDebut", "Date de début de la période en cours"),
            ("dateDernierTraitementEtablissement", "Date du dernier traitement dans Sirene"),
            ("activitePrincipaleEtablissement", "Activité principale, code NAF rév. 2"),
            ("nomenclatureActivitePrincipaleEtablissement", "Nomenclature de l'activité (NAFRev2)"),
            ("activitePrincipaleNAF25Etablissement", "Activité principale, code NAF 2025"),
            ("trancheEffectifsEtablissement", "Tranche d'effectif salarié (code INSEE)"),
            ("caractereEmployeurEtablissement", "Caractère employeur (O / N)"),
            ("codeCommuneEtablissement", "Code commune tel qu'il figure dans le stock"),
            (
                "coordonneeLambertAbscisseEtablissement",
                "Abscisse Lambert 93 du stock (texte), nulle en statut P",
            ),
            (
                "coordonneeLambertOrdonneeEtablissement",
                "Ordonnée Lambert 93 du stock (texte), nulle en statut P",
            ),
            ("code_commune_cog2026", "Code commune au COG 2026 (Lyon = 69123)"),
            ("code_arrondissement", "Code d'arrondissement de Lyon (69381 à 69389), sinon nul"),
            ("x", "Abscisse EPSG:2154 de la géolocalisation INSEE, nulle en statut P"),
            ("y", "Ordonnée EPSG:2154 de la géolocalisation INSEE, nulle en statut P"),
            ("qualite_xy", "Qualité de géolocalisation (11, 12, 21, 22, 33), nulle en statut P"),
            ("plg_code_commune", "Code commune de la géolocalisation (géographie 2024)"),
            ("plg_iris", "Code IRIS de la géolocalisation (géographie 2024)"),
            ("distance_precision", "Précision de la géolocalisation indiquée par l'INSEE"),
            ("geoloc_present", "Fait brut : présent dans le fichier de géolocalisation"),
            ("position_publique", "Géolocalisé et en statut O : seul cas où une position existe"),
        ),
        exemple_sql=(
            "select code_commune_cog2026, count(*) as actifs from etablissements "
            "where etatAdministratifEtablissement = 'A' group by 1 order by 2 desc limit 5"
        ),
    ),
    Table(
        name="etablissements_zones",
        description=(
            "Rattachement de chaque établissement à position publique à sa zone du PLU-H, avec "
            "l'indice de confiance de l'ADR-0006. Analyse de localisation, pas constat "
            "réglementaire."
        ),
        niveau="établissement × zone du PLU-H",
        millesime="stock Sirene du 2026-10-01 × zonage téléchargé le 2026-10-28",
        sources=("SRC-001a", "SRC-001b", "SRC-002"),
        produite_par="uv run python -m traboule.geo.jointure",
        columns=_cols(
            ("siret", "Identifiant de l'établissement (SIRET)"),
            ("etat", "État administratif : A (actif) ou F (fermé)"),
            ("diffusion", "Statut de diffusion (toujours O : les statuts P sont exclus)"),
            ("code_commune_cog2026", "Code commune au COG 2026"),
            ("code_arrondissement", "Code d'arrondissement de Lyon, sinon nul"),
            ("qualite_xy", "Qualité de géolocalisation INSEE"),
            ("categorie", "une_zone, multi_zones, aucune_zone ou secteur_sauvegarde"),
            ("zone", "Code de zone du PLU-H contenant le point (nul si aucune ou plusieurs)"),
            ("famille", "Famille de zone (préfixe en majuscules du code)"),
            ("zone_stock", "Zone contenant le point des coordonnées du stock (sensibilité)"),
            ("ecart_sources_m", "Distance en mètres entre géolocalisation et stock"),
            ("dist_autre_zone_m", "Distance au polygone d'une autre zone (nul : au-delà de 200 m)"),
            ("confiance", "Indice de confiance de zone : haute, moyenne ou faible (ADR-0006)"),
        ),
        exemple_sql=(
            "select zone, confiance, count(*) from etablissements_zones "
            "where etat = 'A' and zone = 'UEi2' group by all order by 2"
        ),
    ),
    Table(
        name="zonage",
        description=(
            "Objets du zonage du PLU-H (géométries EPSG:2154). Les attributs chiffrés peuvent "
            "filtrer ou compter, jamais tenir lieu de règle (conventions §6)."
        ),
        niveau="objet de zonage du PLU-H",
        millesime="zonage téléchargé le 2026-10-28 (version opposable 200046977_PLUi_20260326)",
        sources=("SRC-002",),
        produite_par="uv run python -m traboule.ingestion.database",
        columns=_cols(
            ("zid", "Identifiant de l'objet dans le fichier source (OGC_FID)"),
            ("code", "Code de zone (zonage, ou SECTSAUV pour le secteur sauvegardé)"),
            ("kind", "plu ou secteur_sauvegarde"),
            ("famille", "Famille de zone (préfixe en majuscules du code)"),
            ("stecal", "Numéro de STECAL de l'objet (A2s, N2s), sinon nul"),
            ("plafond", "Attribut plafond de l'objet (texte source)"),
            ("ces", "Coefficient d'emprise au sol porté par l'objet (texte source)"),
            ("ces_bande_principale", "CES en bande principale (texte source)"),
            ("ces_bande_secondaire", "CES en bande secondaire (texte source)"),
            ("cpt", "Coefficient de pleine terre porté par l'objet (texte source)"),
            ("cpt_bande_principale", "CPT en bande principale (texte source)"),
            ("cpt_bande_secondaire", "CPT en bande secondaire (texte source)"),
            ("hauteur_bande_principale", "Hauteur en bande principale (texte source)"),
            ("hauteur_bande_secondaire", "Hauteur en bande secondaire (texte source)"),
            ("last_update", "Date de mise à jour de l'objet indiquée par la source"),
            ("geom", "Géométrie de l'objet, EPSG:2154"),
        ),
        exemple_sql=(
            "select code, count(*) as objets, round(sum(ST_Area(geom)) / 1e4, 1) as ha "
            "from zonage group by 1 order by 3 desc limit 5"
        ),
    ),
    Table(
        name="unites",
        description=(
            "Périmètre du minorant des comptages par zone : communes hors Lyon, et les 9 "
            "arrondissements de Lyon à la place de la commune 69123 (règle 7)."
        ),
        niveau="unité du minorant (commune hors Lyon ou arrondissement de Lyon)",
        millesime=(
            "communes 2024 (référentiel adr_voie_lieu, 58 communes) ; arrondissements "
            "téléchargés le 2026-11-01"
        ),
        sources=("REF-COMMUNES-ML-2024", "REF-ARRONDISSEMENTS-LYON"),
        produite_par="uv run python -m traboule.ingestion.database",
        columns=_cols(
            ("code", "Code commune (COG 2026) ou code d'arrondissement de Lyon"),
            ("niveau", "commune ou arrondissement_municipal"),
            ("geom", "Contour de l'unité, EPSG:2154"),
        ),
        exemple_sql="select niveau, count(*) from unites group by 1",
    ),
    Table(
        name="zones_reglement",
        description=(
            "Correspondance code de zone → chapitre du règlement écrit, avec la citation de "
            "chaque rattachement (configs/zones_reglement.csv)."
        ),
        niveau="code de zone du PLU-H",
        millesime=(
            "règlement « Modification n° 4 – Approbation 2024 » (document GPU "
            "200046977_PLUi_20260326) ; zonage téléchargé le 2026-10-28"
        ),
        sources=("SRC-005", "SRC-002"),
        produite_par="uv run python -m traboule.geo.zones_reglement",
        columns=_cols(
            ("code_zone", "Code de zone du zonage SRC-002"),
            (
                "methode",
                "Règle de rattachement (exact, suffixe, stecal, au_reference, libelong_gpu…)",
            ),
            ("document", "Document qui porte les règles applicables"),
            ("chapitre", "Chapitre du règlement (zone mère), vide si aucun"),
            ("page_chapitre", "Page PDF de début du chapitre"),
            ("secteur", "Code de secteur dont les dispositions propres sont à vérifier"),
            ("dispositions_secteur", "oui si le secteur est cité dans le chapitre applicable"),
            ("pages_dispositions_secteur", "Pages PDF où le secteur est cité"),
            ("numeros_stecal", "Numéros de STECAL présents dans le zonage pour ce code"),
            (
                "alias_statut",
                "Statut de l'alias du secteur (probable, confirmé) : une disposition propre "
                "au secteur est signalée « correspondance de code probable » tant qu'il n'est "
                "pas confirmé",
            ),
            ("zone_u_reference", "Zone U de référence d'une zone AU (sigle après AU)"),
            ("chapitre_u", "Chapitre de la zone U de référence"),
            ("page_chapitre_u", "Page PDF de début du chapitre U"),
            ("citation", "Extrait exact du règlement qui justifie le rattachement"),
            ("source_citation", "Origine de la citation : §0.2, chapitre, titre, page dédiée"),
            ("citation_page_pdf", "Page PDF de la citation"),
            ("preuve", "Preuve externe du rattachement (réponse du GPU), le cas échéant"),
            ("version_piece", "Version de la pièce lue dans son en-tête"),
            ("version_gpu", "Identifiant de la version du document au GPU"),
            ("abstention_motif", "Signal d'abstention de l'ADR-0010, si le texte n'est pas ingéré"),
        ),
        exemple_sql=("select methode, count(*) from zones_reglement group by 1 order by 2 desc"),
    ),
)

META_TABLES: tuple[Table, ...] = (
    Table(
        name="_catalogue",
        description="Catalogue des tables de la base : niveau, millésime, sources, lignes.",
        niveau="table",
        millesime="date de construction de la base",
        sources=(),
        produite_par="uv run python -m traboule.ingestion.database",
        columns=_cols(
            ("nom", "Nom de la table"),
            ("description", "Rôle de la table"),
            ("niveau", "Niveau géographique"),
            ("millesime", "Millésime des données"),
            ("sources", "Identifiants des sources (registre)"),
            ("produite_par", "Commande qui produit la table ou son entrée"),
            ("avertissement", "Règle d'usage à respecter, le cas échéant"),
            ("lignes", "Nombre de lignes"),
            ("construite_le", "Date et heure de construction (UTC)"),
        ),
        exemple_sql="select nom, niveau, millesime, lignes from _catalogue order by nom",
    ),
    Table(
        name="_sources",
        description="Ressources téléchargées et leur empreinte, lues dans les manifestes.",
        niveau="ressource téléchargée",
        millesime="date de téléchargement de chaque ressource",
        sources=(),
        produite_par="uv run python -m traboule.ingestion.database",
        columns=_cols(
            ("source_id", "Identifiant de la source (registre)"),
            ("ressource", "Dossier de la ressource : <date>/<nom>"),
            ("source_url", "URL de téléchargement"),
            ("sha256", "Empreinte sha256 du fichier"),
            ("retrieved_at", "Date et heure du téléchargement (UTC)"),
            ("licence", "Licence consignée dans le manifeste"),
        ),
        exemple_sql="select source_id, ressource, left(sha256, 8) from _sources order by 1, 2",
    ),
)


def table(name: str) -> Table:
    """Entrée du catalogue pour `name`."""
    return next(t for t in TABLES + META_TABLES if t.name == name)
