from sqlalchemy import Column, Integer, String, Text, DateTime
import datetime
from app.db.database import Base

class Workout(Base):
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True, index=True)
    goal = Column(String)
    level = Column(String)
    equipment = Column(String)
    generated_plan = Column(Text)
    feedback = Column(Text, nullable=True)
    
    split_day = Column(Integer, default=1)
    banned_exercises = Column(Text, default="")
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)