"""Démo : marché immobilier de l'Hérault (DVF 2021-2025).

Lit uniquement des agrégats (app/data/*.csv, quelques centaines de Ko) : aucune vente individuelle.
Fonctionne en local (uv run streamlit run app/streamlit_app.py) et dans le navigateur via stlite.
"""

from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DONNEES = Path(__file__).resolve().parent / "data"
SEUIL = 30
VILLES = ["Montpellier", "Sète", "Béziers"]
COULEURS_TYPES = alt.Scale(domain=["Appartement", "Maison"], range=["#1F8A7E", "#C8811A"])
COULEURS_VILLES = alt.Scale(domain=VILLES, range=["#1F8A7E", "#3C6FB0", "#C8811A"])

st.set_page_config(page_title="Immobilier dans l'Hérault (DVF)", layout="wide")


@st.cache_data
def charger(nom: str) -> pd.DataFrame:
    return pd.read_csv(DONNEES / f"{nom}.csv", dtype={"code_commune": str})


def euros(valeur: float) -> str:
    return f"{valeur:,.0f}".replace(",", " ") + " €"


def pourcent(valeur: float) -> str:
    return f"{valeur * 100:+.1f} %".replace(".", ",")


annee_type = charger("ind_annee_type")
communes = charger("ind_commune_annee_type")
ic = charger("ic_medianes")
mois = charger("ind_mois_type")
annees = sorted(annee_type.annee.unique())

st.title("Marché immobilier de l'Hérault, 2021-2025")
st.caption(
    "Ventes d'un seul logement (maison ou appartement) issues des Demandes de valeurs foncières "
    "géolocalisées (Etalab, DGFiP), après nettoyage. Prix au m² = valeur foncière / surface bâtie. "
    f"Une médiane de commune n'est affichée qu'à partir de {SEUIL} ventes."
)

with st.sidebar:
    st.header("Filtres")
    type_bien = st.radio("Type de bien", ["Appartement", "Maison"], horizontal=True)
    annee = st.select_slider("Année", options=annees, value=annees[-1])
    st.markdown(
        "Source : [DVF géolocalisées](https://www.data.gouv.fr/fr/datasets/demandes-de-valeurs-foncieres-geolocalisees/), "
        "Licence Ouverte 2.0. Code : [dvf-herault-immobilier](https://github.com/yzasmin/dvf-herault-immobilier)."
    )

ligne = annee_type[(annee_type.annee == annee) & (annee_type.type_bien == type_bien)].iloc[0]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Ventes retenues", f"{int(ligne.nb_ventes):,}".replace(",", " "),
          None if pd.isna(ligne.evolution_volume) else pourcent(ligne.evolution_volume))
k2.metric("Prix médian au m²", euros(ligne.prix_m2_median),
          None if pd.isna(ligne.evolution_prix_m2) else pourcent(ligne.evolution_prix_m2))
k3.metric("Valeur médiane", euros(ligne.valeur_mediane))
k4.metric("Surface médiane", f"{ligne.surface_mediane:.0f} m²")
st.caption("Variation par rapport à l'année précédente, même type de bien.")

onglet_dep, onglet_villes, onglet_communes, onglet_commune = st.tabs(
    ["Hérault", "Montpellier, Sète, Béziers", "Classement des communes", "Une commune"]
)

with onglet_dep:
    herault = ic[ic.perimetre == "Hérault"]
    base = alt.Chart(herault).encode(x=alt.X("annee:O", title=None))
    bande = base.mark_area(opacity=0.2).encode(
        y=alt.Y("ic95_bas:Q", title="Prix médian au m² (€)", scale=alt.Scale(zero=False)),
        y2="ic95_haut:Q", color=alt.Color("type_bien:N", scale=COULEURS_TYPES, title=None),
    )
    courbe = base.mark_line(point=True).encode(
        y="prix_m2_median:Q", color=alt.Color("type_bien:N", scale=COULEURS_TYPES, title=None),
        tooltip=[alt.Tooltip("annee:O", title="Année"), alt.Tooltip("type_bien:N", title="Type"),
                 alt.Tooltip("prix_m2_median:Q", title="Médiane €/m²", format=",.0f"),
                 alt.Tooltip("ic95_bas:Q", title="IC 95 % bas", format=",.0f"),
                 alt.Tooltip("ic95_haut:Q", title="IC 95 % haut", format=",.0f"),
                 alt.Tooltip("nb_ventes:Q", title="Ventes")],
    )
    gauche, droite = st.columns(2)
    gauche.subheader("Prix médian au m² (IC 95 % bootstrap)")
    gauche.altair_chart((bande + courbe).properties(height=320), use_container_width=True)
    droite.subheader("Nombre de ventes par an")
    barres = alt.Chart(annee_type).mark_bar().encode(
        x=alt.X("annee:O", title=None), y=alt.Y("nb_ventes:Q", title="Ventes"),
        color=alt.Color("type_bien:N", scale=COULEURS_TYPES, title=None),
        tooltip=["annee:O", "type_bien:N", alt.Tooltip("nb_ventes:Q", title="Ventes")],
    )
    droite.altair_chart(barres.properties(height=320), use_container_width=True)
    st.subheader("Série mensuelle")
    serie = mois[mois.type_bien == type_bien].copy()
    serie["mois"] = pd.to_datetime(serie.annee_mois + "-01")
    ligne_mois = alt.Chart(serie).mark_line(color="#1F8A7E" if type_bien == "Appartement" else "#C8811A").encode(
        x=alt.X("mois:T", title=None),
        y=alt.Y("prix_m2_median:Q", title="Prix médian au m² (€)", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("annee_mois:N", title="Mois"),
                 alt.Tooltip("prix_m2_median:Q", title="Médiane €/m²", format=",.0f"),
                 alt.Tooltip("nb_ventes:Q", title="Ventes")],
    )
    st.altair_chart(ligne_mois.properties(height=260), use_container_width=True)

