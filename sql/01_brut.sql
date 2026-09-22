-- Étape 1 : lecture directe des csv.gz, retrait des doublons exacts, typage.
-- {fichiers} est remplacé par le motif des fichiers bruts (data/raw/dvf_34_*.csv.gz).
-- Tout est lu en texte puis converti avec TRY_CAST : une valeur illisible devient NULL au lieu de bloquer.

CREATE OR REPLACE TABLE brut_lu AS
SELECT * FROM read_csv('{fichiers}', all_varchar = true, header = true);

-- Doublon exact : ligne identique sur les 40 colonnes du fichier.
CREATE OR REPLACE TABLE brut AS
SELECT
    id_mutation,
    TRY_CAST(date_mutation AS DATE)                AS date_mutation,
    nature_mutation,
    TRY_CAST(valeur_fonciere AS DOUBLE)            AS valeur_fonciere,
    code_postal,
    code_commune,
    nom_commune,
    id_parcelle,
    lot1_numero,
    TRY_CAST(code_type_local AS INTEGER)           AS code_type_local,
    type_local,
    TRY_CAST(surface_reelle_bati AS DOUBLE)        AS surface_reelle_bati,
    TRY_CAST(nombre_pieces_principales AS INTEGER) AS nombre_pieces_principales,
    code_nature_culture,
    TRY_CAST(surface_terrain AS DOUBLE)            AS surface_terrain
FROM (SELECT DISTINCT * FROM brut_lu);

DROP TABLE brut_lu;
