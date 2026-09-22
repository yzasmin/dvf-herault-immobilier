-- Étape 2 : passer de la ligne (un local x une nature de culture) à la mutation (une vente).
--
-- Dans DVF géolocalisées, une mutation s'étale sur plusieurs lignes : une par local (maison, appartement,
-- dépendance, local d'activité) et par nature de culture du terrain. La valeur foncière est celle de la
-- mutation entière, répétée sur chaque ligne : la sommer compterait le prix plusieurs fois.

-- 2a. Locaux distincts d'une mutation. Une maison posée sur une parcelle à deux natures de culture
--     (sol et jardin) apparaît sur deux lignes identiques pour les colonnes du local : on la compte une fois.
CREATE OR REPLACE TABLE locaux AS
SELECT DISTINCT
    id_mutation, id_parcelle, lot1_numero, code_type_local, type_local,
    surface_reelle_bati, nombre_pieces_principales, code_commune
FROM brut
WHERE code_type_local IS NOT NULL;

-- 2b. Terrain : une ligne par (parcelle, nature de culture) distincte.
CREATE OR REPLACE TABLE terrains AS
SELECT id_mutation, SUM(surface_terrain) AS surface_terrain
FROM (
    SELECT DISTINCT id_mutation, id_parcelle, code_nature_culture, surface_terrain
    FROM brut
    WHERE surface_terrain IS NOT NULL
)
GROUP BY id_mutation;

-- 2c. Une ligne par mutation, avec sa composition.
CREATE OR REPLACE TABLE mutations AS
WITH entete AS (
    SELECT
        id_mutation,
        MIN(date_mutation)                   AS date_mutation,
        COUNT(DISTINCT date_mutation)        AS nb_dates,
        ANY_VALUE(nature_mutation)           AS nature_mutation,
        COUNT(DISTINCT nature_mutation)      AS nb_natures,
        MAX(valeur_fonciere)                 AS valeur_fonciere,
        COUNT(DISTINCT valeur_fonciere)      AS nb_valeurs,
        COUNT(DISTINCT code_commune)         AS nb_communes,
        COUNT(*)                             AS nb_lignes
    FROM brut
    GROUP BY id_mutation
),
composition AS (
    SELECT
        id_mutation,
        COUNT(*) FILTER (WHERE code_type_local = 1) AS nb_maisons,
        COUNT(*) FILTER (WHERE code_type_local = 2) AS nb_appartements,
        COUNT(*) FILTER (WHERE code_type_local = 3) AS nb_dependances,
        COUNT(*) FILTER (WHERE code_type_local = 4) AS nb_locaux_activite
    FROM locaux
    GROUP BY id_mutation
),
logement AS (
    -- Caractéristiques du logement quand la mutation n'en contient qu'un seul.
    SELECT
        id_mutation,
        ANY_VALUE(type_local)                AS type_local,
        ANY_VALUE(surface_reelle_bati)       AS surface_reelle_bati,
        ANY_VALUE(nombre_pieces_principales) AS nombre_pieces_principales,
        ANY_VALUE(code_commune)              AS code_commune
    FROM locaux
    WHERE code_type_local IN (1, 2)
    GROUP BY id_mutation
    HAVING COUNT(*) = 1
)
SELECT
    e.*,
    COALESCE(c.nb_maisons, 0)          AS nb_maisons,
    COALESCE(c.nb_appartements, 0)     AS nb_appartements,
    COALESCE(c.nb_dependances, 0)      AS nb_dependances,
    COALESCE(c.nb_locaux_activite, 0)  AS nb_locaux_activite,
    l.type_local,
    l.surface_reelle_bati,
    l.nombre_pieces_principales,
    l.code_commune,
    t.surface_terrain
FROM entete e
LEFT JOIN composition c USING (id_mutation)
LEFT JOIN logement l USING (id_mutation)
LEFT JOIN terrains t USING (id_mutation);
