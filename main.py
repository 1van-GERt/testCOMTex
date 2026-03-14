from fastapi import FastAPI, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, Date, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import os

# --- Настройка Базы Данных ---
DATABASE_URL = "sqlite:///./tech_tracker.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class TechItem(Base):
    __tablename__ = "tech"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    barcode = Column(String, unique=True, index=True) # Поле для штрих-кода
    category = Column(String)
    status = Column(String)
    location = Column(String)
    notes = Column(Text, nullable=True)
    created_at = Column(Date, default=datetime.now().date)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Tech Tracker Pro")
templates = Jinja2Templates(directory="templates")

# Зависимость для получения сессии БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Маршруты ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    db = SessionLocal()
    items = db.query(TechItem).all()
    db.close()
    return templates.TemplateResponse("index.html", {"request": request, "items": items})

@app.post("/add/")
async def add_item(
    name: str = Form(...),
    barcode: str = Form(...),
    category: str = Form(...),
    status: str = Form(...),
    location: str = Form(...),
    notes: str = Form(...)
):
    db = SessionLocal()
    # Проверка на дубликат штрих-кода
    existing = db.query(TechItem).filter(TechItem.barcode == barcode).first()
    if existing:
        db.close()
        return {"error": "Такой штрих-код уже существует!"}
    
    new_item = TechItem(
        name=name, barcode=barcode, category=category, 
        status=status, location=location, notes=notes
    )
    db.add(new_item)
    db.commit()
    db.close()
    return {"message": "Успешно добавлено!"}

if __name__ == "__main__":
    import uvicorn
    # Запуск на всех интерфейсах (важно для хостинга)
    uvicorn.run(app, host="0.0.0.0", port=8000)