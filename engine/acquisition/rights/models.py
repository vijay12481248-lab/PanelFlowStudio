from enum import Enum
from pydantic import BaseModel, Field

class RightsStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    CREATIVE_COMMONS = "CREATIVE_COMMONS"
    LICENSED = "LICENSED"
    USER_OWNED = "USER_OWNED"
    EXPLICIT_PERMISSION = "EXPLICIT_PERMISSION"


class RightsDeclaration(BaseModel):
    status: RightsStatus = Field(default=RightsStatus.UNKNOWN)
    license_type: str | None = Field(default=None, description="e.g. CC-BY 4.0, MIT, Public Domain Mark 1.0")
    license_url: str | None = Field(default=None, description="Direct URL to license terms if applicable")
    holder: str | None = Field(default=None, description="Author, copyright holder, or creator name")
    permission_notes: str | None = Field(default=None, description="Verification details, authorization record, or user-owned affirmation")

    def is_actionable(self) -> bool:
        """Determines if the rights status allows pipeline processing and acquisition."""
        return self.status != RightsStatus.UNKNOWN

    def validate_for_acquisition(self) -> None:
        """Raises ValueError if rights status is UNKNOWN."""
        if self.status == RightsStatus.UNKNOWN:
            raise ValueError(
                "Acquisition cannot proceed with UNKNOWN rights status. "
                "Explicitly declare PUBLIC_DOMAIN, CREATIVE_COMMONS, LICENSED, "
                "USER_OWNED, or EXPLICIT_PERMISSION."
            )
