"""Backend local de Agender."""

import os

# Polars crea su grupo global en el primer import. Este límite conserva
# capacidad para la interfaz y para el sistema operativo durante análisis.
DEFAULT_WORKER_THREADS = min(4, max(1, (os.cpu_count() or 2) // 2))
os.environ.setdefault("AGENDER_WORKER_THREADS", str(DEFAULT_WORKER_THREADS))
os.environ.setdefault("POLARS_MAX_THREADS", os.environ["AGENDER_WORKER_THREADS"])
