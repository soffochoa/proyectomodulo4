#!/usr/bin/env python3
"""
ETL Pipeline — Spotify Charts: México vs el mundo (2017-2021)

Lee el charts.csv de Kaggle, lo transforma al modelo dimensional
y lo carga a Aurora PostgreSQL en el schema proyecto_spotify.

Antes de correr este script hay que haber ejecutado los 4 SQLs:
    01_schema_ddl.sql
    02_dim_fecha_populate.sql
    03_dim_region_populate.sql
    04_dim_chart_populate.sql

Cómo correrlo:
    python etl_pipeline.py \\
        --host     aurora-mod4.cluster-XXX.us-east-1.rds.amazonaws.com \\
        --password TU_PASSWORD \\
        --database northwind \\
        --csv      datasets/charts.csv

El script es idempotente: si se re-corre trunca las tablas antes de volver
a cargar, así no quedan datos duplicados.
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from tqdm import tqdm

logger = logging.getLogger("etl_spotify")

# =============================================================================
# Configuración
# =============================================================================

SCHEMA       = "proyecto_spotify"
CHUNKSIZE    = 50_000      # proceso el CSV en bloques de 50k filas para no cargar 3.48 GB en RAM de un jalón
CSV_ENCODING = "utf-8"

# columnas que tiene el CSV de Kaggle
CSV_COLUMNS = ["title", "rank", "date", "artist", "url", "region", "chart", "trend", "streams"]

# mapa para convertir el nombre del chart a su clave numérica, tiene que coincidir con dim_chart
CHART_KEY_MAP = {"top200": 1, "viral50": 2}


# =============================================================================
# Extract
# =============================================================================

def extract(csv_path: str) -> pd.io.parsers.TextFileReader:
    """
    Abre el CSV como un iterador de chunks.
    No carga todo en memoria porque el archivo pesa 3.48 GB.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {csv_path}")

    logger.info("Abriendo CSV en modo chunk: %s", csv_path)

    reader = pd.read_csv(
        path,
        chunksize=CHUNKSIZE,
        encoding=CSV_ENCODING,
        parse_dates=["date"],
        dtype={
            "title":   str,
            "rank":    "Int16",
            "artist":  str,
            "url":     str,
            "region":  str,
            "chart":   str,
            "trend":   str,
            "streams": "Int64",   # Int64 nullable porque viral50 no tiene streams
        },
        on_bad_lines="warn",  # si hay líneas malformadas las ignora y avisa en lugar de tronar
    )
    return reader


# =============================================================================
# Transform
# =============================================================================

