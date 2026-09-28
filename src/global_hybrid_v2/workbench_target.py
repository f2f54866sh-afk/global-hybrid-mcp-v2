"""Server-owned XLSX target identity; qualification can never name production."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TargetMode(StrEnum):
    PRODUCTION = "PRODUCTION"
    NONPRODUCTION_QUALIFICATION = "NONPRODUCTION_QUALIFICATION"


@dataclass(frozen=True)
class WorkbenchTargetBinding:
    mode: TargetMode
    file_id: str

    def __post_init__(self) -> None:
        from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID

        if self.mode is TargetMode.PRODUCTION:
            if self.file_id != CANONICAL_WORKBENCH_FILE_ID:
                raise ValueError("PRODUCTION_WORKBENCH_TARGET_OVERRIDE_FORBIDDEN")
        elif (self.mode is not TargetMode.NONPRODUCTION_QUALIFICATION
              or not self.file_id or self.file_id == CANONICAL_WORKBENCH_FILE_ID):
            raise ValueError("NONPRODUCTION_WORKBENCH_TARGET_INVALID")

    @classmethod
    def production(cls) -> WorkbenchTargetBinding:
        from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID

        return cls(TargetMode.PRODUCTION, CANONICAL_WORKBENCH_FILE_ID)

    @classmethod
    def qualification(cls, disposable_file_id: str) -> WorkbenchTargetBinding:
        return cls(TargetMode.NONPRODUCTION_QUALIFICATION, disposable_file_id)
