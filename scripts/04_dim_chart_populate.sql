-- dim_chart — insertar los dos tipos de chart
--
-- Solo hay dos valores en el dataset: top200 y viral50.
-- Lo dejo en script separado para poder re-cargar solo esta tabla si hace falta.

SET search_path TO proyecto_spotify;

INSERT INTO dim_chart (chart_key, nombre, descripcion) VALUES
    (1, 'top200',  'Top 200 canciones más escuchadas — incluye conteo de streams'),
    (2, 'viral50', 'Viral 50 — canciones con mayor crecimiento viral, sin conteo de streams')
ON CONFLICT (chart_key) DO NOTHING;  -- idempotente: re-ejecutar no duplica

-- VERIFICACIÓN (ejemplo):
-- SELECT * FROM proyecto_spotify.dim_chart ORDER BY chart_key;  -- debería mostrar 2 filas