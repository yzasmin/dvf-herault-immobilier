"""Compare les mesures DAX évaluées dans Power BI Desktop aux mêmes mesures recalculées en SQL.

Entrées : results/powerbi/*.csv (sorties de scripts/executer_dax.ps1, moteur Power BI)
          results/mesures_dax_sql.csv (sorties de scripts/pipeline.py, DuckDB)
Sortie  : results/concordance_dax_powerbi.csv et un tableau Markdown affiché.

Usage : uv run python scripts/concordance.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parents[1]
RESULTATS = RACINE / "results"
POWERBI = RESULTATS / "powerbi"

# Colonne du résultat DAX -> nom de la mesure tel qu'il figure dans results/mesures_dax_sql.csv.
MESURES = {
    "Nb ventes": "Nb ventes",
    "Prix m2 median": "Prix m² médian",
    "Prix m2 moyen": "Prix m² moyen",
    "Prix m2 1er quartile": "Prix m² 1er quartile",
    "Prix m2 3e quartile": "Prix m² 3e quartile",
    "Valeur mediane": "Valeur médiane",
    "Surface mediane": "Surface médiane",
    "Volume d affaires": "Volume d'affaires",
    "Part des maisons": "Part des maisons %",
    "Evolution prix": "Évolution prix m² %",
    "Evolution volume": "Évolution volume %",
    "Evolution depuis 2021": "Évolution depuis 2021 %",
    "Prix m2 median publiable": "Prix m² médian publiable",
    "Ecart a l Herault": "Écart à l'Hérault %",
    "Rang prix commune": "Rang prix commune",
}


def lire_dax(nom: str) -> pd.DataFrame:
    """Lit un CSV produit par ADOMD : entêtes entre crochets, virgule décimale."""
    df = pd.read_csv(POWERBI / f"{nom}.csv", decimal=",", encoding="utf-8")
    df.columns = [c.strip("[]").split("[")[-1].rstrip("]") for c in df.columns]
    return df


def valeurs_dax() -> pd.DataFrame:
    lignes = []

    def ajouter(ligne: pd.Series, contexte: str) -> None:
        for colonne, mesure in MESURES.items():
            if colonne in ligne.index and pd.notna(ligne[colonne]):
                lignes.append({"mesure": mesure, "contexte": contexte, "valeur_dax": float(ligne[colonne])})

    ajouter(lire_dax("01_total").iloc[0], "aucun filtre")

    annees = lire_dax("02_par_annee")
    ajouter(annees[annees.annee == 2025].iloc[0], "annee=2025")

    annees_types = lire_dax("03_par_annee_type")
    for _, ligne in annees_types[annees_types.annee == 2025].iterrows():
        ajouter(ligne, f"annee=2025, type_bien={ligne.type_bien}")

    villes = lire_dax("04_villes_2025")
    for _, ligne in villes.iterrows():
        ajouter(ligne, f"annee=2025, type_bien={ligne.type_bien}, commune={ligne.nom_commune}")

    return pd.DataFrame(lignes)


def main() -> None:
    sql = pd.read_csv(RESULTATS / "mesures_dax_sql.csv")[["mesure", "contexte", "valeur_sql"]]
    dax = valeurs_dax()
    comparaison = dax.merge(sql, on=["mesure", "contexte"], how="inner")
    comparaison["ecart_absolu"] = comparaison.valeur_dax - comparaison.valeur_sql
    comparaison["ecart_relatif"] = comparaison.ecart_absolu / comparaison.valeur_sql.replace(0, pd.NA)
    comparaison["identique"] = comparaison.ecart_relatif.abs().fillna(0) < 1e-9
    comparaison = comparaison.sort_values(["contexte", "mesure"]).reset_index(drop=True)
    comparaison.to_csv(RESULTATS / "concordance_dax_powerbi.csv", index=False,
                       encoding="utf-8", float_format="%.12g")

    total = len(comparaison)
    identiques = int(comparaison.identique.sum())
    print(f"{identiques}/{total} valeurs identiques (écart relatif < 1e-9)")
    ecarts = comparaison[~comparaison.identique]
    if not ecarts.empty:
        print("Écarts :")
        print(ecarts.to_string(index=False))
    extrait = comparaison[comparaison.contexte.isin(
        ["aucun filtre", "annee=2025, type_bien=Appartement", "annee=2025, type_bien=Maison"])]
    print("\n| Mesure | Contexte | Power BI (DAX) | DuckDB (SQL) | Écart |")
    print("| --- | --- | --- | --- | --- |")
    for _, ligne in extrait.iterrows():
        print(f"| {ligne.mesure} | {ligne.contexte} | {ligne.valeur_dax:.6f} | {ligne.valeur_sql:.6f} "
              f"| {ligne.ecart_absolu:.2e} |")


if __name__ == "__main__":
    main()
