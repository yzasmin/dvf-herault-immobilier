"""Convertit le notebook exécuté en HTML et y insère la balise `noindex`.

Les conditions générales d'utilisation DVF interdisent l'indexation des données par les moteurs de recherche :
toutes les pages publiées sur GitHub Pages portent `<meta name="robots" content="noindex, nofollow">`.
nbconvert ne pose pas cette balise, ce script l'ajoute après la conversion.

Usage : uv run python scripts/exporter_html.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
NOTEBOOK = RACINE / "notebooks" / "analyse.ipynb"
HTML = RACINE / "notebooks" / "analyse.html"
BALISE = '<meta name="robots" content="noindex, nofollow">'


def main() -> None:
    subprocess.run(
        [sys.executable, "-m", "jupyter", "nbconvert", "--to", "html",
         "--output-dir", str(HTML.parent), str(NOTEBOOK)],
        check=True,
    )
    contenu = HTML.read_text(encoding="utf-8")
    if BALISE in contenu:
        print(f"{HTML.name} : balise déjà présente")
        return
    marqueur = "<head>"
    position = contenu.find(marqueur)
    if position == -1:
        raise RuntimeError("Aucune balise <head> dans le HTML produit par nbconvert.")
    coupe = position + len(marqueur)
    HTML.write_text(contenu[:coupe] + "\n" + BALISE + contenu[coupe:], encoding="utf-8")
    print(f"{HTML.name} : balise noindex insérée ({HTML.stat().st_size} octets)")


if __name__ == "__main__":
    main()
