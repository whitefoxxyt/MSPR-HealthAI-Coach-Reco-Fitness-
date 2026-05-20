from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class HealthGoalFitness(str, Enum):
    fat_loss = "fat_loss"
    muscle_strength = "muscle_strength"
    endurance = "endurance"
    general_health = "general_health"


class ExperienceLevel(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class SessionPreferences(BaseModel):
    duration_min_per_session: int = Field(ge=10, le=300, default=45)
    sessions_per_week: int = Field(ge=1, le=14, default=3)


class FitnessProfileRequest(BaseModel):
    health_goal_fitness: HealthGoalFitness
    experience_level: ExperienceLevel
    equipment: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    preferences: SessionPreferences = Field(default_factory=SessionPreferences)


class FitnessProfileResponse(BaseModel):
    user_id: str
    health_goal_fitness: HealthGoalFitness
    experience_level: ExperienceLevel
    equipment: list[str]
    limitations: list[str]
    preferences: SessionPreferences
    updated_at: datetime
