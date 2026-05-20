from sqlalchemy import ARRAY, Column, Integer, String

from app.db.session import Base


class ExerciseORM(Base):
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    target_muscles = Column(ARRAY(String), nullable=False, default=list)
    equipment = Column(ARRAY(String), nullable=False, default=list)
    difficulty = Column(String, nullable=False, default="beginner")
    category = Column(String, nullable=True)
    description = Column(String, nullable=True)
    instructions = Column(ARRAY(String), nullable=True, default=list)
    duration_seconds = Column(Integer, nullable=True)
    calories_per_minute = Column(Integer, nullable=True)
