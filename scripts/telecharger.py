"""Télécharge les fichiers DVF géolocalisés (Etalab) de l'Hérault, tous millésimes disponibles.

Source : https://files.data.gouv.fr/geo-dvf/latest/csv/<annee>/departements/34.csv.gz
Les fichiers sont écrits dans data/raw/ (ignoré par git) et ne sont jamais commités.
Un manifeste (taille, empreinte SHA-256, date de publication) est écrit dans results/sources.json.

Usage : uv run python scripts/telecharger.py [--departement 34]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
DOSSIER_BRUT = RACINE / "data" / "raw"
MANIFESTE = RACINE / "results" / "sources.json"
BASE_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/"


def lister_millesimes() -> list[int]:
    """Lit l'index du serveur et renvoie les années publiées (ex. [2021, ..., 2025])."""
    with urllib.request.urlopen(BASE_URL, timeout=60) as reponse:
        html = reponse.read().decode("utf-8")
    annees = sorted({int(a) for a in re.findall(r"/csv/(\d{4})/", html)})
    if not annees:
        raise RuntimeError(f"Aucun millésime trouvé dans l'index {BASE_URL}")
    return annees


def date_publication(annee: int, departement: str) -> str | None:
    """Date du fichier telle qu'affichée par l'index du dossier départements."""
    url = f"{BASE_URL}{annee}/departements/"
    with urllib.request.urlopen(url, timeout=60) as reponse:
        html = reponse.read().decode("utf-8")
    motif = rf"{departement}\.csv\.gz</a></td>\s*<td>\s*\d+\s*</td>\s*<td>\s*([^<\s]+)"
    trouve = re.search(motif, html)
    return trouve.group(1) if trouve else None


def telecharger(annee: int, departement: str) -> dict:
    url = f"{BASE_URL}{annee}/departements/{departement}.csv.gz"
    cible = DOSSIER_BRUT / f"dvf_{departement}_{annee}.csv.gz"
    cible.parent.mkdir(parents=True, exist_ok=True)
    temporaire = cible.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=300) as reponse, open(temporaire, "wb") as sortie:
        while bloc := reponse.read(1 << 20):
            sortie.write(bloc)
    temporaire.replace(cible)
    contenu = cible.read_bytes()
    return {
        "annee": annee,
        "url": url,
        "fichier": cible.relative_to(RACINE).as_posix(),
        "octets": len(contenu),
        "sha256": hashlib.sha256(contenu).hexdigest(),
        "date_publication_serveur": date_publication(annee, departement),
    }


def main() -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--departement", default="34")
    args = parseur.parse_args()

    annees = lister_millesimes()
    print(f"Millésimes disponibles : {annees}")
    fichiers = []
    for annee in annees:
        info = telecharger(annee, args.departement)
        print(f"  {annee} : {info['octets']:>10} octets  {info['fichier']}")
        fichiers.append(info)

    MANIFESTE.parent.mkdir(parents=True, exist_ok=True)
    manifeste = {
        "source": "DVF géolocalisées, Etalab (data.gouv.fr), d'après les Demandes de valeurs foncières de la DGFiP",
        "licence": "Licence Ouverte / Open Licence 2.0, conditions générales d'utilisation DVF (art. R. 112 A-3 LPF)",
        "departement": args.departement,
        "telecharge_le": datetime.now(UTC).isoformat(timespec="seconds"),
        "millesimes": annees,
        "fichiers": fichiers,
    }
    MANIFESTE.write_text(json.dumps(manifeste, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Manifeste : {MANIFESTE.relative_to(RACINE).as_posix()}")


if __name__ == "__main__":
    main()
