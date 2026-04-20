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

def get_filtered_workout(goal: str, level: str, equipment: str, split_day: int, bans: list, temp_injuries: list, past_plan: str = None):
    file_path = os.path.join("app", "data", GOAL_FILES.get(goal.lower(), "mass.json"))
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            all_ex = json.load(f)
    except FileNotFoundError:
        return [], WARMUP, "no_file"

    user_lvl = 3 if "профи" in level.lower() else (2 if "средн" in level.lower() else 1)
    user_eq = 3 if "спортзал" in equipment.lower() else (2 if "гантел" in equipment.lower() or "турник" in equipment.lower() else 1)

    allowed = []
    reason_empty = "no_exercises"

    for ex in all_ex:
        name_lc = ex['name'].lower()
        muscles_lc = ex.get('muscle_group', '').lower()
        
        # 1. Постоянные баны (теперь работает идеально, потому что ИИ отдает только имя)
        if any(b.lower() in name_lc for b in bans if b): 
            continue
            
        # 2. Сегодняшние травмы
        if any(i.lower() in muscles_lc for i in temp_injuries if i):
            reason_empty = "injury_conflict"
            continue

        # 3. Сложность
        ex_lvl = 1 if "новичок" in ex.get("min_level", "") else (2 if "средний" in ex.get("min_level", "") else 3)
        if ex_lvl > user_lvl: 
            continue

        # 4. УМНЫЙ ИНВЕНТАРЬ
        ex_eq = 3 if "спортзал" in ex.get("equipment", "").lower() else (2 if "гантел" in ex.get("equipment", "").lower() or "турник" in ex.get("equipment", "").lower() else 1)
        
        if user_eq == 3:
            if ex_eq == 1 and ex.get("split_day") != 0: continue
        elif user_eq == 2:
            if ex_eq == 3: continue
        elif user_eq == 1:
            if ex_eq > 1: continue
            
        # 5. Сплит или Анти-повтор
        if goal.lower() == "масса":
            if ex.get("split_day") not in [0, split_day]: 
                continue
        elif past_plan and name_lc in past_plan.lower():
            continue

        allowed.append({"exercise": ex['name'], "sets": 4 if user_lvl > 1 else 3, "reps": "10-12"})

    return allowed, WARMUP, reason_empty

def get_all_exercises_catalog(goal: str):
    catalog = []
    file_name = GOAL_FILES.get(goal.lower(), "mass.json")
    path = os.path.join("app", "data", file_name)
    
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for ex in data:
                # ОЧИЩЕННЫЙ ФОРМАТ ДЛЯ ИИ
                catalog.append(f"Название: \"{ex['name']}\" (Мышцы: {ex.get('muscle_group', 'Разное')})")
    return "\n".join(catalog)