"""Génère le projet Power BI versionnable `powerbi/DVF-Herault.pbip` (modèle TMDL + rapport).

Le modèle sémantique est décrit en TMDL (texte, diffable) et les mesures sont lues dans
`powerbi/mesures.dax` : il n'y a donc qu'une seule définition des mesures dans le dépôt.
Les tables sont chargées depuis les Parquet produits par `scripts/pipeline.py`, via le paramètre
de requête `DossierDonnees` (à adapter après un clone : Power BI Desktop > Transformer les données >
Gérer les paramètres).

Usage : uv run python scripts/construire_pbip.py [--dossier-donnees "C:\\chemin\\vers\\data\\processed\\powerbi"]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import uuid
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
POWERBI = RACINE / "powerbi"
NOM = "DVF-Herault"
MODELE = POWERBI / f"{NOM}.SemanticModel"
RAPPORT = POWERBI / f"{NOM}.Report"

# Colonnes du modèle : (nom, type TMDL, type M, résumé par défaut, format éventuel)
COLONNES = {
    "fait_ventes": [
        ("id_vente", "int64", "Int64.Type", "none", None),
        ("id_mutation", "string", "type text", "none", None),
        ("date", "dateTime", "type date", "none", "Short Date"),
        ("code_commune", "string", "type text", "none", None),
        ("code_type_bien", "int64", "Int64.Type", "none", None),
        ("valeur_fonciere", "double", "type number", "sum", "#,0 €"),
        ("surface_bati", "double", "type number", "sum", "#,0"),
        ("nb_pieces", "int64", "Int64.Type", "sum", None),
        ("surface_terrain", "double", "type number", "sum", "#,0"),
        ("nb_dependances", "int64", "Int64.Type", "sum", None),
        ("prix_m2", "double", "type number", "none", "#,0 €"),
    ],
    "dim_date": [
        ("date", "dateTime", "type date", "none", "Short Date"),
        ("annee", "int64", "Int64.Type", "none", "0"),
        ("trimestre", "int64", "Int64.Type", "none", "0"),
        ("mois", "int64", "Int64.Type", "none", "0"),
        ("annee_mois", "string", "type text", "none", None),
        ("annee_trimestre", "string", "type text", "none", None),
    ],
    "dim_commune": [
        ("code_commune", "string", "type text", "none", None),
        ("nom_commune", "string", "type text", "none", None),
        ("code_postal_principal", "string", "type text", "none", None),
        ("ville_suivie", "boolean", "type logical", "none", None),
    ],
    "dim_type_bien": [
        ("code_type_bien", "int64", "Int64.Type", "none", None),
        ("type_bien", "string", "type text", "none", None),
    ],
}

DOSSIERS_MESURES = {
    "Nb ventes": "Volumes", "Volume d'affaires": "Volumes", "Nb ventes N-1": "Volumes",
    "Évolution volume %": "Volumes", "Part des maisons %": "Volumes",
    "Prix m² médian": "Prix", "Prix m² moyen": "Prix", "Prix m² 1er quartile": "Prix",
    "Prix m² 3e quartile": "Prix", "Valeur médiane": "Prix", "Surface médiane": "Prix",
    "Prix m² médian N-1": "Prix", "Évolution prix m² %": "Prix", "Prix m² médian 2021": "Prix",
    "Évolution depuis 2021 %": "Prix",
    "Seuil de publication": "Communes", "Prix m² médian publiable": "Communes",
    "Prix m² médian Hérault": "Communes", "Écart à l'Hérault %": "Communes",
    "Rang prix commune": "Communes",
}

FORMATS_MESURES = {
    "Nb ventes": "#,0", "Nb ventes N-1": "#,0", "Volume d'affaires": "#,0 €",
    "Évolution volume %": "0.0 %", "Part des maisons %": "0.0 %", "Évolution prix m² %": "0.0 %",
    "Évolution depuis 2021 %": "0.0 %", "Écart à l'Hérault %": "0.0 %",
    "Prix m² médian": "#,0 €", "Prix m² moyen": "#,0 €", "Prix m² 1er quartile": "#,0 €",
    "Prix m² 3e quartile": "#,0 €", "Prix m² médian N-1": "#,0 €", "Prix m² médian 2021": "#,0 €",
    "Prix m² médian publiable": "#,0 €", "Prix m² médian Hérault": "#,0 €",
    "Valeur médiane": "#,0 €", "Surface médiane": "#,0", "Seuil de publication": "0",
    "Rang prix commune": "0",
}


def lire_mesures() -> list[tuple[str, str]]:
    """Extrait (nom, expression) de chaque mesure de powerbi/mesures.dax."""
    texte = (POWERBI / "mesures.dax").read_text(encoding="utf-8")
    mesures = []
    motif = r"^\[(?P<nom>[^\]]+)\] =(?P<corps>(?:.*\n?)*?)(?=^\[|^//|\Z)"
    for bloc in re.finditer(motif, texte, re.MULTILINE):
        lignes = [ligne.strip() for ligne in bloc.group("corps").splitlines() if ligne.strip()]
        if lignes:
            mesures.append((bloc.group("nom"), "\n".join(lignes)))
    return mesures


def nom_tmdl(nom: str) -> str:
    """Identifiant TMDL entre apostrophes ; une apostrophe interne se double."""
    return "'" + nom.replace("'", "''") + "'"


def tmdl_mesure(nom: str, expression: str, indent: str = "\t") -> str:
    lignes = [f"{indent}measure {nom_tmdl(nom)} ="]
    for ligne in expression.splitlines():
        lignes.append(f"{indent}\t\t{ligne.strip()}")
    lignes.append(f"{indent}\tlineageTag: {uuid.uuid4()}")
    if nom in FORMATS_MESURES:
        lignes.append(f"{indent}\tformatString: {FORMATS_MESURES[nom]}")
    if nom in DOSSIERS_MESURES:
        lignes.append(f"{indent}\tdisplayFolder: {DOSSIERS_MESURES[nom]}")
    return "\n".join(lignes) + "\n"


def tmdl_colonnes(table: str) -> str:
    morceaux = []
    for nom, type_tmdl, _type_m, resume, format_ in COLONNES[table]:
        bloc = [f"\tcolumn {nom}", f"\t\tdataType: {type_tmdl}"]
        if table == "dim_date" and nom == "date":
            bloc.append("\t\tisKey")
        if format_:
            bloc.append(f"\t\tformatString: {format_}")
        bloc += [f"\t\tlineageTag: {uuid.uuid4()}", f"\t\tsummarizeBy: {resume}", f"\t\tsourceColumn: {nom}"]
        morceaux.append("\n".join(bloc) + "\n")
    return "\n".join(morceaux)


def tmdl_partition(table: str) -> str:
    transformations = ", ".join(
        f'{{"{nom}", {type_m}}}' for nom, _t, type_m, _r, _f in COLONNES[table]
    )
    m = [
        "let",
        f'    Source = Parquet.Document(File.Contents(DossierDonnees & "\\{table}.parquet")),',
        f"    Types = Table.TransformColumnTypes(Source, {{{transformations}}})",
        "in",
        "    Types",
    ]
    corps = "\n".join(f"\t\t\t\t{ligne}" for ligne in m)
    return (
        f"\tpartition {table} = m\n"
        f"\t\tmode: import\n"
        f"\t\tsource =\n"
        f"{corps}\n"
        f"\n"
    )


def ecrire_modele(dossier_donnees: str) -> None:
    definition = MODELE / "definition"
    tables = definition / "tables"
    tables.mkdir(parents=True, exist_ok=True)

    (MODELE / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": NOM},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (MODELE / "definition.pbism").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.0",
        "settings": {},
    }, indent=2), encoding="utf-8")

    (definition / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1550\n", encoding="utf-8")

    (definition / "expressions.tmdl").write_text(
        "/// Dossier contenant les Parquet produits par scripts/pipeline.py.\n"
        "/// Après un clone, adapter ce paramètre au chemin local.\n"
        f'expression DossierDonnees = "{dossier_donnees}" meta [IsParameterQuery=true, Type="Text", '
        "IsParameterQueryRequired=true]\n"
        f"\tlineageTag: {uuid.uuid4()}\n"
        "\n"
        "\tannotation PBI_ResultType = Text\n",
        encoding="utf-8",
    )

    (definition / "model.tmdl").write_text(
        "model Model\n"
        "\tculture: fr-FR\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: fr-FR\n"
        "\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n"
        "\t\treturnErrorValuesAsNull\n"
        "\n"
        "ref table fait_ventes\n"
        "ref table dim_date\n"
        "ref table dim_commune\n"
        "ref table dim_type_bien\n"
        "ref table Mesures\n",
        encoding="utf-8",
    )

    titres = {
        "fait_ventes": "Une ligne par vente retenue (mutation portant sur un seul logement).",
        "dim_date": "Table de dates, du 1er janvier de la première année au 31 décembre de la dernière.",
        "dim_commune": "Communes de l'Hérault présentes dans les DVF.",
        "dim_type_bien": "Maison ou appartement.",
    }
    for table in COLONNES:
        contenu = [f"/// {titres[table]}", f"table {table}", f"\tlineageTag: {uuid.uuid4()}"]
        if table == "dim_date":
            contenu.append("\tdataCategory: Time")
        contenu.append("")
        contenu.append(tmdl_colonnes(table))
        if table == "dim_date":
            contenu.append(
                "\thierarchy Calendrier\n"
                f"\t\tlineageTag: {uuid.uuid4()}\n"
                "\n"
                "\t\tlevel Annee\n"
                f"\t\t\tlineageTag: {uuid.uuid4()}\n"
                "\t\t\tcolumn: annee\n"
                "\n"
                "\t\tlevel Trimestre\n"
                f"\t\t\tlineageTag: {uuid.uuid4()}\n"
                "\t\t\tcolumn: annee_trimestre\n"
                "\n"
                "\t\tlevel Mois\n"
                f"\t\t\tlineageTag: {uuid.uuid4()}\n"
                "\t\t\tcolumn: annee_mois\n"
            )
        contenu.append(tmdl_partition(table))
        (tables / f"{table}.tmdl").write_text("\n".join(contenu), encoding="utf-8")

    mesures = lire_mesures()
    bloc_mesures = [
        "/// Table technique qui porte les mesures (aucune donnée).",
        "table Mesures",
        f"\tlineageTag: {uuid.uuid4()}",
        "",
    ]
    bloc_mesures += [tmdl_mesure(nom, expression) for nom, expression in mesures]
    bloc_mesures.append(
        "\tcolumn Value\n"
        "\t\tisHidden\n"
        "\t\tformatString: 0\n"
        f"\t\tlineageTag: {uuid.uuid4()}\n"
        "\t\tsummarizeBy: none\n"
        "\t\tsourceColumn: [Value]\n"
        "\n"
        "\t\tannotation SummarizationSetBy = Automatic\n"
        "\n"
        "\tpartition Mesures = calculated\n"
        "\t\tmode: import\n"
        '\t\tsource = ROW("Value", 0)\n'
    )
    (tables / "Mesures.tmdl").write_text("\n".join(bloc_mesures), encoding="utf-8")

    relations = [
        ("fait_ventes", "date", "dim_date", "date"),
        ("fait_ventes", "code_commune", "dim_commune", "code_commune"),
        ("fait_ventes", "code_type_bien", "dim_type_bien", "code_type_bien"),
    ]
    blocs = []
    for table_fait, colonne_fait, table_dim, colonne_dim in relations:
        blocs.append(
            f"relationship {uuid.uuid4()}\n"
            f"\tfromColumn: {table_fait}.{colonne_fait}\n"
            f"\ttoColumn: {table_dim}.{colonne_dim}\n"
        )
    (definition / "relationships.tmdl").write_text("\n".join(blocs), encoding="utf-8")
    print(f"modèle : {len(mesures)} mesures, {len(COLONNES)} tables, {len(relations)} relations")


def carte(nom_mesure: str, x: int, y: int, largeur: int, hauteur: int, identifiant: str) -> dict:
    config = {
        "name": identifiant,
        "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": largeur, "height": hauteur}}],
        "singleVisual": {
            "visualType": "card",
            "projections": {"Values": [{"queryRef": f"Mesures.{nom_mesure}"}]},
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "m", "Entity": "Mesures", "Type": 0}],
                "Select": [{
                    "Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": nom_mesure},
                    "Name": f"Mesures.{nom_mesure}",
                }],
            },
            "drillFilterOtherVisuals": True,
            "vcObjects": {"title": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": f"'{nom_mesure}'"}}},
            }}]},
        },
    }
    return {"x": x, "y": y, "z": 0, "width": largeur, "height": hauteur,
            "config": json.dumps(config, ensure_ascii=False)}


def visuel_categorie(type_visuel: str, mesure: str, entite: str, colonne: str, titre: str,
                     x: int, y: int, largeur: int, hauteur: int, identifiant: str,
                     role_categorie: str = "Category", role_valeur: str = "Y",
                     trier_par_mesure: bool = False) -> dict:
    tri = ([{"Direction": 2, "Expression": {
                "Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": mesure}}}]
           if trier_par_mesure else
           [{"Direction": 1, "Expression": {
                "Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": colonne}}}])
    config = {
        "name": identifiant,
        "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": largeur, "height": hauteur}}],
        "singleVisual": {
            "visualType": type_visuel,
            "projections": {
                role_categorie: [{"queryRef": f"{entite}.{colonne}"}],
                role_valeur: [{"queryRef": f"Mesures.{mesure}"}],
            },
            "prototypeQuery": {
                "Version": 2,
                "From": [
                    {"Name": "d", "Entity": entite, "Type": 0},
                    {"Name": "m", "Entity": "Mesures", "Type": 0},
                ],
                "Select": [
                    {"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": colonne},
                     "Name": f"{entite}.{colonne}"},
                    {"Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": mesure},
                     "Name": f"Mesures.{mesure}"},
                ],
                "OrderBy": tri,
            },
            "drillFilterOtherVisuals": True,
            "vcObjects": {"title": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": f"'{titre}'"}}},
            }}]},
        },
    }
    return {"x": x, "y": y, "z": 0, "width": largeur, "height": hauteur,
            "config": json.dumps(config, ensure_ascii=False)}


def tableau(entite: str, colonne: str, mesures: list[str], titre: str, x: int, y: int,
            largeur: int, hauteur: int, identifiant: str) -> dict:
    """Tableau : une ligne par valeur de `colonne`, une colonne par mesure."""
    selection = [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": colonne},
                  "Name": f"{entite}.{colonne}"}]
    selection += [{"Measure": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": mesure},
                   "Name": f"Mesures.{mesure}"} for mesure in mesures]
    config = {
        "name": identifiant,
        "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": largeur, "height": hauteur}}],
        "singleVisual": {
            "visualType": "tableEx",
            "projections": {"Values": [{"queryRef": f"{entite}.{colonne}"}]
                            + [{"queryRef": f"Mesures.{mesure}"} for mesure in mesures]},
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "d", "Entity": entite, "Type": 0},
                         {"Name": "m", "Entity": "Mesures", "Type": 0}],
                "Select": selection,
                "OrderBy": [{"Direction": 1, "Expression": {
                    "Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": colonne}}}],
            },
            "drillFilterOtherVisuals": True,
            "vcObjects": {"title": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": f"'{titre}'"}}},
            }}]},
        },
    }
    return {"x": x, "y": y, "z": 0, "width": largeur, "height": hauteur,
            "config": json.dumps(config, ensure_ascii=False)}


def segment(entite: str, colonne: str, titre: str, x: int, y: int, largeur: int, hauteur: int,
            identifiant: str) -> dict:
    config = {
        "name": identifiant,
        "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": largeur, "height": hauteur}}],
        "singleVisual": {
            "visualType": "slicer",
            "projections": {"Values": [{"queryRef": f"{entite}.{colonne}"}]},
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": "d", "Entity": entite, "Type": 0}],
                "Select": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": colonne},
                            "Name": f"{entite}.{colonne}"}],
            },
            "drillFilterOtherVisuals": True,
            "vcObjects": {"title": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": f"'{titre}'"}}},
            }}]},
        },
    }
    return {"x": x, "y": y, "z": 0, "width": largeur, "height": hauteur,
            "config": json.dumps(config, ensure_ascii=False)}


def ecrire_rapport() -> None:
    RAPPORT.mkdir(parents=True, exist_ok=True)
    (RAPPORT / ".platform").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": NOM},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (RAPPORT / "definition.pbir").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/1.0.0/schema.json",
        "version": "1.0",
        "datasetReference": {"byPath": {"path": f"../{NOM}.SemanticModel"}},
    }, indent=2), encoding="utf-8")

    visuels = [
        carte("Nb ventes", 20, 16, 290, 120, "carteVentes"),
        carte("Prix m² médian", 325, 16, 290, 120, "cartePrix"),
        carte("Part des maisons %", 630, 16, 290, 120, "carteMaisons"),
        carte("Volume d'affaires", 935, 16, 290, 120, "carteVolume"),
        visuel_categorie("lineChart", "Prix m² médian", "dim_date", "annee",
                         "Prix médian au m² par année", 20, 148, 600, 250, "courbePrix"),
        visuel_categorie("columnChart", "Nb ventes", "dim_date", "annee",
                         "Nombre de ventes par année", 630, 148, 595, 250, "barresVentes"),
        tableau("dim_date", "annee",
                ["Nb ventes", "Prix m² médian", "Évolution prix m² %", "Évolution volume %"],
                "Par année : volumes, prix et évolutions", 20, 408, 600, 290, "tableauAnnees"),
        visuel_categorie("barChart", "Prix m² médian publiable", "dim_commune", "nom_commune",
                         "Communes les plus chères (au moins 30 ventes)",
                         630, 408, 400, 290, "barresCommunes", trier_par_mesure=True),
        segment("dim_type_bien", "type_bien", "Type de bien", 1040, 408, 185, 140, "segmentType"),
        segment("dim_date", "annee", "Année", 1040, 558, 185, 140, "segmentAnnee"),
    ]
    rapport = {
        "config": json.dumps({
            "version": "5.55",
            "themeCollection": {"baseTheme": {"name": "CY24SU10", "version": "5.55", "type": 2}},
            "activeSectionIndex": 0,
            "defaultDrillFilterOtherVisuals": True,
            "settings": {"useStylableVisualContainerHeader": True},
        }, ensure_ascii=False),
        "layoutOptimization": 0,
        "resourcePackages": [{"resourcePackage": {
            "disabled": False,
            "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": 202}],
            "name": "SharedResources", "type": 2,
        }}],
        "sections": [{
            "config": "{}",
            "displayName": "Vue d'ensemble",
            "displayOption": 1,
            "filters": "[]",
            "height": 720.0,
            "name": "pageVueDensemble",
            "ordinal": 0,
            "visualContainers": visuels,
            "width": 1280.0,
        }],
    }
    (RAPPORT / "report.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rapport : 1 page, {len(visuels)} visuels")


def main() -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--dossier-donnees",
                         default=str((RACINE / "data" / "processed" / "powerbi").resolve()))
    args = parseur.parse_args()

    for dossier in (MODELE, RAPPORT):
        if dossier.exists():
            shutil.rmtree(dossier)
    POWERBI.mkdir(exist_ok=True)

    (POWERBI / f"{NOM}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NOM}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    }, indent=2), encoding="utf-8")

    ecrire_modele(args.dossier_donnees)
    ecrire_rapport()
    print(f"projet : {(POWERBI / f'{NOM}.pbip').relative_to(RACINE).as_posix()}")


if __name__ == "__main__":
    main()
