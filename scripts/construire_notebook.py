"""Construit notebooks/analyse.ipynb (cellules sans sorties). L'exécution se fait ensuite avec nbconvert.

Usage : uv run python scripts/construire_notebook.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

RACINE = Path(__file__).resolve().parents[1]

cellules: list[tuple[str, str]] = [
    ("md", """# Marché immobilier de l'Hérault, 2021-2025

Analyse des Demandes de valeurs foncières (DVF géolocalisées, Etalab) pour le département de l'Hérault (34).

**Questions.** Comment ont évolué le prix au m² et le nombre de ventes depuis 2021 ? Quelles communes sont les plus
et les moins chères ? Montpellier, Sète et Béziers suivent-elles la même trajectoire ?

**Pré-requis.** `uv run python scripts/telecharger.py` puis `uv run python scripts/pipeline.py`. Ce notebook ne fait
que lire `results/` et le modèle en étoile de `data/processed/powerbi/` : chaque chiffre affiché vient de là."""),
    ("code", """import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import Image, display

RACINE = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
R = RACINE / "results"
pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 20)
pd.set_option("display.float_format", lambda v: f"{v:,.2f}".replace(",", " "))
resume = json.loads((R / "resume.json").read_text(encoding="utf-8"))
cles = json.loads((R / "chiffres_cles.json").read_text(encoding="utf-8"))
sources = json.loads((R / "sources.json").read_text(encoding="utf-8"))"""),
    ("md", "## 1. Sources téléchargées"),
    ("code", """pd.DataFrame(sources["fichiers"])[["annee", "octets", "date_publication_serveur", "sha256"]]"""),
    ("md", """## 2. Nettoyage : chaque règle et ce qu'elle retire

Une mutation DVF s'étale sur plusieurs lignes (une par local et par nature de culture) et sa valeur foncière est répétée
sur chacune. L'analyse se fait donc à la mutation. On ne garde que les ventes d'un seul logement, pour que le prix au m²
ait un sens (valeur foncière / surface bâtie ; les dépendances comme garage ou cave restent incluses dans le prix)."""),
    ("code", """journal = pd.read_csv(R / "journal_nettoyage.csv")
journal.assign(part_retiree=(journal.part_retiree * 100).round(2).astype(str) + " %")"""),
    ("code", """print(f"Mutations brutes : {resume['mutations_brutes']:,}".replace(",", " "))
print(f"Ventes retenues  : {resume['ventes_retenues']:,}".replace(",", " "),
      f"({resume['part_mutations_retenues'] * 100:.1f} % des mutations)")"""),
    ("md", """La règle la plus lourde (étape 6) retire les mutations sans logement : terrains, parkings et caves vendus seuls.
Elles ne relèvent pas du marché du logement. La règle des aberrants (étape 9) est appliquée au logarithme du prix au m²,
par type de bien et par année ; les bornes obtenues :"""),
    ("code", """pd.read_csv(R / "bornes_aberrants.csv")[["type_local", "annee", "n_candidats", "borne_basse_m2", "borne_haute_m2"]]"""),
    ("code", """pd.read_csv(R / "retraits_aberrants_par_type.csv")"""),
    ("md", """Les retraits se font surtout par le bas (prix au m² très faibles) : ventes entre proches, parts de biens,
viagers ou erreurs de saisie de surface. La distribution du log du prix au m² avant filtrage (ventes candidates)
et les bornes retenues :"""),
    ("code", """fait = pd.read_parquet(RACINE / "data" / "processed" / "powerbi" / "fait_ventes.parquet")
bornes = pd.read_csv(R / "bornes_aberrants.csv")
fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)
for ax, (code, nom) in zip(axes, [(2, "Appartement"), (1, "Maison")]):
    valeurs = fait.loc[fait.code_type_bien == code, "prix_m2"]
    ax.hist(np.log10(valeurs), bins=80, color="#1F8A7E" if code == 2 else "#C8811A")
    b = bornes[(bornes.type_local == nom) & (bornes.annee == 2025)].iloc[0]
    for borne in (b.borne_basse_m2, b.borne_haute_m2):
        ax.axvline(np.log10(borne), color="#444", linestyle="--")
    ax.set_title(f"{nom}s retenus, 2021-2025 (bornes 2025 en pointillés)")
    ax.set_xlabel("log10 du prix au m²")
