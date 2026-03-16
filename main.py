from fastapi import FastAPI, Request, Form, HTTPException, Depends, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import os, shutil, uuid, traceback
import pandas as pd
from io import BytesIO

# --- НАСТРОЙКИ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
if not os.path.exists(UPLOAD_DIR): os.makedirs(UPLOAD_DIR)

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "pages"))

DATABASE_URL = "sqlite:///./tech_tracker.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- МОДЕЛЬ БД ---
class TechItem(Base):
    __tablename__ = "tech"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    barcode = Column(String, unique=True, index=True, nullable=False)
    inv_number = Column(String, nullable=True)
    serial_number = Column(String, nullable=True)
    photo_filename = Column(String, nullable=True)
    category = Column(String, nullable=False)
    status = Column(String, nullable=False)
    location = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    
    issued_by = Column(String, nullable=True)
    issued_to = Column(String, nullable=True)
    issue_time = Column(DateTime, nullable=True)
    return_deadline = Column(DateTime, nullable=True)
    work_location = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.now)

def format_date(dt):
    if not dt: return "-"
    return dt.strftime("%d-%m-%Y %H:%M")

def format_date_only(dt):
    if not dt: return "-"
    return dt.strftime("%d-%m-%Y")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="COMTex")

# --- СТАТИКА ---
app.mount("/static/tech", StaticFiles(directory=os.path.join(BASE_DIR, "pages", "tech")), name="static_tech")
app.mount("/static/details", StaticFiles(directory=os.path.join(BASE_DIR, "pages", "details")), name="static_details")
app.mount("/static/calendar", StaticFiles(directory=os.path.join(BASE_DIR, "pages", "calendar")), name="static_calendar")
app.mount("/static/issue", StaticFiles(directory=os.path.join(BASE_DIR, "pages", "issue")), name="static_issue")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- МАРШРУТЫ ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    db = SessionLocal()
    try:
        # 1. Статистика
        count_work = db.query(TechItem).filter(TechItem.status == "В работе").count()
        count_repair = db.query(TechItem).filter(TechItem.status == "Ремонт").count()
        count_total = db.query(TechItem).count()
        
        # 2. Получаем ВСЕ активные выдачи с датами, отсортированные по дате возврата
        # Сначала идут самые старые даты (просроченные), потом будущие
        all_returns = db.query(TechItem)\
            .filter(TechItem.status == "В работе")\
            .filter(TechItem.return_deadline != None)\
            .order_by(TechItem.return_deadline.asc())\
            .limit(3) \
            .all()
        
        # Преобразуем в список словарей с дополнительным флагом urgency
        returns_list = []
        for item in all_returns:
            is_urgent = item.return_deadline < datetime.now()
            returns_list.append({
                "item": item,
                "is_urgent": is_urgent,
                "class_name": "urgent" if is_urgent else "soon"
            })
        
        return templates.TemplateResponse("home/template.html", {
            "request": request,
            "count_work": count_work,
            "count_repair": count_repair,
            "count_total": count_total,
            "returns_list": returns_list, # Передаем список вместо одного элемента
            "format_date": format_date_only
        })
    finally:
        db.close()

@app.get("/tech", response_class=HTMLResponse)
async def tech_list(request: Request, search: str = "", sort_by: str = "name", sort_order: str = "asc"):
    db = SessionLocal()
    try:
        query = db.query(TechItem)
        if search:
            sf = f"%{search}%"
            query = query.filter((TechItem.name.like(sf)) | (TechItem.category.like(sf)) | (TechItem.status.like(sf)) | (TechItem.inv_number.like(sf)) | (TechItem.barcode.like(sf)))
        
        col_map = {"name": TechItem.name, "status": TechItem.status, "category": TechItem.category, "return_deadline": TechItem.return_deadline}
        col = col_map.get(sort_by, TechItem.name)
        query = query.order_by(col.desc() if sort_order == "desc" else col.asc())
        
        items = query.all()
        return templates.TemplateResponse("tech/template.html", {
            "request": request, "items": items, "format_date": format_date_only,
            "current_search": search, "sort_by": sort_by, "sort_order": sort_order
        })
    finally: db.close()

