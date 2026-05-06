from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
import json

from app.db.database import engine, Base, get_db
from app.db import models
from app.services import llm_service, kb_service, progress_service

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Fitness Generative AI")

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
    target_time_minutes: int = 40 
    fallback_choice: Optional[str] = None

class FeedbackRequest(BaseModel):
    feedback_text: str

# Модель для Бан-листа
class UnbanRequest(BaseModel):
    exercise_name: str

@app.get("/")
def read_root(): return {"message": "Генеративный бэкенд работает!"}

@app.post("/api/v1/users/onboarding")
async def onboarding(req: OnboardingRequest, db: Session = Depends(get_db)):
    # Ищем, есть ли уже такой пользователь в базе
    user = db.query(models.User).filter(models.User.device_id == req.device_id).first()
    
    # В любом случае просим ИИ проанализировать новые данные и выдать ранг
    ai = await llm_service.analyze_onboarding(
        req.weight, req.height, req.age, req.experience, req.equipment
    )
    rank = ai.get("initial_rank", "новичок")
    
    if user:
        # ОБНОВЛЯЕМ существующего пользователя новыми данными из анкеты
        user.goal = req.goal
        user.weight = req.weight
        user.height = req.height
        user.age = req.age
        user.experience_level = req.experience
        user.equipment = req.equipment
        user.base_rank = rank
        user.current_rank = rank # Сбрасываем ранг на начальный при пересоздании плана
        
        db.commit()
        return {
            "status": "updated", 
            "reason": ai.get("reason"), 
            "rank": rank
        }
    
    # Если пользователя нет (первая регистрация), создаем новую запись
    new_user = models.User(
        device_id=req.device_id, 
        goal=req.goal, 
        weight=req.weight, 
        height=req.height,
        age=req.age, 
        experience_level=req.experience, 
        equipment=req.equipment,
        base_rank=rank, 
        current_rank=rank
    )
    db.add(new_user)
    db.commit()
    
    return {
        "status": "success", 
        "reason": ai.get("reason"), 
        "rank": rank
    }

@app.post("/api/v1/workout/generate")
async def generate(req: WorkoutRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.device_id == req.device_id).first()
    if not user: raise HTTPException(404, "Run onboarding first!")

    last = db.query(models.Workout).filter(models.Workout.device_id == req.device_id).order_by(models.Workout.id.desc()).first()
    original_split = (last.split_day % 3) + 1 if (last and user.goal.lower() == "масса") else 1
    
    # ФИКС: Безопасное чтение банов
    bans = [b.strip() for b in (last.banned_exercises or "").split(",") if b.strip()] if last else []
    
    valid_tags = kb_service.get_all_contraindications()
    analysis = await llm_service.extract_entities(req.pre_workout_text, mode="pre_workout", valid_injuries=valid_tags)
    
    injuries = analysis.get("injuries", [])
    doms = analysis.get("doms", [])
    mood = analysis.get("mood_boost", "none")

    lvl = user.current_rank.lower()
    if mood == "up": lvl = "средний" if "новичок" in lvl else ("профи" if "средн" in lvl else lvl)
    elif mood == "down": lvl = "средний" if "профи" in lvl else ("новичок" if "средн" in lvl else lvl)

    if not req.fallback_choice:
        planned_targets = kb_service.get_split_targets(user.goal, original_split)
        test_catalogs = kb_service.get_filtered_catalogs(
            user.goal, lvl, user.equipment, original_split, bans, injuries, is_light_fullbody=False
        )
        if len(test_catalogs["main"]) < 2 and user.goal.lower() == "масса":
            return {
                "status": "choice_required",
                "message": f"Острая травма ({', '.join(injuries)}) блокирует тренировку на целевые мышцы ({', '.join(planned_targets)}). Что делаем?",
                "options": [
                    {"id": "next_split", "label": "Перейти к следующему дню сплита"},
                    {"id": "light_fullbody", "label": "Сделать легкую тренировку на всё тело"}
                ]
            }

    active_split = original_split
    is_light = False
    
    if req.fallback_choice == "next_split": active_split = (original_split % 3) + 1
    elif req.fallback_choice == "light_fullbody": is_light = True

    full_catalogs = kb_service.get_filtered_catalogs(
        user.goal, lvl, user.equipment, active_split, bans, injuries, is_light_fullbody=is_light
    )
    
    compact_catalog = kb_service.prepare_catalog_for_llm(full_catalogs)
    
    llm_plan_ids = await llm_service.generate_workout_logic(
        goal=user.goal, 
        target_time_minutes=req.target_time_minutes, 
        catalog_for_llm=compact_catalog, 
        doms=doms 
    )
    
    final_plan_objects = kb_service.get_full_exercises_by_ids(full_catalogs, llm_plan_ids)
    
    note = await llm_service.generate_coach_note(user.goal, injuries, doms, mood, req.fallback_choice)
    
    final_workout_json = {
        "coach_note": note,
        "estimated_minutes": llm_plan_ids.get("estimated_total_minutes", req.target_time_minutes),
        "phases": final_plan_objects
    }

    new_w = models.Workout(
        device_id=user.device_id, goal=user.goal, level=lvl, equipment=user.equipment,
        target_time_minutes=req.target_time_minutes,
        split_day=active_split if not is_light else original_split, 
        banned_exercises=",".join(bans), generated_plan=json.dumps(final_workout_json, ensure_ascii=False)
    )
    db.add(new_w); db.commit()
    
    return {
        "status": "success",
        "workout_id": new_w.id,
        "active_level": lvl,
        "fallback_applied": req.fallback_choice,
        "workout": final_workout_json
    }

