from sqlalchemy.orm import Session
from app.db import models

# Словарь всех доступных достижений в приложении
ACHIEVEMENTS_DB = {
    "first_workout": {"title": "Первый шаг 🥉", "desc": "Завершена первая тренировка."},
    "marathon_50": {"title": "Марафонец 🥈", "desc": "Суммарно 50 минут тренировок."},
    "marathon_100": {"title": "Железный человек 🥇", "desc": "Суммарно 100 минут тренировок."},
    "perfect_week": {"title": "Дисциплина 🏅", "desc": "Завершено 3 тренировки."}
}

def get_user_stats(db: Session, device_id: str):
    """Собирает красивую статистику для дашборда профиля."""
    workouts = db.query(models.Workout).filter(models.Workout.device_id == device_id).all()
    
    total_workouts = len(workouts)
    total_minutes = sum(w.target_time_minutes for w in workouts if w.target_time_minutes)
    
    achievements = db.query(models.UserAchievement).filter(models.UserAchievement.device_id == device_id).all()
    achievements_list = [{"title": a.title, "desc": a.description, "date": a.unlocked_at} for a in achievements]

    return {
        "total_workouts": total_workouts,
        "total_minutes": total_minutes,
        "achievements_count": len(achievements_list),
        "achievements": achievements_list
    }

def check_and_unlock_achievements(db: Session, device_id: str):
    """Проверяет условия и выдает новые ачивки. Вызывается после каждого отзыва."""
    workouts = db.query(models.Workout).filter(models.Workout.device_id == device_id).all()
    total_workouts = len(workouts)
    total_minutes = sum(w.target_time_minutes for w in workouts if w.target_time_minutes)
    
    # Получаем уже разблокированные ачивки, чтобы не выдать их дважды
    unlocked = db.query(models.UserAchievement.achievement_id).filter(models.UserAchievement.device_id == device_id).all()
    unlocked_ids = {u[0] for u in unlocked}
    
    newly_unlocked = []

    def _grant(ach_id: str):
        if ach_id not in unlocked_ids:
            ach_data = ACHIEVEMENTS_DB[ach_id]
            new_ach = models.UserAchievement(
                device_id=device_id, 
                achievement_id=ach_id, 
                title=ach_data["title"], 
                description=ach_data["desc"]
            )
            db.add(new_ach)
            newly_unlocked.append(ach_data["title"])

    # УСЛОВИЯ ДЛЯ АЧИВОК:
    if total_workouts >= 1: _grant("first_workout")
    if total_workouts >= 3: _grant("perfect_week")
    
    if total_minutes >= 50: _grant("marathon_50")
    if total_minutes >= 100: _grant("marathon_100")

    if newly_unlocked:
        db.commit()
        
    return newly_unlocked