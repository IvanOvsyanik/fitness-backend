from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
import json

from app.db.database import engine, Base, get_db
from app.db import models
from app.services import llm_service, kb_service

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
    target_time_minutes: int = 40 # НОВОЕ: Юзер может запросить время (по умолчанию 40)
    fallback_choice: Optional[str] = None

class FeedbackRequest(BaseModel):
    feedback_text: str

@app.get("/")
def read_root(): return {"message": "Генеративный бэкенд работает!"}

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
    
    # 1. Анализ текста (разделение травм и крепатуры)
    valid_tags = kb_service.get_all_contraindications()
    analysis = await llm_service.extract_entities(req.pre_workout_text, mode="pre_workout", valid_injuries=valid_tags)
    
    injuries = analysis.get("injuries", [])
    doms = analysis.get("doms", [])
    mood = analysis.get("mood_boost", "none")

    # Регулировка уровня
    lvl = user.current_rank.lower()
    if mood == "up": lvl = "средний" if "новичок" in lvl else ("профи" if "средн" in lvl else lvl)
    elif mood == "down": lvl = "средний" if "профи" in lvl else ("новичок" if "средн" in lvl else lvl)

    # 2. ПРОВЕРКА НА АВАРИЮ СПЛИТА (Только по injuries, doms не блокирует тренировку)
    if not req.fallback_choice:
        planned_targets = kb_service.get_split_targets(user.goal, original_split)
        
        # Получаем тестовый каталог, чтобы понять, убила ли травма тренировку
        test_catalogs = kb_service.get_filtered_catalogs(
            user.goal, lvl, user.equipment, original_split, bans, injuries, is_light_fullbody=False
        )
        
        # Если в основном блоке не осталось упражнений (или меньше 2) -> Требуем выбор
        if len(test_catalogs["main"]) < 2 and user.goal.lower() == "масса":
            return {
                "status": "choice_required",
                "message": f"Острая травма ({', '.join(injuries)}) блокирует тренировку на целевые мышцы ({', '.join(planned_targets)}). Что делаем?",
                "options": [
                    {"id": "next_split", "label": "Перейти к следующему дню сплита"},
                    {"id": "light_fullbody", "label": "Сделать легкую тренировку на всё тело"}
                ]
            }

    # 3. Применяем выбор
    active_split = original_split
    is_light = False
    
    if req.fallback_choice == "next_split": active_split = (original_split % 3) + 1
    elif req.fallback_choice == "light_fullbody": is_light = True

    # 4. Получаем финальный отфильтрованный каталог из базы
    full_catalogs = kb_service.get_filtered_catalogs(
        user.goal, lvl, user.equipment, active_split, bans, injuries, is_light_fullbody=is_light
    )
    
    # 5. ГЕНЕРАЦИЯ: Отправляем сжатый каталог в LLM для сборки по минутам
    compact_catalog = kb_service.prepare_catalog_for_llm(full_catalogs)
    
    llm_plan_ids = await llm_service.generate_workout_logic(
        goal=user.goal, 
        target_time_minutes=req.target_time_minutes, 
        catalog_for_llm=compact_catalog, 
        doms=doms  # ИИ учтет крепатуру при выборе ID
    )
    
    # 6. Восстанавливаем полные объекты (с анимациями и таймерами) из выбранных ID
    final_plan_objects = kb_service.get_full_exercises_by_ids(full_catalogs, llm_plan_ids)
    
    note = await llm_service.generate_coach_note(user.goal, injuries, doms, mood, req.fallback_choice)
    
    # Итоговый JSON
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