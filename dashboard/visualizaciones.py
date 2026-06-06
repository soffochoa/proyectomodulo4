"""
Dashboard — Spotify Charts: México vs el mundo (2017-2021)

Genera 4 visualizaciones estáticas (PNG) a partir de queries contra Aurora
PostgreSQL. Requiere que el ETL ya haya cargado los datos.

Uso:
    export AURORA_HOST=aurora-mod4.cluster-XXX.us-east-1.rds.amazonaws.com
    export AURORA_PASSWORD=tu_password
    python dashboard/dashboard.py

    O bien con argumentos directos:
    python dashboard/dashboard.py \\
        --host     aurora-mod4.cluster-XXX.us-east-1.rds.amazonaws.com \\
        --password TU_PASSWORD \\
        --database northwind

Salida: dashboard/img/{01_top_artistas, 02_evolucion_trimestral,
                        03_artistas_locales, 04_streams_por_anio}.png
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
from sqlalchemy import create_engine, text

logger = logging.getLogger("dashboard_spotify")
OUT = Path(__file__).parent / "img"
OUT.mkdir(exist_ok=True)

SCHEMA = "proyecto_spotify"


# =============================================================================
# Conexión
# =============================================================================

def conectar(host: str, password: str, database: str, port: int = 5432):
    engine = create_engine(
        f"postgresql+psycopg2://postgres:{password}@{host}:{port}/{database}",
        pool_pre_ping=True,
    )
    # Verificar conexión antes de continuar
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Conexión a Aurora establecida correctamente")
    return engine


# =============================================================================
# Queries
# =============================================================================

def query_top_artistas(engine) -> pd.DataFrame:
    """Top 10 artistas por streams totales en México y Global."""
    return pd.read_sql(text("""
        WITH streams_por_artista AS (
            SELECT
                dr.region,
                dc.artista,
                SUM(fce.streams)                AS streams_totales,
                COUNT(DISTINCT fce.fecha_key)   AS dias_en_chart
            FROM      proyecto_spotify.fact_chart_entry   fce
            JOIN      proyecto_spotify.dim_cancion        dc  USING (cancion_key)
            JOIN      proyecto_spotify.dim_region         dr  USING (region_key)
            WHERE     fce.chart_key = 1
              AND     fce.streams IS NOT NULL
              AND     (dr.es_mexico OR dr.es_global)
            GROUP BY  dr.region, dc.artista
        ),
        ranking AS (
            SELECT
                region, artista, streams_totales, dias_en_chart,
                RANK() OVER (
                    PARTITION BY region
                    ORDER BY streams_totales DESC
                ) AS posicion
            FROM streams_por_artista
        )
        SELECT * FROM ranking WHERE posicion <= 10
        ORDER BY region DESC, posicion
    """), engine)


def query_evolucion_trimestral(engine) -> pd.DataFrame:
    """Evolución trimestral de streams en México con delta respecto al trimestre anterior."""
    return pd.read_sql(text("""
        WITH trimestral AS (
            SELECT
                df.anio,
                df.trimestre,
                SUM(fce.streams)            AS streams_totales,
                COUNT(DISTINCT dc.artista)  AS artistas_distintos
            FROM      proyecto_spotify.fact_chart_entry  fce
            JOIN      proyecto_spotify.dim_fecha         df  USING (fecha_key)
            JOIN      proyecto_spotify.dim_cancion       dc  USING (cancion_key)
            JOIN      proyecto_spotify.dim_region        dr  USING (region_key)
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
    """), engine)


def query_artistas_locales(engine) -> pd.DataFrame:
    """Top 20 artistas con presencia en México pero invisibles globalmente."""
    return pd.read_sql(text("""
        WITH artistas_mexico AS (
            SELECT
                dc.artista,
                COUNT(*)            AS entradas_mx,
                SUM(fce.streams)    AS streams_mx,
                MIN(fce.rank)       AS mejor_rank_mx
            FROM      proyecto_spotify.fact_chart_entry  fce
            JOIN      proyecto_spotify.dim_cancion       dc  USING (cancion_key)
            JOIN      proyecto_spotify.dim_region        dr  USING (region_key)
            WHERE     dr.es_mexico
              AND     fce.chart_key = 1
              AND     fce.streams IS NOT NULL
            GROUP BY  dc.artista
            HAVING    COUNT(*) >= 30
        ),
        artistas_global AS (
            SELECT DISTINCT dc.artista
            FROM      proyecto_spotify.fact_chart_entry  fce
            JOIN      proyecto_spotify.dim_cancion       dc  USING (cancion_key)
            JOIN      proyecto_spotify.dim_region        dr  USING (region_key)
            WHERE     dr.es_global AND fce.chart_key = 1
        )
        SELECT mx.artista, mx.entradas_mx, mx.streams_mx, mx.mejor_rank_mx
        FROM        artistas_mexico  mx
        LEFT JOIN   artistas_global  gl  ON mx.artista = gl.artista
        WHERE       gl.artista IS NULL
        ORDER BY    mx.streams_mx DESC
        LIMIT 20
    """), engine)


def query_streams_por_anio(engine) -> pd.DataFrame:
    """Distribución de streams por año en México (mediana y percentil 95)."""
    return pd.read_sql(text("""
        SELECT
            df.anio,
            COUNT(*)                                                    AS entradas,
            ROUND(AVG(fce.streams), 0)                                  AS promedio,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY fce.streams)   AS mediana,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY fce.streams)   AS p95,
            MAX(fce.streams)                                            AS maximo
        FROM      proyecto_spotify.fact_chart_entry  fce
        JOIN      proyecto_spotify.dim_fecha         df  USING (fecha_key)
        JOIN      proyecto_spotify.dim_region        dr  USING (region_key)
        WHERE     dr.es_mexico
          AND     fce.chart_key = 1
          AND     fce.streams IS NOT NULL
        GROUP BY  df.anio
        ORDER BY  df.anio
    """), engine)


# =============================================================================
# Visualizaciones
# =============================================================================

def viz_top_artistas(df: pd.DataFrame):
    """
    Viz 1 — Top 10 artistas por streams totales: México vs Global
    Responde: ¿Quién domina en México comparado con el chart global?
    """
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    fig.suptitle(
        "Top 10 artistas por streams totales (2017-2021)\nMéxico vs Global — Spotify Top 200",
        fontsize=14, fontweight="bold", y=1.01,
    )

    regiones = [("Mexico", axes[0], "#1DB954"), ("global", axes[1], "#191414")]
    for region, ax, color in regiones:
        sub = df[df["region"] == region].sort_values("streams_totales")
        bars = ax.barh(
            sub["artista"], sub["streams_totales"] / 1e9,
            color=color, edgecolor="black", linewidth=0.5, alpha=0.85,
        )
        ax.set_xlabel("Streams totales (miles de millones)")
        ax.set_title(f"{'México 🇲🇽' if region == 'Mexico' else 'Global 🌍'}", fontsize=13)
        ax.grid(True, axis="x", alpha=0.3)
        for bar, val in zip(bars, sub["streams_totales"] / 1e9):
            ax.text(val + 0.01, bar.get_y() + bar.get_height() / 2,
                    f"{val:.2f}B", va="center", fontsize=8)

    plt.tight_layout()
    plt.savefig(OUT / "01_top_artistas.png", dpi=110, bbox_inches="tight")
    plt.close()
    logger.info("✓ 01_top_artistas.png generada")


def viz_evolucion_trimestral(df: pd.DataFrame):
    """
    Viz 2 — Evolución trimestral de streams en México
    Responde: ¿Cómo creció el consumo musical en México año a año?
    """
    fig, ax1 = plt.subplots(figsize=(13, 6))

    etiquetas = [f"{r.anio}-Q{r.trimestre}" for _, r in df.iterrows()]
    x = range(len(etiquetas))

    # Barras: streams totales
    bars = ax1.bar(x, df["streams_totales"] / 1e9, color="#1DB954",
                   edgecolor="black", linewidth=0.5, alpha=0.8, label="Streams (miles de millones)")
    ax1.set_ylabel("Streams totales (miles de millones)", color="#1DB954")
    ax1.tick_params(axis="y", labelcolor="#1DB954")

    # Línea: % cambio trimestral
    ax2 = ax1.twinx()
    pct = df["pct_cambio"].fillna(0)
    ax2.plot(x, pct, color="#E91429", marker="o", linewidth=2,
             label="% cambio vs trimestre anterior")
    ax2.axhline(0, color="gray", linestyle="--", linewidth=0.8)
    ax2.set_ylabel("% cambio trimestral", color="#E91429")
    ax2.tick_params(axis="y", labelcolor="#E91429")

    ax1.set_xticks(x)
    ax1.set_xticklabels(etiquetas, rotation=45, ha="right", fontsize=8)
    ax1.set_title(
        "Evolución trimestral de streams en México (2017-2021)\nSpotify Top 200",
        fontsize=13, fontweight="bold",
    )
    ax1.grid(True, axis="y", alpha=0.3)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)

    plt.tight_layout()
    plt.savefig(OUT / "02_evolucion_trimestral.png", dpi=110, bbox_inches="tight")
    plt.close()
    logger.info("✓ 02_evolucion_trimestral.png generada")


def viz_artistas_locales(df: pd.DataFrame):
    """
    Viz 3 — Artistas locales invisibles globalmente
    Responde: ¿Quiénes son populares en México pero ausentes del chart global?
    """
    top15 = df.head(15).sort_values("streams_mx")

    fig, ax = plt.subplots(figsize=(12, 7))
    bars = ax.barh(
        top15["artista"], top15["streams_mx"] / 1e6,
        color="#FF6B35", edgecolor="black", linewidth=0.5, alpha=0.85,
    )
    ax.set_xlabel("Streams totales en México (millones)")
    ax.set_title(
        "Artistas populares en México pero ausentes del chart global\n"
        "Top 15 por streams — Spotify Top 200 (2017-2021)",
        fontsize=13, fontweight="bold",
    )
    ax.grid(True, axis="x", alpha=0.3)

    for bar, row in zip(bars, top15.itertuples()):
        ax.text(
            bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
            f"{row.streams_mx / 1e6:.0f}M  (rank #{row.mejor_rank_mx})",
            va="center", fontsize=8,
        )

    plt.tight_layout()
    plt.savefig(OUT / "03_artistas_locales.png", dpi=110, bbox_inches="tight")
    plt.close()
    logger.info("✓ 03_artistas_locales.png generada")


def viz_streams_por_anio(df: pd.DataFrame):
    """
    Viz 4 — Distribución de streams por año en México (mediana y P95)
    Responde: ¿Creció el "piso" de streams necesario para entrar al chart?
    """
    x = df["anio"].astype(str)
    x_pos = range(len(x))
    ancho = 0.3

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar([p - ancho / 2 for p in x_pos], df["mediana"] / 1e6,
           width=ancho, label="Mediana", color="#1DB954",
           edgecolor="black", linewidth=0.5, alpha=0.85)
    ax.bar([p + ancho / 2 for p in x_pos], df["p95"] / 1e6,
           width=ancho, label="Percentil 95", color="#191414",
           edgecolor="black", linewidth=0.5, alpha=0.85)
    ax.plot(x_pos, df["promedio"] / 1e6, color="#E91429",
            marker="D", linewidth=2, label="Promedio", zorder=5)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(x)
    ax.set_xlabel("Año")
    ax.set_ylabel("Streams (millones)")
    ax.set_title(
        "Distribución de streams por año en México\n"
        "Mediana, Percentil 95 y Promedio — Spotify Top 200",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=10)
    ax.grid(True, axis="y", alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.1f}M"))

    plt.tight_layout()
    plt.savefig(OUT / "04_streams_por_anio.png", dpi=110, bbox_inches="tight")
    plt.close()
    logger.info("✓ 04_streams_por_anio.png generada")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Dashboard Spotify Charts → PNG")
    parser.add_argument("--host",     default=os.environ.get("AURORA_HOST"))
    parser.add_argument("--password", default=os.environ.get("AURORA_PASSWORD"))
    parser.add_argument("--database", default=os.environ.get("AURORA_DATABASE", "northwind"))
    parser.add_argument("--port",     default=5432, type=int)
    args = parser.parse_args()

    if not args.host or not args.password:
        print(
            "ERROR: Debes proporcionar --host y --password, "
            "o definir AURORA_HOST y AURORA_PASSWORD como variables de entorno."
        )
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    engine = conectar(args.host, args.password, args.database, args.port)

    logger.info("Ejecutando queries y generando visualizaciones...")

    viz_top_artistas(query_top_artistas(engine))
    viz_evolucion_trimestral(query_evolucion_trimestral(engine))
    viz_artistas_locales(query_artistas_locales(engine))
    viz_streams_por_anio(query_streams_por_anio(engine))

    logger.info("Dashboard completo — 4 imágenes en %s/", OUT)


if __name__ == "__main__":
    main()