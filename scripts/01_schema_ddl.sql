-- =============================================================================
-- Proyecto Final — Spotify Charts: México vs el mundo (2017-2021)
-- =============================================================================
-- Schema  : proyecto_spotify
-- Grano   : una fila por (canción × región × chart × fecha)
--           = una entrada en un chart de Spotify para un día y región concretos
-- Fuente  : charts.csv — Top 200 y Viral 50 (descargado de Kaggle)
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS proyecto_spotify;
SET search_path TO proyecto_spotify;
-- -----------------------------------------------------------------------------
-- DIMENSIONES
-- -----------------------------------------------------------------------------

-- Dimensión fecha
-- Me permite agrupar por año/trimestre/mes y detectar patrones en el tiempo.
-- Uso una "smart key" (YYYYMMDD como INT) para joins simples y rápidos.
CREATE TABLE dim_fecha (
    fecha_key           INT          PRIMARY KEY,        -- smart key YYYYMMDD
    fecha_completa      DATE         NOT NULL UNIQUE,
    anio                SMALLINT     NOT NULL,
    trimestre           SMALLINT     NOT NULL,           -- 1-4
    mes_numero          SMALLINT     NOT NULL,           -- 1-12
    mes_nombre          VARCHAR(12)  NOT NULL,
    semana_anio         SMALLINT     NOT NULL,           -- ISO week 1-53
    dia_semana_numero   SMALLINT     NOT NULL,           -- 1=lunes … 7=domingo
    dia_semana_nombre   VARCHAR(10)  NOT NULL,
    es_fin_de_semana    BOOLEAN      NOT NULL
);

-- Dimensión canción
-- Incluyo artista como atributo directo porque el CSV guarda el artista como
-- una sola cadena (p. ej. "DJ Snake, Justin Bieber"). Hacer una tabla puente
-- many-to-many complicaría el modelo sin aportar mucho para estas preguntas.
CREATE TABLE dim_cancion (
    cancion_key     INT             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titulo          VARCHAR(500)    NOT NULL,
    artista         VARCHAR(500)    NOT NULL,
    url_spotify     VARCHAR(200),
    UNIQUE (titulo, artista)        -- natural key compuesta
);

-- Dimensión región
-- Contiene países/regiones del chart y la región especial "Global".
-- Las columnas booleanas (es_global, es_mexico) me permiten filtrar fácil
-- sin escribir literales en las consultas.
CREATE TABLE dim_region (
    region_key      INT             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region          VARCHAR(60)     NOT NULL UNIQUE,
    es_global       BOOLEAN         NOT NULL DEFAULT FALSE,
    es_mexico       BOOLEAN         NOT NULL DEFAULT FALSE
);

-- Dimensión chart
-- Separa Top 200 (tiene streams) de Viral 50 (sin streams).
-- La idea es poder filtrar por tipo de chart desde el dashboard.
CREATE TABLE dim_chart (
    chart_key       SMALLINT        PRIMARY KEY,        -- 1=top200, 2=viral50
    nombre          VARCHAR(20)     NOT NULL UNIQUE,    -- 'top200' | 'viral50'
    descripcion     VARCHAR(100)
);


-- -----------------------------------------------------------------------------
-- FACT
-- -----------------------------------------------------------------------------

-- fact_chart_entry
-- Cada fila es una aparición de una canción en un chart para una región y fecha.
-- Medidas principales: rank, streams (NULL para viral50) y trend (movimiento).
CREATE TABLE fact_chart_entry (
    entry_id        BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha_key       INT             NOT NULL REFERENCES dim_fecha(fecha_key),
    cancion_key     INT             NOT NULL REFERENCES dim_cancion(cancion_key),
    region_key      INT             NOT NULL REFERENCES dim_region(region_key),
    chart_key       SMALLINT        NOT NULL REFERENCES dim_chart(chart_key),
    rank            SMALLINT        NOT NULL,           -- posición 1-200 / 1-50
    streams         BIGINT,                             -- NULL para viral50
    trend           VARCHAR(15)                         -- MOVE_UP, MOVE_DOWN, SAME_POSITION, NEW_ENTRY
);

-- Índices para las queries que usaré en análisis
-- Consultas frecuentes: filtro por región+fecha, por canción o por chart
CREATE INDEX idx_fact_region_fecha   ON fact_chart_entry(region_key, fecha_key);
CREATE INDEX idx_fact_cancion        ON fact_chart_entry(cancion_key);
CREATE INDEX idx_fact_fecha_chart    ON fact_chart_entry(fecha_key, chart_key);
CREATE INDEX idx_fact_region_chart   ON fact_chart_entry(region_key, chart_key);


-- -----------------------------------------------------------------------------
-- CATÁLOGO INICIAL — dim_chart (solo 2 valores, se inserta con el schema)
-- -----------------------------------------------------------------------------

INSERT INTO dim_chart (chart_key, nombre, descripcion) VALUES
    (1, 'top200',  'Top 200 canciones más escuchadas — incluye conteo de streams'),
    (2, 'viral50', 'Viral 50 — canciones con mayor crecimiento, sin conteo de streams');


-- =============================================================================
-- VERIFICACIÓN
-- =============================================================================
-- Ejecuta esto después de crear el schema para comprobar que quedaron las 5 tablas:
--
--   SELECT table_name
--   FROM   information_schema.tables
--   WHERE  table_schema = 'proyecto_spotify'
--   ORDER  BY table_name;
--
-- Resultado esperado: dim_cancion, dim_chart, dim_fecha, dim_region, fact_chart_entry
-- =============================================================================