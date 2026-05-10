"""TemplateLoader — walks device_templates/, validates, builds catalog.

Per the foundation design spec (2026-05-09): edp-api walks its
device_templates/ at startup, validates every YAML, and panics on the
first failure. Catalog is keyed by template slug.
"""

from pathlib import Path

import yaml
from pydantic import ValidationError

from src.shared.schemas.template import DeviceTemplate


class TemplateLoadError(Exception):
    """Raised when a template file fails to parse or validate."""


class TemplateLoader:
    """Walks `<root>/{leaf,module}/*.yaml`, validates each, returns catalog."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def load_catalog(self) -> dict[str, DeviceTemplate]:
        """Return catalog keyed by template slug. Raises on first failure."""
        catalog: dict[str, DeviceTemplate] = {}
        for kind_dir in ("leaf", "module"):
            sub = self._root / kind_dir
            if not sub.is_dir():
                continue
            for path in sorted(sub.glob("*.yaml")):
                tpl = self._load_file(path)
                if tpl.template in catalog:
                    raise TemplateLoadError(
                        f"duplicate template slug {tpl.template!r}: "
                        f"{path} conflicts with prior file"
                    )
                catalog[tpl.template] = tpl
        self._check_contains_refs(catalog)
        return catalog

    @staticmethod
    def _check_contains_refs(catalog: dict[str, DeviceTemplate]) -> None:
        """Assert every module's contains[].template resolves to a catalog key."""
        for tpl in catalog.values():
            for entry in tpl.contains:
                if entry.template not in catalog:
                    raise TemplateLoadError(
                        f"template {tpl.template!r}: "
                        f"contains[].template {entry.template!r} not in catalog"
                    )

    @staticmethod
    def _load_file(path: Path) -> DeviceTemplate:
        try:
            raw = yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            raise TemplateLoadError(f"{path}: invalid YAML: {e}") from e
        try:
            return DeviceTemplate.model_validate(raw)
        except ValidationError as e:
            raise TemplateLoadError(f"{path}: schema validation failed:\n{e}") from e
