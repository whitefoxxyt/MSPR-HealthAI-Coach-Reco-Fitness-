from sqlalchemy import ARRAY, Column, Integer, String, Text

from app.db.session import Base


class ExerciseORM(Base):
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    target_muscles = Column(ARRAY(String), nullable=False, default=list)
    # La colonne SQL s'appelle "equipments" (cf. MSPR-DB/migrations/V01__init_schema.sql).
    # On expose l'attribut Python `equipment` pour rester aligne avec le reste du code.
    equipment = Column("equipments", ARRAY(String), nullable=False, default=list)
    instructions = Column(Text, nullable=True)
    gif_url = Column(String, nullable=True)
