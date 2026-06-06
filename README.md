# Spotify Charts: México vs el mundo (2017-2021)

## Pregunta analítica

¿Qué tan diferente es el gusto musical de México comparado con el chart global de Spotify entre 2017 y 2021? ¿Existen artistas que dominan el chart mexicano pero son invisibles globalmente, y cómo ha evolucionado esa brecha cultural a lo largo del tiempo?

La pregunta tiene tres subpreguntas concretas:

1. ¿Qué artistas acumularon más streams en México vs el chart global?
2. ¿Hay artistas con presencia sostenida en México que nunca aparecieron globalmente?
3. ¿Cómo creció el volumen de consumo musical en México entre 2017 y 2021?

## Dataset

Spotify Charts — Kaggle (dhruvildave/spotify-charts)

Contiene todas las entradas diarias de los charts Top 200 y Viral 50 publicados por Spotify a nivel global desde enero de 2017 hasta diciembre de 2021. El archivo `charts.csv` tiene aproximadamente 26 millones de filas y 9 columnas: título, artista, rank, fecha, región, tipo de chart, tendencia, URL y streams.

El dataset permite responder la pregunta porque tiene dimensión temporal diaria, cobertura de más de 60 regiones incluyendo México y Global, y la métrica de streams que permite comparar volúmenes reales de consumo entre regiones.

Fuente: https://www.kaggle.com/datasets/dhruvildave/spotify-charts

El archivo no está en el repositorio por su tamaño (3.48 GB). Para descargarlo ir al enlace anterior y hacer click en Download.

## Modelo dimensional

Esquema estrella con una tabla de hechos y cuatro dimensiones.

Grano: una fila por canción en un chart, en una región, en una fecha específica.

```
                   dim_fecha
                      |
dim_chart ---- fact_chart_entry ---- dim_region
                      |
                  dim_cancion
```

La tabla `fact_chart_entry` registra cada aparición de una canción en un chart con sus medidas: rank, streams y trend. Las dimensiones describen el contexto de cada entrada.

Decisiones de diseño:

- El artista vive dentro de `dim_cancion` y no en una tabla separada porque el CSV representa artistas compuestos como una sola cadena (por ejemplo "DJ Snake, Justin Bieber"). Separar implicaría una tabla puente muchos-a-muchos que añade complejidad sin beneficio analítico para la pregunta planteada.
- `dim_region` tiene dos columnas booleanas `es_global` y `es_mexico` que facilitan el filtrado central de la pregunta sin necesidad de literales en las queries.
- `dim_fecha` se genera con `generate_series` de PostgreSQL para el rango 2017-2021, independientemente del CSV.
- El diagrama completo del esquema está en `docs/diagrama_modelo.png`.

DDL completo en `scripts/01_schema_ddl.sql`.

## Infraestructura AWS

Cluster Aurora PostgreSQL 17 en AWS (aurora-mod4), región us-east-1. El modelo dimensional vive en el schema `proyecto_spotify` dentro de la base de datos `northwind`.

## Cómo ejecutar

### Requisitos

```
Python 3.9 o superior
pandas
sqlalchemy
psycopg2-binary
tqdm
matplotlib
```

Instalar con:

```bash
pip install pandas sqlalchemy psycopg2-binary tqdm matplotlib
```

### 1. Crear el schema en Aurora

Ejecutar en DBeaver contra la base `northwind`, en este orden:

```
scripts/01_schema_ddl.sql
scripts/02_dim_fecha_populate.sql
scripts/03_dim_region_populate.sql
scripts/04_dim_chart_populate.sql
```

Abrir cada archivo en DBeaver y ejecutar con Ctrl+Shift+Enter (Windows) o Cmd+Shift+Enter (Mac).

### 2. Correr el ETL

```bash
python scripts/etl_pipeline.py \
    --host     aurora-mod4.cluster-cr74j5deqarh.us-east-1.rds.amazonaws.com \
    --password TU_PASSWORD \
    --database northwind \
    --csv      datasets/charts.csv
```

El script lee el CSV en chunks de 50,000 filas para no saturar la memoria, carga `dim_cancion` y `fact_chart_entry`, y al final ejecuta validaciones de integridad. Tarda aproximadamente 20-40 minutos dependiendo de la conexión. El log se guarda en `etl_spotify.log`.

El script es idempotente: si se re-corre, trunca las tablas antes de volver a cargar.

### 3. Generar el dashboard

```bash
python dashboard/dashboard.py \
    --host     aurora-mod4.cluster-cr74j5deqarh.us-east-1.rds.amazonaws.com \
    --password TU_PASSWORD \
    --database northwind
```

Las 4 imágenes se guardan en `dashboard/img/`.

### 4. Queries analíticas

Abrir `analisis/queries_analiticas.sql` en DBeaver y ejecutar cada query individualmente para explorar los resultados.

## SQL avanzado

Las cinco queries en `analisis/queries_analiticas.sql` usan las siguientes técnicas:

- Query 1: CTE + RANK() — top 10 artistas por streams en México vs Global
- Query 2: CTE + LAG() — evolución trimestral de streams con delta porcentual
- Query 3: CTEs encadenadas + ROW_NUMBER() — detección de rachas consecutivas en el Top 10
- Query 4: PERCENTILE_CONT — distribución de streams por año (mediana y percentil 95)
- Query 5: CTEs dobles + antipattern LEFT JOIN/IS NULL — artistas locales invisibles globalmente

## Dashboard

Cuatro visualizaciones generadas con matplotlib a partir de queries contra Aurora:

- `01_top_artistas.png` — Top 10 artistas por streams totales, México vs Global lado a lado
- `02_evolucion_trimestral.png` — Evolución trimestral de streams en México con % de cambio
- `03_artistas_locales.png` — Artistas populares en México pero ausentes del chart global
- `04_streams_por_anio.png` — Distribución de streams por año (mediana, P95 y promedio)

## Hallazgos

El chart de México muestra una identidad musical claramente diferenciada del chart global durante el período analizado. Los artistas de reggaetón y música regional mexicana concentran una proporción significativa de los streams en México que no se replica en el chart global, donde dominan artistas de pop anglosajón. Esto sugiere que Spotify México funciona como un ecosistema con preferencias propias, donde el contenido en español y los géneros latinoamericanos tienen un peso mucho mayor que en la agregación global.

En cuanto al crecimiento, el volumen de streams en México aumentó de forma sostenida entre 2017 y 2020, con una desaceleración notable hacia finales de 2021. La mediana de streams necesaria para entrar al Top 200 creció año con año, lo que refleja tanto el aumento de usuarios de Spotify en México como una mayor competencia entre canciones por las posiciones del chart.

## Estructura del repositorio

```
proyecto-final/
├── README.md
├── datasets/
│   └── (charts.csv — descargar de Kaggle, ver enlace arriba)
├── scripts/
│   ├── 01_schema_ddl.sql
│   ├── 02_dim_fecha_populate.sql
│   ├── 03_dim_region_populate.sql
│   ├── 04_dim_chart_populate.sql
│   └── etl_pipeline.py
├── analisis/
│   └── queries_analiticas.sql
├── dashboard/
│   ├── dashboard.py
│   └── img/
│       ├── 01_top_artistas.png
│       ├── 02_evolucion_trimestral.png
│       ├── 03_artistas_locales.png
│       └── 04_streams_por_anio.png
└── docs/
    └── diagrama_modelo.png
```