# Modèle sémantique Power BI : DVF Hérault

Schéma en étoile : une table de faits (les ventes) et trois dimensions. Les tables sont produites par
`scripts/pipeline.py` dans `data/processed/powerbi/` en Parquet et en CSV (dossier ignoré par git : il contient
les ventes ligne à ligne, que les conditions d'utilisation DVF interdisent de rediffuser de façon indexable).
Les deux dimensions sans donnée individuelle sont versionnées dans `powerbi/tables/`.

Le projet est livré au format **Power BI Project (`.pbip`)** : le modèle sémantique est écrit en **TMDL**
(texte, lisible et diffable) et le rapport en JSON. Tout est généré par `scripts/construire_pbip.py`, qui lit les
mesures directement dans `mesures.dax` : il n'existe donc qu'une seule définition des mesures dans le dépôt.

> **Vérifié le 23/09/2026 :** le projet a été ouvert dans Power BI Desktop 2.157.1354.0 (version Microsoft Store).
> Le modèle se charge, l'actualisation importe les 105 463 ventes et les 20 mesures s'évaluent. Les valeurs
> renvoyées par le moteur ont été comparées aux mêmes mesures recalculées en SQL (DuckDB) :
> **129 comparaisons, 15 mesures, 10 contextes de filtre, aucune différence** (écart relatif maximal 4,8e-14,
> c'est-à-dire l'arrondi du flottant). Détail : `results/concordance_dax_powerbi.csv`. Capture du rapport :
> `capture-rapport.png`.

## Tables

| Table | Grain | Lignes (exécution du 22/09/2026) | Colonnes clés |
| --- | --- | --- | --- |
| `fait_ventes` | une vente (mutation d'un seul logement) | 105 463 | `id_vente`, `date`, `code_commune`, `code_type_bien`, `valeur_fonciere`, `surface_bati`, `nb_pieces`, `surface_terrain`, `nb_dependances`, `prix_m2` |
| `dim_date` | un jour | 1 826 | `date`, `annee`, `trimestre`, `mois`, `annee_mois`, `annee_trimestre` |
| `dim_commune` | une commune | 342 | `code_commune`, `nom_commune`, `code_postal_principal`, `ville_suivie` |
| `dim_type_bien` | un type de bien | 2 | `code_type_bien`, `type_bien` |

## Relations

| De | Vers | Cardinalité | Sens du filtre |
| --- | --- | --- | --- |
| `dim_date[date]` | `fait_ventes[date]` | un à plusieurs | simple |
| `dim_commune[code_commune]` | `fait_ventes[code_commune]` | un à plusieurs | simple |
| `dim_type_bien[code_type_bien]` | `fait_ventes[code_type_bien]` | un à plusieurs | simple |

`dim_date` est marquée comme table de dates (« Marquer comme table de dates » sur la colonne `date`) : c'est ce qui
rend utilisables les fonctions de temps et garantit qu'aucune date ne manque entre le 1er janvier 2021 et le
31 décembre 2025.

## Ouvrir le projet

1. `uv run python scripts/telecharger.py` puis `uv run python scripts/pipeline.py` : les Parquet du modèle sont
   écrits dans `data/processed/powerbi/`.
2. `uv run python scripts/construire_pbip.py --dossier-donnees "<chemin absolu vers data/processed/powerbi>"` :
   le paramètre de requête `DossierDonnees` est écrit dans le modèle. Sans argument, le script prend le chemin
   du clone courant.
3. Ouvrir `powerbi/DVF-Herault.pbip` dans Power BI Desktop (le double clic fonctionne si l'extension `.pbip` est
   associée ; sinon **Fichier > Ouvrir**).
4. Au premier chargement, Power BI signale que les tables sont vides : cliquer **Actualiser** dans le ruban
   Accueil (environ une minute, 105 463 lignes importées). La table `Mesures` est une table calculée : elle exige
   cette actualisation manuelle.
5. Le paramètre se change ensuite dans **Transformer les données > Gérer les paramètres > DossierDonnees**.

## Contrôle des mesures depuis l'extérieur de Power BI

Power BI Desktop expose un moteur Analysis Services local ; `scripts/executer_dax.ps1` s'y connecte avec le client
ADOMD livré avec Power BI, exécute les requêtes de `powerbi/controles/*.dax` et écrit les résultats dans
`results/powerbi/`. `scripts/concordance.py` compare ensuite ces valeurs à celles de `results/mesures_dax_sql.csv`
(DuckDB) et produit `results/concordance_dax_powerbi.csv`.

```powershell
.\scripts\executer_dax.ps1          # Power BI Desktop doit être ouvert sur le .pbip et actualisé
uv run python scripts/concordance.py
```

## Page du rapport

**Vue d'ensemble** (livrée) : quatre cartes (`[Nb ventes]`, `[Prix m² médian]`, `[Part des maisons %]`,
`[Volume d'affaires]`), courbe du prix médian par année, histogramme des volumes, tableau par année
(`[Évolution prix m² %]`, `[Évolution volume %]`), barres des communes les plus chères
(`[Prix m² médian publiable]`), segments type de bien et année.

Attention à la ligne « Total » du tableau : les mesures d'évolution y comparent la valeur toutes années confondues
à celle de l'année précédente, ce qui n'a pas de sens métier. Elles se lisent ligne par ligne.

Pages à ajouter : **Communes** (carte par code INSEE, `[Écart à l'Hérault %]`, `[Rang prix commune]`) et
**Comparaison de villes** (segment `dim_commune[ville_suivie]`).

## Choix de modélisation

- **Prix au m² stocké dans le fait** plutôt que calculé en mesure : la médiane d'un ratio n'est pas le ratio des
  médianes ; il faut le ratio ligne à ligne avant d'agréger.
- **Pas de table de faits agrégée** : 105 463 lignes tiennent sans difficulté en mémoire, l'agrégation se fait à la
  volée et le détail reste disponible.
- **Seuil de publication dans une mesure** (`[Prix m² médian publiable]`) plutôt que dans le pipeline : le seuil
  reste visible et modifiable dans le rapport, alors que les agrégats publiés dans `app/data/` sont déjà filtrés.
- **`dim_commune` sans population ni EPCI** : ces informations viendraient d'une autre source (INSEE) et n'ont pas
  été intégrées ; c'est la première extension utile du modèle.
- **`.pbip` versionné, `.pbix` non publié** : le `.pbip` ne contient que des définitions (TMDL et JSON), donc aucune
  donnée. Un `.pbix` embarque au contraire les 105 463 ventes ligne à ligne dans son modèle compressé ; le publier
  dans un dépôt public indexable irait contre les conditions d'utilisation DVF appliquées partout ailleurs dans ce
  projet (pas d'indexation des données par les moteurs de recherche). Ce n'est pas une question de taille : le
  Parquet du fait ne pèse que 2,4 Mo. Chacun peut reconstruire un `.pbix` en local avec
  **Fichier > Enregistrer sous** après avoir actualisé le projet.
