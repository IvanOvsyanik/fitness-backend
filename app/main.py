from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
import json
import random

from app.db.database import engine, Base, get_db
from app.db import models
from app.services import llm_service, kb_service

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Fitness Neuro-Symbolic AI")

class WorkoutRequest(BaseModel):
    goal: str
    level: str
    equipment: str
    pre_workout_text: Optional[str] = None

class FeedbackRequest(BaseModel):
    feedback_text: str

@app.get("/")
def read_root(): return {"message": "Бекенд запущен!"}

@app.post("/api/v1/workout/generate")
async def generate(req: WorkoutRequest, db: Session = Depends(get_db)):
    last = db.query(models.Workout).filter(models.Workout.goal == req.goal).order_by(models.Workout.id.desc()).first()
    
    current_split = (last.split_day % 3) + 1 if (last and req.goal.lower() == "масса") else 1
    long_term_bans = [b.strip() for b in last.banned_exercises.split(",") if b.strip()] if last else []
    
    analysis = await llm_service.extract_entities(req.pre_workout_text, mode="pre_workout")
    temp_injuries = analysis.get("temp_injuries", [])

    allowed, warmup, reason = kb_service.get_filtered_workout(
        req.goal, req.level, req.equipment, current_split, 
        long_term_bans, temp_injuries, last.generated_plan if last else None
    )

    if len(allowed) < 3:
        special_prompt = "Упражнений слишком мало. "
        if reason == "injury_conflict":
            special_prompt += "Боль пользователя заблокировала мышцы сегодняшнего дня. Предложи сменить день сплита."
        else:
            special_prompt += f"Слишком много банов. В черном списке: {', '.join(long_term_bans)}. Попроси разблокировать."
        note = await llm_service.generate_coach_note(req.goal, special_prompt, temp_injuries)
    else:
        note = await llm_service.generate_coach_note(req.goal, req.pre_workout_text or "Всё отлично", temp_injuries)

    selected_main = random.sample(allowed, min(len(allowed), 5)) if allowed else []
    plan_dict = {"warmup": warmup, "main_workout": selected_main, "coach_note": note}

    new_w = models.Workout(
        goal=req.goal, level=req.level, equipment=req.equipment,
        split_day=current_split, banned_exercises=",".join(long_term_bans),
        generated_plan=json.dumps(plan_dict, ensure_ascii=False)
    )
    db.add(new_w)
    db.commit()
    db.refresh(new_w)
    
    return {"workout_id": new_w.id, "split_day": current_split, "plan": plan_dict}

@app.post("/api/v1/workout/{wid}/feedback")
async def feedback(wid: int, req: FeedbackRequest, db: Session = Depends(get_db)):
    w = db.query(models.Workout).filter(models.Workout.id == wid).first()
    if not w: raise HTTPException(404, detail="Тренировка не найдена")

    current_bans_str = w.banned_exercises or ""
    catalog_str = kb_service.get_all_exercises_catalog(w.goal) 
    
    analysis = await llm_service.extract_entities(
        req.feedback_text, 
        mode="post_workout", 
        existing_bans=current_bans_str,
        catalog=catalog_str
    )
    
    # 1. ОБРАБОТКА БАНОВ
    current_bans = set([b.strip() for b in current_bans_str.split(",") if b.strip()])
    
    for new_ban in analysis.get("banned", []):
        clean_ban = new_ban.strip(' "\'')
        if clean_ban:
            current_bans.add(clean_ban)
        
    for unban in analysis.get("unbanned", []):
        clean_unban = unban.strip(' "\'')
        to_remove = []
        for b in current_bans:
            if clean_unban.lower() in b.lower():
                to_remove.append(b)
        for r in to_remove:
            current_bans.discard(r)
    
    w.banned_exercises = ",".join(filter(None, current_bans))
    w.feedback = req.feedback_text
    
    # 2. ОБРАБОТКА СЛОЖНОСТИ (Auto-regulation)
    level_change = analysis.get("level_change", "none")
    current_level = w.level.lower()
    new_level = current_level

    if level_change == "up":
        if "новичок" in current_level: new_level = "средний"
        elif "средн" in current_level: new_level = "профи"
    elif level_change == "down":
        if "профи" in current_level: new_level = "средний"
        elif "средн" in current_level: new_level = "новичок"
        
    # Сохраняем новый уровень в эту тренировку, чтобы история была актуальной
    w.level = new_level
    db.commit()
    
    return {
        "status": "success", 
        "ai_analysis": analysis, 
        "current_bans": w.banned_exercises,
        "recommended_level": new_level # Отдаем фронтенду, чтобы он знал новый уровень юзера
    }