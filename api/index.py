from flask import Flask, request, render_template
import email
import quopri
import re
from bs4 import BeautifulSoup

app = Flask(__name__, template_folder="../templates")

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


@app.route("/", methods=["GET", "POST"])
def index():
    print("GET or POST received.")
    caregivers = []

    if request.method == "POST":
        print("POST request received.")
        files = request.files.getlist("file")
        pay_rate = float(request.form.get("pay_rate", 0))
        overtime_pay_rate = float(request.form.get("overtime_pay_rate", 0))

        for file in files:
            if file:
                print("File uploaded:", file.filename)
                content = file.read()
                msg = email.message_from_bytes(content)

                extracted_items = []
                total_hours = 0.0
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

                        for td in tds:
                            style = td.get("style", "").lower().replace(" ", "")
                            if "text-wrap:nowrap;" in style:
                                text = td.get_text(strip=True)
                                if re.fullmatch(r"\d{4}-\d{4}", text):
                                    extracted_items.append(text)
                                    total_hours += get_duration_hours(text)

                        for a in a_s:
                            label = a.get("aria-label", "").lower().replace(" ", "")
                            if "viewaidedetails:" in label:
                                name = a.get_text(strip=True)
                                try:
                                    last_name, first_name = name.split(" ")
                                    caregiver_name = f"{first_name} {last_name}"
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
                    "intime_pay": intime_pay,
                    "overtime_pay": overtime_pay,
                    "total_pay": total_pay,
                    "time_ranges": extracted_items
                })

    return render_template("index.html", caregivers=caregivers)
