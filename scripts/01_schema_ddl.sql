-- Proyecto Final — Spotify Charts: México vs el mundo (2017-2021)
-- Schema: proyecto_spotify
-- Base de datos: northwind (Aurora PostgreSQL)
--
-- Grano de la fact: una fila por canción en un chart, en una región, en una fecha
-- o sea cada vez que una canción aparece en el Top 200 o Viral 50 de algún país
-- eso es una fila en fact_chart_entry
--
-- Fuente de los datos: charts.csv de Kaggle (dhruvildave/spotify-charts)

CREATE SCHEMA IF NOT EXISTS proyecto_spotify;
SET search_path TO proyecto_spotify;


-- dim_fecha
-- guarda todos los días del rango 2017-2021, la lleno con generate_series en otro script
-- uso una smart key YYYYMMDD como entero porque es más rápido para joins que usar DATE directo
CREATE TABLE dim_fecha (
    fecha_key           INT          PRIMARY KEY,        -- ej: 20170101
    fecha_completa      DATE         NOT NULL UNIQUE,
    anio                SMALLINT     NOT NULL,
    trimestre           SMALLINT     NOT NULL,           -- 1 al 4
    mes_numero          SMALLINT     NOT NULL,           -- 1 al 12
    mes_nombre          VARCHAR(12)  NOT NULL,
    semana_anio         SMALLINT     NOT NULL,           -- semana ISO, del 1 al 53
    dia_semana_numero   SMALLINT     NOT NULL,           -- 1=lunes, 7=domingo
    dia_semana_nombre   VARCHAR(10)  NOT NULL,
    es_fin_de_semana    BOOLEAN      NOT NULL
);

-- dim_cancion
-- decidí meter el artista aquí en vez de hacer una tabla aparte porque en el CSV
-- los artistas colaboradores vienen como una sola cadena (ej: "DJ Snake, Justin Bieber")
-- separar eso implicaría una tabla puente muchos-a-muchos que complica todo sin
-- aportar nada útil para la pregunta que quiero responder
CREATE TABLE dim_cancion (
    cancion_key     INT             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titulo          VARCHAR(500)    NOT NULL,
    artista         VARCHAR(500)    NOT NULL,
    url_spotify     VARCHAR(200),
    UNIQUE (titulo, artista)        -- la combinación título+artista identifica una canción única
);

-- dim_region
-- todos los países del dataset más la región "global"
-- agregué las columnas es_global y es_mexico para no tener que escribir
-- WHERE region = 'Mexico' en cada query, así es más limpio filtrar
CREATE TABLE dim_region (
    region_key      INT             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region          VARCHAR(60)     NOT NULL UNIQUE,
    es_global       BOOLEAN         NOT NULL DEFAULT FALSE,
    es_mexico       BOOLEAN         NOT NULL DEFAULT FALSE
);

-- dim_chart
-- solo hay dos tipos de chart en el dataset: top200 y viral50
-- el viral50 no tiene streams, por eso en la fact ese campo puede ser NULL
CREATE TABLE dim_chart (
    chart_key       SMALLINT        PRIMARY KEY,        -- 1=top200, 2=viral50
    nombre          VARCHAR(20)     NOT NULL UNIQUE,
    descripcion     VARCHAR(100)
);


-- fact_chart_entry
-- tabla central del esquema estrella
-- cada fila es una canción que apareció en un chart, en un país, en un día específico
-- las medidas son rank (posición en el chart), streams (cuántas veces se escuchó)
-- y trend (si subió, bajó o se mantuvo respecto al día anterior)
CREATE TABLE fact_chart_entry (
    entry_id        BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha_key       INT             NOT NULL REFERENCES dim_fecha(fecha_key),
    cancion_key     INT             NOT NULL REFERENCES dim_cancion(cancion_key),
    region_key      INT             NOT NULL REFERENCES dim_region(region_key),
    chart_key       SMALLINT        NOT NULL REFERENCES dim_chart(chart_key),
    rank            SMALLINT        NOT NULL,           -- posición 1-200 o 1-50
    streams         BIGINT,                             -- viene NULL cuando es viral50
    trend           VARCHAR(15)                         -- MOVE_UP, MOVE_DOWN, SAME_POSITION, NEW_ENTRY
);

-- índices para que las queries del dashboard no sean lentas
-- los más importantes son los que filtran por región y fecha porque son los filtros principales
CREATE INDEX idx_fact_region_fecha   ON fact_chart_entry(region_key, fecha_key);
CREATE INDEX idx_fact_cancion        ON fact_chart_entry(cancion_key);
CREATE INDEX idx_fact_fecha_chart    ON fact_chart_entry(fecha_key, chart_key);
CREATE INDEX idx_fact_region_chart   ON fact_chart_entry(region_key, chart_key);


-- cargo dim_chart aquí mismo porque solo tiene 2 valores fijos que no cambian
INSERT INTO dim_chart (chart_key, nombre, descripcion) VALUES
    (1, 'top200',  'Top 200 canciones más escuchadas — incluye conteo de streams'),
    (2, 'viral50', 'Viral 50 — canciones con mayor crecimiento viral, sin conteo de streams');


-- para verificar que todo se creó bien:
--
--   SELECT table_name
--   FROM   information_schema.tables
--   WHERE  table_schema = 'proyecto_spotify'
--   ORDER  BY table_name;
--
-- deberían aparecer 5 tablas: dim_cancion, dim_chart, dim_fecha, dim_region, fact_chart_entry