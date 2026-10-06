from flask import Flask, jsonify, request, render_template
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3
import re

BASE = Path(__file__).resolve().parent
DB = BASE / "pitchbrew.db"

app = Flask(__name__, static_folder="static", template_folder="templates")

# Allow the GitHub Pages customer app to read the live schedule API.
# The customer frontend is hosted on GitHub Pages while this Flask API
# is hosted on PythonAnywhere, so browser CORS permission is required.
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


DAYS = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]

def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = get_db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS slots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            day TEXT NOT NULL,
            start TEXT NOT NULL,
            end TEXT NOT NULL,
            status TEXT NOT NULL,
            booked_by TEXT DEFAULT ''
        )
    """)
    con.commit()
    con.close()

def parse_clock(value, suffix=None):
    value = value.strip().upper().replace(" ", "").replace(".", "")
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(AM|PM)?", value)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    token_suffix = m.group(3) or suffix
    if hour < 1 or hour > 12 or minute > 59:
        return None
    if token_suffix == "AM":
        hour = 0 if hour == 12 else hour
    elif token_suffix == "PM":
        hour = 12 if hour == 12 else hour + 12
    else:
        if hour > 23:
            return None
    return f"{hour:02d}:{minute:02d}"


def parse_range(value):
    """Parse the WhatsApp time style used by PITCH&BREW.

    Important project conventions:
      11-1 AM       = 11 PM -> 1 AM
      12-2 AM       = 12 AM -> 2 AM
      10:30-12:30PM = 10:30 PM -> 12:30 AM (the WhatsApp text has a typo)
      5-7 PM        = 5 PM -> 7 PM
    """
    value = value.replace("–", "-").replace("—", "-").strip()
    m = re.match(r"^(.+?)\s*-\s*(.+?)$", value)
    if not m:
        return None
    left_raw, right_raw = m.group(1).strip(), m.group(2).strip()

    left_suffix_m = re.search(r"(AM|PM)$", left_raw, re.I)
    right_suffix_m = re.search(r"(AM|PM)$", right_raw, re.I)
    left_suffix = left_suffix_m.group(1).upper() if left_suffix_m else None
    right_suffix = right_suffix_m.group(1).upper() if right_suffix_m else None
    suffix = right_suffix or left_suffix

    left_num = re.sub(r"(AM|PM)$", "", left_raw, flags=re.I).strip()
    right_num = re.sub(r"(AM|PM)$", "", right_raw, flags=re.I).strip()

    # If both ends explicitly contain a suffix, respect them exactly.
    if left_suffix or right_suffix:
        if left_suffix and right_suffix:
            start = parse_clock(left_num, left_suffix)
            end = parse_clock(right_num, right_suffix)
            return (start, end) if start and end else None

        # Only one suffix is written, normally on the END of the range.
        # Apply PITCH&BREW's overnight convention rather than blindly
        # applying the suffix to both ends.
        try:
            lh = int(left_num.split(":")[0])
            rh = int(right_num.split(":")[0])
        except ValueError:
            return None

        start_suffix = suffix
        end_suffix = suffix

        if suffix == "AM":
            # 11-1 AM means 11 PM -> 1 AM.
            # 12-2 AM means 12 AM -> 2 AM.
            if lh != 12 and lh > rh:
                start_suffix = "PM"
        elif suffix == "PM":
            # 10-12 PM / 11-12 PM are night slots ending after midnight.
            # A right-side 12 PM in this schedule means midnight (12 AM).
            if rh == 12:
                end_suffix = "AM"
            elif lh > rh:
                end_suffix = "AM"

        start = parse_clock(left_num, start_suffix)
        end = parse_clock(right_num, end_suffix)
        return (start, end) if start and end else None

    # No suffix at all: accept explicit 24-hour values only.
    start = parse_clock(left_num)
    end = parse_clock(right_num)
    return (start, end) if start and end else None


def parse_schedule(text):
    lines = [line.strip().replace("*", "") for line in text.splitlines() if line.strip()]
    current_day = None
    block_index = -1
    items = []

    for line in lines:
        clean = line.strip().rstrip(":").strip()
        day = next((d for d in DAYS if clean.lower() == d.lower()), None)
        if day:
            # Do NOT use DAYS.index(day). Sunday appears twice in a weekly
            # schedule (start Sunday and next Sunday), and the second Sunday
            # must become day 7, not day 0.
            block_index += 1
            current_day = day
            continue

        if current_day is None:
            continue

        low = line.lower()
        if "weekly booking schedule" in low:
            continue
        if re.match(r"^\d{1,2}\s+\w+\s+to\s+\d{1,2}\s+\w+", low):
            continue

        # Find the status word first. WhatsApp messages often contain
        # inconsistent punctuation/spacing such as:
        #   9-10PM ,:Booked (Rehan)
        #   11-1 AM :Booked (Saqib)
        #   09-11PM : Booked (Hussain)
        #   09-11 PM Booked Hussain
        status_match = re.search(r"\b(Available|Booked)\b", line, re.I)
        if not status_match:
            continue

        time_text = line[:status_match.start()].strip().rstrip(" :;,\t")
        status = status_match.group(1).title()
        tail = line[status_match.end():].strip().lstrip(":;, \t").strip()
        booked_by = ""
        if status.lower() == "booked":
            if tail.startswith("(") and tail.endswith(")"):
                booked_by = tail[1:-1].strip()
            else:
                booked_by = tail.strip()

        times = parse_range(time_text)
        if not times:
            continue

        items.append({
            "day": current_day,
            "block_index": block_index,
            "start": times[0],
            "end": times[1],
            "status": status,
            "booked_by": booked_by
        })

    return items

def nearest_sunday(date_obj):
    return date_obj - timedelta(days=(date_obj.weekday()+1)%7)

# Make sure the database/table exists when Flask is loaded by WSGI.
init_db()

@app.route("/")
def admin():
    return render_template("admin.html")

@app.route("/app")
def customer():
    return app.send_static_file("index.html")

@app.route("/api/schedule")
def api_schedule():
    date = request.args.get("date","")
    try:
        datetime.strptime(date,"%Y-%m-%d")
    except ValueError:
        return jsonify({"error":"Invalid date"}),400

    con = get_db()
    rows = con.execute(
        "SELECT start,end,status,booked_by FROM slots WHERE date=? ORDER BY id",
        (date,)
    ).fetchall()
    con.close()

    day = datetime.strptime(date,"%Y-%m-%d").strftime("%A")
    return jsonify({
        "date": date,
        "day": day,
        "slots": [[r["start"],r["end"],r["status"],r["booked_by"]] for r in rows]
    })

@app.route("/api/update", methods=["POST"])
def update_schedule():
    payload = request.get_json(silent=True) or {}
    text = payload.get("text","").strip()
    week_start = payload.get("week_start","").strip()

    if not text:
        return jsonify({"error":"Schedule text is empty."}),400

    if week_start:
        try:
            # IMPORTANT: use the exact date selected in Admin.
            # Never shift it to another Sunday; shifting caused bookings
            # to appear under the wrong calendar date.
            start_date = datetime.strptime(week_start,"%Y-%m-%d")
        except ValueError:
            return jsonify({"error":"Invalid week start date."}),400
    else:
        # Try to read the first date from the pasted heading.
        m = re.search(r"(\d{1,2})\s+([A-Za-z]+)", text)
        start_date = datetime.now()
        if m:
            try:
                start_date = datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {datetime.now().year}",
                    "%d %B %Y"
                )
            except ValueError:
                pass

    parsed = parse_schedule(text)

    if not parsed:
        return jsonify({"error":"No valid Available/Booked slots were found."}),400

    # The pasted schedule does not always start on Sunday.
    # For example, after Sunday 4 Oct is finished, the new schedule may
    # start with Monday 5 Oct.  The old code always assigned the FIRST
    # parsed block to week_start, causing Monday 5 Oct to be saved as
    # Sunday 4 Oct and every following day to be one day behind.
    #
    # Fix: anchor the FIRST parsed day to its actual occurrence on/after
    # the selected week-start date, then keep the schedule blocks in the
    # exact order they appear. This also correctly handles a second Sunday.
    first_day = parsed[0]["day"]
    day_to_pyweekday = {
        "Sunday": 6,
        "Monday": 0,
        "Tuesday": 1,
        "Wednesday": 2,
        "Thursday": 3,
        "Friday": 4,
        "Saturday": 5,
    }
    first_pyweekday = day_to_pyweekday[first_day]
    start_pyweekday = start_date.weekday()
    first_day_offset = (first_pyweekday - start_pyweekday) % 7
    first_block_date = start_date + timedelta(days=first_day_offset)

    con = get_db()
    con.execute("DELETE FROM slots")

    for item in parsed:
        date_obj = first_block_date + timedelta(days=item["block_index"])
        con.execute("""
            INSERT INTO slots(date,day,start,end,status,booked_by)
            VALUES(?,?,?,?,?,?)
        """, (
            date_obj.strftime("%Y-%m-%d"),
            item["day"],
            item["start"],
            item["end"],
            item["status"],
            item["booked_by"]
        ))

    con.commit()
    count = con.execute("SELECT COUNT(*) FROM slots").fetchone()[0]
    con.close()

    return jsonify({"ok":True,"slots_imported":count})

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
