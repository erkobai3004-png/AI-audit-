import paramiko
from flask import Flask, render_template, request, jsonify, redirect, session, send_file
from datetime import datetime
import csv, os
from user_agents import parse
from collections import defaultdict, deque
import pandas as pd
from google import genai
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
import os
import requests
from dotenv import load_dotenv

load_dotenv()
from io import BytesIO

from flask import send_file
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

CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")
SERVER_IP = os.getenv("SERVER_IP", "161.35.70.26")
BASE_DOMAIN = os.getenv("BASE_DOMAIN", "uni-system.cc")
VPS_HOST = os.getenv("VPS_HOST", "").strip()
VPS_USER = os.getenv("VPS_USER", "").strip()
VPS_PASSWORD = os.getenv("VPS_PASSWORD", "").strip()

CF_HEADERS = {
    "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
    "Content-Type": "application/json"
}


def cf_request(method, url, json=None):
    if not CLOUDFLARE_API_TOKEN or not CLOUDFLARE_ZONE_ID:
        return {
            "success": False,
            "errors": ["Cloudflare API Token немесе Zone ID .env ішінде жазылмаған."]
        }

    response = requests.request(
        method,
        url,
        headers=CF_HEADERS,
        json=json,
        timeout=15
    )

    return response.json()



@app.route("/admin/dns", methods=["GET", "POST"])
def admin_dns():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    message = None
    error = None

    if request.method == "POST":
        subdomain = request.form.get("subdomain", "").strip().lower()
        proxied = request.form.get("proxied") == "on"
        scenario_port = request.form.get("scenario", "8000")
        scenario_path = ""

        scenario_path = ""

        if scenario_port == "8000":
            scenario_path = "/microsoft365"

        elif scenario_port == "8001":
            scenario_path = "/oprosnik"
            scenario_port = "8000"

        elif scenario_port == "8002":
            scenario_path = "/avtomaty"
            scenario_port = "8000"
        if not subdomain:
            error = "Subdomain бос болмауы керек."
        elif "." in subdomain or "/" in subdomain or " " in subdomain:
            error = "Тек subdomain атын жазыңыз. Мысалы: test немесе oprosnik"
        else:
            full_name = f"{subdomain}.{BASE_DOMAIN}"

            url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records"

            payload = {
                "type": "A",
                "name": full_name,
                "content": SERVER_IP,
                "ttl": 1
            }

            if proxied:
                payload["proxied"] = True
            else:
                payload["proxied"] = False

            result = cf_request("POST", url, json=payload)

            if result.get("success"):
                os.makedirs("generated_nginx", exist_ok=True)

                config_path = os.path.join("generated_nginx", f"{subdomain}.conf")

                nginx_config = f"""
            server {{
                listen 80;
                server_name {full_name};

                location / {{
                    proxy_pass http://127.0.0.1:{scenario_port}{scenario_path};
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                }}
            }}
            """

                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(nginx_config)

                deploy_ok, deploy_msg = deploy_nginx_config(
                    config_path,
                    f"{subdomain}.conf"
                )

                if deploy_ok:
                    message = f"{full_name} DNS және nginx deploy жасалды."
                else:
                    error = f"DNS қосылды, бірақ nginx deploy қатесі: {deploy_msg}"

            else:
                error = str(result)
    list_url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records?type=A"
    records_result = cf_request("GET", list_url)

    records = []
    if records_result.get("success"):
        records = records_result.get("result", [])

    return render_template(
        "admin_dns.html",
        records=records,
        message=message,
        error=error,
        server_ip=SERVER_IP,
        base_domain=BASE_DOMAIN
    )

@app.route("/admin/dns/delete/<record_id>", methods=["POST"])
def delete_dns_record(record_id):

    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records/{record_id}"

    result = cf_request("DELETE", url)

    return redirect("/admin/dns")
@app.route("/admin/dns/update/<record_id>", methods=["POST"])
def update_dns_record(record_id):

    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    name = request.form.get("name")
    record_type = request.form.get("type", "A")
    ip = request.form.get("ip", SERVER_IP)
    proxied = request.form.get("proxied") == "on"
    scenario_port = request.form.get("scenario", "8000")
    url = f"https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_ID}/dns_records/{record_id}"

    payload = {
        "type": "A",
        "name": full_name,
        "content": SERVER_IP,
        "ttl": 1
    }

    if proxied:
        payload["proxied"] = True
    else:
        payload["proxied"] = False

    result = cf_request("PATCH", url, json=payload)

    return redirect("/admin/dns")
