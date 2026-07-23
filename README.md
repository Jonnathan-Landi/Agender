# Agender

Aplicación local para consultar el inventario y la completitud de estaciones hidrometeorológicas.

## Estructura

```text
backend/                 API FastAPI y procesamiento
  data/stations.xlsx     Catálogo maestro de estaciones
  readers/               Lectores independientes de datos crudos y QC
  requirements.txt       Dependencias Python
frontend/                Aplicación web
  index.html
  css/
  js/
tests/                   Pruebas y archivos pequeños de ejemplo
```

## Instalación

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-dev.ps1
```

El entorno queda aislado en `.venv` (ignorado por Git). Durante desarrollo,
Tauri utiliza automáticamente `.venv\Scripts\python.exe`; no es necesario
activar el entorno antes de ejecutar la aplicación.

## Ejecución

```powershell
.\.venv\Scripts\python.exe -m backend
```

Para iniciar la aplicación de escritorio en desarrollo:

```powershell
cargo tauri dev
```

Antes de confirmar cambios en el backend, ejecuta el análisis estático:

```powershell
.\.venv\Scripts\ruff.exe check backend
```

Abre `http://localhost:3000`.

## Aplicación de escritorio

El empaquetado usa Tauri 2 y un backend Python `onedir` generado por PyInstaller. Instala una sola vez Rust, Tauri CLI y las dependencias de compilación; después ejecuta:

```powershell
python -m pip install -r packaging\requirements-build.txt
cargo install tauri-cli --version "^2" --locked
powershell -ExecutionPolicy Bypass -File scripts\build-desktop.ps1
```

El instalador de Windows se genera en `src-tauri\target\release\bundle\nsis`.

## Publicar actualizaciones

Agender consulta la última release de GitHub desde **Configuración > Actualizaciones**.
Los paquetes se firman para impedir que una descarga manipulada pueda instalarse.

1. Conserva `updater-private.key` en un lugar seguro; Git lo ignora deliberadamente.
2. Crea en GitHub Actions el secreto `TAURI_SIGNING_PRIVATE_KEY` con todo el contenido
   de ese archivo. La clave actual no tiene contraseña.
3. Actualiza la misma versión SemVer en `src-tauri/tauri.conf.json` y `src-tauri/Cargo.toml`.
   En la línea `1.13.x`, el tercer número identifica el acumulado de correcciones publicadas:
   por ejemplo, seis correcciones corresponden a `1.13.6`.
4. Antes de crear la etiqueta, ejecuta localmente el mismo build y las mismas validaciones
   que usará GitHub Actions:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-release.ps1 -ExpectedTag v1.13.1
```

El comando no publica nada. Comprueba las versiones, el backend empaquetado, el instalador
y su firma, y deja en `release-artifacts/` exactamente los archivos que se publicarían.

5. Si todo termina correctamente, confirma los cambios y publica la etiqueta:

```powershell
git tag v1.13.1
git push origin v1.13.1
```

GitHub Actions vuelve a construir y validar desde cero. Después carga los artefactos en una
release en borrador y solo la hace pública cuando confirma que todos llegaron a GitHub. Si
falla cualquier fase, la actualización no queda visible para las instalaciones en producción.

## Datos locales

Las rutas de datos crudos y QC se configuran desde **Configuración > Rutas**. El backend lee `.csv`, `.dat` y `.txt` mediante Polars y mantiene índices incrementales en `%APPDATA%\Agender\cache`.

Los usuarios, credenciales, rutas, solicitudes, tareas diarias y eventos de agenda se conservan en `%APPDATA%\Agender`. Los datos funcionales se almacenan en SQLite y se vinculan al identificador interno de cada usuario. Al iniciar esta versión, Agender migra automáticamente los datos anteriores de `localStorage`; después lo utiliza solo como cola temporal de recuperación mientras confirma cada escritura en SQLite. Una actualización normal reemplaza los binarios de la aplicación sin eliminar este directorio de datos.

`backend/data/stations.xlsx` es el catálogo maestro. La tabla siempre muestra sus estaciones y obtiene de allí Código, Tipo, X_UTM, Y_UTM, Z y Cuenca. Solo los archivos cuyo nombre coincide con un código del catálogo completan Primer registro, Último registro, Actualizada y Completitud.

## Viewer de estaciones

Haz clic derecho sobre una estación de la tabla o del mapa y selecciona
**Viewer**. Agender abre internamente el visor de series temporales y carga
el archivo más reciente de la estación para la fuente activa (datos crudos o
control de calidad). El módulo está aislado en `backend/viewer` y
`frontend/viewer`; consulta su README para conocer el contrato de integración.

## Licencias y acceso local

Agender verifica licencias Ed25519 desde `C:\ProgramData\Agender\license.json`
o `%APPDATA%\Agender\license.json`. Los usuarios se provisionan desde la
licencia firmada y sus contraseñas se validan localmente mediante Argon2id.
Las sesiones caducan tras una hora sin actividad o después de 24 horas y se
revocan en todos los equipos locales cuando se cambia la contraseña.

La clave privada de la autoridad no forma parte del instalador. Un administrador
puede importarla desde **Generar licencia** y emitir allí licencias versión 2
con permisos granulares y una revisión creciente. Una misma licencia puede
activarse en varias computadoras para el usuario provisionado. Al actualizar
la misma licencia se conserva su identificador y se incrementa la revisión;
una licencia nueva firmada también puede reemplazarla si pertenece al mismo
usuario.

En Windows, la autoridad importada se guarda en
`%APPDATA%\Agender\authority\license_private_key.pem` con acceso restringido al
usuario actual, Administradores y SYSTEM. La clave de firma del actualizador se
mantiene por separado en `%APPDATA%\Agender\secrets\updater-private.key` para
compilaciones locales; ninguna de las dos debe residir en el repositorio.

La autoridad debe corresponder a
`backend/security/license_public_key.pem`. Conserva una copia de seguridad
segura de la clave privada: sin ella no se pueden emitir nuevas licencias
compatibles. No se debe distribuir la clave privada junto con Agender ni crear
una autoridad nueva para una instalación existente.
