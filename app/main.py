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

class OnboardingRequest(BaseModel):
    device_id: str
    goal: str
    weight: int
    height: int
    age: int
    experience: str
    equipment: str

class WorkoutRequest(BaseModel):
    device_id: str
    pre_workout_text: Optional[str] = None
    fallback_choice: Optional[str] = None  # НОВОЕ ПОЛЕ: "next_split" или "light_fullbody"

class FeedbackRequest(BaseModel):
    feedback_text: str

@app.get("/")
def read_root(): return {"message": "Сервер работает!"}

@app.post("/api/v1/users/onboarding")
async def onboarding(req: OnboardingRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.device_id == req.device_id).first()
    if user: return {"status": "exists", "rank": user.current_rank}
    
    ai = await llm_service.analyze_onboarding(req.weight, req.height, req.age, req.experience, req.equipment)
    rank = ai.get("initial_rank", "новичок")
    
    new_user = models.User(
        device_id=req.device_id, goal=req.goal, weight=req.weight, height=req.height,
        age=req.age, experience_level=req.experience, equipment=req.equipment,
        base_rank=rank, current_rank=rank
    )
    db.add(new_user); db.commit()
    return {"status": "success", "reason": ai.get("reason"), "rank": rank}

@app.post("/api/v1/workout/generate")
async def generate(req: WorkoutRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.device_id == req.device_id).first()
    if not user: raise HTTPException(404, "Run onboarding first!")

    last = db.query(models.Workout).filter(models.Workout.device_id == req.device_id).order_by(models.Workout.id.desc()).first()
    original_split = (last.split_day % 3) + 1 if (last and user.goal.lower() == "масса") else 1
    bans = [b.strip() for b in last.banned_exercises.split(",") if b.strip()] if last else []
    
    valid_tags = kb_service.get_all_contraindications()
    analysis = await llm_service.extract_entities(req.pre_workout_text, mode="pre_workout", valid_injuries=valid_tags)
    
    mood = analysis.get("mood_boost", "none")
    injuries = analysis.get("temp_injuries", [])

    lvl = user.current_rank.lower()
    if mood == "up": lvl = "средний" if "новичок" in lvl else ("профи" if "средн" in lvl else lvl)
    elif mood == "down": lvl = "средний" if "профи" in lvl else ("новичок" if "средн" in lvl else lvl)

    # ШАГ 1: Если юзер еще не сделал выбор, проверяем "черновик" тренировки
    if not req.fallback_choice:
        test_allowed, _, test_muscles = kb_service.get_filtered_workout(
            user.goal, lvl, user.equipment, original_split, bans, injuries, None, is_light_fullbody=False
        )
        
        # Если фильтр травм убил основные мышцы или оставил < 3 упражнений -> Требуем выбор!
        is_blocked = len(test_allowed) < 3 or (user.goal.lower() == "масса" and not test_muscles)
        
        if is_blocked:
            planned_targets = kb_service.get_split_targets(user.goal, original_split)
            return {
                "status": "choice_required",
                "message": f"Из-за травмы ({', '.join(injuries)}) тренировка на ({', '.join(planned_targets)}) сегодня отменяется. Что делаем?",
                "options": [
                    {"id": "next_split", "label": "Перейти к следующему дню сплита"},
                    {"id": "light_fullbody", "label": "Сделать легкую тренировку на всё тело"}
                ]
            }

    # ШАГ 2: Применяем выбор юзера
    active_split = original_split
    is_light = False
    
    if req.fallback_choice == "next_split":
        active_split = (original_split % 3) + 1
    elif req.fallback_choice == "light_fullbody":
        is_light = True

    # ШАГ 3: Финальная генерация
    allowed, warmup, muscles = kb_service.get_filtered_workout(
        user.goal, lvl, user.equipment, active_split, bans, injuries, 
        last.generated_plan if last else None, is_light_fullbody=is_light
    )

    note = await llm_service.generate_coach_note(user.goal, injuries, mood, active_split, muscles, req.fallback_choice)
    plan = {"warmup": warmup, "main": random.sample(allowed, min(len(allowed), 5)), "note": note}

    new_w = models.Workout(
        device_id=user.device_id, goal=user.goal, level=lvl, equipment=user.equipment,
        split_day=active_split if not is_light else original_split, 
        banned_exercises=",".join(bans), generated_plan=json.dumps(plan, ensure_ascii=False)
    )
    db.add(new_w); db.commit()
    
    return {
        "status": "success",
        "workout_id": new_w.id,
        "active_level": lvl,
        "fallback_applied": req.fallback_choice,
        "plan": plan
    }

@app.post("/api/v1/workout/{wid}/feedback")
async def feedback(wid: int, req: FeedbackRequest, db: Session = Depends(get_db)):
    # ... (эндпоинт отзыва остается абсолютно без изменений) ...
    w = db.query(models.Workout).filter(models.Workout.id == wid).first()
    if not w: raise HTTPException(404, "Workout not found")
    user = db.query(models.User).filter(models.User.device_id == w.device_id).first()
    catalog = kb_service.get_all_exercises_catalog(w.goal)
    analysis = await llm_service.extract_entities(req.feedback_text, mode="post_workout", existing_bans=w.banned_exercises, catalog=catalog)
    current_bans = set([b.strip() for b in w.banned_exercises.split(",") if b.strip()])
    for b in analysis.get("banned", []): current_bans.add(b.strip())
    for u in analysis.get("unbanned", []): current_bans = {x for x in current_bans if u.lower() not in x.lower()}
    w.banned_exercises = ",".join(filter(None, current_bans))
    change = analysis.get("level_change", "none")
    rank = user.current_rank.lower()
    if change == "up": user.current_rank = "средний" if "новичок" in rank else "профи"
    elif change == "down": user.current_rank = "средний" if "профи" in rank else "новичок"
    db.commit()
    return {"status": "success", "new_rank": user.current_rank, "bans": w.banned_exercises}