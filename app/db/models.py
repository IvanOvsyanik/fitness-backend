from sqlalchemy import Column, Integer, String, Text, DateTime
import datetime
from app.db.database import Base

class Workout(Base):
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True, index=True)
    
    # Входные параметры
    goal = Column(String, index=True)
    level = Column(String)
    equipment = Column(String)
    
    # Результат от ИИ
    generated_plan = Column(Text)
    
    # Обратная связь (оценка). Изначально пустая, заполнится после тренировки
    feedback = Column(Text, nullable=True) 
    
    # Время создания записи
    created_at = Column(DateTime, default=datetime.datetime.utcnow)