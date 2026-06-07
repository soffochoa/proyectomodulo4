"""
Dashboard interactivo — Spotify Charts: México vs el mundo (2017-2021)

Cómo usar:
    Instala dependencias: pip install streamlit plotly pandas sqlalchemy psycopg2-binary

    Ejecuta con Streamlit y pasa las credenciales como argumentos:
    streamlit run dashboard/visualizaciones.py -- \\
        --host     aurora-mod4.cluster-cr74j5deqarh.us-east-1.rds.amazonaws.com \\
        --password TU_PASSWORD \\
        --database northwind

O usa variables de entorno:
    export AURORA_HOST=aurora-mod4.cluster-cr74j5deqarh.us-east-1.rds.amazonaws.com
    export AURORA_PASSWORD=TU_PASSWORD
    streamlit run dashboard/visualizaciones.py
"""

import argparse
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, text

# =============================================================================
# Configuración de página
# =============================================================================

st.set_page_config(
    page_title="Spotify Charts: México vs el mundo",
    layout="wide",
)

# Paleta de colores usada consistentemente en las visualizaciones.
# Elegí tonos que recuerdan el tema de Spotify y que contrastan bien en plots.
COLOR_VERDE   = "#1DB954"
COLOR_NEGRO   = "#191414"
COLOR_NARANJA = "#FF6B35"
COLOR_ROJO    = "#E91429"


# =============================================================================
# Conexión a Aurora
# =============================================================================

def get_engine():
    """Crear un engine SQLAlchemy con credenciales tomadas de:

    1) variables de entorno AURORA_HOST / AURORA_PASSWORD (preferido)
    2) argumentos de la línea de comandos (fallback si no hay env)

    Devuelvo un engine con pool_pre_ping para evitar conexiones muertas.
    """
    host     = os.environ.get("AURORA_HOST")
    password = os.environ.get("AURORA_PASSWORD")
    database = os.environ.get("AURORA_DATABASE", "northwind")
    port     = int(os.environ.get("AURORA_PORT", 5432))

    if not host or not password:
        parser = argparse.ArgumentParser()
        parser.add_argument("--host",     default=host)
        parser.add_argument("--password", default=password)
        parser.add_argument("--database", default=database)
        parser.add_argument("--port",     default=port, type=int)
        args, _ = parser.parse_known_args()
        host     = args.host
        password = args.password
        database = args.database
        port     = args.port

    if not host or not password:
        st.error("Falta --host y --password. Ver instrucciones en el README.")
        st.stop()

    return create_engine(
        f"postgresql+psycopg2://postgres:{password}@{host}:{port}/{database}",
        pool_pre_ping=True,
    )


# Cacheo la conexión: Streamlit mantiene el recurso entre reruns para usar el
# mismo engine y evitar re-conexiones innecesarias cuando el usuario interactúa.
@st.cache_resource
def engine():
    return get_engine()


# =============================================================================
# Queries — cacheadas para no re-ejecutar en cada interacción
# =============================================================================

@st.cache_data(ttl=600)
def load_top_artistas():
    """Devuelvo el top 10 de artistas por streams totales en México y Global.

    El DataFrame contiene: region, artista, streams_totales, dias_en_chart, posicion.
    """
    return pd.read_sql(text("""
        WITH streams_por_artista AS (
            SELECT
                dr.region,
                dc.artista,
                SUM(fce.streams)              AS streams_totales,
                COUNT(DISTINCT fce.fecha_key) AS dias_en_chart
            FROM      proyecto_spotify.fact_chart_entry fce
            JOIN      proyecto_spotify.dim_cancion      dc  USING (cancion_key)
            JOIN      proyecto_spotify.dim_region       dr  USING (region_key)
            WHERE     fce.chart_key = 1
              AND     fce.streams IS NOT NULL
              AND     (dr.es_mexico OR dr.es_global)
            GROUP BY  dr.region, dc.artista
        ),
        ranking AS (
            SELECT
                region, artista, streams_totales, dias_en_chart,
                RANK() OVER (PARTITION BY region ORDER BY streams_totales DESC) AS posicion
            FROM streams_por_artista
        )
        SELECT * FROM ranking WHERE posicion <= 10
        ORDER BY region DESC, posicion
    """), engine())


