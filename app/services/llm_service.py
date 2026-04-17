from openai import AsyncOpenAI
import json
from app.core.config import settings

client = AsyncOpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

# 1. Анализирует текст (и перед, и после тренировки)
async def extract_entities(text: str, mode: str = "pre_workout"):
    if not text or len(text) < 3:
        return {"banned": [], "unbanned": [], "temp_injuries": []}

    if mode == "pre_workout":
        system_prompt = """Проанализируй жалобы пользователя перед тренировкой. 
        Извлеки части тела или суставы, которые болят сегодня.
        Верни JSON: {"temp_injuries": ["спина", "колено"]}"""
    else:
        system_prompt = """Проанализируй отзыв после тренировки. 
        Извлеки названия упражнений, которые нужно навсегда убрать (banned) 
        или которые нужно вернуть из черного списка (unbanned).
        Верни JSON: {"banned": ["жим лежа"], "unbanned": ["планка"]}"""

    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content)
    except:
        return {"banned": [], "unbanned": [], "temp_injuries": []}

# 2. Пишет приветствие
async def generate_coach_note(goal: str, pre_text: str, temp_injuries: list):
    system_prompt = f"""Ты — заботливый тренер. Напиши ОДНО приветственное предложение.
    Сегодня цель: {goal}. У пользователя болит: {', '.join(temp_injuries) if temp_injuries else 'ничего'}.
    Если что-то болит, скажи, что ты адаптировал план. Если нет — просто пожелай удачи."""
    
    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": system_prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except:
        return "План готов, приступай к тренировке!"