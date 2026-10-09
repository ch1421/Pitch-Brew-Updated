import os, sqlite3, re
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "pitchbrew.db")
app = Flask(__name__)
app.secret_key = os.environ.get("PITCHBREW_SECRET", "change-this-secret-before-public-launch")
ADMIN_PASSWORD = os.environ.get("PITCHBREW_ADMIN_PASSWORD", "change-me")

SPORTS = ["Cricket", "Football", "Badminton", "Volleyball"]
CAFE = [
    {"id":"paratha","name":"Paratha","price":50,"emoji":"🫓"},
    {"id":"fries","name":"Fries","price":100,"emoji":"🍟"},
    {"id":"chai","name":"Chai","price":50,"emoji":"☕"},
    {"id":"lays","name":"Lays","price":70,"emoji":"🥔"},
    {"id":"cold-drink","name":"Cold Drink","price":220,"emoji":"🥤"},
    {"id":"water","name":"Water","price":150,"emoji":"💧"},
    {"id":"juice","name":"Juice","price":150,"emoji":"🧃"},
    {"id":"loaded-fries","name":"Loaded Fries","price":350,"emoji":"🍟"},
]

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL, phone TEXT NOT NULL,
            sport TEXT NOT NULL, booking_date TEXT NOT NULL,
            start_time TEXT NOT NULL, duration_days INTEGER NOT NULL DEFAULT 1,
            players INTEGER NOT NULL DEFAULT 1, message TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS schedule_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_date TEXT NOT NULL, start_time TEXT NOT NULL,
            end_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Available',
            booked_name TEXT DEFAULT '', sport TEXT DEFAULT '',
            UNIQUE(slot_date, start_time)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS cafe_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT NOT NULL,
            phone TEXT NOT NULL, items_json TEXT NOT NULL, total INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending', created_at TEXT NOT NULL
        )""")

init_db()

def parse_time_to_minutes(value):
    value = (value or "").strip().upper().replace(".", "")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(AM|PM)$", value)
    if not m: return None
    h, minute, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if h < 1 or h > 12 or minute > 59: return None
    h = h % 12 + (12 if ap == "PM" else 0)
    return h*60+minute

def normalize_time(value):
    value = (value or "").strip().upper().replace(".", "")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(AM|PM)$", value)
    if not m: return None
    h, minute, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if h < 1 or h > 12 or minute > 59: return None
    return f"{h}:{minute:02d} {ap}"

def parse_weekly_schedule(raw):
    """
    Accepts lines such as:
    Monday
    5 PM - 6 PM Available
    6 PM - 7 PM Booked - Ali
    Also accepts 'Available: 5 PM to 6 PM' and 'Booked: 6 PM - 7 PM - Name'.
    """
    day_map = {"MONDAY":0,"TUESDAY":1,"WEDNESDAY":2,"THURSDAY":3,"FRIDAY":4,"SATURDAY":5,"SUNDAY":6}
    current_day = None
    parsed = []
    for rawline in (raw or "").splitlines():
        line = rawline.strip()
        if not line: continue
        upper = line.upper().strip(" :-")
        found_day = next((d for d in day_map if re.search(r"\b"+d+r"\b", upper)), None)
        if found_day and not re.search(r"\d{1,2}(:\d{2})?\s*(AM|PM)", upper):
            current_day = found_day
            continue
        if not current_day:
            continue
        # time range then status/name can be on either side
        m = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:AM|PM))\s*(?:-|–|—|to|TO)\s*(\d{1,2}(?::\d{2})?\s*(?:AM|PM))", line, re.I)
        if not m: continue
        start, end = normalize_time(m.group(1)), normalize_time(m.group(2))
        if not start or not end: continue
        after = line[m.end():].strip(" :-|")
        before = line[:m.start()].strip(" :-|")
        text = (after + " " + before).strip()
        status = "Booked" if re.search(r"\bBOOKED\b|\bRESERVED\b", text, re.I) else "Available"
        name = ""
        if status == "Booked":
            name = re.sub(r"\b(BOOKED|RESERVED|AVAILABLE|NOT AVAILABLE)\b", "", text, flags=re.I)
            name = re.sub(r"^[\s:|,-]+|[\s:|,-]+$", "", name)
            name = re.sub(r"\s+", " ", name)
        parsed.append({"day": current_day.title(), "weekday": day_map[current_day],
                       "start":start,"end":end,"status":status,"name":name})
    return parsed

def upsert_schedule(raw, start_date):
    parsed = parse_weekly_schedule(raw)
    if not parsed:
        return 0
    # Each day block follows the actual named weekday, avoiding Sunday/Monday shifts.
    with connect() as con:
        con.execute("DELETE FROM schedule_slots WHERE slot_date >= ? AND slot_date <= ?",
                    (start_date.isoformat(), (start_date + timedelta(days=13)).isoformat()))
        for item in parsed:
            offset = (item["weekday"] - start_date.weekday()) % 7
            slot_day = start_date + timedelta(days=offset)
            with con:
                con.execute("""INSERT OR REPLACE INTO schedule_slots
                    (slot_date,start_time,end_time,status,booked_name,sport)
                    VALUES (?,?,?,?,?,?)""",
                    (slot_day.isoformat(), item["start"], item["end"], item["status"], item["name"], ""))
    return len(parsed)

@app.after_request
def headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response

@app.route("/")
def home():
    return render_template("index.html", cafe=CAFE, sports=SPORTS)

@app.route("/admin")
def admin():
    if not session.get("admin"):
        return render_template("admin_login.html")
    with connect() as con:
        bookings = con.execute("SELECT * FROM bookings ORDER BY id DESC LIMIT 100").fetchall()
        orders = con.execute("SELECT * FROM cafe_orders ORDER BY id DESC LIMIT 100").fetchall()
        slots = con.execute("SELECT * FROM schedule_slots ORDER BY slot_date,start_time LIMIT 300").fetchall()
    return render_template("admin.html", bookings=bookings, orders=orders, slots=slots)

@app.route("/admin/login", methods=["POST"])
def admin_login():
    if request.form.get("password", "") == ADMIN_PASSWORD:
        session["admin"] = True
        return redirect(url_for("admin"))
    flash("Password incorrect.")
    return redirect(url_for("admin"))

@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin"))

@app.route("/admin/schedule", methods=["POST"])
def admin_schedule():
    if not session.get("admin"): return redirect(url_for("admin"))
    raw = request.form.get("schedule_text", "")
    try: start = date.fromisoformat(request.form.get("start_date", ""))
    except ValueError:
        flash("Please choose a valid start date."); return redirect(url_for("admin"))
    count = upsert_schedule(raw, start)
    flash(f"Schedule updated: {count} slots parsed." if count else "No valid time slots found. Use e.g. 5 PM - 6 PM Available under a weekday heading.")
    return redirect(url_for("admin"))

@app.route("/admin/booking/<int:booking_id>", methods=["POST"])
def admin_booking_status(booking_id):
    if not session.get("admin"): return redirect(url_for("admin"))
    status = request.form.get("status", "Pending")
    if status not in ("Pending","Confirmed","Cancelled"): status = "Pending"
    with connect() as con:
        con.execute("UPDATE bookings SET status=? WHERE id=?", (status, booking_id))
    return redirect(url_for("admin"))

@app.route("/api/schedule")
def api_schedule():
    day = request.args.get("date", "")
    try: date.fromisoformat(day)
    except ValueError: return jsonify({"error":"Use date=YYYY-MM-DD"}), 400
    with connect() as con:
        rows = con.execute("SELECT * FROM schedule_slots WHERE slot_date=? ORDER BY id", (day,)).fetchall()
        bookings = con.execute("""SELECT start_time, customer_name, status, sport FROM bookings
            WHERE booking_date=? AND status IN ('Pending','Confirmed')""", (day,)).fetchall()
    result = []
    for row in rows:
        result.append(dict(row))
    # Reservations from booking form also mark overlapping exact start times.
    for b in bookings:
        if not any(x["start_time"] == b["start_time"] for x in result):
            result.append({"slot_date":day,"start_time":b["start_time"],"end_time":"","status":"Booked",
                           "booked_name":b["customer_name"],"sport":b["sport"]})
        else:
            for x in result:
                if x["start_time"] == b["start_time"]:
                    x["status"] = "Booked"; x["booked_name"] = b["customer_name"]; x["sport"] = b["sport"]
    return jsonify({"date":day,"slots":result})

@app.route("/api/bookings", methods=["POST"])
def create_booking():
    data = request.get_json(silent=True) or request.form
    name = str(data.get("name","")).strip()
    phone = str(data.get("phone","")).strip()
    sport = str(data.get("sport","Cricket")).strip()
    day = str(data.get("date","")).strip()
    start = normalize_time(str(data.get("time","")))
    try: date.fromisoformat(day)
    except ValueError: return jsonify({"error":"Please select a valid date."}), 400
    try: duration = int(data.get("duration",1))
    except (ValueError, TypeError): duration = 1
    try: players = int(data.get("players",1))
    except (ValueError, TypeError): players = 1
    duration = max(1, min(duration, 3)); players = max(1, min(players, 40))
    if not name or len(name) > 80 or not phone or len(phone) > 30:
        return jsonify({"error":"Enter your name and phone number."}), 400
    if sport not in SPORTS: return jsonify({"error":"Choose a valid sport."}), 400
    if not start: return jsonify({"error":"Choose a valid time such as 6:00 PM."}), 400
    # Check each requested day on the server.
    dates = [date.fromisoformat(day) + timedelta(days=i) for i in range(duration)]
    with connect() as con:
        for d in dates:
            slot = con.execute("SELECT * FROM schedule_slots WHERE slot_date=? AND start_time=?", (d.isoformat(), start)).fetchone()
            if slot and slot["status"] != "Available":
                return jsonify({"error":f"{d.strftime('%d %b')} at {start} is already booked."}), 409
            existing = con.execute("""SELECT id FROM bookings WHERE booking_date=? AND start_time=?
                AND status IN ('Pending','Confirmed')""", (d.isoformat(), start)).fetchone()
            if existing: return jsonify({"error":f"{d.strftime('%d %b')} at {start} is already reserved."}), 409
        con.execute("""INSERT INTO bookings(customer_name,phone,sport,booking_date,start_time,duration_days,players,message,status,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (name,phone,sport,day,start,duration,players,str(data.get("message",""))[:500],"Pending",datetime.now().isoformat(timespec="seconds")))
    return jsonify({"ok":True,"message":"Booking request saved. WhatsApp will open so you can send it to the arena."})