@st.cache_data(ttl=600)
def load_evolucion_trimestral():
    """Devuelvo la evolución trimestral de streams en México, con % de cambio.

    Columnas: anio, trimestre, streams_totales, artistas_distintos, pct_cambio.
    """
    return pd.read_sql(text("""
        WITH trimestral AS (
            SELECT
                df.anio,
                df.trimestre,
                SUM(fce.streams)           AS streams_totales,
                COUNT(DISTINCT dc.artista) AS artistas_distintos
            FROM      proyecto_spotify.fact_chart_entry fce
            JOIN      proyecto_spotify.dim_fecha        df  USING (fecha_key)
            JOIN      proyecto_spotify.dim_cancion      dc  USING (cancion_key)
            JOIN      proyecto_spotify.dim_region       dr  USING (region_key)
            WHERE     dr.es_mexico
              AND     fce.chart_key = 1
              AND     fce.streams IS NOT NULL
            GROUP BY  df.anio, df.trimestre
        )
        SELECT
            anio, trimestre, streams_totales, artistas_distintos,
            ROUND(
                100.0 * (streams_totales - LAG(streams_totales) OVER (ORDER BY anio, trimestre))
                / NULLIF(LAG(streams_totales) OVER (ORDER BY anio, trimestre), 0),
                1
            ) AS pct_cambio
        FROM trimestral
        ORDER BY anio, trimestre
    """), engine())


@st.cache_data(ttl=600)
def load_artistas_locales():
    """Devuelvo artistas populares en México que no aparecen en el chart global.

    Filtra artistas con >=30 entradas en México y que no aparecen en global.
    """
    return pd.read_sql(text("""
        WITH artistas_mexico AS (
            SELECT
                dc.artista,
                COUNT(*)         AS entradas_mx,
                SUM(fce.streams) AS streams_mx,
                MIN(fce.rank)    AS mejor_rank_mx
            FROM      proyecto_spotify.fact_chart_entry fce
            JOIN      proyecto_spotify.dim_cancion      dc  USING (cancion_key)
            JOIN      proyecto_spotify.dim_region       dr  USING (region_key)
            WHERE     dr.es_mexico
              AND     fce.chart_key = 1
              AND     fce.streams IS NOT NULL
            GROUP BY  dc.artista
            HAVING    COUNT(*) >= 30
        ),
        artistas_global AS (
            SELECT DISTINCT dc.artista
            FROM      proyecto_spotify.fact_chart_entry fce
            JOIN      proyecto_spotify.dim_cancion      dc  USING (cancion_key)
            JOIN      proyecto_spotify.dim_region       dr  USING (region_key)
            WHERE     dr.es_global AND fce.chart_key = 1
        )
        SELECT mx.artista, mx.entradas_mx, mx.streams_mx, mx.mejor_rank_mx
        FROM      artistas_mexico mx
        LEFT JOIN artistas_global gl ON mx.artista = gl.artista
        WHERE     gl.artista IS NULL
        ORDER BY  mx.streams_mx DESC
        LIMIT 20
    """), engine())


@st.cache_data(ttl=600)
def load_streams_por_anio():
    """Devuelvo estadísticas por año: entradas, promedio, mediana (P50), P95 y máximo.

    Útil para analizar si el umbral de streams para entrar al chart cambió.
    """
    return pd.read_sql(text("""
        SELECT
            df.anio,
            COUNT(*)                                                   AS entradas,
            ROUND(AVG(fce.streams), 0)                                 AS promedio,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY fce.streams)  AS mediana,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY fce.streams)  AS p95,
            MAX(fce.streams)                                           AS maximo
        FROM      proyecto_spotify.fact_chart_entry fce
        JOIN      proyecto_spotify.dim_fecha        df  USING (fecha_key)
        JOIN      proyecto_spotify.dim_region       dr  USING (region_key)
        WHERE     dr.es_mexico
          AND     fce.chart_key = 1
          AND     fce.streams IS NOT NULL
        GROUP BY  df.anio
        ORDER BY  df.anio
    """), engine())


