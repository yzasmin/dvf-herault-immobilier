"""Pipeline DVF Hérault : nettoyage chiffré, modèle en étoile, indicateurs, intervalles de confiance.

Entrées : data/raw/dvf_34_*.csv.gz (voir scripts/telecharger.py).
Sorties :
  results/                  chiffres publiés (CSV et JSON, commités)
  app/data/                 agrégats légers lus par la démo Streamlit (commités)
  data/processed/powerbi/   tables du modèle en étoile, Parquet et CSV (non commitées : données ligne à ligne)

Usage : uv run python scripts/pipeline.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parents[1]
SQL = RACINE / "sql"
RESULTATS = RACINE / "results"
APP_DATA = RACINE / "app" / "data"
POWERBI = RACINE / "data" / "processed" / "powerbi"
# Chemins relatifs à RACINE dans le SQL : le chemin absolu du poste contient une apostrophe.
FICHIERS_BRUTS = "data/raw/dvf_34_*.csv.gz"

# Règles de nettoyage et de publication (reprises dans le README et la fiche).
SURFACE_MIN_M2 = 9  # surface minimale d'un logement décent (décret n° 2002-120)
SURFACE_MAX_M2 = 1000  # au-delà : bâtiments atypiques (châteaux, domaines), non comparables
IQR_K = 1.5  # coefficient de Tukey appliqué au log du prix au m²
SEUIL_PUBLICATION = 30  # ventes minimales pour publier une médiane de commune
VILLES = {"34172": "Montpellier", "34032": "Béziers", "34301": "Sète"}
N_BOOTSTRAP = 2000
N_TIRAGES = 200  # tirages du test split-sample sur le rattrapage des communes
GRAINE = 20260922


def relatif(chemin: Path) -> str:
    """Chemin relatif à RACINE, au format POSIX, sans apostrophe, utilisable dans une chaîne SQL."""
    texte = chemin.relative_to(RACINE).as_posix()
    return texte.replace("'", "''")


def lire_sql(nom: str, **parametres: object) -> str:
    texte = (SQL / nom).read_text(encoding="utf-8")
    for cle, valeur in parametres.items():
        texte = texte.replace("{" + cle + "}", str(valeur))
    return texte


def compter(con: duckdb.DuckDBPyConnection, requete: str) -> int:
    return int(con.execute(requete).fetchone()[0])


def nettoyer(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Applique les règles une à une et renvoie le journal des lignes et mutations retirées."""
    journal: list[dict] = []

    def noter(etape: str, regle: str, unite: str, avant: int, apres: int) -> None:
        journal.append(
            {
                "etape": etape,
                "regle": regle,
                "unite": unite,
                "avant": avant,
                "retirees": avant - apres,
                "apres": apres,
                "part_retiree": round((avant - apres) / avant, 6) if avant else 0.0,
            }
        )

    lignes_brutes = compter(con, f"SELECT COUNT(*) FROM read_csv('{FICHIERS_BRUTS}', all_varchar=true)")
    con.execute(lire_sql("01_brut.sql", fichiers=FICHIERS_BRUTS))
    lignes_distinctes = compter(con, "SELECT COUNT(*) FROM brut")
    noter("1", "Doublons exacts (ligne identique sur les 40 colonnes)", "lignes", lignes_brutes, lignes_distinctes)

    con.execute(lire_sql("02_mutations.sql"))
    con.execute("CREATE OR REPLACE TABLE etape AS SELECT * FROM mutations")

    filtres = [
        ("2", "Mutation cohérente (une date, une nature, une valeur foncière)",
         "nb_dates = 1 AND nb_natures = 1 AND nb_valeurs <= 1"),
        ("3", "Nature « Vente » uniquement (hors VEFA, échange, adjudication, expropriation, terrain à bâtir)",
         "nature_mutation = 'Vente'"),
        ("4", "Valeur foncière renseignée et strictement positive",
         "valeur_fonciere IS NOT NULL AND valeur_fonciere > 0"),
        ("5", "Aucun local industriel ou commercial dans la mutation (prix non séparable)",
         "nb_locaux_activite = 0"),
        ("6", "Au moins un logement (retire terrains nus et dépendances vendues seules)",
         "nb_maisons + nb_appartements >= 1"),
        ("7", "Un seul logement (mutations multi-logements : prix global non ventilable)",
         "nb_maisons + nb_appartements = 1"),
        ("8", f"Surface bâtie renseignée, entre {SURFACE_MIN_M2} et {SURFACE_MAX_M2} m²",
         f"surface_reelle_bati BETWEEN {SURFACE_MIN_M2} AND {SURFACE_MAX_M2}"),
    ]
    for etape, regle, predicat in filtres:
        avant = compter(con, "SELECT COUNT(*) FROM etape")
        con.execute(f"CREATE OR REPLACE TABLE etape AS SELECT * FROM etape WHERE {predicat}")
        noter(etape, regle, "mutations", avant, compter(con, "SELECT COUNT(*) FROM etape"))

    con.execute(
        """
        CREATE OR REPLACE TABLE candidats AS
        SELECT *, YEAR(date_mutation) AS annee, valeur_fonciere / surface_reelle_bati AS prix_m2
        FROM etape
        """
    )
    avant = compter(con, "SELECT COUNT(*) FROM candidats")
    con.execute(lire_sql("03_aberrants.sql", k=IQR_K))
    noter(
        "9",
        f"Prix au m² hors [Q1 - {IQR_K} IQR ; Q3 + {IQR_K} IQR] du log, par type et par année",
        "mutations",
        avant,
        compter(con, "SELECT COUNT(*) FROM ventes"),
    )
    return pd.DataFrame(journal)


