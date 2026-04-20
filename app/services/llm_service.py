from openai import AsyncOpenAI
import json
from app.core.config import settings

client = AsyncOpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

async def extract_entities(text: str, mode: str = "pre_workout", existing_bans: str = "", catalog: str = ""):
    if not text or len(text) < 3:
        return {"banned": [], "unbanned": [], "temp_injuries": []}

    if mode == "pre_workout":
        system_prompt = """Прочитай жалобу пользователя перед тренировкой.
        Извлеки боли/травмы (например: колено, спина, плечо). 
        Верни СТРОГИЙ JSON: {"temp_injuries": ["спина"]}"""
    else:
        system_prompt = f"""Ты — строгий алгоритм фильтрации баз данных. Анализируй отзыв.
        ТЕКУЩИЙ ЧЕРНЫЙ СПИСОК: {existing_bans}
        
        ДОСТУПНЫЕ УПРАЖНЕНИЯ:
        {catalog}
        
        ЖЕСТКИЕ ПРАВИЛА:
        1. В списки "banned" и "unbanned" копируй слова ИСКЛЮЧИТЕЛЬНО из поля Название, НО БЕЗ КАВЫЧЕК. Никаких скобок и мышц!
        2. ЗАБЛОКИРОВАТЬ: Если юзер просит убрать/заблокировать упражнение или группу мышц (например "грудь"), найди их в каталоге и помести в "banned".
        3. РАЗБЛОКИРОВАТЬ: Если юзер просит вернуть/разблокировать упражнение или группу мышц, найди их в каталоге и помести в "unbanned".
        4. Оставляй "unbanned" пустым: [], если юзер ПРЯМО не просит что-то вернуть.
        
        Ответ строго JSON: {{"banned": ["Точное название без кавычек"], "unbanned": []}}"""

    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {"banned": [], "unbanned": [], "temp_injuries": []}

async def generate_coach_note(goal: str, prompt_text: str, temp_injuries: list):
    system_prompt = f"""Ты — заботливый фитнес-тренер. Напиши клиенту 1-2 предложения.
    Цель: {goal}. Ситуация: {prompt_text}. Травмы: {', '.join(temp_injuries) if temp_injuries else 'Нет'}.
    Если упражнений мало — предложи сменить день сплита или разблокировать базу."""
    
    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": system_prompt}],
            temperature=0.6
        )
        return response.choices[0].message.content
    except:
        return "Тренировка адаптирована и готова. Удачи!"