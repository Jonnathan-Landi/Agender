# Auditoría de Agender 1.14.3

## Resumen ejecutivo

La auditoría partió de `1.13.1` en el commit
`f5caf070de4fa351a9fee887df2046897e472aae`. Se revisaron la estructura,
contratos frontend/backend, persistencia, autenticación, licencias, API local,
dependencias, Tauri, PyInstaller y publicación. No se encontraron secretos
versionados. La publicación queda en `1.14.3` por tres correcciones
independientes:

1. se restauró el manifiesto de desarrollo requerido por GitHub Actions;
2. se activaron integridad referencial y espera de escritura en SQLite;
3. se impidió exponer accidentalmente la API integrada fuera de loopback.

## Inventario y Parte 1: depuración estructural

| Elemento | Evidencia | Decisión |
|---|---|---|
| `layers/` | Seis archivos, sin referencias, con SHA-256 idéntico a seis recursos de `frontend/assets/hydromet-report/` | Carpeta eliminada; 5,66 MB duplicados |
| `.venv/`, `build/`, `dist/`, `src-tauri/target/` | Generados, ignorados y necesarios para validar la publicación | Conservados localmente, no versionados |
| Recursos hidrometeorológicos | Consumidos por backend, frontend, PyInstaller y pruebas | Conservados |
| Importación interna del mapa de temperatura | Solo permitía que una prueba alcanzara un auxiliar de lluvia | Prueba acoplada corregida; importación retirada |

El árbol base contenía 145 archivos versionados y 6.310.092 bytes. El aumento
del candidato corresponde principalmente a los datos, imágenes y código del
nuevo reporte hidrometeorológico, no a artefactos generados.

## Parte 2: funcionalidad y seguridad

| Severidad | Hallazgo | Corrección o decisión | Evidencia |
|---|---|---|---|
| Alta | El servidor aceptaba `0.0.0.0` mediante CLI aunque la API es exclusivamente local | Solo permite `127.0.0.1` o `localhost` | Prueba negativa de enlace |
| Media | SQLite declaraba claves foráneas sin activar su aplicación por conexión | `foreign_keys=ON` | Prueba de PRAGMA |
| Media | Una escritura concurrente podía fallar sin una política explícita del proyecto | `busy_timeout=5000` | Prueba de PRAGMA |
| Media aceptada | La sesión no caduca por inactividad | Requisito funcional explícito; logout, cambio de contraseña y licencia inválida la revocan | Pruebas de seguridad |
| Baja | La cookie usa HTTP sin `Secure` | Aceptado porque el servicio solo usa loopback; `HttpOnly` y `SameSite=Strict` permanecen activos | Revisión de middleware y cookie |
| Baja | `cargo-audit` no estaba instalado | Se intentó instalar dos veces; la compilación excedió el límite operativo. `Cargo.lock` sí se validó con Cargo | Limitación documentada |

La licencia conserva Ed25519, clave privada separada e ignorada, clave pública
embebida y verificación de firma. Importar una licencia para reemisión no altera
el formato: valida la firma y exige una revisión posterior; la activación sigue
validando vigencia y revisión.

Las dependencias Python de ejecución y compilación se auditaron con
`pip-audit 2.10.0`: no se reportaron vulnerabilidades conocidas.

## Parte 3: rendimiento y distribución

La importación en frío de `backend.main` se midió cinco veces: 449,4; 418,8;
406,6; 411,0 y 409,5 ms (media 419,3 ms). El frontend sin bibliotecas vendorizadas
ocupa 7.004.613 bytes en 61 archivos. No se identificó un cuello de botella que
justificara cambios especulativos; se conservaron la aplicación ASGI diferida
del Viewer, la carga bajo demanda de los módulos de reporte y el límite de ocho
hilos del backend.

## Lotes

### Lote 1

- Parte: 1.
- Objetivo: inventario y duplicados.
- Analizado: raíz, backend, frontend, empaquetado, Tauri, pruebas y generados.
- Eliminado: `layers/` (seis imágenes duplicadas, 5,66 MB).
- Conservado: generados ignorados y recursos con consumidores.
- Riesgo: bajo.
- Pruebas: hashes, búsqueda de referencias, suite completa.
- Regresiones: ninguna observada.

### Lote 2

- Parte: 2.
- Objetivo: contratos, licencia, sesión, base de datos y API local.
- Cambios: restricciones de loopback; PRAGMA de integridad y concurrencia;
  pruebas de regresión.
- Riesgo: medio por afectar inicio y persistencia.
- Pruebas: seguridad, servidor y suite completa.
- Regresiones: ninguna observada.

### Lote 3

- Parte: 3.
- Objetivo: línea base, dependencias y publicación.
- Cambios: manifiesto de desarrollo reproducible, versión, novedades y notas.
- Riesgo: bajo.
- Métricas: importación media 419,3 ms; 5,66 MB redundantes retirados.
- Optimizaciones descartadas: toda modificación sin beneficio medible.

## Validaciones y publicación

La matriz final se completa con los resultados del último ciclo:

| Validación | Resultado |
|---|---|
| Ruff | Correcto |
| Pruebas Python | 155 correctas con pytest y unittest |
| Sintaxis JavaScript | Correcta, excluyendo bibliotecas vendorizadas |
| Cargo fmt/check/clippy | Correctos con lockfile y advertencias como error |
| Dependencias Python | Sin vulnerabilidades conocidas |
| PyInstaller | Backend construido y trabajador empaquetado validado |
| Tauri/NSIS y firma | Instalador de 82.455.335 bytes y firma válidos |
| Arranque del artefacto | `/api/health` respondió dentro del verificador |
| Versiones y notas | `1.14.3`/`v1.14.3` coherentes |
| Secretos y diff | Correcto en la revisión previa al commit |

## Archivos y compatibilidad

- Carpeta eliminada: `layers/`.
- Código retirado: importación indirecta sin consumidor productivo.
- Dependencias retiradas: ninguna; todas las dependencias de aplicación
  permanecen justificadas por importaciones o empaquetado.
- Novedades: `frontend/index.html`.
- Notas: `release-notes/v1.14.3.md`.
- Formato de licencias: sin cambios.
- Migraciones: compatibles y no destructivas.

Los hashes de commits, etiqueta y resultado del push se registran en la entrega
final porque el propio commit cambia su hash y el flujo termina inmediatamente
después de subir la etiqueta.
