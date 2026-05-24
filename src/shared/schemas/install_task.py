"""Install task primitives — one task in a device's commissioning sequence.

Lives apart from template.py so the file-size budget holds; re-exported
from template.py so external imports stay stable.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CxLevel(StrEnum):
    """BICSI / data-center commissioning levels (L1→L5).

    L1: factory acceptance / energization. L2: point-to-point continuity.
    L3: functional / single-system. L4: integrated. L5: performance / final.
    Used as a milestone gate in the install sequence DAG — L(n) tasks
    don't start until every L(n-1) task across all devices is complete.
    """

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class InstallTask(BaseModel):
    """One install task within a device template's commissioning sequence.

    `depends_on` lists task names within the SAME template — cross-device
    dependencies are auto-derived from `cx_level` milestone gates.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    depends_on: list[str] = Field(default_factory=list)
    est_minutes: int = Field(gt=0)
    crew_role: Literal["electrician", "plumber", "it", "general"]
    cx_level: CxLevel
