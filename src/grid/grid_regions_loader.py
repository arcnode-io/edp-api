"""GridRegionsLoader — reads + validates config/grid_regions.yaml.

Same fail-fast shape as src/dtm/template_loader.py: parse the YAML, validate
against the pydantic schema, raise on the first failure so drift surfaces at
app startup rather than at request time.
"""

from pathlib import Path

import yaml
from pydantic import ValidationError

from src.shared.schemas.grid_regions import GridRegionsConfig


class GridRegionsLoadError(Exception):
    """Raised when config/grid_regions.yaml fails to parse or validate."""


class GridRegionsLoader:
    """Loads + validates the single grid_regions.yaml file at `path`."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> GridRegionsConfig:
        """Return the parsed config. Raises GridRegionsLoadError on any failure."""
        try:
            raw = self._path.read_text()
        except OSError as e:
            raise GridRegionsLoadError(f"{self._path}: {e}") from e
        try:
            parsed = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise GridRegionsLoadError(f"{self._path}: invalid YAML: {e}") from e
        try:
            return GridRegionsConfig.model_validate(parsed)
        except ValidationError as e:
            raise GridRegionsLoadError(
                f"{self._path}: schema validation failed:\n{e}"
            ) from e
