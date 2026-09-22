-- Étape 3 : prix au m² aberrants.
-- Règle : pour chaque couple (type de bien, année), on calcule les quartiles Q1 et Q3 du logarithme
-- du prix au m² et on retire les ventes hors de [Q1 - {k} x IQR ; Q3 + {k} x IQR].
-- Le logarithme rend la distribution à peu près symétrique : sans lui, la borne basse serait négative
-- et ne retirerait rien, alors que les ventes à 50 EUR/m² (cessions familiales, parts, erreurs) existent.

CREATE OR REPLACE TABLE bornes_aberrants AS
SELECT
    type_local,
    annee,
    COUNT(*)                                     AS n_candidats,
    QUANTILE_CONT(LN(prix_m2), 0.25)             AS q1_log,
    QUANTILE_CONT(LN(prix_m2), 0.75)             AS q3_log,
    EXP(QUANTILE_CONT(LN(prix_m2), 0.25)
        - {k} * (QUANTILE_CONT(LN(prix_m2), 0.75) - QUANTILE_CONT(LN(prix_m2), 0.25))) AS borne_basse_m2,
    EXP(QUANTILE_CONT(LN(prix_m2), 0.75)
        + {k} * (QUANTILE_CONT(LN(prix_m2), 0.75) - QUANTILE_CONT(LN(prix_m2), 0.25))) AS borne_haute_m2
FROM candidats
GROUP BY type_local, annee;

CREATE OR REPLACE TABLE ventes AS
SELECT c.*
FROM candidats c
JOIN bornes_aberrants b USING (type_local, annee)
WHERE c.prix_m2 BETWEEN b.borne_basse_m2 AND b.borne_haute_m2;