@app.get("/tech/export/excel")
async def export_technique_to_excel():
    db = SessionLocal()
    try:
        items = db.query(TechItem).all()
        if not items: raise HTTPException(status_code=404, detail="Нет данных")
        
        data = []
        for item in items:
            data.append({
                "ID": item.id, "Название": item.name, "Категория": item.category,
                "Статус": item.status, "Инв. номер": item.inv_number or "-",
                "Серийный номер": item.serial_number or "-", "Штрих-код": item.barcode,
                "Выдано кому": item.issued_to or "-",
                "Дата возврата": item.return_deadline.strftime("%d-%m-%Y %H:%M") if item.return_deadline else "-",
                "Место работы": item.work_location or "-", "Заметки": item.notes or "-",
                "Дата добавления": item.created_at.strftime("%d-%m-%Y") if item.created_at else "-"
            })
        
        df = pd.DataFrame(data)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Техника')
        output.seek(0)
        
        filename = f"export_technique_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={filename}"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally: db.close()

@app.post("/add/")
async def add_item(request: Request, name: str = Form(...), barcode: str = Form(...),
    inv_number: str = Form(default=""), serial_number: str = Form(default=""),
    category: str = Form(...), status: str = Form(...), location: str = Form(default=""),
    notes: str = Form(default=""), photo: UploadFile = File(None),
    issued_by: str = Form(default=""), issued_to: str = Form(default=""),
    issue_time: str = Form(default=""), return_deadline: str = Form(default=""),
    work_location: str = Form(default="")):
    
    db = SessionLocal()
    try:
        if not barcode or barcode.strip() == "": return JSONResponse(status_code=400, content={"error": "Штрих-код обязателен"})
        barcode = barcode.strip()
        if db.query(TechItem).filter(TechItem.barcode == barcode).first():
            return JSONResponse(status_code=400, content={"error": "Такой код уже существует"})
        
        photo_filename = None
        if photo and photo.filename:
            ext = os.path.splitext(photo.filename)[1].lower()
            if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]: return JSONResponse(status_code=400, content={"error": "Только изображения"})
            photo_filename = f"{uuid.uuid4()}{ext}"
            with open(os.path.join(UPLOAD_DIR, photo_filename), "wb") as buffer: shutil.copyfileobj(photo.file, buffer)

        dt_issue = datetime.strptime(issue_time, "%Y-%m-%dT%H:%M") if issue_time else None
        dt_return = datetime.strptime(return_deadline, "%Y-%m-%dT%H:%M") if return_deadline else None

        new_item = TechItem(name=name, barcode=barcode, inv_number=inv_number, serial_number=serial_number,
            photo_filename=photo_filename, category=category, status=status, location=location, notes=notes,
            issued_by=issued_by, issued_to=issued_to, issue_time=dt_issue, return_deadline=dt_return, work_location=work_location)
        db.add(new_item)
        db.commit()
        return RedirectResponse(url="/tech", status_code=303)
    except Exception as e:
        db.rollback()
        print(traceback.format_exc())
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally: db.close()

@app.get("/item/{item_id}", response_class=HTMLResponse)
async def view_item(request: Request, item_id: int):
    db = SessionLocal()
    item = db.query(TechItem).filter(TechItem.id == item_id).first()
    db.close()
    if not item: raise HTTPException(status_code=404, detail="Не найдено")
    return templates.TemplateResponse("details/template.html", {"request": request, "item": item, "format_date": format_date})

@app.post("/edit/{item_id}")
async def edit_item(item_id: int, name: str = Form(...), barcode: str = Form(...),
    inv_number: str = Form(default=""), serial_number: str = Form(default=""),
    category: str = Form(...), status: str = Form(...), location: str = Form(default=""),
    notes: str = Form(default=""), photo: UploadFile = File(None), remove_photo: str = Form(default=""),
    issued_by: str = Form(default=""), issued_to: str = Form(default=""),
    issue_time: str = Form(default=""), return_deadline: str = Form(default=""),
    work_location: str = Form(default="")):
    db = SessionLocal()
    try:
        item = db.query(TechItem).filter(TechItem.id == item_id).first()
        if not item: return JSONResponse(status_code=404, content={"error": "Не найдено"})
        
        if remove_photo == "on" and item.photo_filename:
            path = os.path.join(UPLOAD_DIR, item.photo_filename)
            if os.path.exists(path): os.remove(path)
            item.photo_filename = None
        
        if photo and photo.filename:
            ext = os.path.splitext(photo.filename)[1].lower()
            if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]: return JSONResponse(status_code=400, content={"error": "Только изображения"})
            if item.photo_filename:
                path = os.path.join(UPLOAD_DIR, item.photo_filename)
                if os.path.exists(path): os.remove(path)
            new_filename = f"{uuid.uuid4()}{ext}"
            with open(os.path.join(UPLOAD_DIR, new_filename), "wb") as buffer: shutil.copyfileobj(photo.file, buffer)
            item.photo_filename = new_filename
        
        item.name = name; item.barcode = barcode; item.inv_number = inv_number
        item.serial_number = serial_number; item.category = category; item.status = status
        item.location = location; item.notes = notes
        item.issued_by = issued_by; item.issued_to = issued_to; item.work_location = work_location
        if issue_time: item.issue_time = datetime.strptime(issue_time, "%Y-%m-%dT%H:%M")
        if return_deadline: item.return_deadline = datetime.strptime(return_deadline, "%Y-%m-%dT%H:%M")
        
        db.commit()
        return RedirectResponse(url=f"/item/{item_id}", status_code=303)
    except Exception as e:
        db.rollback()
        print(traceback.format_exc())
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally: db.close()

