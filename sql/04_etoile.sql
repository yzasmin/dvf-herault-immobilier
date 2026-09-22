-- Étape 4 : modèle en étoile pour Power BI.
-- fait_ventes (une ligne par vente retenue) relié à dim_date, dim_commune et dim_type_bien.

CREATE OR REPLACE TABLE dim_type_bien AS
SELECT * FROM (VALUES (1, 'Maison'), (2, 'Appartement')) AS t(code_type_bien, type_bien);

-- Nom et code postal les plus fréquents de chaque commune dans les données brutes.
CREATE OR REPLACE TABLE dim_commune AS
WITH noms AS (
    SELECT code_commune, nom_commune, COUNT(*) AS n,
           ROW_NUMBER() OVER (PARTITION BY code_commune ORDER BY COUNT(*) DESC, nom_commune) AS rang
    FROM brut GROUP BY code_commune, nom_commune
),
postaux AS (
    SELECT code_commune, code_postal,
           ROW_NUMBER() OVER (PARTITION BY code_commune ORDER BY COUNT(*) DESC, code_postal) AS rang
    FROM brut WHERE code_postal IS NOT NULL GROUP BY code_commune, code_postal
)
SELECT
    n.code_commune,
    n.nom_commune,
    p.code_postal AS code_postal_principal,
    n.code_commune IN ({villes}) AS ville_suivie
FROM noms n
LEFT JOIN postaux p ON p.code_commune = n.code_commune AND p.rang = 1
WHERE n.rang = 1;

CREATE OR REPLACE TABLE dim_date AS
SELECT
    CAST(d AS DATE)                          AS date,
    YEAR(d)                                  AS annee,
    QUARTER(d)                               AS trimestre,
    MONTH(d)                                 AS mois,
    STRFTIME(d, '%Y-%m')                     AS annee_mois,
    YEAR(d) || '-T' || QUARTER(d)            AS annee_trimestre
FROM GENERATE_SERIES(
    (SELECT DATE_TRUNC('year', MIN(date_mutation)) FROM ventes),
    (SELECT MAKE_DATE(YEAR(MAX(date_mutation)), 12, 31) FROM ventes),
    INTERVAL 1 DAY
) AS g(d);

CREATE OR REPLACE TABLE fait_ventes AS
SELECT
    ROW_NUMBER() OVER (ORDER BY v.date_mutation, v.id_mutation) AS id_vente,
    v.id_mutation,
    v.date_mutation                                          AS date,
    v.code_commune,
    CASE v.type_local WHEN 'Maison' THEN 1 ELSE 2 END        AS code_type_bien,
    v.valeur_fonciere,
    v.surface_reelle_bati                                    AS surface_bati,
    v.nombre_pieces_principales                              AS nb_pieces,
    v.surface_terrain,
    v.nb_dependances,
    v.prix_m2
FROM ventes v;
