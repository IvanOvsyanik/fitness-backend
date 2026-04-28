import json
import os

GOAL_FILES = {
    "масса": "mass.json",
    "жиросжигание": "fat_burn.json",
    "растяжка": "stretch.json"
}

def _load_json(filename: str):
    path = os.path.join("app", "data", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def get_all_contraindications():
    """Собирает уникальные теги травм из всех 5 файлов."""
    contraindications = set()
    files_to_check = ["warmup.json", "cooldown.json"] + list(GOAL_FILES.values())
    for file_name in files_to_check:
        data = _load_json(file_name)
        for ex in data:
            for c in ex.get("contraindications", []):
                contraindications.add(c.lower())
    return list(contraindications)

def get_split_targets(goal: str, split_day: int):
    """Определяет, какие мышцы планировалось качать сегодня (для проверки аварии)."""
    file_name = GOAL_FILES.get(goal.lower(), "mass.json")
    data = _load_json(file_name)
    targets = set()
    for ex in data:
        if ex.get("split_day") == split_day and ex.get("muscle_group"):
            for m in ex["muscle_group"]:
                targets.add(m.strip().lower())
    return list(targets)

def get_filtered_catalogs(goal: str, level: str, equipment: str, split_day: int, bans: list, injuries: list, is_light_fullbody: bool = False):
    """Фильтрует 3 файла (разминка, основа, заминка) и возвращает безопасные упражнения."""
    warmup_data = _load_json("warmup.json")
    main_data = _load_json(GOAL_FILES.get(goal.lower(), "mass.json"))
    cooldown_data = _load_json("cooldown.json")

    user_lvl = 1 if is_light_fullbody else (3 if "профи" in level.lower() else (2 if "средн" in level.lower() else 1))
    user_eq = 3 if "спортзал" in equipment.lower() else (2 if "гантел" in equipment.lower() or "турник" in equipment.lower() else 1)

    def _filter_list(ex_list, is_main_block=False):
        allowed = []
        for ex in ex_list:
            name_lc = ex['name'].lower()
            contraindications = [c.lower() for c in ex.get('contraindications', [])]
            
            # 1. Постоянные баны из БД
            if any(b.lower() in name_lc for b in bans if b): continue
                
            # 2. Острые травмы (injuries) - Жесткий БАН
            if any(any(inj.lower() in c for c in contraindications) for inj in injuries): 
                continue

            # 3. Уровень
            ex_lvl_str = ex.get("min_level", "новичок")
            ex_lvl = 1 if "новичок" in ex_lvl_str else (2 if "средний" in ex_lvl_str else 3)
            if ex_lvl > user_lvl: continue

            # 4. Инвентарь
            ex_eq_str = ex.get("equipment", "свой вес").lower()
            ex_eq = 3 if "спортзал" in ex_eq_str else (2 if "гантел" in ex_eq_str or "турник" in ex_eq_str else 1)
            if user_eq == 3 and ex_eq == 1 and ex.get("split_day") != 0: continue
            elif user_eq == 2 and ex_eq == 3: continue
            elif user_eq == 1 and ex_eq > 1: continue
                
            # 5. Сплит (только для основного блока массы)
            if is_main_block and not is_light_fullbody and goal.lower() == "масса":
                if ex.get("split_day") not in [0, split_day]: continue
            
            if is_main_block and is_light_fullbody and ex_lvl > 1:
                continue

            allowed.append(ex)
        return allowed

    return {
        "warmup": _filter_list(warmup_data),
        "main": _filter_list(main_data, is_main_block=True),
        "cooldown": _filter_list(cooldown_data)
    }

def prepare_catalog_for_llm(catalogs: dict):
    """Сжимает объекты, чтобы не тратить токены LLM, оставляя только математику времени."""
    def _strip(ex_list):
        return [
            {
                "id": e["id"], 
                "name": e["name"], 
                "muscles": e.get("muscle_group", []),
                "sets": e.get("sets", 1), 
                "work_sec": e.get("work_sec_per_set", 45), 
                "rest_sec": e.get("rest_sec_between_sets", 30)
            } for e in ex_list
        ]
    return {
        "warmup": _strip(catalogs["warmup"]),
        "main": _strip(catalogs["main"]),
        "cooldown": _strip(catalogs["cooldown"])
    }

def get_full_exercises_by_ids(catalogs: dict, id_lists: dict):
    """Превращает ID, которые выбрала нейросеть, обратно в полные JSON-объекты для фронтенда."""
    final_plan = {"warmup": [], "main": [], "cooldown": []}
    
    for phase in ["warmup", "main", "cooldown"]:
        for ex_id in id_lists.get(f"{phase}_ids", []):
            # Ищем полное упражнение в отфильтрованном каталоге
            found_ex = next((item for item in catalogs[phase] if item["id"] == ex_id), None)
            if found_ex:
                final_plan[phase].append(found_ex)
                
    return final_plan

def get_all_exercises_catalog(goal: str):
    data = _load_json(GOAL_FILES.get(goal.lower(), "mass.json"))
    return "\n".join([f"Название: \"{ex['name']}\"" for ex in data])