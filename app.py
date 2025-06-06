from flask import Flask, render_template, request, redirect, url_for, send_from_directory, jsonify
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import time

app = Flask(__name__)

# Задаем фиксированный токен для доступа к админке
ADMIN_TOKEN = "123456"  # Ваш токен доступа

DB_PATH = "doctors.db"
UPLOAD_FOLDER = "static/photos"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Это позволит обращаться к столбцам по имени
    return conn

def init_db():
    with get_db() as db:
        # Таблица врачей
        db.execute('''
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            position TEXT NOT NULL,
            room INTEGER NOT NULL,
            photo TEXT,
            token TEXT UNIQUE,
            info TEXT,
            occupied INTEGER DEFAULT 0
        )
        ''')
        
        # Таблица расписания
        db.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL, -- 0-6 (пн-вс)
            start_time TEXT NOT NULL,     -- формат "HH:MM"
            end_time TEXT NOT NULL,       -- формат "HH:MM"
            FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE
        )
        ''')
        
        db.commit()

# Инициализация базы данных
init_db()

def get_current_doctor_for_room(room):
    """Определяет, какой врач должен принимать в данном кабинете в текущее время"""
    now = datetime.now()
    day_of_week = now.weekday()  # 0-6 (пн-вс)
    current_time = now.strftime("%H:%M")
    
    with get_db() as db:
        # Находим всех врачей, которые должны принимать в этом кабинете в текущий день и время
        cur = db.execute('''
            SELECT d.id, d.name, d.position, d.photo, d.info, d.occupied, s.start_time, s.end_time
            FROM doctors d
            JOIN schedules s ON d.id = s.doctor_id
            WHERE d.room = ? AND s.day_of_week = ? AND s.start_time <= ? AND s.end_time >= ?
            ORDER BY s.start_time
        ''', (room, day_of_week, current_time, current_time))
        
        doctor = cur.fetchone()
        
        if doctor:
            return dict(doctor)
        
        # Если никто не принимает прямо сейчас, найдем ближайшего врача в этом кабинете
        # Сначала проверим сегодняшний день
        cur = db.execute('''
            SELECT d.id, d.name, d.position, d.photo, d.info, d.occupied, s.start_time, s.end_time
            FROM doctors d
            JOIN schedules s ON d.id = s.doctor_id
            WHERE d.room = ? AND s.day_of_week = ? AND s.start_time > ?
            ORDER BY s.start_time
            LIMIT 1
        ''', (room, day_of_week, current_time))
        
        doctor = cur.fetchone()
        
        if doctor:
            return dict(doctor)
        
        # Если никого нет сегодня, найдем первого врача в следующие дни
        for next_day in range(1, 8):  # Проверяем следующие 7 дней
            future_day = (day_of_week + next_day) % 7
            
            cur = db.execute('''
                SELECT d.id, d.name, d.position, d.photo, d.info, d.occupied, s.start_time, s.end_time
                FROM doctors d
                JOIN schedules s ON d.id = s.doctor_id
                WHERE d.room = ? AND s.day_of_week = ?
                ORDER BY s.start_time
                LIMIT 1
            ''', (room, future_day))
            
            doctor = cur.fetchone()
            
            if doctor:
                return dict(doctor)
        
        # Если расписания нет, вернем первого врача из этого кабинета
        cur = db.execute('SELECT * FROM doctors WHERE room = ? LIMIT 1', (room,))
        doctor = cur.fetchone()
        
        if doctor:
            return dict(doctor)
        
        return None

@app.route("/admin", methods=["GET", "POST"])
def admin():
    # Проверка токена
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return "Доступ запрещен. Неверный токен.", 403
    
    if request.method == "POST":
        form = request.form
        action = form.get("action")
        photo_file = request.files.get("photo")
        photo_filename = None

        if photo_file and photo_file.filename:
            photo_filename = secure_filename(photo_file.filename)
            photo_path = os.path.join(UPLOAD_FOLDER, photo_filename)
            photo_file.save(photo_path)

        if action == "add":
            room_number = int(form["room"])
            with get_db() as db:
                # Генерируем уникальный токен для врача
                token = f"{room_number}_{int(time.time())}"
                
                doctor_id = db.execute("""
                    INSERT INTO doctors (name, position, room, photo, token, info, occupied)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                """, (
                    form["name"],
                    form["position"],
                    room_number,
                    photo_filename or "",
                    token,
                    form.get("info", "")
                )).lastrowid
                
                # Добавляем расписание, если оно предоставлено
                if "schedule" in form and form["schedule"]:
                    schedule_data = form["schedule"].strip().split('\n')
                    for line in schedule_data:
                        if not line.strip():
                            continue
                        try:
                            day, times = line.split(':', 1)
                            day = int(day.strip())
                            start_time, end_time = times.strip().split('-')
                            
                            db.execute("""
                                INSERT INTO schedules (doctor_id, day_of_week, start_time, end_time)
                                VALUES (?, ?, ?, ?)
                            """, (doctor_id, day, start_time.strip(), end_time.strip()))
                        except Exception as e:
                            print(f"Error parsing schedule line: {line}, error: {e}")

        elif action == "edit":
            room_number = int(form["room"])
            doctor_id = form["id"]
            occupied = 1 if form.get("occupied") == "1" else 0
            
            with get_db() as db:
                if photo_filename:
                    db.execute("""
                        UPDATE doctors SET name=?, position=?, room=?, photo=?, info=?, occupied=? WHERE id=?
                    """, (
                        form["name"],
                        form["position"],
                        room_number,
                        photo_filename,
                        form.get("info", ""),
                        occupied,
                        doctor_id
                    ))
                else:
                    db.execute("""
                        UPDATE doctors SET name=?, position=?, room=?, info=?, occupied=? WHERE id=?
                    """, (
                        form["name"],
                        form["position"],
                        room_number,
                        form.get("info", ""),
                        occupied,
                        doctor_id
                    ))
                
                # Обновляем расписание
                if "update_schedule" in form and form["update_schedule"] == "1":
                    # Сначала удаляем старое расписание
                    db.execute("DELETE FROM schedules WHERE doctor_id=?", (doctor_id,))
                    
                    # Затем добавляем новое
                    if "schedule" in form and form["schedule"]:
                        schedule_data = form["schedule"].strip().split('\n')
                        for line in schedule_data:
                            if not line.strip():
                                continue
                            try:
                                day, times = line.split(':', 1)
                                day = int(day.strip())
                                start_time, end_time = times.strip().split('-')
                                
                                db.execute("""
                                    INSERT INTO schedules (doctor_id, day_of_week, start_time, end_time)
                                    VALUES (?, ?, ?, ?)
                                """, (doctor_id, day, start_time.strip(), end_time.strip()))
                            except Exception as e:
                                print(f"Error parsing schedule line: {line}, error: {e}")

        elif action == "delete":
            with get_db() as db:
                db.execute("DELETE FROM doctors WHERE id=?", (form["id"],))
                # Расписание удалится автоматически благодаря ON DELETE CASCADE

        elif action == "status":
            with get_db() as db:
                db.execute("UPDATE doctors SET occupied=? WHERE id=?", (
                    1 if form["occupied"] == "1" else 0,
                    form["id"]
                ))

    with get_db() as db:
        # Получаем список всех врачей
        cur = db.execute("SELECT * FROM doctors ORDER BY room ASC, name ASC")
        doctors = cur.fetchall()
        
        # Получаем расписание для каждого врача
        doctor_schedules = {}
        for doctor in doctors:
            cur = db.execute("""
                SELECT day_of_week, start_time, end_time 
                FROM schedules 
                WHERE doctor_id=? 
                ORDER BY day_of_week, start_time
            """, (doctor['id'],))
            
            schedules = cur.fetchall()
            formatted_schedules = []
            
            for schedule in schedules:
                day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                day_name = day_names[schedule['day_of_week']]
                formatted_schedules.append(
                    f"{day_name}: {schedule['start_time']} - {schedule['end_time']}"
                )
            
            doctor_schedules[doctor['id']] = formatted_schedules

    # Передаем токен в шаблон для сохранения в формах и ссылках
    return render_template(
        "admin.html", 
        doctors=doctors, 
        doctor_schedules=doctor_schedules,
        url_root=request.url_root, 
        admin_token=ADMIN_TOKEN
    )

@app.route("/status", methods=["GET", "POST"])
def status_control():
    token = request.args.get("token")
    if not token:
        return "Token required", 403

    with get_db() as db:
        cur = db.execute("SELECT id, name, room, occupied, position FROM doctors WHERE token=?", (token,))
        doc = cur.fetchone()

    if not doc:
        return "Invalid token", 403

    if request.method == "POST":
        new_status = request.form["status"]
        with get_db() as db:
            db.execute("UPDATE doctors SET occupied=? WHERE id=?", (1 if new_status == "occupied" else 0, doc['id']))
        return redirect(url_for("status_control", token=token))

    # Получаем расписание для врача
    with get_db() as db:
        cur = db.execute("""
            SELECT day_of_week, start_time, end_time 
            FROM schedules 
            WHERE doctor_id=? 
            ORDER BY day_of_week, start_time
        """, (doc['id'],))
        
        schedules = cur.fetchall()
        
        # Форматируем расписание для отображения
        day_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        formatted_schedules = []
        
        for schedule in schedules:
            day_name = day_names[schedule['day_of_week']]
            formatted_schedules.append({
                'day': day_name,
                'time': f"{schedule['start_time']} - {schedule['end_time']}"
            })
    
    return render_template("status_control.html", doctor=doc, schedules=formatted_schedules)

@app.route("/display/<int:room>")
def display(room):
    # Определяем, какой врач должен принимать в данном кабинете сейчас
    doctor = get_current_doctor_for_room(room)
    
    if not doctor:
        return "Кабинет не найден", 404
    
    # Получаем расписание для кабинета
    with get_db() as db:
        cur = db.execute("""
            SELECT d.id, d.name, s.day_of_week, s.start_time, s.end_time
            FROM doctors d
            JOIN schedules s ON d.id = s.doctor_id
            WHERE d.room = ?
            ORDER BY s.day_of_week, s.start_time, d.name
        """, (room,))
        
        schedules = cur.fetchall()
        
        # Форматируем расписание для отображения
        day_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        formatted_schedules = []
        
        for schedule in schedules:
            day_name = day_names[schedule['day_of_week']]
            formatted_schedules.append({
                'doctor_name': schedule['name'],
                'day': day_name,
                'time': f"{schedule['start_time']} - {schedule['end_time']}"
            })
    
    return render_template(
        "display.html", 
        name=doctor['name'], 
        position=doctor['position'], 
        photo=doctor['photo'],
        occupied=bool(doctor['occupied']), 
        info=doctor['info'], 
        room=room,
        schedules=formatted_schedules
    )

@app.route("/api/status/<int:room>")
def api_status(room):
    doctor = get_current_doctor_for_room(room)
    
    if doctor:
        return jsonify({
            "occupied": bool(doctor['occupied']),
            "name": doctor['name'],
            "position": doctor['position']
        })
    return jsonify({"error": "not found"}), 404

@app.route("/static/photos/<path:filename>")
def photo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == "__main__":
    app.run(debug=True)