plt.tight_layout()
print(f"Ventes dans le modèle : {len(fait):,}".replace(",", " "))"""),
    ("md", "## 3. Indicateurs départementaux"),
    ("code", """annee_type = pd.read_csv(R / "ind_annee_type.csv")
annee_type[["annee", "type_bien", "nb_ventes", "prix_m2_median", "prix_m2_moyen", "valeur_mediane",
            "surface_mediane", "evolution_prix_m2", "evolution_volume"]]"""),
    ("md", """La moyenne dépasse toujours la médiane : la distribution du prix au m² a une queue à droite (biens de
standing, bord de mer). La médiane est l'indicateur retenu partout."""),
    ("code", """display(Image(filename=str(RACINE / "figures" / "01-prix-m2-herault.png")))
display(Image(filename=str(RACINE / "figures" / "02-volumes-annuels.png")))"""),
    ("code", """ev = pd.read_csv(R / "ic_evolutions.csv")
ev.assign(**{c: (ev[c] * 100).round(1) for c in ["evolution", "ic95_bas", "ic95_haut"]})"""),
    ("md", """**Lecture.** Entre 2021 et 2025, le prix médian au m² des appartements a augmenté de 10,2 % dans l'Hérault
(IC à 95 % bootstrap : 8,8 % à 11,6 %), celui des maisons de 7,5 % (6,0 % à 9,1 %). Toute la hausse a lieu entre 2021
et 2023 ; depuis, les prix sont stables. Le nombre de ventes, lui, a chuté de 31 % entre 2021 et 2024 avant de
remonter de 13 % en 2025. Ce sont des prix nominaux : sur la même période, l'inflation cumulée est du même ordre de
grandeur, donc en euros constants la hausse serait bien plus faible (non calculé ici)."""),
    ("md", "## 4. Montpellier, Sète, Béziers"),
    ("code", """ic = pd.read_csv(R / "ic_medianes.csv")
villes = ic[ic.perimetre != "Hérault"]
villes.pivot_table(index=["perimetre", "type_bien"], columns="annee", values="prix_m2_median")"""),
    ("code", """display(Image(filename=str(RACINE / "figures" / "03-trois-villes-appartements.png")))"""),
    ("md", """En 2025, un appartement se vend à Sète au même prix médian au m² qu'à Montpellier, alors qu'il était
nettement moins cher en 2021. Béziers reste environ deux fois moins cher que Montpellier, mais ses prix d'appartements
ont progressé plus vite en proportion. Pour les maisons de Montpellier et de Sète, l'intervalle de confiance de
l'évolution 2021-2025 contient 0 : l'effectif (quelques centaines de ventes par an) ne permet pas de conclure."""),
    ("md", "## 5. Communes"),
    ("code", """couverture = pd.read_csv(R / "couverture_communes.csv")
couverture.assign(part_ventes_couvertes=(couverture.ventes_dans_communes_publiees / couverture.ventes).round(3))"""),
    ("md", """Le seuil de 30 ventes laisse de côté la plupart des petites communes, mais les communes publiées concentrent
l'essentiel des ventes d'appartements. Classement 2025 des appartements :"""),
    ("code", """display(Image(filename=str(RACINE / "figures" / "04-communes-appartements.png")))
pd.DataFrame(cles["communes_extremes_annee_fin"])"""),
    ("md", """### Les communes les moins chères rattrapent-elles les autres ?

Pour les couples (commune, type) publiables en 2021 et en 2025, on mesure la corrélation de rang de Spearman entre le
prix médian 2021 et l'évolution 2021-2025. La p-valeur vient d'un test de permutation (10 000 permutations), pour ne
pas dépendre d'une hypothèse de loi."""),
    ("code", """evo = pd.read_csv(R / "ind_commune_evolution.csv").dropna(subset=["evolution_prix_m2"])
rng = np.random.default_rng(20260922)

def spearman(x, y):
    return np.corrcoef(pd.Series(x).rank(), pd.Series(y).rank())[0, 1]

resultats = []
for type_bien, groupe in evo.groupby("type_bien"):
    x, y = groupe.prix_m2_median_debut.to_numpy(), groupe.evolution_prix_m2.to_numpy()
    rho = spearman(x, y)
    permutations = np.array([spearman(x, rng.permutation(y)) for _ in range(10_000)])
    p = (np.sum(np.abs(permutations) >= abs(rho)) + 1) / (len(permutations) + 1)
    resultats.append({"type_bien": type_bien, "communes": len(groupe), "rho_spearman": rho, "p_valeur_permutation": p})
rattrapage = pd.DataFrame(resultats)
(R / "rattrapage_communes.json").write_text(rattrapage.to_json(orient="records", force_ascii=False, indent=2),
                                             encoding="utf-8")
rattrapage"""),
    ("code", """fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
for ax, (type_bien, groupe) in zip(axes, evo.groupby("type_bien")):
    ax.scatter(groupe.prix_m2_median_debut, groupe.evolution_prix_m2 * 100, s=np.sqrt(groupe.nb_ventes_periode) * 3,
               alpha=0.6, color="#1F8A7E" if type_bien == "Appartement" else "#C8811A")
    ax.axhline(0, color="#999", linewidth=0.8)
    ax.set_title(f"{type_bien}s : prix 2021 et évolution 2021-2025")
    ax.set_xlabel("Prix médian au m² en 2021 (€)")
    ax.set_ylabel("Évolution 2021-2025 (%)")
plt.tight_layout()"""),
    ("md", """Une corrélation négative signifierait que les communes les moins chères en 2021 ont le plus augmenté.
L'interprétation reste prudente : l'effet de régression vers la moyenne (une médiane 2021 basse par hasard remonte
mécaniquement) produit le même signe, et la composition des ventes change d'une année à l'autre."""),
    ("md", """## 6. Mesures DAX recalculées en SQL

Power BI Desktop n'est pas installé sur le poste de réalisation : les mesures de `powerbi/mesures.dax` n'ont pas été
exécutées. Chacune est recalculée en SQL (DuckDB) avec la même définition dans plusieurs contextes de filtre."""),
    ("code", """mesures = pd.read_csv(R / "mesures_dax_sql.csv")
mesures[mesures.contexte.isin(["annee=2025, type_bien=Appartement",
                               "annee=2025, type_bien=Appartement, commune=Montpellier"])]"""),
    ("md", """## 7. Limites

- Prix nominaux, non corrigés de l'inflation.
- DVF ne décrit ni l'état du bien, ni l'étage, ni la vue, ni le DPE : un écart de prix entre communes mélange effet
  de localisation et différence de biens vendus.
- Le prix d'une maison inclut son terrain ; le prix au m² bâti des maisons à grand terrain est donc surestimé.
- Seules les ventes d'un seul logement sont gardées (59 % des mutations) : les ventes en bloc et les VEFA
  (logements neufs sur plan) sont exclues, ce qui sous-représente le neuf.
- Les données de l'année la plus récente peuvent encore être complétées lors des mises à jour semestrielles."""),
]


def main() -> None:
    carnet = nbf.v4.new_notebook()
    carnet.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    carnet.cells = [nbf.v4.new_markdown_cell(t) if k == "md" else nbf.v4.new_code_cell(t) for k, t in cellules]
    cible = RACINE / "notebooks" / "analyse.ipynb"
    cible.parent.mkdir(exist_ok=True)
    nbf.write(carnet, cible)
    print(cible.relative_to(RACINE).as_posix())


if __name__ == "__main__":
    main()
