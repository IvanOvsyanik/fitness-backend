import os
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()

class Settings:
    PROJECT_NAME: str = "Fitness Planner AI"
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY")

# Создаем объект настроек, который будем использовать в других файлах
settings = Settings()