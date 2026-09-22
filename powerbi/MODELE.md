# Modèle sémantique Power BI : DVF Hérault

Schéma en étoile : une table de faits (les ventes) et trois dimensions. Les tables sont produites par
`scripts/pipeline.py` dans `data/processed/powerbi/` en Parquet et en CSV (dossier ignoré par git : il contient
les ventes ligne à ligne, que les conditions d'utilisation DVF interdisent de rediffuser de façon indexable).
Les deux dimensions sans donnée individuelle sont versionnées dans `powerbi/tables/`.

> **Power BI Desktop n'est pas installé sur le poste de réalisation (vérifié le 22/09/2026).** Les mesures de
> `mesures.dax` sont écrites et documentées mais n'ont pas été exécutées dans Power BI. Tous les chiffres publiés
> sont calculés en SQL sur DuckDB avec la même définition, et la correspondance mesure par mesure est enregistrée
> dans `results/mesures_dax_sql.csv`.

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

## Import dans Power BI Desktop

1. **Obtenir les données** > **Parquet** (ou **Texte/CSV**), choisir les quatre fichiers de `data/processed/powerbi/`.
2. Dans le modèle, créer les trois relations ci-dessus (elles sont détectées automatiquement si les noms de colonnes
   sont conservés ; vérifier le sens et la cardinalité).
3. Marquer `dim_date` comme table de dates.
4. Coller les mesures de `mesures.dax` dans une table de mesures dédiée (`_Mesures`), dossiers d'affichage
   « Volumes », « Prix » et « Communes » comme indiqué en commentaire.
5. Masquer dans la vue rapport les colonnes techniques de `fait_ventes` (`id_vente`, `id_mutation`, clés) : les
   visuels se construisent avec les dimensions et les mesures.

## Pages du rapport prévues

1. **Vue d'ensemble** : cartes `[Nb ventes]`, `[Prix m² médian]`, `[Évolution prix m² %]`, courbe du prix médian par
   année et type, histogramme des volumes.
2. **Communes** : carte (longitude/latitude non incluses dans le fait pour rester agrégé ; jointure par code INSEE
   possible), tableau `[Prix m² médian publiable]`, `[Écart à l'Hérault %]`, `[Rang prix commune]`.
3. **Comparaison de villes** : segment `dim_commune[ville_suivie]`, courbes Montpellier, Sète, Béziers.

## Choix de modélisation

- **Prix au m² stocké dans le fait** plutôt que calculé en mesure : la médiane d'un ratio n'est pas le ratio des
  médianes ; il faut le ratio ligne à ligne avant d'agréger.
- **Pas de table de faits agrégée** : 105 463 lignes tiennent sans difficulté en mémoire, l'agrégation se fait à la
  volée et le détail reste disponible.
- **Seuil de publication dans une mesure** (`[Prix m² médian publiable]`) plutôt que dans le pipeline : le seuil
  reste visible et modifiable dans le rapport, alors que les agrégats publiés dans `app/data/` sont déjà filtrés.
- **`dim_commune` sans population ni EPCI** : ces informations viendraient d'une autre source (INSEE) et n'ont pas
  été intégrées ; c'est la première extension utile du modèle.