@app.post("/delete/{item_id}")
async def delete_item(item_id: int):
    db = SessionLocal()
    try:
        item = db.query(TechItem).filter(TechItem.id == item_id).first()
        if item:
            if item.photo_filename:
                path = os.path.join(UPLOAD_DIR, item.photo_filename)
                if os.path.exists(path): os.remove(path)
            db.delete(item)
            db.commit()
        return RedirectResponse(url="/tech", status_code=303)
    except Exception as e:
        db.rollback()
        print(traceback.format_exc())
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally: db.close()

@app.get("/api/calendar-events")
async def get_calendar_events():
    db = SessionLocal()
    try:
        items = db.query(TechItem).filter(TechItem.status == "В работе").filter(TechItem.return_deadline != None).all()
        events = []
        for item in items:
            color = "#d32f2f" if item.return_deadline < datetime.now() else "#2196f3"
            events.append({
                "id": item.id, "title": f"{item.name} ({item.issued_to or 'Не указан'})",
                "start": item.return_deadline.strftime("%Y-%m-%dT%H:%M:%S"),
                "url": f"/item/{item.id}", "backgroundColor": color, "borderColor": color,
                "extendedProps": {"category": item.category, "inv_number": item.inv_number, "barcode": item.barcode}
            })
        return JSONResponse(content=events)
    finally: db.close()

@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):
    return templates.TemplateResponse("calendar/template.html", {"request": request})

# --- НОВЫЕ МАРШРУТЫ ДЛЯ ВЫДАЧИ ---

@app.get("/issue", response_class=HTMLResponse)
async def issue_page(request: Request):
    db = SessionLocal()
    # Получаем только технику со статусом "Склад"
    available_items = db.query(TechItem).filter(TechItem.status == "Склад").all()
    db.close()
    return templates.TemplateResponse("issue/template.html", {"request": request, "available_items": available_items})

@app.post("/issue/process")
async def process_issue(
    request: Request,
    issued_to: str = Form(...),
    issued_by: str = Form(...),
    issue_time: str = Form(...),
    return_deadline: str = Form(...),
    work_location: str = Form(...),
    item_ids: str = Form(...)
):
    db = SessionLocal()
    try:
        if not item_ids:
            return JSONResponse(status_code=400, content={"error": "Не выбрано ни одного устройства"})
        
        ids = [int(x.strip()) for x in item_ids.split(',') if x.strip()]
        if not ids:
            return JSONResponse(status_code=400, content={"error": "Некорректный список"})

        dt_issue = datetime.strptime(issue_time, "%Y-%m-%dT%H:%M")
        dt_return = datetime.strptime(return_deadline, "%Y-%m-%dT%H:%M")

        updated_count = 0
        for item_id in ids:
            item = db.query(TechItem).filter(TechItem.id == item_id).first()
            if item and item.status == "Склад":
                item.status = "В работе"
                item.issued_to = issued_to
                item.issued_by = issued_by
                item.issue_time = dt_issue
                item.return_deadline = dt_return
                item.work_location = work_location
                updated_count += 1
        
        db.commit()
        return RedirectResponse(url="/issue?success=true&count=" + str(updated_count), status_code=303)

    except Exception as e:
        db.rollback()
        print(traceback.format_exc())
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally: db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)