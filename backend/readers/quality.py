from .base import DelimitedReader


class QualityReader(DelimitedReader):
    source = "quality"

    def select_variables(self, columns: list[str]) -> list[str]:
        # QC tiene su propio esquema: se conserva exactamente el conjunto de
        # variables publicado por cada archivo procesado.
        return super().select_variables(columns)
