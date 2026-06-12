-- Queries analíticas — Spotify Charts: México vs el mundo (2017-2021)
--
-- Cinco queries que usan las técnicas de SQL avanzado del módulo:
--   1. CTE + RANK()          → top 10 artistas por streams en México vs Global
--   2. CTE + LAG()           → evolución trimestral de streams en México
--   3. ROW_NUMBER() rachas   → artistas con más semanas consecutivas en Top 10
--   4. PERCENTILE_CONT       → distribución de streams por año
--   5. CTEs dobles + antipattern → artistas locales invisibles globalmente

SET search_path TO proyecto_spotify;


-- -----------------------------------------------------------------------------
-- Query 1 — Top 10 artistas por streams en México vs Global
-- uso una CTE para calcular los totales primero y luego aplico RANK()
-- para no tener que hacer un subquery anidado feo
-- -----------------------------------------------------------------------------

WITH streams_por_artista AS (
    SELECT
        dr.region,
        dc.artista,
        SUM(fce.streams)                    AS streams_totales,
        COUNT(DISTINCT fce.fecha_key)       AS dias_en_chart
    FROM      fact_chart_entry   fce
    JOIN      dim_cancion        dc  USING (cancion_key)
    JOIN      dim_region         dr  USING (region_key)
    WHERE     fce.chart_key = 1                    -- solo top200 porque viral50 no tiene streams
      AND     fce.streams IS NOT NULL
      AND     (dr.es_mexico OR dr.es_global)       -- filtro los dos que me interesan
    GROUP BY  dr.region, dc.artista
),
ranking AS (
    SELECT
        region,
        artista,
        streams_totales,
        dias_en_chart,
        RANK() OVER (
            PARTITION BY region          -- ranking independiente por región
            ORDER BY streams_totales DESC
        ) AS posicion
    FROM streams_por_artista
)
SELECT *
FROM   ranking
WHERE  posicion <= 10
ORDER  BY region DESC, posicion;


-- -----------------------------------------------------------------------------
-- Query 2 — Evolución trimestral de streams en México con % de cambio
-- LAG() me da el valor del trimestre anterior para calcular el delta
-- -----------------------------------------------------------------------------

WITH trimestral AS (
    SELECT
        df.anio,
        df.trimestre,
        SUM(fce.streams)            AS streams_totales,
        COUNT(DISTINCT dc.artista)  AS artistas_distintos
    FROM      fact_chart_entry  fce
    JOIN      dim_fecha         df  USING (fecha_key)
    JOIN      dim_cancion       dc  USING (cancion_key)
    JOIN      dim_region        dr  USING (region_key)
    WHERE     dr.es_mexico
      AND     fce.chart_key = 1
      AND     fce.streams IS NOT NULL
    GROUP BY  df.anio, df.trimestre
)
SELECT
    anio,
    trimestre,
    streams_totales,
    artistas_distintos,
    LAG(streams_totales) OVER (
        ORDER BY anio, trimestre
    )                               AS streams_trimestre_anterior,
    streams_totales - LAG(streams_totales) OVER (
        ORDER BY anio, trimestre
    )                               AS delta_streams,
    ROUND(
        100.0 * (streams_totales - LAG(streams_totales) OVER (ORDER BY anio, trimestre))
        / NULLIF(LAG(streams_totales) OVER (ORDER BY anio, trimestre), 0),
        1
    )                               AS pct_cambio    -- NULLIF evita división entre cero
FROM  trimestral
ORDER BY anio, trimestre;


-- -----------------------------------------------------------------------------
-- Query 3 — Artistas con más semanas consecutivas en el Top 10 de México
--
-- la técnica para detectar rachas es: semana - ROW_NUMBER() = constante
-- dentro de una racha continua del mismo artista
-- es un truco clásico que vimos en clase y aquí tiene mucho sentido usarlo
-- -----------------------------------------------------------------------------

