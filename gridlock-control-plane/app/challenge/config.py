"""The two explicitly versioned distance profiles and their thresholds."""
import os
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class Profile(str, Enum):
    STARTER_COMPATIBILITY = "STARTER_COMPATIBILITY"
    CHALLENGE_GEOMETRY = "CHALLENGE_GEOMETRY"


class Config(BaseModel):
    profile: Profile = Profile.CHALLENGE_GEOMETRY
    profile_id: str = "sperry-gridlock-v1"
    engine_version: str = "1.0.0"
    maximum_meters: float = Field(40000, gt=0, allow_inf_nan=False)
    row_access_meters: float = Field(1600, gt=0)
    site_logistics_meters: float = Field(8000, gt=0)
    close_milestone_days: int = 365
    meters_per_mile: float = 1609.344
    earth_radius_meters: float = 6371008.8
    upper_bound: str = "STRICTLY_LESS_THAN"
    eligible_statuses: tuple[str, ...] = ("proposed", "planned", "approved", "in_progress", "under_construction")

    @model_validator(mode="after")
    def ordered(self):
        if self.row_access_meters >= self.site_logistics_meters:
            raise ValueError("ROW threshold must be smaller than logistics threshold")
        return self


def get_config(profile: Profile = Profile.CHALLENGE_GEOMETRY, maximum_meters: float | None = None):
    default = 25 * 1609.344 if profile == Profile.STARTER_COMPATIBILITY else float(os.getenv("CHALLENGE_MAXIMUM_METERS", "40000"))
    return Config(profile=profile, maximum_meters=default if maximum_meters is None else maximum_meters)