def deploy_nginx_config(local_path, remote_name):
    if not VPS_HOST or not VPS_USER or not VPS_PASSWORD:
        return False, "VPS_HOST, VPS_USER немесе VPS_PASSWORD .env ішінде жоқ."

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            VPS_HOST,
            username=VPS_USER,
            password=VPS_PASSWORD,
            timeout=15
        )

        sftp = ssh.open_sftp()
        remote_temp = f"/root/generated_nginx/{remote_name}"
        sftp.put(local_path, remote_temp)
        sftp.close()

        commands = [
            f"cp {remote_temp} /etc/nginx/sites-available/{remote_name}",
            f"ln -sf /etc/nginx/sites-available/{remote_name} /etc/nginx/sites-enabled/{remote_name}",
            "nginx -t",
            "systemctl reload nginx"
        ]

        output = ""

        for cmd in commands:
            stdin, stdout, stderr = ssh.exec_command(cmd)
            out = stdout.read().decode()
            err = stderr.read().decode()
            output += f"\n$ {cmd}\n{out}\n{err}"

            if cmd == "nginx -t" and "successful" not in err.lower():
                return False, output

        ssh.close()
        return True, output

    except Exception as e:
        return False, str(e)
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
# 🛡 ADMIN PANEL
@app.route("/admin")
def admin():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    return render_template("admin.html")
@app.route("/admin/analytics")
def analytics():

    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    return render_template("analytics.html")
