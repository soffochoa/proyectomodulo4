-- dim_region — insertar todas las regiones del dataset
--
-- saqué esta lista revisando los valores únicos de la columna "region" del CSV
-- son 69 regiones en total contando "global"
-- los flags es_global y es_mexico los puse para no tener que escribir
-- WHERE region = 'Mexico' o WHERE region = 'global' en cada query

SET search_path TO proyecto_spotify;

INSERT INTO dim_region (region, es_global, es_mexico) VALUES
    ('global',              TRUE,  FALSE),
    ('Mexico',              FALSE, TRUE),
    ('Argentina',           FALSE, FALSE),
    ('Australia',           FALSE, FALSE),
    ('Austria',             FALSE, FALSE),
    ('Belgium',             FALSE, FALSE),
    ('Bolivia',             FALSE, FALSE),
    ('Brazil',              FALSE, FALSE),
    ('Bulgaria',            FALSE, FALSE),
    ('Canada',              FALSE, FALSE),
    ('Chile',               FALSE, FALSE),
    ('Colombia',            FALSE, FALSE),
    ('Costa Rica',          FALSE, FALSE),
    ('Czech Republic',      FALSE, FALSE),
    ('Denmark',             FALSE, FALSE),
    ('Dominican Republic',  FALSE, FALSE),
    ('Ecuador',             FALSE, FALSE),
    ('Egypt',               FALSE, FALSE),
    ('El Salvador',         FALSE, FALSE),
    ('Estonia',             FALSE, FALSE),
    ('Finland',             FALSE, FALSE),
    ('France',              FALSE, FALSE),
    ('Germany',             FALSE, FALSE),
    ('Greece',              FALSE, FALSE),
    ('Guatemala',           FALSE, FALSE),
    ('Honduras',            FALSE, FALSE),
    ('Hong Kong',           FALSE, FALSE),
    ('Hungary',             FALSE, FALSE),
    ('Iceland',             FALSE, FALSE),
    ('India',               FALSE, FALSE),
    ('Indonesia',           FALSE, FALSE),
    ('Ireland',             FALSE, FALSE),
    ('Israel',              FALSE, FALSE),
    ('Italy',               FALSE, FALSE),
    ('Japan',               FALSE, FALSE),
    ('Latvia',              FALSE, FALSE),
    ('Lithuania',           FALSE, FALSE),
    ('Luxembourg',          FALSE, FALSE),
    ('Malaysia',            FALSE, FALSE),
    ('Malta',               FALSE, FALSE),
    ('Netherlands',         FALSE, FALSE),
    ('New Zealand',         FALSE, FALSE),
    ('Nicaragua',           FALSE, FALSE),
    ('Norway',              FALSE, FALSE),
    ('Panama',              FALSE, FALSE),
    ('Paraguay',            FALSE, FALSE),
    ('Peru',                FALSE, FALSE),
    ('Philippines',         FALSE, FALSE),
    ('Poland',              FALSE, FALSE),
    ('Portugal',            FALSE, FALSE),
    ('Romania',             FALSE, FALSE),
    ('Russia',              FALSE, FALSE),
    ('Saudi Arabia',        FALSE, FALSE),
    ('Singapore',           FALSE, FALSE),
    ('Slovakia',            FALSE, FALSE),
    ('South Africa',        FALSE, FALSE),
    ('South Korea',         FALSE, FALSE),
    ('Spain',               FALSE, FALSE),
    ('Sweden',              FALSE, FALSE),
    ('Switzerland',         FALSE, FALSE),
    ('Taiwan',              FALSE, FALSE),
    ('Thailand',            FALSE, FALSE),
    ('Turkey',              FALSE, FALSE),
    ('Ukraine',             FALSE, FALSE),
    ('United Arab Emirates',FALSE, FALSE),
    ('United Kingdom',      FALSE, FALSE),
    ('United States',       FALSE, FALSE),
    ('Uruguay',             FALSE, FALSE),
    ('Vietnam',             FALSE, FALSE)
ON CONFLICT (region) DO NOTHING;  -- idempotente, se puede re-correr sin problema


-- para verificar:
-- SELECT COUNT(*) FROM proyecto_spotify.dim_region;
-- debería dar 69
--
-- SELECT region FROM proyecto_spotify.dim_region WHERE es_global OR es_mexico;
-- debería mostrar solo 'global' y 'Mexico'