def exporter_modele(con: duckdb.DuckDBPyConnection) -> dict:
    con.execute(lire_sql("04_etoile.sql", villes=", ".join(f"'{c}'" for c in VILLES)))
    POWERBI.mkdir(parents=True, exist_ok=True)
    tailles = {}
    for table in ["fait_ventes", "dim_date", "dim_commune", "dim_type_bien"]:
        for extension, option in [("parquet", "(FORMAT PARQUET)"), ("csv", "(HEADER, DELIMITER ',')")]:
            cible = relatif(POWERBI / f"{table}.{extension}")
            con.execute(f"COPY {table} TO '{cible}' {option}")
        tailles[table] = compter(con, f"SELECT COUNT(*) FROM {table}")
    # Les dimensions ne contiennent aucune vente : elles sont aussi versionnées dans powerbi/tables/.
    dims = RACINE / "powerbi" / "tables"
    dims.mkdir(parents=True, exist_ok=True)
    for table, cle in [("dim_commune", "code_commune"), ("dim_type_bien", "code_type_bien")]:
        # Tri explicite : sans ORDER BY, l'ordre des lignes varie d'une exécution à l'autre
        # et le fichier versionné change sans raison.
        con.execute(
            f"COPY (SELECT * FROM {table} ORDER BY {cle}) "
            f"TO '{relatif(dims / f'{table}.csv')}' (HEADER, DELIMITER ',')"
        )
    return tailles


def medianes_bootstrap(valeurs: np.ndarray, rng: np.random.Generator, lot: int = 100) -> np.ndarray:
    """N_BOOTSTRAP médianes de rééchantillons, calculées par lots pour limiter la mémoire."""
    resultats = []
    for debut in range(0, N_BOOTSTRAP, lot):
        taille = min(lot, N_BOOTSTRAP - debut)
        resultats.append(np.median(rng.choice(valeurs, size=(taille, len(valeurs)), replace=True), axis=1))
    return np.concatenate(resultats)


