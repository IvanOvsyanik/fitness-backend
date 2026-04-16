from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Указываем путь к локальному файлу базы данных SQLite
SQLALCHEMY_DATABASE_URL = "sqlite:///./fitness_app.db"

# Создаем "движок", который будет общаться с базой
# check_same_thread: False нужен только для SQLite в FastAPI
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Создаем фабрику сессий (через сессию мы будем записывать и читать данные)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс, от которого будут наследоваться все наши таблицы
Base = declarative_base()

# Специальная функция для FastAPI, чтобы безопасно открывать и закрывать БД при каждом запросе
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()