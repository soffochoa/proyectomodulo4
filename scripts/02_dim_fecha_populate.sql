-- =============================================================================
-- Poblar dim_fecha — rango completo del dataset (2017-01-01 a 2021-12-31)
-- =============================================================================
-- Genero esta tabla con generate_series: no depende del CSV, es puro cálculo.
-- Cubre exactamente el rango del dataset de Spotify Charts (Kaggle).
-- =============================================================================

SET search_path TO proyecto_spotify;

INSERT INTO dim_fecha (
    fecha_key,
    fecha_completa,
    anio,
    trimestre,
    mes_numero,
    mes_nombre,
    semana_anio,
    dia_semana_numero,
    dia_semana_nombre,
    es_fin_de_semana
)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT                         AS fecha_key,
    d::DATE                                             AS fecha_completa,
    EXTRACT(YEAR    FROM d)::SMALLINT                   AS anio,
    EXTRACT(QUARTER FROM d)::SMALLINT                   AS trimestre,
    EXTRACT(MONTH   FROM d)::SMALLINT                   AS mes_numero,
    TO_CHAR(d, 'TMMonth')                               AS mes_nombre,
    EXTRACT(WEEK    FROM d)::SMALLINT                   AS semana_anio,
    EXTRACT(ISODOW  FROM d)::SMALLINT                   AS dia_semana_numero,  -- 1=lunes … 7=domingo
    TO_CHAR(d, 'TMDay')                                 AS dia_semana_nombre,
    EXTRACT(ISODOW  FROM d) IN (6, 7)                   AS es_fin_de_semana
FROM generate_series(
    '2017-01-01'::DATE,
    '2021-12-31'::DATE,
    '1 day'::INTERVAL
) AS d
ON CONFLICT (fecha_key) DO NOTHING;   -- idempotente: re-ejecutar no duplica


-- =============================================================================
-- VERIFICACIÓN
-- =============================================================================
-- Comprueba que la tabla quedó con todas las fechas esperadas
 SELECT COUNT(*) FROM proyecto_spotify.dim_fecha;
 -- Esperado: 1826 filas (5 años, 2020 bisiesto)

 SELECT anio, COUNT(*) FROM proyecto_spotify.dim_fecha GROUP BY anio ORDER BY anio;
 -- Esperado: 365, 365, 365, 366, 365
-- =============================================================================