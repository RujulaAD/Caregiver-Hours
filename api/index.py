from flask import Flask, request, render_template
import email
import quopri
import re
from bs4 import BeautifulSoup
import json
import os
import os
from dotenv import load_dotenv

load_dotenv()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
app = Flask(__name__, template_folder="../templates")
CARDS_FILE = "saved_cards.json"


def safe_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def get_duration_hours(time_range):
    try:
        start_str, end_str = time_range.split("-")
        start_hour = int(start_str[:2])
        start_min = int(start_str[2:])
        end_hour = int(end_str[:2])
        end_min = int(end_str[2:])

        start_total = start_hour * 60 + start_min
        end_total = end_hour * 60 + end_min

        if end_total < start_total:  # overnight
            end_total += 24 * 60

        duration_min = end_total - start_total
        duration_hours = round(duration_min / 60, 2)
        return duration_hours
    except Exception as e:
        print("Error in get_duration_hours:", time_range, "|", e)
        return 0.0

def load_cards():
    if not os.path.exists(CARDS_FILE):
        return []
    with open(CARDS_FILE, "r") as f:
        return json.load(f)

def save_cards(cards):
    with open(CARDS_FILE, "w") as f:
        json.dump(cards, f, indent=2)


@app.route("/", methods=["GET", "POST"])
def index():
    print("GET or POST received.")
    caregivers = []

    if request.method == "POST":
        print("POST request received.")
        files = request.files.getlist("file")
        pay_rate = safe_float(request.form.get("pay_rate"))
        overtime_pay_rate = safe_float(request.form.get("overtime_pay_rate"))


        for file in files:
            if file:
                print("File uploaded:", file.filename)
                content = file.read()
                msg = email.message_from_bytes(content)

                scheduled_times = []
                visit_times = []
                total_hours = 0.0
                total_hours_visit = 0.0
                total_pay = 0.0
                intime_pay = 0.0
                overtime_pay = 0.0
                caregiver_name = None

                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        raw_payload = part.get_payload(decode=True)
                        decoded_bytes = quopri.decodestring(raw_payload)

                        try:
                            decoded_html = decoded_bytes.decode("utf-8")
                        except UnicodeDecodeError:
                            decoded_html = decoded_bytes.decode("latin1")

                        html = decoded_html.replace("=\n", "").replace("=3D", "=")
                        soup = BeautifulSoup(html, "html.parser")
                        tds = soup.find_all("td")
                        a_s = soup.find_all("a")

                        for td in tds: #scheduled times
                            style = td.get("style", "").lower().replace(" ", "")
                            if "text-wrap:nowrap;" in style:
                                text = td.get_text(strip=True)
                                if re.fullmatch(r"\d{4}-\d{4}", text):
                                    scheduled_times.append(text)
                                    total_hours += get_duration_hours(text)

                        for td in tds: #visit times
                            style = td.get("style", "").lower().replace(" ", "")
                            if "#254679" in style:
                                text = td.get_text(strip=True)
                                if re.fullmatch(r"\d{4}-\d{4}", text):
                                    visit_times.append(text)
                                    total_hours_visit += round(get_duration_hours(text) *4) / 4

                        for a in a_s: #name
                            label = a.get("aria-label", "").lower().replace(" ", "")
                            if "viewaidedetails:" in label:
                                name = a.get_text(strip=True)
                                try:
                                    last_name, first_name = name.split(" ")
                                    caregiver_name = f"{first_name} {last_name}"
                                except ValueError:
                                    try:
                                        middle_name, last_name, first_name = name.split(" ")
                                        caregiver_name = f"{first_name} {middle_name} {last_name}"
                                    except ValueError:
                                        caregiver_name = name
                                break

                # Pay calculations
                if total_hours > 80:
                    overtime = total_hours - 80
                    overtime_pay = round(overtime * overtime_pay_rate, 2)
                    intime_pay = round(80 * pay_rate, 2)
                    total_pay = round(intime_pay + overtime_pay, 2)
                else:
                    intime_pay = round(total_hours * pay_rate, 2)
                    total_pay = intime_pay

                caregivers.append({
                    "name": caregiver_name or file.filename,
                    "total_hours": round(total_hours, 2),
                    "total_hours_visit": round(total_hours_visit, 2),
                    "intime_pay": intime_pay,
                    "overtime_pay": overtime_pay,
                    "total_pay": total_pay,
                    "scheduled_times": scheduled_times,
                    "visit_times": visit_times
                })

    return render_template("index.html", caregivers=caregivers)

@app.route("/saved", methods=["GET", "POST"])
def saved():
    if not session.get("authenticated"):
        if request.method == "POST":
            if request.form.get("password") == ADMIN_PASSWORD:
                session["authenticated"] = True
                return redirect(url_for("saved"))
            else:
                flash("Incorrect password", "error")
        return render_template("password_prompt.html")

    cards = load_cards()
    return render_template("saved_cards.html", cards=cards)

@app.route("/save_card", methods=["POST"])
def save_card():
    if not session.get("authenticated"):
        return redirect(url_for("saved"))

    card = {
        "name": request.form.get("name"),
        "total_hours": request.form.get("total_hours"),
        "intime_pay": request.form.get("intime_pay"),
        "overtime_pay": request.form.get("overtime_pay"),
        "total_pay": request.form.get("total_pay")
    }

    cards = load_cards()
    cards.append(card)
    save_cards(cards)
    return redirect(url_for("saved"))

@app.route("/delete/<int:index>")
def delete_card(index):
    if not session.get("authenticated"):
        return redirect(url_for("saved"))
    cards = load_cards()
    if 0 <= index < len(cards):
        del cards[index]
        save_cards(cards)
    return redirect(url_for("saved"))

@app.route("/delete_all")
def delete_all():
    if not session.get("authenticated"):
        return redirect(url_for("saved"))
    save_cards([])
    return redirect(url_for("saved"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))
