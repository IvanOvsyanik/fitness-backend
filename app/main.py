from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.services.llm_service import generate_workout
from app.db.database import engine, Base, get_db
from app.db import models

# Проверяем и создаем таблицы при запуске
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Fitness Planner AI")

@app.get("/")
def read_root():
    return {"message": "Бекенд фитнес-приложения успешно запущен!"}

# Обрати внимание: мы добавили db: Session = Depends(get_db)
@app.post("/api/v1/workout/generate")
async def get_workout_plan(
    goal: str, 
    level: str, 
    equipment: str, 
    feedback: str = None,
    db: Session = Depends(get_db)  # Подключаемся к нашей базе
):
    # 1. Запрашиваем план у нейросети
    plan = await generate_workout(goal, level, equipment, feedback)
    
    # 2. Создаем новую запись для таблицы
    new_workout = models.Workout(
        goal=goal,
        level=level,
        equipment=equipment,
        generated_plan=plan,
        feedback=feedback # Пока тут пусто или то, что ввел юзер
    )
    
    # 3. Сохраняем запись в базу данных SQLite
    db.add(new_workout)
    db.commit()
    db.refresh(new_workout) # Обновляем объект, чтобы база присвоила ему ID
    
    # 4. Отдаем результат пользователю
    return {
        "status": "success",
        "workout_id": new_workout.id,  # УРА! Теперь у тренировки есть номер
        "parameters": {"goal": goal, "level": level, "equipment": equipment},
        "workout_plan": plan
    }