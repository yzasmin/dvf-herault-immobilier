"""Tests : règles de regroupement par mutation (données synthétiques) et cohérence des sorties publiées."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

RACINE = Path(__file__).resolve().parents[1]
RESULTATS = RACINE / "results"


@pytest.fixture()
def con_synthetique() -> duckdb.DuckDBPyConnection:
    """Trois mutations : une maison sur deux natures de culture, deux appartements vendus ensemble,
    un appartement avec une cave."""
    con = duckdb.connect()
    con.execute(
        """
        CREATE TABLE brut AS SELECT * FROM (VALUES
          ('M1', DATE '2024-03-01', 'Vente', 300000.0, '34000', '34172', 'Montpellier', 'P1', NULL, 1, 'Maison', 100.0, 4, 'S', 400.0),
          ('M1', DATE '2024-03-01', 'Vente', 300000.0, '34000', '34172', 'Montpellier', 'P1', NULL, 1, 'Maison', 100.0, 4, 'J', 200.0),
          ('M2', DATE '2024-04-01', 'Vente', 250000.0, '34000', '34172', 'Montpellier', 'P2', '10', 2, 'Appartement', 40.0, 2, NULL, NULL),
          ('M2', DATE '2024-04-01', 'Vente', 250000.0, '34000', '34172', 'Montpellier', 'P2', '11', 2, 'Appartement', 45.0, 2, NULL, NULL),
          ('M3', DATE '2024-05-01', 'Vente', 150000.0, '34500', '34032', 'Béziers', 'P3', '5', 2, 'Appartement', 60.0, 3, NULL, NULL),
          ('M3', DATE '2024-05-01', 'Vente', 150000.0, '34500', '34032', 'Béziers', 'P3', '6', 3, 'Dépendance', NULL, 0, NULL, NULL)
        ) AS t(id_mutation, date_mutation, nature_mutation, valeur_fonciere, code_postal, code_commune, nom_commune,
               id_parcelle, lot1_numero, code_type_local, type_local, surface_reelle_bati,
               nombre_pieces_principales, code_nature_culture, surface_terrain)
        """
    )
    con.execute((RACINE / "sql" / "02_mutations.sql").read_text(encoding="utf-8"))
    yield con
    con.close()


def test_maison_sur_deux_cultures_comptee_une_fois(con_synthetique):
    m1 = con_synthetique.execute("SELECT * FROM mutations WHERE id_mutation = 'M1'").df().iloc[0]
    assert m1.nb_maisons == 1
    assert m1.surface_reelle_bati == 100.0
    assert m1.surface_terrain == 600.0  # 400 m² de sol + 200 m² de jardin
    assert m1.valeur_fonciere == 300000.0  # valeur de la mutation, jamais sommée


def test_vente_de_deux_appartements_sans_logement_unique(con_synthetique):
    m2 = con_synthetique.execute("SELECT * FROM mutations WHERE id_mutation = 'M2'").df().iloc[0]
    assert m2.nb_appartements == 2
    assert pd.isna(m2.type_local)  # pas de logement unique : écartée par la règle 7


def test_dependance_rattachee_au_logement(con_synthetique):
    m3 = con_synthetique.execute("SELECT * FROM mutations WHERE id_mutation = 'M3'").df().iloc[0]
    assert (m3.nb_appartements, m3.nb_dependances) == (1, 1)
    assert m3.surface_reelle_bati == 60.0


def lire(nom: str) -> pd.DataFrame:
    chemin = RESULTATS / nom
    if not chemin.exists():
        pytest.skip(f"{nom} absent : lancer scripts/pipeline.py")
    return pd.read_csv(chemin)


def test_journal_enchaine_les_etapes():
    journal = lire("journal_nettoyage.csv")
    assert (journal.avant - journal.retirees == journal.apres).all()
    mutations = journal[journal.unite == "mutations"].reset_index(drop=True)
    assert (mutations.avant.iloc[1:].to_numpy() == mutations.apres.iloc[:-1].to_numpy()).all()
    resume = json.loads((RESULTATS / "resume.json").read_text(encoding="utf-8"))
    assert mutations.apres.iloc[-1] == resume["ventes_retenues"]


def test_aucune_mediane_de_commune_sous_le_seuil():
    communes = lire("ind_commune_annee_type.csv")
    seuil = json.loads((RESULTATS / "resume.json").read_text(encoding="utf-8"))["regles"]["seuil_publication_commune"]
    assert communes.loc[communes.nb_ventes < seuil, "prix_m2_median"].isna().all()
    assert communes.loc[communes.nb_ventes >= seuil, "prix_m2_median"].notna().all()


def test_mesures_sql_egales_aux_tables_d_indicateurs():
    mesures = lire("mesures_dax_sql.csv")
    annee_type = lire("ind_annee_type.csv")
    for type_bien in ["Appartement", "Maison"]:
        contexte = f"annee=2025, type_bien={type_bien}"
        valeur = mesures[(mesures.mesure == "Prix m² médian") & (mesures.contexte == contexte)].valeur_sql.iloc[0]
        attendu = annee_type[(annee_type.annee == 2025) & (annee_type.type_bien == type_bien)].prix_m2_median.iloc[0]
        assert valeur == pytest.approx(attendu, rel=1e-5)
