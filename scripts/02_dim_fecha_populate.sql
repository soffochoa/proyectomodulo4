-- dim_fecha — llenar todos los días del rango 2017-2021
--
-- uso generate_series de PostgreSQL para generar una fila por día
-- sin necesitar el CSV para nada, es puramente matemático
-- el rango cubre exactamente los datos del dataset de Spotify Charts

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
    TO_CHAR(d, 'YYYYMMDD')::INT                         AS fecha_key,       -- ej: 20170115
    d::DATE                                             AS fecha_completa,
    EXTRACT(YEAR    FROM d)::SMALLINT                   AS anio,
    EXTRACT(QUARTER FROM d)::SMALLINT                   AS trimestre,
    EXTRACT(MONTH   FROM d)::SMALLINT                   AS mes_numero,
    TO_CHAR(d, 'TMMonth')                               AS mes_nombre,
    EXTRACT(WEEK    FROM d)::SMALLINT                   AS semana_anio,
    EXTRACT(ISODOW  FROM d)::SMALLINT                   AS dia_semana_numero, -- ISODOW: 1=lunes, 7=domingo
    TO_CHAR(d, 'TMDay')                                 AS dia_semana_nombre,
    EXTRACT(ISODOW  FROM d) IN (6, 7)                   AS es_fin_de_semana   -- sábado o domingo
FROM generate_series(
    '2017-01-01'::DATE,
    '2021-12-31'::DATE,
    '1 day'::INTERVAL
) AS d
ON CONFLICT (fecha_key) DO NOTHING;  -- si se re-corre no duplica nada


-- para verificar:
-- SELECT COUNT(*) FROM proyecto_spotify.dim_fecha;
-- debería dar 1826 (5 años, 2020 fue bisiesto)
--
-- SELECT anio, COUNT(*) FROM proyecto_spotify.dim_fecha GROUP BY anio ORDER BY anio;
-- debería dar: 365, 365, 365, 366, 365