def intervalle_mediane(valeurs: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    """IC à 95 % de la médiane par bootstrap percentile."""
    medianes = medianes_bootstrap(valeurs, rng)
    return float(np.percentile(medianes, 2.5)), float(np.percentile(medianes, 97.5))


def intervalles(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, pd.DataFrame]:
    """IC bootstrap des médianes (département et trois villes) et de l'évolution première -> dernière année."""
    rng = np.random.default_rng(GRAINE)
    ventes = con.execute(
        "SELECT annee, type_bien, code_commune, prix_m2 FROM ventes_modele"
    ).df()
    lignes = []
    perimetres = {"Hérault": ventes, **{nom: ventes[ventes.code_commune == code] for code, nom in VILLES.items()}}
    for perimetre, donnees in perimetres.items():
        for (annee, type_bien), groupe in donnees.groupby(["annee", "type_bien"]):
            valeurs = groupe.prix_m2.to_numpy()
            bas, haut = intervalle_mediane(valeurs, rng)
            lignes.append({"perimetre": perimetre, "annee": int(annee), "type_bien": type_bien,
                           "nb_ventes": len(valeurs), "prix_m2_median": float(np.median(valeurs)),
                           "ic95_bas": bas, "ic95_haut": haut})
    ic = pd.DataFrame(lignes)

    a0, a1 = int(ventes.annee.min()), int(ventes.annee.max())
    evolutions = []
    for perimetre, donnees in perimetres.items():
        for type_bien, groupe in donnees.groupby("type_bien"):
            debut = groupe.loc[groupe.annee == a0, "prix_m2"].to_numpy()
            fin = groupe.loc[groupe.annee == a1, "prix_m2"].to_numpy()
            m0 = medianes_bootstrap(debut, rng)
            m1 = medianes_bootstrap(fin, rng)
            rapport = m1 / m0 - 1
            evolutions.append({
                "perimetre": perimetre, "type_bien": type_bien, "annee_debut": a0, "annee_fin": a1,
                "nb_ventes_debut": len(debut), "nb_ventes_fin": len(fin),
                "prix_m2_median_debut": float(np.median(debut)), "prix_m2_median_fin": float(np.median(fin)),
                "evolution": float(np.median(fin) / np.median(debut) - 1),
                "ic95_bas": float(np.percentile(rapport, 2.5)), "ic95_haut": float(np.percentile(rapport, 97.5)),
            })
    return ic, pd.DataFrame(evolutions)


def rattrapage_split_sample(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Le rattrapage des communes, testé sur deux moitiés disjointes des ventes de l'année de départ.

    Le test de permutation employé jusqu'ici corrélait le prix médian de l'année de départ avec
    l'évolution `prix_fin / prix_debut - 1`. Le prix de départ est donc présent dans les deux
    variables, au numérateur de l'une et au dénominateur de l'autre : le seul bruit d'échantillonnage
    sur la médiane de départ suffit à produire une corrélation négative, sans aucun rattrapage réel.
    Permuter y détruit ce couplage, donc le test ne répond pas à l'objection qu'il prétend écarter.

    Le test ci-dessous sépare aléatoirement les ventes de l'année de départ de chaque commune en deux
    moitiés : l'abscisse (prix de départ) est estimée sur la première, le dénominateur de l'évolution
    sur la seconde. Les deux bruits deviennent indépendants et le couplage mathématique disparaît.
    On répète N_TIRAGES fois et on publie la médiane de la corrélation de rang et son intervalle.
    """
    rng = np.random.default_rng(GRAINE)
    ventes = con.execute(
        "SELECT annee, type_bien, code_commune, prix_m2 FROM ventes_modele"
    ).df()
    a0, a1 = int(ventes.annee.min()), int(ventes.annee.max())

    # Mêmes couples (commune, type) que le test publié : médiane publiable en a0 et en a1.
    effectifs = ventes.groupby(["code_commune", "type_bien", "annee"]).size().unstack("annee")
    eligibles = effectifs[(effectifs.get(a0, 0) >= SEUIL_PUBLICATION)
                          & (effectifs.get(a1, 0) >= SEUIL_PUBLICATION)].index

    debut = {cle: groupe.prix_m2.to_numpy()
             for cle, groupe in ventes[ventes.annee == a0].groupby(["code_commune", "type_bien"])}
    fin = {cle: float(np.median(groupe.prix_m2.to_numpy()))
           for cle, groupe in ventes[ventes.annee == a1].groupby(["code_commune", "type_bien"])}

    def rho_rang(x: np.ndarray, y: np.ndarray) -> float:
        return float(np.corrcoef(pd.Series(x).rank(), pd.Series(y).rank())[0, 1])

    tirages: dict[str, list[float]] = {}
    for type_bien in sorted({t for _, t in eligibles}):
        cles = [c for c in eligibles if c[1] == type_bien]
        valeurs = []
        for _ in range(N_TIRAGES):
            axe, denominateur = [], []
            for cle in cles:
                v = debut[cle]
                melange = rng.permutation(v)
                moitie = len(melange) // 2
                # Moitié A : abscisse. Moitié B : dénominateur de l'évolution. Disjointes par construction.
                axe.append(float(np.median(melange[:moitie])))
                denominateur.append(float(np.median(melange[moitie:])))
            axe = np.asarray(axe)
            evolution = np.asarray([fin[cle] for cle in cles]) / np.asarray(denominateur) - 1
            valeurs.append(rho_rang(axe, evolution))
        tirages[type_bien] = valeurs

    lignes = []
    for type_bien, valeurs in tirages.items():
        cles = [c for c in eligibles if c[1] == type_bien]
        v = np.asarray(valeurs)
        # Corrélations de référence, sur les médianes entières, pour situer le test.
        axe_complet = np.asarray([float(np.median(debut[c])) for c in cles])
        fin_complet = np.asarray([fin[c] for c in cles])
        evo_complet = fin_complet / axe_complet - 1
        lignes.append({
            "type_bien": type_bien, "communes": len(cles), "tirages": N_TIRAGES,
            "annee_debut": a0, "annee_fin": a1,
            "rho_couple_prix_debut": rho_rang(axe_complet, evo_complet),
            "rho_prix_fin": rho_rang(fin_complet, evo_complet),
            "rho_split_sample_median": float(np.median(v)),
            "ic95_bas": float(np.percentile(v, 2.5)), "ic95_haut": float(np.percentile(v, 97.5)),
            "part_tirages_negatifs": float(np.mean(v < 0)),
        })
    detail = pd.DataFrame([{"type_bien": t, "tirage": i, "rho": r}
                           for t, valeurs in tirages.items() for i, r in enumerate(valeurs, 1)])
    return pd.DataFrame(lignes), detail


def controler_mesures(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Calcule en SQL, dans quelques contextes de filtre, la valeur de chaque mesure de powerbi/mesures.dax."""

    def filtre(contexte: dict) -> str:
        conditions = ["TRUE"]
        if "annee" in contexte:
            conditions.append(f"annee = {contexte['annee']}")
        if "type_bien" in contexte:
            conditions.append(f"type_bien = '{contexte['type_bien']}'")
        if "commune" in contexte:
            conditions.append(f"nom_commune = '{contexte['commune']}'")
        return " AND ".join(conditions)

    def valeur(expression: str, contexte: dict) -> float | None:
        resultat = con.execute(f"SELECT {expression} FROM ventes_modele WHERE {filtre(contexte)}").fetchone()[0]
        return None if resultat is None else float(resultat)

    simples = {
        "Nb ventes": "COUNT(*)",
        "Volume d'affaires": "SUM(valeur_fonciere)",
        "Prix m² médian": "MEDIAN(prix_m2)",
        "Prix m² moyen": "AVG(prix_m2)",
        "Prix m² 1er quartile": "QUANTILE_CONT(prix_m2, 0.25)",
        "Prix m² 3e quartile": "QUANTILE_CONT(prix_m2, 0.75)",
        "Valeur médiane": "MEDIAN(valeur_fonciere)",
        "Surface médiane": "MEDIAN(surface_bati)",
    }
    contextes = [
        {},
        {"annee": 2025},
        {"annee": 2025, "type_bien": "Appartement"},
        {"annee": 2025, "type_bien": "Maison"},
        *({"annee": 2025, "type_bien": t, "commune": v} for v in VILLES.values() for t in ["Appartement", "Maison"]),
    ]
    lignes = []
    for contexte in contextes:
        libelle = ", ".join(f"{k}={v}" for k, v in contexte.items()) or "aucun filtre"
        for mesure, expression in simples.items():
            lignes.append({"mesure": mesure, "contexte": libelle, "sql": expression,
                           "valeur_sql": valeur(expression, contexte)})
        if "annee" in contexte:
            precedent = {**contexte, "annee": contexte["annee"] - 1}
            depart = {**contexte, "annee": 2021}
            for mesure, expression in [("Prix m² médian", "MEDIAN(prix_m2)"), ("Nb ventes", "COUNT(*)")]:
                courant, avant = valeur(expression, contexte), valeur(expression, precedent)
                nom = "Évolution prix m² %" if mesure == "Prix m² médian" else "Évolution volume %"
                lignes.append({"mesure": nom, "contexte": libelle, "sql": f"{expression} / {expression} (N-1) - 1",
                               "valeur_sql": courant / avant - 1})
            med, med0 = valeur("MEDIAN(prix_m2)", contexte), valeur("MEDIAN(prix_m2)", depart)
            lignes.append({"mesure": "Évolution depuis 2021 %", "contexte": libelle,
                           "sql": "MEDIAN(prix_m2) / MEDIAN(prix_m2) (2021) - 1", "valeur_sql": med / med0 - 1})
        sans_type = {k: v for k, v in contexte.items() if k != "type_bien"}
        lignes.append({"mesure": "Part des maisons %", "contexte": libelle,
                       "sql": "AVG(CASE WHEN type_bien = 'Maison' THEN 1.0 ELSE 0.0 END), filtre type retiré",
                       "valeur_sql": valeur("AVG(CASE WHEN type_bien = 'Maison' THEN 1.0 ELSE 0.0 END)", sans_type)})
        if "commune" in contexte:
            n = valeur("COUNT(*)", contexte)
            med = valeur("MEDIAN(prix_m2)", contexte) if n >= SEUIL_PUBLICATION else None
            departement = valeur("MEDIAN(prix_m2)", {k: v for k, v in contexte.items() if k != "commune"})
            lignes.append({"mesure": "Prix m² médian publiable", "contexte": libelle,
                           "sql": f"CASE WHEN COUNT(*) >= {SEUIL_PUBLICATION} THEN MEDIAN(prix_m2) END",
                           "valeur_sql": med})
            lignes.append({"mesure": "Écart à l'Hérault %", "contexte": libelle,
                           "sql": "MEDIAN(prix_m2 commune) / MEDIAN(prix_m2 département) - 1",
                           "valeur_sql": None if med is None else med / departement - 1})
            rang = con.execute(
                f"""
                SELECT rang FROM (
                    SELECT nom_commune, DENSE_RANK() OVER (ORDER BY prix_m2_median DESC) AS rang
                    FROM ind_commune_annee_type
                    WHERE annee = {contexte['annee']} AND type_bien = '{contexte['type_bien']}'
                      AND prix_m2_median IS NOT NULL
                ) WHERE nom_commune = '{contexte['commune']}'
                """
            ).fetchone()
            lignes.append({"mesure": "Rang prix commune", "contexte": libelle,
                           "sql": "DENSE_RANK() OVER (ORDER BY prix_m2_median DESC), communes publiables",
                           "valeur_sql": None if rang is None else float(rang[0])})
    return pd.DataFrame(lignes)


def chiffres_cles(con: duckdb.DuckDBPyConnection, evolutions: pd.DataFrame) -> dict:
    """Chiffres repris dans la fiche et le README, tous lus dans les tables d'indicateurs."""
    annees = con.execute("SELECT * FROM ind_annee ORDER BY annee").df()
    premiere, derniere = annees.iloc[0], annees.iloc[-1]
    creux = annees.loc[annees.nb_ventes.idxmin()]
    pic = annees.loc[annees.prix_m2_median.idxmax()]
    herault = evolutions[evolutions.perimetre == "Hérault"].set_index("type_bien")
    villes = con.execute(
        f"""
        SELECT nom_commune, type_bien, nb_ventes, prix_m2_median
        FROM ind_commune_annee_type
        WHERE annee = {int(derniere.annee)} AND ville_suivie ORDER BY type_bien, prix_m2_median DESC
        """
    ).df()
    return {
        "annee_debut": int(premiere.annee),
        "annee_fin": int(derniere.annee),
        "ventes_annee_debut": int(premiere.nb_ventes),
        "ventes_annee_fin": int(derniere.nb_ventes),
        "annee_creux_volume": int(creux.annee),
        "ventes_annee_creux": int(creux.nb_ventes),
        "evolution_volume_creux_vs_debut": float(creux.nb_ventes / premiere.nb_ventes - 1),
        "evolution_volume_fin_vs_creux": float(derniere.nb_ventes / creux.nb_ventes - 1),
        "prix_m2_median_tous_types_debut": float(premiere.prix_m2_median),
        "prix_m2_median_tous_types_fin": float(derniere.prix_m2_median),
        "annee_pic_prix": int(pic.annee),
        "prix_m2_median_pic": float(pic.prix_m2_median),
        "evolution_prix_tous_types_debut_fin": float(derniere.prix_m2_median / premiere.prix_m2_median - 1),
        "evolution_prix_appartements": {k: float(herault.loc["Appartement", k])
                                        for k in ["evolution", "ic95_bas", "ic95_haut"]},
        "evolution_prix_maisons": {k: float(herault.loc["Maison", k]) for k in ["evolution", "ic95_bas", "ic95_haut"]},
        "villes_annee_fin": villes.to_dict(orient="records"),
        "communes_extremes_annee_fin": con.execute(
            f"""
            SELECT type_bien,
                   ARG_MAX(nom_commune, prix_m2_median) AS commune_plus_chere,
                   MAX(prix_m2_median)                  AS prix_m2_median_max,
                   ARG_MIN(nom_commune, prix_m2_median) AS commune_moins_chere,
                   MIN(prix_m2_median)                  AS prix_m2_median_min,
                   MAX(prix_m2_median) / MIN(prix_m2_median) AS rapport_max_min,
                   COUNT(*)                             AS communes_publiees
            FROM ind_commune_annee_type
            WHERE annee = {int(derniere.annee)} AND prix_m2_median IS NOT NULL
            GROUP BY type_bien ORDER BY type_bien
            """
        ).df().to_dict(orient="records"),
    }


def ecrire_csv(df: pd.DataFrame, chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(chemin, index=False, encoding="utf-8", float_format="%.6g")


def main() -> None:
    os.chdir(RACINE)
    RESULTATS.mkdir(exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'")
    con.execute("SET threads=2")
    con.execute(f"SET temp_directory='{relatif(RACINE / 'data' / 'tmp')}'")

    journal = nettoyer(con)
    ecrire_csv(journal, RESULTATS / "journal_nettoyage.csv")
    print(journal.to_string(index=False))

    bornes = con.execute("SELECT * FROM bornes_aberrants ORDER BY type_local, annee").df()
    ecrire_csv(bornes, RESULTATS / "bornes_aberrants.csv")
    retraits_type = con.execute(
        """
        SELECT c.type_local, c.annee, COUNT(*) AS candidats,
               COUNT(*) FILTER (WHERE c.prix_m2 < b.borne_basse_m2) AS sous_borne_basse,
               COUNT(*) FILTER (WHERE c.prix_m2 > b.borne_haute_m2) AS sur_borne_haute
        FROM candidats c JOIN bornes_aberrants b USING (type_local, annee)
        GROUP BY ALL ORDER BY ALL
        """
    ).df()
    ecrire_csv(retraits_type, RESULTATS / "retraits_aberrants_par_type.csv")

    tailles = exporter_modele(con)
    con.execute(lire_sql("05_indicateurs.sql", seuil=SEUIL_PUBLICATION))

    tables = ["ind_annee_type", "ind_annee", "ind_mois_type", "ind_commune_annee_type", "ind_commune_evolution"]
    for table in tables:
        df = con.execute(f"SELECT * FROM {table}").df()
        ecrire_csv(df, RESULTATS / f"{table}.csv")
        ecrire_csv(df, APP_DATA / f"{table}.csv")

    ic, evolutions = intervalles(con)
    ecrire_csv(ic, RESULTATS / "ic_medianes.csv")
    ecrire_csv(evolutions, RESULTATS / "ic_evolutions.csv")
    ecrire_csv(ic, APP_DATA / "ic_medianes.csv")

    rattrapage, rattrapage_detail = rattrapage_split_sample(con)
    ecrire_csv(rattrapage, RESULTATS / "rattrapage_split_sample.csv")
    ecrire_csv(rattrapage_detail, RESULTATS / "rattrapage_split_sample_tirages.csv")
    print(rattrapage.to_string(index=False))

    # Précision élargie : ce fichier sert de référence à la comparaison avec les mesures DAX
    # évaluées dans Power BI (scripts/concordance.py).
    controler_mesures(con).to_csv(RESULTATS / "mesures_dax_sql.csv", index=False,
                                  encoding="utf-8", float_format="%.17g")
    cles = chiffres_cles(con, evolutions)
    (RESULTATS / "chiffres_cles.json").write_text(json.dumps(cles, ensure_ascii=False, indent=2), encoding="utf-8")

    communes_publiables = con.execute(
        f"""
        SELECT type_bien, annee, COUNT(*) AS communes_avec_ventes,
               COUNT(*) FILTER (WHERE nb_ventes >= {SEUIL_PUBLICATION}) AS communes_publiees,
               SUM(nb_ventes) AS ventes,
               SUM(nb_ventes) FILTER (WHERE nb_ventes >= {SEUIL_PUBLICATION}) AS ventes_dans_communes_publiees
        FROM ind_commune_annee_type GROUP BY ALL ORDER BY ALL
        """
    ).df()
    ecrire_csv(communes_publiables, RESULTATS / "couverture_communes.csv")

    resume = {
        "regles": {
            "surface_min_m2": SURFACE_MIN_M2, "surface_max_m2": SURFACE_MAX_M2, "iqr_k": IQR_K,
            "seuil_publication_commune": SEUIL_PUBLICATION, "bootstrap": N_BOOTSTRAP, "graine": GRAINE,
        },
        "periode": con.execute("SELECT MIN(date)::VARCHAR, MAX(date)::VARCHAR FROM fait_ventes").fetchone(),
        "lignes_brutes": int(journal.iloc[0]["avant"]),
        "mutations_brutes": compter(con, "SELECT COUNT(*) FROM mutations"),
        "ventes_retenues": tailles["fait_ventes"],
        "part_mutations_retenues": round(tailles["fait_ventes"] / compter(con, "SELECT COUNT(*) FROM mutations"), 6),
        "communes_dans_les_donnees": tailles["dim_commune"],
        "communes_avec_vente_retenue": compter(con, "SELECT COUNT(DISTINCT code_commune) FROM fait_ventes"),
        "tailles_tables_modele": tailles,
    }
    (RESULTATS / "resume.json").write_text(json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resume, ensure_ascii=False, indent=2))
    con.close()


if __name__ == "__main__":
    main()