@app.route("/api/cafe-order", methods=["POST"])
def cafe_order():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name","")).strip()
    phone = str(data.get("phone","")).strip()
    items = data.get("items", [])
    if not name or not phone or not isinstance(items, list) or not items:
        return jsonify({"error":"Add your name, phone, and at least one item."}), 400
    catalog = {x["id"]:x for x in CAFE}
    clean, total = [], 0
    for item in items:
        try: qty = int(item.get("qty",0)); key = str(item.get("id",""))
        except (ValueError, TypeError, AttributeError): continue
        if key in catalog and 0 < qty <= 10:
            row = catalog[key]; total += row["price"] * qty
            clean.append({"name":row["name"],"qty":qty,"price":row["price"],"subtotal":row["price"]*qty})
    if not clean: return jsonify({"error":"Your cart is empty."}), 400
    import json
    with connect() as con:
        con.execute("INSERT INTO cafe_orders(customer_name,phone,items_json,total,created_at) VALUES(?,?,?,?,?)",
                    (name,phone,json.dumps(clean),total,datetime.now().isoformat(timespec="seconds")))
    return jsonify({"ok":True,"total":total,"items":clean})

@app.route("/health")
def health():
    return jsonify({"ok":True,"service":"PITCH & BREW","time":datetime.now().isoformat(timespec="seconds")})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