with onglet_villes:
    villes = ic[ic.perimetre.isin(VILLES) & (ic.type_bien == type_bien)]
    base = alt.Chart(villes).encode(x=alt.X("annee:O", title=None))
    graphique = base.mark_area(opacity=0.18).encode(
        y=alt.Y("ic95_bas:Q", title="Prix médian au m² (€)", scale=alt.Scale(zero=False)), y2="ic95_haut:Q",
        color=alt.Color("perimetre:N", scale=COULEURS_VILLES, title=None),
    ) + base.mark_line(point=True).encode(
        y="prix_m2_median:Q", color=alt.Color("perimetre:N", scale=COULEURS_VILLES, title=None),
        tooltip=[alt.Tooltip("perimetre:N", title="Ville"), alt.Tooltip("annee:O", title="Année"),
                 alt.Tooltip("prix_m2_median:Q", title="Médiane €/m²", format=",.0f"),
                 alt.Tooltip("nb_ventes:Q", title="Ventes")],
    )
    st.altair_chart(graphique.properties(height=360), use_container_width=True)
    tableau = villes.pivot(index="perimetre", columns="annee", values="prix_m2_median").reindex(VILLES)
    st.dataframe(tableau.style.format(lambda v: euros(v)), use_container_width=True)
    st.caption("Bande : intervalle de confiance à 95 % de la médiane (2 000 rééchantillonnages bootstrap).")

with onglet_communes:
    classement = communes[(communes.annee == annee) & (communes.type_bien == type_bien)
                          & communes.prix_m2_median.notna()].sort_values("prix_m2_median", ascending=False)
    total = communes[(communes.annee == annee) & (communes.type_bien == type_bien)]
    st.write(
        f"{len(classement)} communes sur {len(total)} ayant au moins une vente atteignent le seuil de {SEUIL} ventes "
        f"({type_bien.lower()}s, {annee})."
    )
    barres = alt.Chart(classement).mark_bar().encode(
        y=alt.Y("nom_commune:N", sort="-x", title=None),
        x=alt.X("prix_m2_median:Q", title="Prix médian au m² (€)"),
        color=alt.condition(alt.datum.ville_suivie, alt.value("#1F8A7E"), alt.value("#B9C2C9")),
        tooltip=[alt.Tooltip("nom_commune:N", title="Commune"),
                 alt.Tooltip("prix_m2_median:Q", title="Médiane €/m²", format=",.0f"),
                 alt.Tooltip("nb_ventes:Q", title="Ventes")],
    )
    st.altair_chart(barres.properties(height=max(300, 18 * len(classement))), use_container_width=True)

with onglet_commune:
    noms = sorted(communes.nom_commune.unique())
    choix = st.selectbox("Commune", noms, index=noms.index("Montpellier"))
    detail = communes[(communes.nom_commune == choix) & (communes.type_bien == type_bien)].sort_values("annee")
    if detail.empty:
        st.info(f"Aucune vente de {type_bien.lower()} retenue à {choix}.")
    else:
        affichage = detail[["annee", "nb_ventes", "prix_m2_median"]].rename(
            columns={"annee": "Année", "nb_ventes": "Ventes", "prix_m2_median": "Prix médian au m²"})
        affichage["Prix médian au m²"] = affichage["Prix médian au m²"].map(
            lambda v: euros(v) if pd.notna(v) else f"non publié (< {SEUIL} ventes)")
        st.dataframe(affichage, hide_index=True, use_container_width=True)

st.divider()
st.caption(
    "Données : DGFiP, Demandes de valeurs foncières, via les DVF géolocalisées d'Etalab (Licence Ouverte 2.0). "
    "Seuls des agrégats sont affichés ; les conditions d'utilisation interdisent la réidentification des personnes. "
    "Prix nominaux, non corrigés de l'inflation."
)
