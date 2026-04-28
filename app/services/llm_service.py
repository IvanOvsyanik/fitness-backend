from openai import AsyncOpenAI
import json
from app.core.config import settings

client = AsyncOpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)
# Самая мощная модель, умная как GPT-4
MODEL_NAME = "llama-3.3-70b-versatile"

async def analyze_onboarding(weight: int, height: int, age: int, experience: str, equipment: str):
    system_prompt = f"""Ты — ИИ-врач. Проанализируй: Вес: {weight}кг, Рост: {height}см, Возраст: {age}, Опыт: {experience}, Инвентарь: {equipment}.
    1. ИМТ > 30 — СТРОГО "новичок". 2. Опыт давно — СТРОГО "новичок".
    Верни СТРОГИЙ JSON: {{"initial_rank": "новичок", "reason": "вывод"}}"""

    try:
        response = await client.chat.completions.create(model=MODEL_NAME, messages=[{"role": "system", "content": system_prompt}], response_format={"type": "json_object"}, temperature=0.1)
        return json.loads(response.choices[0].message.content)
    except:
        return {"initial_rank": "новичок", "reason": "Ошибка анализа."}

async def extract_entities(text: str, mode: str = "pre_workout", existing_bans: str = "", catalog: str = "", valid_injuries: list = None):
    if not text or len(text) < 3: 
        return {"banned": [], "unbanned": [], "injuries": [], "doms": [], "level_change": "none", "mood_boost": "none"}

    if mode == "pre_workout":
        tags_str = ", ".join(valid_injuries) if valid_injuries else "шея, плечо, локоть, кисть, поясница, таз, колено, голеностоп"
        
        system_prompt = f"""Ты — спортивный диагност. Проанализируй жалобу.
        ЗАДАЧА 1: ТРАВМЫ СУСТАВОВ (injuries). Острые боли, хрусты суставов. Используй ТОЛЬКО теги: [{tags_str}]. Если болит нога -> ["колено", "голеностоп"].
        ЗАДАЧА 2: КРЕПАТУРА (doms). Усталость или "забитость" мышц после прошлых тренировок (например: "грудь", "бицепс", "ягодицы").
        ЗАДАЧА 3: НАСТРОЕНИЕ (mood_boost): "up", "down", "none".
        
        Верни СТРОГИЙ JSON: {{"injuries": ["тег"], "doms": ["мышца"], "mood_boost": "none"}}"""
    else:
        system_prompt = f"""Анализ отзыва. Бан-лист: {existing_bans}. Справочник: {catalog}. Верни JSON: {{"banned": [], "unbanned": [], "level_change": "none"}}"""

    try:
        response = await client.chat.completions.create(model=MODEL_NAME, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}], response_format={"type": "json_object"}, temperature=0.1)
        return json.loads(response.choices[0].message.content)
    except:
        return {"banned": [], "unbanned": [], "injuries": [], "doms": [], "level_change": "none", "mood_boost": "none"}

async def generate_workout_logic(goal: str, target_time_minutes: int, catalog_for_llm: dict, doms: list):
    """
    Нейросеть выступает в роли планировщика. Она получает список разрешенных ID и собирает пазл на X минут.
    """
    system_prompt = f"""Ты — элитный фитнес-алгоритм (уровня Nike Training Club).
    ЗАДАЧА: Собрать тренировку, которая длится ровно (или максимально близко к) {target_time_minutes} минут.
    
    ВХОДНЫЕ ДАННЫЕ (Каталог безопасных упражнений с таймингами):
    {json.dumps(catalog_for_llm, ensure_ascii=False)}

    СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ:
    Крепатура (Усталость мышц): {doms}. Постарайся выбирать упражнения, которые НЕ нагружают эти мышцы, или бери их по минимуму.

    МАТЕМАТИКА ВРЕМЕНИ:
    Формула времени одного упражнения: (work_sec + rest_sec) * sets.
    Например: (45 + 90) * 4 = 540 сек = 9 минут.
    
    ПРАВИЛА:
    1. Выбери 1-2 ID из warmup.
    2. Выбери несколько ID из main, чтобы в сумме с разминкой и заминкой получилось ~{target_time_minutes} минут.
    3. Выбери 1-2 ID из cooldown.
    4. Верни СТРОГИЙ JSON формат: {{"warmup_ids": ["w1"], "main_ids": ["m5", "m7"], "cooldown_ids": ["c1"], "estimated_total_minutes": 40}}"""

    try:
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": system_prompt}],
            response_format={"type": "json_object"},
            temperature=0.3 # Немного креативности для разнообразия выбора упражнений
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"LLM Logic Error: {e}")
        # Заглушка на случай сбоя API, чтобы приложение не упало
        return {"warmup_ids": [], "main_ids": [], "cooldown_ids": [], "estimated_total_minutes": 0}

async def generate_coach_note(goal: str, injuries: list, doms: list, mood_boost: str, is_fallback: str):
    action_context = "Сгенерирована легкая восстановительная тренировка." if is_fallback == "light_fullbody" else ("Сдвинули день сплита." if is_fallback == "next_split" else "План готов.")
    mood_msg = {"up": "Вижу отличный настрой!", "down": "Сделаем тренировку в легком темпе.", "none": ""}.get(mood_boost, "")
    injury_msg = f"Острые травмы ({', '.join(injuries)}) учтены, опасные упражнения заблокированы." if injuries else ""
    doms_msg = f"Крепатура ({', '.join(doms)}) учтена, нагрузка на эти зоны снижена." if doms else ""

    system_prompt = f"""Ты — системный робот-ассистент фитнес-приложения. Составь приветствие (2-3 предложения).
    ФАКТЫ: 1. {action_context} 2. {injury_msg} 3. {doms_msg} 4. {mood_msg}
    ПРАВИЛА: 1. Ничего от себя. 2. Сухо, вежливо, на "ты". 3. Без вопросов и метафор."""
    
    try:
        response = await client.chat.completions.create(model=MODEL_NAME, messages=[{"role": "system", "content": system_prompt}], temperature=0.1)
        return response.choices[0].message.content
    except:
        return f"{action_context} Удачи на тренировке."