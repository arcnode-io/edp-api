"""TopologyLoader — pulls assembly topology yamls by URL.

Production impl talks S3; tests inject an in-memory dict-backed fake.
"""

from typing import Protocol

from src.dtm.topology_yaml import TopologyYaml


class TopologyLoader(Protocol):
    """Fetch + parse an assembly topology yaml by URL."""

    def load(self, url: str) -> TopologyYaml:
        """Return the parsed TopologyYaml at `url`."""
        ...
