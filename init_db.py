import sqlite3

# Подключение к базе данных
conn = sqlite3.connect("doctors.db")
cur = conn.cursor()

# Удаление таблиц, если они существуют
cur.execute("DROP TABLE IF EXISTS schedules")  # Сначала удаляем таблицу с внешним ключом
cur.execute("DROP TABLE IF EXISTS doctors")

# Создание таблицы врачей с новым полем active
cur.execute("""
CREATE TABLE doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    position TEXT NOT NULL,
    room INTEGER NOT NULL,
    photo TEXT,
    token TEXT UNIQUE,
    info TEXT,
    occupied INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1
)
""")

# Создание таблицы расписания
cur.execute("""
CREATE TABLE schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL, -- 0-6 (пн-вс)
    start_time TEXT NOT NULL,     -- формат "HH:MM"
    end_time TEXT NOT NULL,       -- формат "HH:MM"
    FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE
)
""")

# Добавление индекса для ускорения поиска по токену
cur.execute("CREATE INDEX idx_doctors_token ON doctors (token)")
# Добавление индекса для ускорения поиска по кабинету
cur.execute("CREATE INDEX idx_doctors_room ON doctors (room)")
# Добавление индекса для ускорения поиска расписания по doctor_id
cur.execute("CREATE INDEX idx_schedules_doctor_id ON schedules (doctor_id)")

# Добавление тестовых данных для врачей
doctors_data = [
    ("Иванов И.И.", "Хирург", 201, "ivanov.jpg", "201", "Прием по будням", 0, 1),
    ("Петров П.П.", "Терапевт", 202, "petrov.jpg", "202", "Консультации", 0, 1),
    ("Сидорова С.С.", "Кардиолог", 203, "sidorova.jpg", "203", "Кардиограмма", 0, 1)
]

for doctor in doctors_data:
    cur.execute("""
    INSERT INTO doctors (name, position, room, photo, token, info, occupied, active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, doctor)
    
    # Получаем ID добавленного врача
    doctor_id = cur.lastrowid
    
    # Добавляем расписание для каждого врача
    if doctor[0] == "Иванов И.И.":
        # Расписание для Иванова (понедельник, среда, пятница утром)
        schedules = [
            (doctor_id, 0, "08:00", "12:00"),  # Понедельник
            (doctor_id, 2, "08:00", "12:00"),  # Среда
            (doctor_id, 4, "08:00", "12:00")   # Пятница
        ]
    elif doctor[0] == "Петров П.П.":
        # Расписание для Петрова (понедельник, среда, пятница после обеда)
        schedules = [
            (doctor_id, 0, "13:00", "17:00"),  # Понедельник
            (doctor_id, 2, "13:00", "17:00"),  # Среда
            (doctor_id, 4, "13:00", "17:00")   # Пятница
        ]
    else:
        # Расписание для Сидоровой (вторник, четверг весь день)
        schedules = [
            (doctor_id, 1, "09:00", "17:00"),  # Вторник
            (doctor_id, 3, "09:00", "17:00")   # Четверг
        ]
    
    # Добавляем расписание в базу данных
    for schedule in schedules:
        cur.execute("""
        INSERT INTO schedules (doctor_id, day_of_week, start_time, end_time)
        VALUES (?, ?, ?, ?)
        """, schedule)

# Сохранение изменений
conn.commit()

# Проверка данных врачей
cur = conn.execute("SELECT * FROM doctors ORDER BY room ASC")
doctors = cur.fetchall()
print("Список врачей, отсортированный по номеру кабинета:")
for doctor in doctors:
    print(f"ID: {doctor[0]}, Имя: {doctor[1]}, Кабинет: {doctor[3]}, Токен: {doctor[5]}, Активен: {doctor[8]}")

# Проверка расписания
cur = conn.execute("""
SELECT d.name, s.day_of_week, s.start_time, s.end_time 
FROM doctors d 
JOIN schedules s ON d.id = s.doctor_id 
ORDER BY d.name, s.day_of_week
""")
schedules = cur.fetchall()
print("\nРасписание врачей:")
day_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
for schedule in schedules:
    print(f"Врач: {schedule[0]}, День: {day_names[schedule[1]]}, Время: {schedule[2]} - {schedule[3]}")

# Закрытие соединения
conn.close()
