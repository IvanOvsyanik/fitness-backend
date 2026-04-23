import json
import os

GOAL_FILES = {
    "масса": "mass.json",
    "жиросжигание": "fat_burn.json",
    "растяжка": "stretch.json"
}

WARMUP = [
    {"name": "Суставная разминка (вращения кистями, локтями, плечами)", "time": "3 мин"}, 
    {"name": "Динамическая растяжка корпуса", "time": "2 мин"}
]

def get_all_contraindications():
    contraindications = set()
    for goal, file_name in GOAL_FILES.items():
        path = os.path.join("app", "data", file_name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for ex in data:
                    for c in ex.get("contraindications", []):
                        contraindications.add(c.lower())
    return list(contraindications)

def get_split_targets(goal: str, split_day: int):
    """Возвращает список основных мышц, которые должны были тренироваться в этот день"""
    file_path = os.path.join("app", "data", GOAL_FILES.get(goal.lower(), "mass.json"))
    targets = set()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            all_ex = json.load(f)
            for ex in all_ex:
                if ex.get("split_day") == split_day and ex.get("muscle_group"):
                    for m in ex["muscle_group"].split(","):
                        targets.add(m.strip().lower())
    except Exception:
        pass
    return list(targets)

def get_filtered_workout(goal: str, level: str, equipment: str, split_day: int, bans: list, temp_injuries: list, past_plan: str = None, is_light_fullbody: bool = False):
    file_path = os.path.join("app", "data", GOAL_FILES.get(goal.lower(), "mass.json"))
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            all_ex = json.load(f)
    except FileNotFoundError:
        return [], WARMUP, []

    # Если выбрана легкая тренировка, принудительно ставим уровень "новичок"
    user_lvl = 1 if is_light_fullbody else (3 if "профи" in level.lower() else (2 if "средн" in level.lower() else 1))
    user_eq = 3 if "спортзал" in equipment.lower() else (2 if "гантел" in equipment.lower() or "турник" in equipment.lower() else 1)

    allowed = []
    muscles_today = set()

    for ex in all_ex:
        name_lc = ex['name'].lower()
        contraindications = [c.lower() for c in ex.get('contraindications', [])]
        
        # 1. Постоянные баны
        if any(b.lower() in name_lc for b in bans if b): 
            continue
            
        # 2. ИДЕАЛЬНАЯ ЛОГИКА ТРАВМ: Смотрим ТОЛЬКО в contraindications
        stop_exercise = False
        for injury in temp_injuries:
            if any(injury.lower() in c for c in contraindications):
                stop_exercise = True
                break
        if stop_exercise: continue

        # 3. Фильтрация по уровню и инвентарю
        ex_lvl = 1 if "новичок" in ex.get("min_level", "") else (2 if "средний" in ex.get("min_level", "") else 3)
        if ex_lvl > user_lvl: continue

        ex_eq = 3 if "спортзал" in ex.get("equipment", "").lower() else (2 if "гантел" in ex.get("equipment", "").lower() or "турник" in ex.get("equipment", "").lower() else 1)
        if user_eq == 3 and ex_eq == 1 and ex.get("split_day") != 0: continue
        elif user_eq == 2 and ex_eq == 3: continue
        elif user_eq == 1 and ex_eq > 1: continue
            
        # 4. Сплит (Если это не легкая фуллбоди тренировка)
        if not is_light_fullbody and goal.lower() == "масса":
            if ex.get("split_day") not in [0, split_day]: 
                continue
        
        # Если легкая фуллбоди, стараемся брать базовые или нулевые упражнения
        if is_light_fullbody and ex_lvl > 1:
            continue

        if past_plan and name_lc in past_plan.lower(): continue

        allowed.append({"exercise": ex['name'], "sets": 3, "reps": "10-12"})
        
        if ex.get("muscle_group"):
            for m in ex["muscle_group"].split(","):
                muscles_today.add(m.strip())

    return allowed, WARMUP, list(muscles_today)

def get_all_exercises_catalog(goal: str):
    catalog = []
    file_name = GOAL_FILES.get(goal.lower(), "mass.json")
    path = os.path.join("app", "data", file_name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for ex in data:
                catalog.append(f"Название: \"{ex['name']}\" (Мышцы: {ex.get('muscle_group', 'Разное')})")
    return "\n".join(catalog)