@app.post("/api/v1/workout/{wid}/feedback")
async def feedback(wid: int, req: FeedbackRequest, db: Session = Depends(get_db)):
    w = db.query(models.Workout).filter(models.Workout.id == wid).first()
    if not w: raise HTTPException(404, "Workout not found")
    user = db.query(models.User).filter(models.User.device_id == w.device_id).first()
    
    safe_bans = w.banned_exercises or ""
    
    # Собираем строковый каталог всех упражнений для ИИ
    catalog_str = kb_service.get_all_exercises_catalog(user.goal)
    
    analysis = await llm_service.extract_entities(
        req.feedback_text, 
        mode="post_workout", 
        existing_bans=safe_bans,
        catalog=catalog_str
    )
    
    current_bans = set([b.strip().lower() for b in safe_bans.split(",") if b.strip()])
    
    for b in analysis.get("banned_exercises", []): current_bans.add(b.strip().lower())
    for b in analysis.get("banned_muscles", []): current_bans.add(b.strip().lower())
    for u in analysis.get("unbanned", []): 
        current_bans = {x for x in current_bans if u.lower() not in x}
        
    w.banned_exercises = ",".join(filter(None, current_bans))
    
    change = analysis.get("level_change", "none")
    rank = user.current_rank.lower()
    if change == "up": 
        user.current_rank = "средний" if "новичок" in rank else "профи"
    elif change == "down": 
        user.current_rank = "средний" if "профи" in rank else "новичок"
        
    db.commit()

    new_achievements = progress_service.check_and_unlock_achievements(db, user.device_id)
    
    return {
        "status": "success", 
        "new_rank": user.current_rank, 
        "bans": w.banned_exercises,
        "newly_unlocked_achievements": new_achievements
    }

@app.get("/api/v1/users/{device_id}/stats")
async def get_user_profile_stats(device_id: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.device_id == device_id).first()
    if not user:
        raise HTTPException(404, "User not found")
        
    stats = progress_service.get_user_stats(db, device_id)
    
    return {
        "status": "success",
        "user_info": {
            "goal": user.goal,
            "rank": user.current_rank,
            "equipment": user.equipment
        },
        "stats": stats
    }

# --- ЭНДПОИНТЫ ДЛЯ ЭКРАНА БАН-ЛИСТА ---
@app.get("/api/v1/users/{device_id}/bans")
async def get_user_bans(device_id: str, db: Session = Depends(get_db)):
    last_w = db.query(models.Workout).filter(models.Workout.device_id == device_id).order_by(models.Workout.id.desc()).first()
    
    if not last_w or not last_w.banned_exercises:
        return {"status": "success", "bans": []}
    
    bans = [b.strip() for b in last_w.banned_exercises.split(",") if b.strip()]
    formatted_bans = [{"id": i, "name": name.capitalize()} for i, name in enumerate(bans)]
    
    return {"status": "success", "bans": formatted_bans}

@app.delete("/api/v1/users/{device_id}/bans")
async def remove_ban(device_id: str, req: UnbanRequest, db: Session = Depends(get_db)):
    last_w = db.query(models.Workout).filter(models.Workout.device_id == device_id).order_by(models.Workout.id.desc()).first()
    
    if not last_w:
        raise HTTPException(404, "Workout history not found")
        
    bans = [b.strip() for b in (last_w.banned_exercises or "").split(",") if b.strip()]
    bans = [b for b in bans if b.lower() != req.exercise_name.lower()]
    
    last_w.banned_exercises = ",".join(bans)
    db.commit()
    
    return {"status": "success"}