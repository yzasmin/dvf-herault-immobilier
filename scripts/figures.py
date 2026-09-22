"""Graphiques du projet, calculés uniquement à partir des fichiers de results/.

Sorties :
  figures/*.png                      thème clair (README, fiche du portfolio)
  teaser/figure-teaser.png           thème sombre 1600x900 (vidéo de présentation)

Usage : uv run python scripts/figures.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

RACINE = Path(__file__).resolve().parents[1]
RESULTATS = RACINE / "results"
FIGURES = RACINE / "figures"
TEASER = RACINE / "teaser"

COULEURS = {"Appartement": "#1F8A7E", "Maison": "#C8811A"}
VILLES = {"Montpellier": "#1F8A7E", "Sète": "#3C6FB0", "Béziers": "#C8811A"}
GRIS = "#8A8F98"
DECALAGES = {"Montpellier": -9, "Sète": 9, "Béziers": 0}  # points : écarte les étiquettes proches


def euros(x: float, _pos: int | None = None) -> str:
    return f"{x:,.0f}".replace(",", " ") + " €"


def pourcent(x: float) -> str:
    return f"{x * 100:+.1f} %".replace(".", ",")


def style_clair() -> None:
    plt.rcParams.update({
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
        "axes.edgecolor": "#444", "axes.labelcolor": "#222", "text.color": "#222",
        "xtick.color": "#333", "ytick.color": "#333", "font.size": 11,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": "#E4E4E4", "grid.linewidth": 0.8,
    })


def fig_prix(ic: pd.DataFrame, evolutions: pd.DataFrame) -> plt.Figure:
    herault = ic[ic.perimetre == "Hérault"]
    fig, ax = plt.subplots(figsize=(10, 5.6))
    for type_bien, couleur in COULEURS.items():
        d = herault[herault.type_bien == type_bien].sort_values("annee")
        ax.fill_between(d.annee, d.ic95_bas, d.ic95_haut, color=couleur, alpha=0.18, linewidth=0)
        ax.plot(d.annee, d.prix_m2_median, marker="o", color=couleur, linewidth=2.4, label=f"{type_bien}s")
        dernier = d.iloc[-1]
        evo = evolutions[(evolutions.perimetre == "Hérault") & (evolutions.type_bien == type_bien)].iloc[0]
        ax.annotate(f"{euros(dernier.prix_m2_median)}\n{pourcent(evo.evolution)} depuis {int(evo.annee_debut)}",
                    (dernier.annee, dernier.prix_m2_median), xytext=(10, 0), textcoords="offset points",
                    va="center", color=couleur, fontsize=10, fontweight="bold")
    evo_app = evolutions[(evolutions.perimetre == "Hérault") & (evolutions.type_bien == "Appartement")].iloc[0]
    ax.set_title(f"Hérault : prix médian au m² en hausse de {int(evo_app.annee_debut)} à 2023, stable ensuite",
                 fontsize=14, fontweight="bold", loc="left")
    ax.set_ylabel("Prix médian au m² (bande : IC 95 % bootstrap)")
    ax.yaxis.set_major_formatter(FuncFormatter(euros))
    ax.set_xticks(sorted(herault.annee.unique()))
    ax.set_xlim(herault.annee.min() - 0.2, herault.annee.max() + 0.9)
    ax.legend(frameon=False, loc="upper left")
    fig.text(0.01, 0.01, "Source : DVF géolocalisées (Etalab, DGFiP), ventes d'un seul logement, calculs de l'autrice.",
             fontsize=8, color=GRIS)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def fig_volumes(annee_type: pd.DataFrame, cles: dict) -> plt.Figure:
    pivot = annee_type.pivot(index="annee", columns="type_bien", values="nb_ventes").sort_index()
    fig, ax = plt.subplots(figsize=(10, 5.6))
    bas = pd.Series(0, index=pivot.index)
    for type_bien, couleur in COULEURS.items():
        ax.bar(pivot.index, pivot[type_bien], bottom=bas, color=couleur, width=0.62, label=f"{type_bien}s")
        bas = bas + pivot[type_bien]
    for annee, total in bas.items():
        ax.text(annee, total + 250, f"{total:,}".replace(",", " "), ha="center", fontsize=10, fontweight="bold")
    ax.set_title(
        f"Ventes retenues : {pourcent(cles['evolution_volume_creux_vs_debut'])} entre "
        f"{cles['annee_debut']} et {cles['annee_creux_volume']}, "
        f"{pourcent(cles['evolution_volume_fin_vs_creux'])} en {cles['annee_fin']}",
        fontsize=14, fontweight="bold", loc="left")
    ax.set_ylabel("Nombre de ventes")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _p: f"{x:,.0f}".replace(",", " ")))
    ax.set_xticks(pivot.index)
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, loc="upper right")
    fig.text(0.01, 0.01, "Source : DVF géolocalisées (Etalab, DGFiP). Mutations d'un seul logement après nettoyage.",
             fontsize=8, color=GRIS)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def fig_villes(ic: pd.DataFrame, type_bien: str = "Appartement", sombre: bool = False) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(16, 9) if sombre else (10, 5.6), dpi=100 if sombre else None)
    for ville, couleur in VILLES.items():
        c = {"Montpellier": "#ECE8DF", "Sète": "#3FD1BE", "Béziers": "#8A8F98"}[ville] if sombre else couleur
        d = ic[(ic.perimetre == ville) & (ic.type_bien == type_bien)].sort_values("annee")
        ax.fill_between(d.annee, d.ic95_bas, d.ic95_haut, color=c, alpha=0.18, linewidth=0)
        ax.plot(d.annee, d.prix_m2_median, marker="o", color=c, linewidth=3 if sombre else 2.4)
        dernier = d.iloc[-1]
        ax.annotate(f"{ville}  {euros(dernier.prix_m2_median)}", (dernier.annee, dernier.prix_m2_median),
                    xytext=(12, DECALAGES[ville] * (2 if sombre else 1)), textcoords="offset points", va="center", color=c,
                    fontsize=20 if sombre else 10, fontweight="bold")
    herault = ic[(ic.perimetre == "Hérault") & (ic.type_bien == type_bien)].sort_values("annee")
    ax.plot(herault.annee, herault.prix_m2_median, linestyle="--", color=GRIS, linewidth=1.6,
            label=f"Hérault, tous {type_bien.lower()}s")
    legende = ax.legend(frameon=False, loc="center right", fontsize=16 if sombre else 9)
    for texte in legende.get_texts():
        texte.set_color(GRIS)
    ax.yaxis.set_major_formatter(FuncFormatter(euros))
    ax.set_xticks(sorted(herault.annee.unique()))
    ax.set_xlim(herault.annee.min() - 0.2, herault.annee.max() + 1.1)
    titre = f"{type_bien}s : prix médian au m², trois villes de l'Hérault"
    if sombre:
        ax.set_title(titre, fontsize=28, fontweight="bold", loc="left", pad=24)
        ax.tick_params(labelsize=18)
    else:
        ax.set_title(titre, fontsize=14, fontweight="bold", loc="left")
        ax.set_ylabel("Prix médian au m² (bande : IC 95 % bootstrap)")
        fig.text(0.01, 0.01, "Source : DVF géolocalisées (Etalab, DGFiP), calculs de l'autrice.", fontsize=8, color=GRIS)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def fig_communes(commune_annee: pd.DataFrame, annee: int, type_bien: str = "Appartement") -> plt.Figure:
    d = commune_annee[(commune_annee.annee == annee) & (commune_annee.type_bien == type_bien)
                      & commune_annee.prix_m2_median.notna()].sort_values("prix_m2_median")
    fig, ax = plt.subplots(figsize=(10, max(5.6, 0.3 * len(d) + 1.5)))
    couleurs = [VILLES.get(n, "#B9C2C9") for n in d.nom_commune]
    ax.barh(d.nom_commune, d.prix_m2_median, color=couleurs, height=0.7)
    for y, (valeur, n) in enumerate(zip(d.prix_m2_median, d.nb_ventes)):
        ax.text(valeur + 40, y, f"{euros(valeur)}  (n = {n})", va="center", fontsize=8.5, color="#333")
    ax.set_title(f"{type_bien}s vendus en {annee} : prix médian au m² par commune\n"
                 f"({len(d)} communes avec au moins 30 ventes)", fontsize=13, fontweight="bold", loc="left")
    ax.xaxis.set_major_formatter(FuncFormatter(euros))
    ax.set_xlim(0, d.prix_m2_median.max() * 1.28)
    ax.grid(axis="y", visible=False)
    fig.text(0.01, 0.005, "Source : DVF géolocalisées (Etalab, DGFiP). En couleur : Montpellier, Sète, Béziers.",
             fontsize=8, color=GRIS)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    return fig


def style_sombre(fig: plt.Figure) -> None:
    fond, texte = "#0D0F12", "#ECE8DF"
    fig.patch.set_facecolor(fond)
    for ax in fig.axes:
        ax.set_facecolor(fond)
        ax.tick_params(colors=texte)
        ax.title.set_color(texte)
        for spine in ax.spines.values():
            spine.set_color("#3A3F47")
        ax.grid(color="#23272E")


def main() -> None:
    import json

    FIGURES.mkdir(exist_ok=True)
    TEASER.mkdir(exist_ok=True)
    ic = pd.read_csv(RESULTATS / "ic_medianes.csv")
    evolutions = pd.read_csv(RESULTATS / "ic_evolutions.csv")
    annee_type = pd.read_csv(RESULTATS / "ind_annee_type.csv")
    commune_annee = pd.read_csv(RESULTATS / "ind_commune_annee_type.csv", dtype={"code_commune": str})
    cles = json.loads((RESULTATS / "chiffres_cles.json").read_text(encoding="utf-8"))

    style_clair()
    sorties = {
        "01-prix-m2-herault.png": fig_prix(ic, evolutions),
        "02-volumes-annuels.png": fig_volumes(annee_type, cles),
        "03-trois-villes-appartements.png": fig_villes(ic),
        "04-communes-appartements.png": fig_communes(commune_annee, cles["annee_fin"]),
    }
    for nom, fig in sorties.items():
        fig.savefig(FIGURES / nom, dpi=150)
        plt.close(fig)
        print(f"figures/{nom}")

    plt.rcParams.update({"text.color": "#ECE8DF", "axes.labelcolor": "#ECE8DF"})
    fig = fig_villes(ic, sombre=True)
    style_sombre(fig)
    fig.savefig(TEASER / "figure-teaser.png", dpi=100, facecolor="#0D0F12")
    plt.close(fig)
    print("teaser/figure-teaser.png")


if __name__ == "__main__":
    main()