# =============================================================================
# Header
# =============================================================================

st.title("Spotify Charts: México vs el mundo")
st.markdown("**2017 – 2021 · Top 200 · Análisis comparativo de consumo musical**")
st.divider()

# =============================================================================
# Viz 1 — Top 10 artistas: México vs Global
# =============================================================================

st.subheader("Top 10 artistas por streams totales")
st.caption("¿Quién domina en México comparado con el chart global?")

df_top = load_top_artistas()

# Slicer: permite al usuario elegir cuántos artistas mostrar (5-10)
n_artistas = st.slider("Número de artistas a mostrar", min_value=5, max_value=10, value=10, key="slider_top")

col1, col2 = st.columns(2)

# Nota sobre regiones: en la dimensión las regiones clave son 'Mexico' y 'Global'
# (uso esas cadenas para filtrar; ojo con mayúsculas/minúsculas si cambias la fuente).
for region, col, color, titulo in [
    ("Mexico", col1, COLOR_VERDE, "México"),
    ("Global", col2, COLOR_NEGRO, "Global"),
]:
    # Filtrar por región y ordenar para graficar en horizontal (barh)
    sub = df_top[df_top["region"] == region].head(n_artistas).sort_values("streams_totales")
    fig = px.bar(
        sub,
        x="streams_totales",
        y="artista",
        orientation="h",
        text=sub["streams_totales"].apply(lambda v: f"{v/1e9:.2f}B"),
        color_discrete_sequence=[color],
    )
    # Pongo los valores como texto fuera de las barras para mejor lectura
    fig.update_traces(textposition="outside")
    fig.update_layout(
        title=titulo,
        xaxis_title="Streams totales",
        yaxis_title="",
        xaxis_tickformat=".1s",
        plot_bgcolor="white",
        height=400,
        margin=dict(l=10, r=80, t=40, b=40),
    )
    col.plotly_chart(fig, use_container_width=True)

st.divider()

# =============================================================================
# Viz 2 — Evolución trimestral de streams en México
# =============================================================================

st.subheader("Evolución trimestral de streams en México")
st.caption("¿Cómo creció el consumo musical entre 2017 y 2021?")

df_trim = load_evolucion_trimestral()
df_trim["periodo"] = df_trim["anio"].astype(str) + "-Q" + df_trim["trimestre"].astype(str)

# Slicer: rango de años para filtrar la serie trimestral
anios = sorted(df_trim["anio"].unique().tolist())
anio_min, anio_max = st.select_slider(
    "Rango de años",
    options=anios,
    value=(anios[0], anios[-1]),
    key="slider_anios",
)
df_trim_f = df_trim[(df_trim["anio"] >= anio_min) & (df_trim["anio"] <= anio_max)]

fig2 = go.Figure()

# Barras: muestran streams totales por periodo (eje izquierdo)
fig2.add_trace(go.Bar(
    x=df_trim_f["periodo"],
    y=df_trim_f["streams_totales"] / 1e9,
    name="Streams (miles de millones)",
    marker_color=COLOR_VERDE,
    opacity=0.85,
    yaxis="y1",
))

 # Línea: % cambio trimestral (eje derecho) para ver dinamismo trimestre a trimestre
fig2.add_trace(go.Scatter(
    x=df_trim_f["periodo"],
    y=df_trim_f["pct_cambio"].fillna(0),
    name="% cambio vs trimestre anterior",
    mode="lines+markers",
    line=dict(color=COLOR_ROJO, width=2),
    marker=dict(size=6),
    yaxis="y2",
))