@app.route("/admin/ai")
def ai_insights():

    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    return render_template("ai_insights.html")
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
    site_filter = request.args.get("site")
    event_filter = request.args.get("event")
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
            if site_filter and site != site_filter:
                continue

            if event_filter and event != event_filter:
                continue
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
    site_filter = request.args.get("site")
    event_filter = request.args.get("event")
    logs = deque(maxlen=20)

    if not os.path.exists(LOG_FILE):
        return jsonify([])

    with open(LOG_FILE, "r", encoding="utf-8") as f:

        reader = csv.DictReader(f)

        rows = list(reader)

        for row in reversed(rows[-20:]):
            site = row.get("site", "")
            event = row.get("event", "")

            if site_filter and site != site_filter:
                continue

            if event_filter and event != event_filter:
                continue
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
@app.route("/admin/ai/analyze")
def ai_analyze():

        if not session.get("admin_logged_in"):
            return jsonify({
                "error": "Авторизация қажет"
            }), 401

        api_key = os.environ.get(
            "GEMINI_API_KEY"
        )

        if not api_key:
            return jsonify({
                "error": "GEMINI_API_KEY табылмады"
            }), 500

        if not os.path.exists(LOG_FILE):
            return jsonify({
                "error": "Лог файлы табылмады"
            }), 404

        with open(
                LOG_FILE,
                "r",
                encoding="utf-8"
        ) as f:

            logs_text = f.read()

        prompt = f"""
    Сен кәсіби киберқауіпсіздік аудиторы және SOC аналитигісің.
    Сенің міндетің — Social Engineering Audit Tool логтары негізінде толық, терең, коммерциялық аудит есебін дайындау.

    Маңызды:
    - Жауап тек қазақ тілінде болсын.
    - Жауап қысқа болмасын.
    - Әр бөлім толық, нақты, ақпаратқа бай болсын.
    - Ұсыныстар көп және практикалық болсын.
    - Компания сатып алатын аудит есебі сияқты professional форматта жаз.
    - Тек жалпы сөздер жазба, логтардағы нақты әрекеттерге сүйен.
    - Нақты логин/пароль талданбайды және сақталмайды.
    - Бұл тек этикалық аудит және awareness testing.

    Сценарийлер:

    1) microsoft365
    - OSINT арқылы нақты адамға бағытталған spear phishing сценарийі.
    - Арна: электрондық пошта.
    - Аудитория: 1 нақты адам.
    - Триггер: шұғылдық / қорқыныш.
    - Қауіп: корпоративтік аккаунтқа сену, жалған Microsoft365 бетіне кіру, credential submission risk.

    2) oprosnik
    - AI voice cloning арқылы voice phishing simulation.
    - Арна: WhatsApp дауыстық хабарлама.
    - Аудитория: 5 адам.
    - Триггер: сенім / көмек / қызығушылық.
    - Қауіп: таныс дауысқа сену, emotional manipulation, urgency-based help request.

    3) avtomaty
    - Пайда мен қызығушылыққа негізделген baiting сценарийі.
    - Арна: WhatsApp студенттік топ.
    - Аудитория: топтық аудитория.
    - Триггер: пайда / қызығушылық.
    - Қауіп: топтық ортада сілтемеге тез басу, reward-based manipulation.

    Логтардағы event мағынасы:
    - visit — пайдаланушы сайтқа кірді
    - click — пайдаланушы батырма немесе әрекет элементін басты
    - leave — пайдаланушы сайттан шықты
    - login_attempt — пайдаланушы формаға дерек енгізуге дейін барды
    - time_spent — бетте өткізген уақыт
    - device/browser/os — техникалық орта

    Міндетті түрде мына форматпен жаз:

    # 1. Executive Summary
    Жалпы аудит нәтижесін толық түсіндір.
    Қандай қауіп байқалды, қандай сценарий әсерлі болды, қандай оң нәтиже бар.

    # 2. Жалпы статистикалық талдау
    Логтардан:
    - жалпы visit саны
    - жалпы click саны
    - login_attempt саны
    - leave саны
    - орташа time_spent
    - құрылғы/browser/os туралы қорытынды
    шығарып жаз.

    # 3. Әр сценарий бойынша жеке талдау
    Әр сценарийді бөлек талда:

    ## microsoft365
    - Нысаналы spear phishing неге қауіпті
    - OSINT қолдану қаупі
    - Email арқылы жіберудің әсері
    - Шұғылдық/қорқыныш trigger әсері
    - Логтар бойынша пайдаланушы әрекеті
    - Risk level

    ## oprosnik
    - Voice phishing қаупі
    - AI voice cloning арқылы сенімге әсер ету
    - WhatsApp арнасының ерекшелігі
    - Көмек/сенім/қызығушылық trigger әсері
    - Логтар бойынша әрекет
    - Risk level

    ## avtomaty
    - Reward baiting қаупі
    - WhatsApp group арқылы кең таралу қаупі
    - Пайда/қызығушылық trigger әсері
    - Логтар бойынша әрекет
    - Risk level

    # 4. Behavioral Analysis
    Пайдаланушылардың мінез-құлқын талда:
    - сілтемеге сену деңгейі
    - күмәндану белгілері
    - тез шыққан жағдайлар
    - ұзақ отырған жағдайлар
    - click жасағандар
    - дерек енгізуге бармағандар
    - қандай behavior қауіпті екенін жаз.

    # 5. Psychological Trigger Analysis
    Әр trigger-ді талда:
    - Шұғылдық
    - Қорқыныш
    - Сенім
    - Көмек сұрау
    - Қызығушылық
    - Пайда

    Қайсысы көбірек әсер еткенін түсіндір.

    # 6. Technical Risk Analysis
    Техникалық тұрғыдан талда:
    - phishing page interaction
    - browser/device/os exposure
    - IP logging
    - session behavior
    - endpoint visibility
    - email/WhatsApp delivery risks
    - MFA болмаса қандай қауіп болуы мүмкін

    # 7. Risk Rating
    Әр сценарийге risk бер:
    - LOW / MEDIUM / HIGH
    Неге солай екенін түсіндір.
    Кесте түрінде жаз.

    # 8. Нақты ұсыныстар
    Кемінде 15 ұсыныс бер.
    Ұсыныстарды мына топтарға бөл:
    - Қызметкерлерді оқыту
    - Email security
    - WhatsApp / messenger қауіпсіздігі
    - MFA және access control
    - OSINT exposure reduction
    - Incident response
    - Policy and governance
    - Technical monitoring

    # 9. Қысқа мерзімді іс-шаралар
    Алдағы 7 күнде не істеу керек.

    # 10. Орта мерзімді іс-шаралар
    Алдағы 1 айда не істеу керек.

    # 11. Ұзақ мерзімді стратегия
    3–6 айда қандай security awareness program құру керек.

    # 12. Қорытынды
    Толық, кәсіби қорытынды жаз.

    Жауапта markdown қолдан.
    Бөлімдер анық болсын.
    Кесте қолдануға болады.
    Жауап кемінде 1200–1800 сөз болсын.

    Логтар:
{logs_text[-12000:]}

"""

        try:

            client = genai.Client(
                api_key=api_key
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )

            return jsonify({
                "answer": response.text
            })

        except Exception as e:

            return jsonify({
                "error": str(e)
            }), 500
