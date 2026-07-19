# Arquitectura de Agender

Agender es una aplicación de escritorio local con tres capas:

1. `frontend/`: interfaz principal y Viewer embebido.
2. `backend/`: API local, persistencia, sincronización y procesamiento.
3. `src-tauri/`: ciclo de vida de escritorio, empaquetado y actualizaciones.

## Reglas de dependencia

- `src-tauri` inicia y detiene el backend, pero no contiene reglas de negocio.
- `backend/main.py` compone rutas y middleware; la lógica debe vivir en módulos de dominio.
- `backend/viewer/api.py` expone HTTP y coordina sesiones; no debe encargarse de formatos ni diálogos.
- `backend/viewer/export_output.py` genera DAT, CSV y XLSX y administra destinos locales.
- `backend/viewer/aggregations.py` define resoluciones y reglas de agregación de variables.
- `backend/viewer/naming.py` concentra la normalización de nombres del Viewer.
- `backend/desktop_dialogs.py` es el único adaptador para diálogos nativos de archivos y carpetas.
- `backend/hydromet_export.py` genera el inventario Excel; `main.py` solo valida y enruta la solicitud.
- `backend/lazy_asgi.py` mantiene módulos pesados fuera del camino crítico de arranque.

## Rendimiento de arranque

- El proceso principal no debe importar Polars, DuckDB ni el Viewer antes de anunciar el puerto.
- `/viewer-api` carga su aplicación ASGI con la primera solicitud.
- La indexación hidrometeorológica se importa dentro de un trabajador cuando se solicita el inventario.
- La sincronización remota no bloquea la construcción inicial de la interfaz.
- Las migraciones independientes de almacenamiento del frontend pueden ejecutarse en paralelo.
- `frontend/js/core/` contiene infraestructura compartida.
- `frontend/js/features/` contiene controladores de cada función visible.
- `frontend/viewer/` es un módulo encapsulado y se comunica mediante `/viewer-api`.

No se permiten dependencias desde módulos de dominio hacia `backend/main.py`.

## Estado actual y siguientes separaciones

La migración debe ser gradual y conservar una aplicación ejecutable después de cada cambio.

### Backend Viewer

Estado actual:

- `api.py`: sesiones, ingestión, consultas y rutas.
- `export_output.py`: formatos, nombres y selección de destinos.
- `aggregations.py`: resoluciones temporales y funciones de agregación.
- `naming.py`: normalización de nombres y encabezados.

Siguientes extracciones:

1. `sessions.py`: caché, metadatos y ciclo de vida de sesiones.
2. `ingestion.py`: lectura, detección de timestamps y normalización.
3. `queries.py`: agregaciones, estadísticas y consultas DuckDB.
4. `exports.py`: modelos y coordinación de exportación individual y por lotes.
5. `api.py`: únicamente rutas y traducción de errores HTTP.

### Frontend principal

Siguientes extracciones:

1. Dividir `features/viewer.js` en apertura del visor, descarga individual y descarga por lotes.
2. Separar los modales hidrometeorológicos de `index.html` cuando exista un cargador de componentes local.
3. Dividir `hydromet.css` por tabla, mapa, menús contextuales y descargas.
4. Mantener `app.js` como punto de composición, sin lógica de dominio.

## Política de eliminación

Un archivo fuente solo se elimina cuando:

- no aparece en imports, scripts HTML, configuración de empaquetado ni pruebas;
- su comportamiento no forma parte de una ruta activa;
- la suite completa continúa pasando después de retirarlo.

Las funciones de copia de seguridad, sincronización, compatibilidad gráfica y migración de datos
no son rollback obsoleto: protegen datos o mantienen compatibilidad activa.

## Archivos generados

Estas rutas no son código fuente y ya están excluidas por `.gitignore`:

- `build/`
- `dist/`
- `release-artifacts/`
- `src-tauri/target/`
- `src-tauri/resources/backend/`

Pueden limpiarse antes de una compilación reproducible. `release-artifacts/` debe conservarse cuando
sus instaladores o firmas todavía sean necesarios para distribución.

## Criterio de finalización por etapa

Cada extracción debe cumplir:

- análisis estático sin errores;
- pruebas unitarias completas;
- validación de JavaScript;
- verificación del empaquetado cuando cambien imports o recursos;
- ningún cambio simultáneo de comportamiento y estructura salvo que tenga una prueba específica.