WITH semanas_top10 AS (
    -- primero saco una fila por artista+semana si estuvo en top 10 esa semana
    SELECT
        dc.artista,
        df.anio,
        df.semana_anio,
        MIN(fce.rank) AS mejor_rank_semana
    FROM      fact_chart_entry  fce
    JOIN      dim_cancion       dc  USING (cancion_key)
    JOIN      dim_fecha         df  USING (fecha_key)
    JOIN      dim_region        dr  USING (region_key)
    WHERE     dr.es_mexico
      AND     fce.chart_key = 1
      AND     fce.rank <= 10
    GROUP BY  dc.artista, df.anio, df.semana_anio
),
numeradas AS (
    SELECT
        artista,
        anio,
        semana_anio,
        mejor_rank_semana,
        -- la resta semana - ROW_NUMBER() da el mismo valor para semanas consecutivas
        -- cuando cambia ese valor significa que hubo un salto (racha interrumpida)
        semana_anio - ROW_NUMBER() OVER (
            PARTITION BY artista
            ORDER BY anio, semana_anio
        ) AS grupo_racha
    FROM semanas_top10
),
rachas AS (
    SELECT
        artista,
        COUNT(*)               AS semanas_consecutivas,
        MIN(semana_anio)       AS semana_inicio,
        MAX(semana_anio)       AS semana_fin,
        MIN(anio)              AS anio_racha,
        MIN(mejor_rank_semana) AS mejor_rank_en_racha
    FROM  numeradas
    GROUP BY artista, grupo_racha
)
SELECT *
FROM   rachas
ORDER  BY semanas_consecutivas DESC, mejor_rank_en_racha
LIMIT  15;


-- -----------------------------------------------------------------------------
-- Query 4 — Distribución de streams por año en México
-- PERCENTILE_CONT me da la mediana y el percentil 95
-- sirve para ver si el "piso" de streams para entrar al chart creció con los años
-- -----------------------------------------------------------------------------

SELECT
    df.anio,
    COUNT(*)                                                        AS entradas,
    ROUND(AVG(fce.streams), 0)                                      AS promedio,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY fce.streams)       AS mediana,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY fce.streams)       AS p95,
    MAX(fce.streams)                                                AS maximo
FROM      fact_chart_entry  fce
JOIN      dim_fecha         df  USING (fecha_key)
JOIN      dim_region        dr  USING (region_key)
WHERE     dr.es_mexico
  AND     fce.chart_key = 1
  AND     fce.streams IS NOT NULL
GROUP BY  df.anio
ORDER BY  df.anio;


-- -----------------------------------------------------------------------------
-- Query 5 — Artistas populares en México pero invisibles globalmente
--
-- esta es la query central del proyecto — responde directamente la pregunta analítica
-- uso dos CTEs y un LEFT JOIN con IS NULL (antipattern) para encontrar
-- artistas que están en México pero nunca aparecieron en el chart global
-- -----------------------------------------------------------------------------

WITH artistas_mexico AS (
    -- artistas con presencia real en México (mínimo 30 entradas para filtrar los que
    -- aparecieron un día y desaparecieron)
    SELECT
        dc.artista,
        COUNT(*)         AS entradas_mx,
        SUM(fce.streams) AS streams_mx,
        MIN(fce.rank)    AS mejor_rank_mx
    FROM      fact_chart_entry  fce
    JOIN      dim_cancion       dc  USING (cancion_key)
    JOIN      dim_region        dr  USING (region_key)
    WHERE     dr.es_mexico
      AND     fce.chart_key = 1
      AND     fce.streams IS NOT NULL
    GROUP BY  dc.artista
    HAVING    COUNT(*) >= 30
),
artistas_global AS (
    -- artistas que sí aparecieron en el chart global en algún momento
    SELECT DISTINCT dc.artista
    FROM      fact_chart_entry  fce
    JOIN      dim_cancion       dc  USING (cancion_key)
    JOIN      dim_region        dr  USING (region_key)
    WHERE     dr.es_global AND fce.chart_key = 1
)
-- el LEFT JOIN + IS NULL me da los que están en México pero NO en global
SELECT
    mx.artista,
    mx.entradas_mx,
    mx.streams_mx,
    mx.mejor_rank_mx
FROM        artistas_mexico  mx
LEFT JOIN   artistas_global  gl  ON mx.artista = gl.artista
WHERE       gl.artista IS NULL
ORDER BY    mx.streams_mx DESC
LIMIT 20;

SELECT region, es_global FROM proyecto_spotify.dim_region 
WHERE es_global = TRUE;