def transform(chunk: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia y transforma un chunk del CSV crudo al formato que necesita la fact.

    Lo que hace:
      1. Renombrar columnas al nombre que uso en el modelo
      2. Calcular fecha_key como YYYYMMDD entero para hacer join con dim_fecha
      3. Convertir nombre del chart a su clave numérica
      4. Descartar filas con datos inválidos o fuera de rango
      5. Truncar strings por si alguno viene más largo de lo esperado
    """
    df = chunk.copy()

    # 1. Renombrar columnas al convenio del modelo
    df = df.rename(columns={
        "title":   "titulo",
        "artist":  "artista",
        "url":     "url_spotify",
        "region":  "region",
        "chart":   "chart_nombre",
        "trend":   "trend",
        "streams": "streams",
        "rank":    "rank",
        "date":    "fecha",
    })

    # 2. Calcular fecha_key — tiene que ser YYYYMMDD como entero para hacer join con dim_fecha
    df["fecha_key"] = (
        df["fecha"]
        .dt.strftime("%Y%m%d")
        .astype("Int32")
    )

    # 3. Convertir nombre del chart a clave numérica y descartar filas con chart desconocido
    df["chart_key"] = df["chart_nombre"].map(CHART_KEY_MAP).astype("Int8")
    df = df.dropna(subset=["chart_key", "fecha_key", "titulo", "artista", "region"])

    # 4. Ranks fuera de rango no tienen sentido, los descarto
    df = df[df["rank"].between(1, 200)]

    # 5. Trunco strings por seguridad, el CSV a veces trae valores raros
    df["titulo"]      = df["titulo"].str.strip().str[:500]
    df["artista"]     = df["artista"].str.strip().str[:500]
    df["url_spotify"] = df["url_spotify"].str.strip().str[:200]
    df["region"]      = df["region"].str.strip()
    df["trend"]       = df["trend"].str.strip().str[:15]

    return df[[
        "titulo", "artista", "url_spotify",   # para dim_cancion
        "region", "chart_key", "fecha_key",   # FKs de la fact
        "rank", "streams", "trend",           # medidas
    ]]


# =============================================================================
# Load helpers
# =============================================================================

def upsert_canciones(df: pd.DataFrame, engine) -> dict:
    """
    Inserta canciones nuevas en dim_cancion ignorando las que ya existen.
    Devuelve un diccionario {(titulo, artista): cancion_key} para resolver FKs.
    """
    canciones = (
        df[["titulo", "artista", "url_spotify"]]
        .drop_duplicates(subset=["titulo", "artista"])
    )

    # inserto de una en una con ON CONFLICT DO NOTHING para no duplicar si se re-corre
    with engine.begin() as conn:
        for _, row in canciones.iterrows():
            conn.execute(text("""
                INSERT INTO proyecto_spotify.dim_cancion (titulo, artista, url_spotify)
                VALUES (:titulo, :artista, :url)
                ON CONFLICT (titulo, artista) DO NOTHING
            """), {"titulo": row["titulo"], "artista": row["artista"], "url": row["url_spotify"]})

    # leo el mapa completo actualizado para tener los cancion_key correctos
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT cancion_key, titulo, artista FROM proyecto_spotify.dim_cancion"
        ))
        mapa = {(r.titulo, r.artista): r.cancion_key for r in result}

    return mapa


def load_fact(df_fact: pd.DataFrame, engine):
    """Carga el chunk procesado a fact_chart_entry."""
    df_fact.to_sql(
        "fact_chart_entry",
        engine,
        schema=SCHEMA,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=5_000,
    )


# =============================================================================
# Validate
# =============================================================================

def validate(engine):
    """
    Validaciones básicas después de cargar todo.
    Si algo está mal el script falla aquí con un mensaje claro.
    """
    logger.info("Ejecutando validaciones post-carga...")

    with engine.connect() as conn:

        # conteo general de lo que quedó en cada tabla
        totales = conn.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM proyecto_spotify.dim_cancion)      AS canciones,
                (SELECT COUNT(*) FROM proyecto_spotify.dim_region)       AS regiones,
                (SELECT COUNT(*) FROM proyecto_spotify.fact_chart_entry) AS entradas_fact
        """)).fetchone()
        logger.info(
            "Conteos — canciones: %s | regiones: %s | entradas fact: %s",
            f"{totales.canciones:,}",
            f"{totales.regiones:,}",
            f"{totales.entradas_fact:,}",
        )

        # verifico que México y Global tienen datos, si no hay algo salió mal
        mx_global = conn.execute(text("""
            SELECT dr.region, COUNT(*) AS entradas
            FROM   proyecto_spotify.fact_chart_entry fce
            JOIN   proyecto_spotify.dim_region dr USING (region_key)
            WHERE  dr.es_mexico OR dr.es_global
            GROUP  BY dr.region
        """)).fetchall()
        for row in mx_global:
            logger.info("  %s → %s entradas", row.region, f"{row.entradas:,}")

        # no debería haber ranks fuera de rango después del transform
        rank_invalido = conn.execute(text("""
            SELECT COUNT(*) AS n
            FROM   proyecto_spotify.fact_chart_entry
            WHERE  rank < 1 OR rank > 200
        """)).scalar()
        assert rank_invalido == 0, f"Hay {rank_invalido} ranks fuera de rango"
        logger.info("✓ Todos los ranks están en rango válido (1-200)")

        # verifico que todas las fechas de la fact tienen match en dim_fecha
        fechas_huerfanas = conn.execute(text("""
            SELECT COUNT(*) AS n
            FROM   proyecto_spotify.fact_chart_entry fce
            LEFT JOIN proyecto_spotify.dim_fecha df USING (fecha_key)
            WHERE  df.fecha_key IS NULL
        """)).scalar()
        assert fechas_huerfanas == 0, f"Hay {fechas_huerfanas} fechas sin match en dim_fecha"
        logger.info("✓ Integridad referencial fecha OK")

    logger.info("Validaciones completadas correctamente")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="ETL Spotify Charts → Aurora PostgreSQL")
    parser.add_argument("--host",     required=True,  help="Host del cluster Aurora")
    parser.add_argument("--password", required=True,  help="Password de Aurora")
    parser.add_argument("--database", default="northwind", help="Nombre de la base de datos")
    parser.add_argument("--csv",      required=True,  help="Ruta al archivo charts.csv")
    parser.add_argument("--port",     default=5432,   type=int)
    args = parser.parse_args()

    # guardo el log en archivo además de consola para poder revisar qué pasó si algo falla
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("etl_spotify.log"),
        ],
    )

    # conexión a Aurora
    engine = create_engine(
        f"postgresql+psycopg2://postgres:{args.password}"
        f"@{args.host}:{args.port}/{args.database}",
        pool_pre_ping=True,
    )

    try:
        # limpio las tablas antes de cargar para que sea idempotente
        logger.info("Limpiando tablas para carga idempotente...")
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE proyecto_spotify.fact_chart_entry RESTART IDENTITY CASCADE"))
            conn.execute(text("TRUNCATE proyecto_spotify.dim_cancion      RESTART IDENTITY CASCADE"))
        logger.info("Tablas limpiadas")

        # cargo dim_region en memoria para resolver FKs sin hacer queries por cada fila
        with engine.connect() as conn:
            region_map = {
                r.region: r.region_key
                for r in conn.execute(text(
                    "SELECT region_key, region FROM proyecto_spotify.dim_region"
                ))
            }
        logger.info("dim_region cargada en memoria: %d regiones", len(region_map))

        # el CSV tiene ~26M filas, con chunks de 50k son ~520 iteraciones
        reader = extract(args.csv)
        total_chunks = 520   # estimado para que tqdm muestre el progreso bien

        cancion_map = {}     # {(titulo, artista): cancion_key} — va creciendo chunk a chunk

        logger.info("Iniciando carga chunk por chunk (chunksize=%d)...", CHUNKSIZE)

        for chunk in tqdm(reader, total=total_chunks, desc="Procesando chunks"):

            # Transform
            df = transform(chunk)
            if df.empty:
                continue

            # upsert canciones nuevas y actualizar mapa
            cancion_map.update(upsert_canciones(df, engine))

            # resolver FKs para la fact
            df["cancion_key"] = df.apply(
                lambda r: cancion_map.get((r["titulo"], r["artista"])), axis=1
            )
            df["region_key"] = df["region"].map(region_map)

            # descarto filas donde no pude resolver alguna FK (región no encontrada en dim_region)
            df_fact = df.dropna(subset=["cancion_key", "region_key"]).copy()

            df_fact = df_fact[[
                "fecha_key", "cancion_key", "region_key",
                "chart_key", "rank", "streams", "trend",
            ]].astype({
                "fecha_key":   "int32",
                "cancion_key": "int32",
                "region_key":  "int32",
                "chart_key":   "int8",
                "rank":        "int16",
            })

            load_fact(df_fact, engine)

        # validaciones finales
        validate(engine)
        logger.info("ETL completado exitosamente")

    except Exception as exc:
        logger.exception("ETL falló: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()