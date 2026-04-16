from openai import AsyncOpenAI
from app.core.config import settings

# Подключаем стандартную библиотеку, но направляем её на сверхбыстрые серверы Groq
client = AsyncOpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

async def generate_workout(goal: str, level: str, equipment: str, previous_feedback: str = None):
    system_prompt = """Ты — экспертный фитнес-тренер. 
    Твоя задача — составлять тренировочные планы. 
    Выдавай ответ строго в виде списка упражнений с указанием подходов и повторений. 
    Без лишней воды и длинных вступлений."""

    if previous_feedback:
        user_prompt = f"""Клиент оставил отзыв о прошлой тренировке: '{previous_feedback}'. 
        Цель клиента: {goal}. Инвентарь: {equipment}.
        Адаптируй прошлый план: усложни или упрости его на основе отзыва."""
    else:
        user_prompt = f"""Составь план первой тренировки. 
        Цель: {goal}. 
        Уровень подготовки: {level}. 
        Доступный инвентарь: {equipment}."""

    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant", # Используем мгновенную Llama 3.1
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Ошибка при генерации тренировки: {str(e)}"