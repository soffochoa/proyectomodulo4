-- dim_chart — insertar los dos tipos de chart
--
-- solo hay dos valores posibles en el dataset: top200 y viral50
-- lo pongo en script separado para mantener consistencia con los otros
-- aunque técnicamente ya se insertaron en el DDL, este script es por si
-- alguien borra los datos y necesita re-cargar solo esta tabla

SET search_path TO proyecto_spotify;

INSERT INTO dim_chart (chart_key, nombre, descripcion) VALUES
    (1, 'top200',  'Top 200 canciones más escuchadas — incluye conteo de streams'),
    (2, 'viral50', 'Viral 50 — canciones con mayor crecimiento viral, sin conteo de streams')
ON CONFLICT (chart_key) DO NOTHING;  -- no duplica si ya existen


-- para verificar:
-- SELECT * FROM proyecto_spotify.dim_chart ORDER BY chart_key;
-- debería mostrar 2 filas