@app.route("/admin/ai/chat", methods=["POST"])
def ai_chat():

    if not session.get("admin_logged_in"):
        return jsonify({"error": "Авторизация қажет"}), 401

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return jsonify({"error": "GEMINI_API_KEY табылмады"}), 500

    user_message = request.json.get("message", "")

    if not user_message:
        return jsonify({"error": "Сұрақ бос."}), 400

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        logs_text = f.read()

    prompt = f"""
Сен киберқауіпсіздік аудитінің AI аналитигісің.
Төмендегі аудит логтарына сүйеніп, пайдаланушының сұрағына қазақ тілінде жауап бер.

Сценарийлер:
1) microsoft365 — OSINT негізіндегі targeted spear phishing, Email, шұғылдық/қорқыныш.
2) oprosnik — AI voice phishing simulation, WhatsApp voice, сенім/көмек/қызығушылық.
3) avtomaty — reward-based baiting, WhatsApp group, пайда/қызығушылық.

Логтар:
{logs_text[-12000:]}

Пайдаланушы сұрағы:
{user_message}
"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        return jsonify({"answer": response.text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/export/pdf")
def export_pdf():

    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4
    )

    pdfmetrics.registerFont(
        TTFont(
            'DejaVu',
            'fonts/DejaVuSans.ttf'
        )
    )

    styles = getSampleStyleSheet()
    styles['BodyText'].fontName = 'DejaVu'
    styles['Title'].fontName = 'DejaVu'
    styles['Heading2'].fontName = 'DejaVu'

    elements = []

    title = Paragraph(
        "Social Engineering Audit Report",
        styles['Title']
    )

    elements.append(title)
    elements.append(Spacer(1, 20))

    intro = Paragraph(
        """
        Бұл есеп әлеуметтік инженерия аудиті
        нәтижелері негізінде автоматты түрде
        жасалған.<br/><br/>

        Жүйе:<br/>
        - phishing simulation<br/>
        - behavioral analysis<br/>
        - AI-driven security analytics<br/>
        қолданады.
        """,
        styles['BodyText']
    )

    elements.append(intro)
    elements.append(Spacer(1, 20))

    stats = Paragraph(
        """
        <b>Жалпы статистика:</b><br/><br/>

        Visits: 12<br/>
        Clicks: 5<br/>
        Login Attempts: 1<br/>
        Average Time: 24 sec<br/>
        Risk Level: MEDIUM
        """,
        styles['BodyText']
    )

    elements.append(stats)
    elements.append(Spacer(1, 20))

    try:
        api_key = os.environ.get("GEMINI_API_KEY")

        if not api_key:
            raise Exception("GEMINI_API_KEY табылмады")

        client = genai.Client(api_key=api_key)

        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs_text = f.read()

        ai_prompt = f"""
Төмендегі аудит логтарына қысқаша professional
security conclusion жаса.

1. Жалпы қорытынды
2. Ең қауіпті сценарий
3. Ұсыныстар

Қазақ тілінде жаз.

Логтар:
{logs_text[-6000:]}
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=ai_prompt
        )

        ai_text = response.text

    except Exception as e:
        ai_text = f"AI analysis error: {str(e)}"

    ai_title = Paragraph(
        "AI Security Analysis",
        styles['Heading2']
    )

    elements.append(ai_title)
    elements.append(Spacer(1, 12))

    ai_paragraph = Paragraph(
        ai_text.replace("\n", "<br/>"),
        styles['BodyText']
    )

    elements.append(ai_paragraph)
    elements.append(Spacer(1, 20))

    doc.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="audit_report.pdf",
        mimetype="application/pdf"
    )
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)