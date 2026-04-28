from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
import datetime
from app.db.database import Base

class User(Base):
    __tablename__ = "users"
    
    device_id = Column(String, primary_key=True, index=True)
    goal = Column(String)
    weight = Column(Integer)
    height = Column(Integer)
    age = Column(Integer)
    experience_level = Column(String)
    equipment = Column(String)
    
    base_rank = Column(String)     
    current_rank = Column(String)  
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Workout(Base):
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, ForeignKey("users.device_id"), index=True)
    
    goal = Column(String)
    level = Column(String)
    equipment = Column(String)
    target_time_minutes = Column(Integer, default=40) # Новое поле времени
    
    generated_plan = Column(Text) # Здесь будет храниться собранный ИИ JSON
    feedback = Column(Text, nullable=True)
    
    split_day = Column(Integer, default=1)
    banned_exercises = Column(Text, default="")
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)