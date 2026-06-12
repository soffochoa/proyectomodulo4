-- =============================================================================
-- Proyecto Final — Spotify Charts: México vs el mundo (2017-2021)
-- =============================================================================
-- Schema  : proyecto_spotify
-- Grano   : una fila por (canción × región × chart × fecha)
--           = una entrada en un chart de Spotify en un día y región específicos
-- Fuente  : charts.csv — Spotify Top 200 y Viral 50 (Kaggle)
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS proyecto_spotify;
SET search_path TO proyecto_spotify;


-- -----------------------------------------------------------------------------
-- DIMENSIONES
-- -----------------------------------------------------------------------------

-- Dimensión fecha
-- Permite agrupar por año, trimestre, mes y detectar patrones temporales.
-- La smart key (YYYYMMDD como INT) evita joins costosos por DATE.
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
-- Incluye artista como atributo directo: decisión de diseño justificada porque
-- el CSV original representa artistas compuestos como una sola cadena
-- (e.g. "DJ Snake, Justin Bieber"), separar implicaría una tabla puente
-- muchos-a-muchos que añade complejidad sin beneficio analítico para la
-- pregunta planteada.
CREATE TABLE dim_cancion (
    cancion_key     INT             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titulo          VARCHAR(500)    NOT NULL,
    artista         VARCHAR(500)    NOT NULL,
    url_spotify     VARCHAR(200),
    UNIQUE (titulo, artista)        -- natural key compuesta
);

-- Dimensión región
-- Contiene todos los países/regiones del chart más la región "Global".
-- La columna es_global facilita el filtrado central de la pregunta analítica
-- (México vs Global) sin requerir un WHERE con literal.
CREATE TABLE dim_region (
    region_key      INT             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region          VARCHAR(60)     NOT NULL UNIQUE,
    es_global       BOOLEAN         NOT NULL DEFAULT FALSE,
    es_mexico       BOOLEAN         NOT NULL DEFAULT FALSE
);

-- Dimensión chart
-- Separa Top 200 (medible por streams) de Viral 50 (sin streams).
-- Permite filtrar chart_tipo en el dashboard con un slicer limpio.
CREATE TABLE dim_chart (
    chart_key       SMALLINT        PRIMARY KEY,        -- 1=top200, 2=viral50
    nombre          VARCHAR(20)     NOT NULL UNIQUE,    -- 'top200' | 'viral50'
    descripcion     VARCHAR(100)
);


-- -----------------------------------------------------------------------------
-- FACT
-- -----------------------------------------------------------------------------

-- fact_chart_entry
-- Cada fila representa la aparición de una canción en un chart,
-- para una región específica, en una fecha específica.
-- Medidas: rank (posición), streams (nulos para viral50), trend (movimiento).
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

-- Índices para las queries analíticas principales
-- Consultas frecuentes: filtrar por región + fecha, por canción, por chart
CREATE INDEX idx_fact_region_fecha   ON fact_chart_entry(region_key, fecha_key);
CREATE INDEX idx_fact_cancion        ON fact_chart_entry(cancion_key);
CREATE INDEX idx_fact_fecha_chart    ON fact_chart_entry(fecha_key, chart_key);
CREATE INDEX idx_fact_region_chart   ON fact_chart_entry(region_key, chart_key);


-- -----------------------------------------------------------------------------
-- CATÁLOGO INICIAL — dim_chart (solo 2 valores, se carga con el schema)
-- -----------------------------------------------------------------------------

INSERT INTO dim_chart (chart_key, nombre, descripcion) VALUES
    (1, 'top200',  'Top 200 canciones más escuchadas — incluye conteo de streams'),
    (2, 'viral50', 'Viral 50 — canciones con mayor crecimiento, sin conteo de streams');


-- =============================================================================
-- VERIFICACIÓN
-- =============================================================================
-- Ejecutar tras crear el schema para confirmar las 5 tablas:
--
-- SELECT table_name
-- FROM   information_schema.tables
-- WHERE  table_schema = 'proyecto_spotify'
-- ORDER  BY table_name;
