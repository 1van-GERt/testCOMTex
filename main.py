from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, Date, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import os

# Настройка БД
DATABASE_URL = "sqlite:///./tech_tracker.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class TechItem(Base):
    __tablename__ = "tech"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    barcode = Column(String, unique=True, index=True)
    category = Column(String)
    status = Column(String)
    location = Column(String)
    notes = Column(Text, nullable=True)
    created_at = Column(Date, default=datetime.now().date)

# Создаем таблицы при старте
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Tech Tracker Pro")
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    db = SessionLocal()
    items = db.query(TechItem).order_by(TechItem.id.desc()).all() # Сортируем: новые сверху
    db.close()
    return templates.TemplateResponse("index.html", {"request": request, "items": items})

@app.post("/add/")
async def add_item(
    name: str = Form(...),
    barcode: str = Form(...),
    category: str = Form(...),
    status: str = Form(...),
    location: str = Form(...),
    notes: str = Form("") # Делаем заметки необязательными с дефолтным значением
):
    db = SessionLocal()
    try:
        # Проверка дубликатов
        existing = db.query(TechItem).filter(TechItem.barcode == barcode).first()
        if existing:
            return JSONResponse(status_code=400, content={"error": f"Устройство с кодом {barcode} уже существует!"})
        
        new_item = TechItem(
            name=name, 
            barcode=barcode, 
            category=category, 
            status=status, 
            location=location, 
            notes=notes
        )
        db.add(new_item)
        db.commit()
        db.refresh(new_item) # Обновляем объект, чтобы получить ID и даты
        return {"message": "success", "id": new_item.id}
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)