import json
import os
import random

GOAL_FILES = {"масса": "mass.json", "жиросжигание": "fat_burn.json", "растяжка": "stretch.json"}
WARMUP = [{"name": "Суставная разминка", "time": "3 мин"}, {"name": "Динамическая растяжка", "time": "2 мин"}]

def get_filtered_workout(goal: str, level: str, equipment: str, split_day: int, bans: list, temp_injuries: list, past_plan: str = None):
    file_path = os.path.join("app", "data", GOAL_FILES.get(goal.lower(), "mass.json"))
    with open(file_path, "r", encoding="utf-8") as f:
        all_ex = json.load(f)

    user_lvl = 3 if "профи" in level.lower() else (2 if "средн" in level.lower() else 1)
    # 1 - свой вес, 2 - гантели/турник, 3 - спортзал
    user_eq = 3 if "спортзал" in equipment.lower() else (2 if "гантел" in equipment.lower() or "турник" in equipment.lower() else 1)

    allowed = []
    for ex in all_ex:
        name_lc = ex['name'].lower()
        muscles_lc = ex.get('muscle_group', '').lower()
        
        # Фильтр 1: Постоянные баны
        if any(b.lower() in name_lc for b in bans): continue
        # Фильтр 2: Сегодняшние травмы
        if any(i.lower() in muscles_lc for i in temp_injuries): continue
        # Фильтр 3: Сложность
        ex_lvl = 1 if "новичок" in ex.get("min_level", "") else (2 if "средний" in ex.get("min_level", "") else 3)
        if ex_lvl > user_lvl: continue
        # Фильтр 4: Инвентарь (строгое соответствие, кроме пресса split_day=0)
        ex_eq = 3 if "спортзал" in ex.get("equipment", "").lower() else (2 if "гантел" in ex.get("equipment", "").lower() or "турник" in ex.get("equipment", "").lower() else 1)
        if ex.get("split_day") != 0 and ex_eq != user_eq: continue
        
        # Фильтр 5: Сплит или Анти-повтор
        if goal.lower() == "масса":
            if ex.get("split_day") not in [0, split_day]: continue
        elif past_plan and name_lc in past_plan.lower():
            continue

        allowed.append({"exercise": ex['name'], "sets": 4 if user_lvl > 1 else 3, "reps": "10-12"})

    # Случайный выбор из разрешенных
    main = random.sample(allowed, min(len(allowed), 5))
    return {"warmup": WARMUP, "main": main}