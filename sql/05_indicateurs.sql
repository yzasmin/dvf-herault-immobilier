-- Étape 5 : indicateurs, calculés sur le modèle en étoile avec les mêmes définitions que les mesures DAX
-- (powerbi/mesures.dax). MEDIAN en DAX et MEDIAN en DuckDB interpolent tous deux entre les deux valeurs
-- centrales quand l'effectif est pair.
-- {seuil} : nombre minimal de ventes pour publier une médiane de commune.

CREATE OR REPLACE VIEW ventes_modele AS
SELECT f.*, d.annee, d.trimestre, d.annee_mois, t.type_bien, c.nom_commune, c.ville_suivie
FROM fait_ventes f
JOIN dim_date d USING (date)
JOIN dim_type_bien t USING (code_type_bien)
JOIN dim_commune c USING (code_commune);

-- Département, par année et type de bien.
CREATE OR REPLACE TABLE ind_annee_type AS
WITH base AS (
    SELECT
        annee, type_bien,
        COUNT(*)                          AS nb_ventes,
        MEDIAN(prix_m2)                   AS prix_m2_median,
        QUANTILE_CONT(prix_m2, 0.25)      AS prix_m2_q1,
        QUANTILE_CONT(prix_m2, 0.75)      AS prix_m2_q3,
        AVG(prix_m2)                      AS prix_m2_moyen,
        MEDIAN(valeur_fonciere)           AS valeur_mediane,
        MEDIAN(surface_bati)              AS surface_mediane,
        SUM(valeur_fonciere)              AS valeur_totale
    FROM ventes_modele
    GROUP BY annee, type_bien
)
SELECT
    *,
    prix_m2_median / LAG(prix_m2_median) OVER (PARTITION BY type_bien ORDER BY annee) - 1 AS evolution_prix_m2,
    nb_ventes * 1.0 / LAG(nb_ventes) OVER (PARTITION BY type_bien ORDER BY annee) - 1     AS evolution_volume
FROM base
ORDER BY type_bien, annee;

-- Département, par année, tous types.
CREATE OR REPLACE TABLE ind_annee AS
WITH base AS (
    SELECT annee, COUNT(*) AS nb_ventes, MEDIAN(prix_m2) AS prix_m2_median,
           MEDIAN(valeur_fonciere) AS valeur_mediane, SUM(valeur_fonciere) AS valeur_totale,
           AVG(CASE WHEN type_bien = 'Maison' THEN 1.0 ELSE 0.0 END) AS part_maisons
    FROM ventes_modele GROUP BY annee
)
SELECT *,
       prix_m2_median / LAG(prix_m2_median) OVER (ORDER BY annee) - 1 AS evolution_prix_m2,
       nb_ventes * 1.0 / LAG(nb_ventes) OVER (ORDER BY annee) - 1     AS evolution_volume
FROM base ORDER BY annee;

-- Département, par mois et type de bien.
CREATE OR REPLACE TABLE ind_mois_type AS
SELECT annee_mois, type_bien, COUNT(*) AS nb_ventes, MEDIAN(prix_m2) AS prix_m2_median
FROM ventes_modele
GROUP BY annee_mois, type_bien
ORDER BY type_bien, annee_mois;

-- Commune, par année et type de bien. La médiane n'est publiée qu'à partir de {seuil} ventes.
CREATE OR REPLACE TABLE ind_commune_annee_type AS
SELECT
    code_commune, nom_commune, ville_suivie, annee, type_bien,
    COUNT(*) AS nb_ventes,
    CASE WHEN COUNT(*) >= {seuil} THEN MEDIAN(prix_m2) END AS prix_m2_median
FROM ventes_modele
GROUP BY code_commune, nom_commune, ville_suivie, annee, type_bien
ORDER BY code_commune, type_bien, annee;

-- Commune, par type de bien : première et dernière année, évolution quand les deux sont publiables.
CREATE OR REPLACE TABLE ind_commune_evolution AS
WITH bornes AS (SELECT MIN(annee) AS a0, MAX(annee) AS a1 FROM ventes_modele)
SELECT
    c.code_commune, c.nom_commune, c.type_bien,
    SUM(c.nb_ventes)                                                   AS nb_ventes_periode,
    MAX(CASE WHEN c.annee = b.a0 THEN c.nb_ventes END)                 AS nb_ventes_debut,
    MAX(CASE WHEN c.annee = b.a0 THEN c.prix_m2_median END)            AS prix_m2_median_debut,
    MAX(CASE WHEN c.annee = b.a1 THEN c.nb_ventes END)                 AS nb_ventes_fin,
    MAX(CASE WHEN c.annee = b.a1 THEN c.prix_m2_median END)            AS prix_m2_median_fin,
    MAX(CASE WHEN c.annee = b.a1 THEN c.prix_m2_median END)
      / MAX(CASE WHEN c.annee = b.a0 THEN c.prix_m2_median END) - 1    AS evolution_prix_m2
FROM ind_commune_annee_type c CROSS JOIN bornes b
GROUP BY c.code_commune, c.nom_commune, c.type_bien
ORDER BY c.type_bien, nb_ventes_periode DESC;
