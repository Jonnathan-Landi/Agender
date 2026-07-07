# Módulo Viewer

Este módulo encapsula el motor de series temporales de Agender.
Agender se comunica con él únicamente mediante la sub-API montada en
`/viewer-api`; el inventario y el Viewer no comparten estado de dominio.

Contrato de apertura:

```text
POST /viewer-api/api/stations/{codigo}?source=raw|quality
```

La ruta se obtiene siempre de la configuración de Agender. Si hay varios
archivos cuyo nombre corresponde a la estación, se utiliza el más reciente.
El archivo original nunca se modifica: el Viewer trabaja con una sesión
Parquet guardada en `%APPDATA%/Agender/viewer`.

La interfaz encapsulada vive en `frontend/viewer`; la aplicación principal
solo abre esa interfaz dentro de un `iframe` y puede reemplazarla sin cambiar
la tabla o el mapa.