fig2.update_layout(
    xaxis=dict(tickangle=-45),
    yaxis=dict(
        title="Streams (miles de millones)",
        color=COLOR_VERDE,
    ),
    yaxis2=dict(
        title="% cambio trimestral",
        color=COLOR_ROJO,
        overlaying="y",
        side="right",
        zeroline=True,
    ),
    plot_bgcolor="white",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    height=420,
    margin=dict(l=10, r=10, t=40, b=80),
)

st.plotly_chart(fig2, use_container_width=True)
st.divider()

# =============================================================================
# Viz 3 — Artistas locales invisibles globalmente
# =============================================================================

st.subheader("Artistas populares en México pero invisibles globalmente")
st.caption("¿Quiénes dominan México pero nunca aparecieron en el chart global?")

df_local = load_artistas_locales()

# Slicer: cuántos artistas locales mostrar (5-20)
n_local = st.slider("Número de artistas a mostrar", min_value=5, max_value=20, value=15, key="slider_local")
df_local_f = df_local.head(n_local).sort_values("streams_mx")

# Grafico horizontal con color por mejor rank para indicar popularidad relativa
fig3 = px.bar(
    df_local_f,
    x="streams_mx",
    y="artista",
    orientation="h",
    text=df_local_f["streams_mx"].apply(lambda v: f"{v/1e6:.0f}M"),
    color="mejor_rank_mx",
    color_continuous_scale=["#1DB954", "#FF6B35", "#E91429"],
    labels={"mejor_rank_mx": "Mejor rank en México", "streams_mx": "Streams en México"},
)
fig3.update_traces(textposition="outside")
fig3.update_layout(
    xaxis_title="Streams totales en México",
    yaxis_title="",
    xaxis_tickformat=".2s",
    plot_bgcolor="white",
    height=500,
    margin=dict(l=10, r=80, t=20, b=40),
    coloraxis_colorbar=dict(title="Mejor rank"),
)

st.plotly_chart(fig3, use_container_width=True)
st.divider()

# =============================================================================
# Viz 4 — Distribución de streams por año
# =============================================================================

st.subheader("Distribución de streams por año en México")
st.caption("¿Creció el piso de streams necesario para entrar al Top 200?")

df_anio = load_streams_por_anio()

# Multiselect: permite elegir qué métricas mostrar en el gráfico por año
metricas = st.multiselect(
    "Métricas a mostrar",
    options=["Mediana", "Percentil 95", "Promedio"],
    default=["Mediana", "Percentil 95", "Promedio"],
    key="metricas",
)

fig4 = go.Figure()

if "Mediana" in metricas:
    fig4.add_trace(go.Bar(
        x=df_anio["anio"].astype(str),
        y=df_anio["mediana"] / 1e6,
        name="Mediana",
        marker_color=COLOR_VERDE,
        opacity=0.85,
        offsetgroup=0,
    ))

if "Percentil 95" in metricas:
    fig4.add_trace(go.Bar(
        x=df_anio["anio"].astype(str),
        y=df_anio["p95"] / 1e6,
        name="Percentil 95",
        marker_color=COLOR_NEGRO,
        opacity=0.85,
        offsetgroup=1,
    ))

if "Promedio" in metricas:
    fig4.add_trace(go.Scatter(
        x=df_anio["anio"].astype(str),
        y=df_anio["promedio"] / 1e6,
        name="Promedio",
        mode="lines+markers",
        line=dict(color=COLOR_ROJO, width=2),
        marker=dict(size=8, symbol="diamond"),
    ))

fig4.update_layout(
    xaxis_title="Año",
    yaxis_title="Streams (millones)",
    yaxis_ticksuffix="M",
    plot_bgcolor="white",
    barmode="group",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    height=400,
    margin=dict(l=10, r=10, t=40, b=40),
)

st.plotly_chart(fig4, use_container_width=True)

# =============================================================================
# Footer con métricas generales del dataset
# =============================================================================

st.divider()
st.markdown("#### Resumen del dataset")
col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Entradas en fact", "25,450,563")
col_b.metric("Canciones únicas", "197,533")
col_c.metric("Regiones", "69")
col_d.metric("Período", "2017 – 2021")