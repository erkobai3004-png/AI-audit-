from flask import Flask, render_template, request, jsonify, redirect, session
from datetime import datetime
import csv, os
from user_agents import parse
from flask import Flask, render_template, request, jsonify, redirect, session,send_file
from datetime import datetime
import csv, os
from collections import defaultdict, deque
import pandas as pd
app = Flask(__name__)
app.secret_key = "secret123"

ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "12345"
LOG_FILE = "logs/data.csv"

# 📁 logs папкасы болмаса — жасаймыз
os.makedirs("logs", exist_ok=True)

# 📄 CSV файл болмаса — header жазамыз
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:

        writer = csv.writer(f)

        writer.writerow([
            "time", "site", "event", "ip",
            "user_agent", "referrer",
            "time_spent", "clicked",
            "login_entered", "password_entered",
            "device", "browser", "os"
        ])
# 🌐 Клиент IP алу
def get_ip():
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0]
    return request.remote_addr


# 📡 TRACKING API
@app.route("/track", methods=["POST"])
def track():
    data = request.json

    ua_string = request.headers.get("User-Agent")

    user_agent = parse(ua_string)

    device = "Mobile" if user_agent.is_mobile else "Desktop"

    browser = user_agent.browser.family

    os_name = user_agent.os.family

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:

        writer = csv.writer(f)

        writer.writerow([
            datetime.now(),
            data.get("site"),
            data.get("event"),
            get_ip(),
            ua_string,
            data.get("referrer"),
            data.get("time_spent"),
            data.get("clicked"),
            data.get("login_entered"),
            data.get("password_entered"),
            device,
            browser,
            os_name
        ])

    return jsonify({"status": "ok"})
# 🌐 Сценарийлер
@app.route("/microsoft365")
def microsoft365():
    return render_template("microsoft365.html")

@app.route("/avtomaty")
def avtomaty():
    return render_template("avtomaty.html")

@app.route("/oprosnik")
def oprosnik():
    return render_template("oprosnik.html")


# 🛡 ADMIN PANEL
@app.route("/admin")
def admin():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")
    return render_template("admin.html")
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_LOGIN and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect("/admin")

        return render_template("admin_login.html", error="Логин немесе пароль қате")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin/login")
@app.route("/admin/data")
def admin_data():
    stats = {
        "visits": 0,
        "clicks": 0,
        "logins": 0
    }
    devices = defaultdict(int)
    browsers = defaultdict(int)
    oses = defaultdict(int)
    scenarios = defaultdict(lambda: {
        "visits": 0,
        "clicks": 0,
        "logins": 0,
        "time": 0
    })

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            site = row.get("site", "unknown")
            event = row.get("event", "")
            device = row.get("device", "Unknown") or "Unknown"
            browser = row.get("browser", "Unknown") or "Unknown"
            os_name = row.get("os", "Unknown") or "Unknown"

            devices[device] += 1
            browsers[browser] += 1
            oses[os_name] += 1
            try:
                time_spent = int(row.get("time_spent") or 0)
            except:
                time_spent = 0

            if event == "visit":
                stats["visits"] += 1
                scenarios[site]["visits"] += 1

            if event == "click":
                stats["clicks"] += 1
                scenarios[site]["clicks"] += 1

            if event == "login_attempt":
                stats["logins"] += 1
                scenarios[site]["logins"] += 1

            scenarios[site]["time"] += time_spent

    # 📊 пайыз есептеу
    for site in scenarios:
        visits = scenarios[site]["visits"]

        if visits > 0:
            scenarios[site]["click_rate"] = round((scenarios[site]["clicks"] / visits) * 100, 2)
            scenarios[site]["success_rate"] = round((scenarios[site]["logins"] / visits) * 100, 2)
            scenarios[site]["avg_time"] = round((scenarios[site]["time"] / visits), 2)
        else:
            scenarios[site]["click_rate"] = 0
            scenarios[site]["success_rate"] = 0
            scenarios[site]["avg_time"] = 0

    return jsonify({
        "stats": stats,
        "scenarios": scenarios,
        "devices": devices,
        "browsers": browsers,
        "oses": oses
    })
# 📡 LIVE LOG STREAM API
@app.route("/admin/logs")
def admin_logs():

    logs = deque(maxlen=20)

    if not os.path.exists(LOG_FILE):
        return jsonify([])

    with open(LOG_FILE, "r", encoding="utf-8") as f:

        reader = csv.DictReader(f)

        rows = list(reader)

        for row in reversed(rows[-20:]):

            logs.append({
                "time": row.get("time", ""),
                "site": row.get("site", "unknown"),
                "event": row.get("event", ""),
                "device": row.get("device", "Unknown"),
                "browser": row.get("browser", "Unknown"),
                "ip": row.get("ip", "0.0.0.0"),
                "time_spent": row.get("time_spent", "0")
            })

    return jsonify(list(logs))
# 📊 EXPORT EXCEL
@app.route("/export/excel")
def export_excel():

    if not os.path.exists(LOG_FILE):
        return "Log file not found", 404

    export_file = "logs/audit_export.xlsx"

    df = pd.read_csv(LOG_FILE)
    df.to_excel(export_file, index=False)

    return send_file(
        export_file,
        as_attachment=True,
        download_name="audit_export.xlsx"
    )
# ▶️ Запуск
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)