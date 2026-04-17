from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
import json

from app.db.database import engine, Base, get_db
from app.db import models
from app.services import llm_service, kb_service

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Fitness Neuro-Symbolic AI")

class WorkoutRequest(BaseModel):
    goal: str
    level: str
    equipment: str
    pre_workout_text: Optional[str] = None # "Болит шея"

class FeedbackRequest(BaseModel):
    feedback_text: str # "Убери жим, верни планку"

@app.post("/api/v1/workout/generate")
async def generate(req: WorkoutRequest, db: Session = Depends(get_db)):
    # 1. Получаем контекст из истории
    last = db.query(models.Workout).filter(models.Workout.goal == req.goal).order_by(models.Workout.id.desc()).first()
    
    current_split = (last.split_day % 3) + 1 if (last and req.goal == "масса") else 1
    long_term_bans = last.banned_exercises.split(",") if (last and last.banned_exercises) else []
    
    # 2. ИИ Анализирует текущее состояние (Травмы сегодня)
    analysis = await llm_service.extract_entities(req.pre_workout_text, mode="pre_workout")
    temp_injuries = analysis.get("temp_injuries", [])

    # 3. Python генерирует план
    plan = kb_service.get_filtered_workout(
        req.goal, req.level, req.equipment, current_split, 
        long_term_bans, temp_injuries, last.generated_plan if last else None
    )

    # 4. ИИ пишет напутствие
    note = await llm_service.generate_coach_note(req.goal, req.pre_workout_text, temp_injuries)
    plan["coach_note"] = note

    # 5. Сохраняем (травмы не сохраняем, только баны!)
    new_w = models.Workout(
        goal=req.goal, level=req.level, equipment=req.equipment,
        split_day=current_split, banned_exercises=",".join(long_term_bans),
        generated_plan=json.dumps(plan, ensure_ascii=False)
    )
    db.add(new_w)
    db.commit()
    db.refresh(new_w)
    
    return {"workout_id": new_w.id, "plan": plan}

@app.post("/api/v1/workout/{wid}/feedback")
async def feedback(wid: int, req: FeedbackRequest, db: Session = Depends(get_db)):
    w = db.query(models.Workout).filter(models.Workout.id == wid).first()
    if not w: raise HTTPException(404)

    # ИИ анализирует отзыв на предмет банов/разбанов
    analysis = await llm_service.extract_entities(req.feedback_text, mode="post_workout")
    
    # Обновляем долгосрочный список
    current_bans = set(w.banned_exercises.split(",")) if w.banned_exercises else set()
    current_bans.update(analysis.get("banned", []))
    for item in analysis.get("unbanned", []):
        current_bans.discard(item)
    
    w.banned_exercises = ",".join(filter(None, current_bans))
    w.feedback = req.feedback_text
    db.commit()
    
    return {"status": "success", "new_bans": w.banned_exercises}