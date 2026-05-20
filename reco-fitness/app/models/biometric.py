from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String

from app.db.session import Base


class BiometricEntryORM(Base):
    __tablename__ = "biometric_entries"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    weight_kg = Column(Float, nullable=True)
    avg_heart_rate_bpm = Column(Integer, nullable=True)
    experience_level = Column(String, nullable=True)
    measured_at = Column(DateTime(timezone=True), nullable=False)
