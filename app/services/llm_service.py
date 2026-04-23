from openai import AsyncOpenAI
import json
from app.core.config import settings

client = AsyncOpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

async def analyze_onboarding(weight: int, height: int, age: int, experience: str, equipment: str):
    system_prompt = f"""Ты — ИИ-врач. Проанализируй данные: Вес: {weight}кг, Рост: {height}см, Возраст: {age}, Опыт: {experience}, Инвентарь: {equipment}.
    ПРАВИЛА:
    1. ИМТ > 30 — СТРОГО "новичок".
    2. Опыт давно (более 1 года) или не силовой — СТРОГО "новичок".
    Верни СТРОГИЙ JSON: {{"initial_rank": "новичок", "reason": "вывод"}}"""

    try:
        response = await client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "system", "content": system_prompt}], response_format={"type": "json_object"}, temperature=0.1)
        return json.loads(response.choices[0].message.content)
    except:
        return {"initial_rank": "новичок", "reason": "Ошибка анализа."}

async def extract_entities(text: str, mode: str = "pre_workout", existing_bans: str = "", catalog: str = "", valid_injuries: list = None):
    if not text or len(text) < 3: return {"banned": [], "unbanned": [], "temp_injuries": [], "level_change": "none", "mood_boost": "none"}

    if mode == "pre_workout":
        tags_str = ", ".join(valid_injuries) if valid_injuries else "колено, голеностоп, плечо, кисть, поясница, локоть, спина, шея, ноги, грудь"
        system_prompt = f"""Анализ перед тренировкой. 
        ЗАДАЧА 1: Переведи жалобу в СТРОГИЕ ТЕГИ: [{tags_str}]. Выбирай ТОЛЬКО слова из списка!
        ЗАДАЧА 2: Настроение (mood_boost): "up", "down", "none".
        Верни JSON: {{"temp_injuries": ["тег1"], "mood_boost": "none"}}"""
    else:
        system_prompt = f"""Анализ отзыва. Бан-лист: {existing_bans}. Справочник: {catalog}. Верни JSON: {{"banned": [], "unbanned": [], "level_change": "none"}}"""

    try:
        response = await client.chat.completions.create(model="llama-3.1-8b-instant", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}], response_format={"type": "json_object"}, temperature=0.1)
        return json.loads(response.choices[0].message.content)
    except:
        return {"banned": [], "unbanned": [], "temp_injuries": [], "level_change": "none", "mood_boost": "none"}

async def generate_coach_note(goal: str, temp_injuries: list, mood_boost: str, split_day: int, muscles: list, fallback_choice: str):
    # Строго русские, простые фразы
    action_context = ""
    if fallback_choice == "next_split":
        action_context = f"Сдвинули план. Сегодня качаем: {', '.join(muscles)}."
    elif fallback_choice == "light_fullbody":
        action_context = "Сгенерирована легкая восстановительная тренировка в обход травмы."
    else:
        action_context = f"Сегодня качаем: {', '.join(muscles)}." if goal.lower() == "масса" and muscles else "План готов."

    mood_msg = {"up": "Вижу отличный настрой!", "down": "Сделаем тренировку в легком темпе.", "none": ""}.get(mood_boost, "")
    injury_msg = f"Травма ({', '.join(temp_injuries)}) учтена, опасные упражнения удалены." if temp_injuries else ""

    system_prompt = f"""Ты — системный робот-ассистент фитнес-приложения. Составь приветствие из 2-3 предложений.
    
    ИСПОЛЬЗУЙ ЭТИ ФАКТЫ:
    1. {action_context}
    2. {injury_msg}
    3. {mood_msg}

    ЖЕСТКИЕ ПРАВИЛА:
    1. НЕ придумывай ничего от себя.
    2. НЕ используй метафоры, идиомы и странные слова (забудь про "заряд", "кора", "жми").
    3. НЕ задавай вопросы.
    4. Текст должен быть сухим, точным и вежливым."""
    
    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": system_prompt}],
            temperature=0.1 # Минимальная температура для отключения фантазии
        )
        return response.choices[0].message.content
    except:
        return f"{action_context} Удачи."