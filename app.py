import json
import os
import re
import uuid
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
import qrcode
import psycopg
from psycopg.types.json import Jsonb
from qrcode.constants import ERROR_CORRECT_L
from flask import Flask, abort, make_response, redirect, render_template, request, send_file, send_from_directory, url_for

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
QR_DIR = DATA_DIR / "qr"
UPLOAD_DIR = DATA_DIR / "uploads"
PROFILES_FILE = DATA_DIR / "profiles.json"
INVITATION_FILE = DATA_DIR / "invitation"
for folder in (QR_DIR, UPLOAD_DIR):
    folder.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def load_profiles():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        try:
            with psycopg.connect(database_url) as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS profiles_store (store_id INTEGER PRIMARY KEY, payload JSONB NOT NULL)"
                )
                row = connection.execute("SELECT payload FROM profiles_store WHERE store_id = 1").fetchone()
                return row[0] if row else {}
        except psycopg.Error as error:
            app.logger.exception("Could not load profiles from PostgreSQL")
            raise RuntimeError("Không thể kết nối database PostgreSQL. Kiểm tra DATABASE_URL trên Render.") from error
    if not PROFILES_FILE.exists():
        return {}
    return json.loads(PROFILES_FILE.read_text(encoding="utf-8"))


def save_profiles(profiles):
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        try:
            with psycopg.connect(database_url) as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS profiles_store (store_id INTEGER PRIMARY KEY, payload JSONB NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO profiles_store (store_id, payload) VALUES (1, %s) "
                    "ON CONFLICT (store_id) DO UPDATE SET payload = EXCLUDED.payload",
                    (Jsonb(profiles),),
                )
            return
        except psycopg.Error as error:
            app.logger.exception("Could not save profiles to PostgreSQL")
            raise RuntimeError("Không thể lưu dữ liệu vào database PostgreSQL. Kiểm tra DATABASE_URL trên Render.") from error
    temporary_file = PROFILES_FILE.with_suffix(".tmp")
    temporary_file.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_file.replace(PROFILES_FILE)


def attendance_stats(profiles):
    sales = {}
    for profile in profiles.values():
        sale = next((value for key, value in profile["fields"].items() if "nhân viên phụ trách" in key.lower()), "Chưa phân sale") or "Chưa phân sale"
        entry = sales.setdefault(sale, {"invited": 0, "checked_in": 0})
        entry["invited"] += 1
        entry["checked_in"] += bool(profile.get("checkin_at"))
    for entry in sales.values():
        entry["rate"] = round(entry["checked_in"] * 100 / entry["invited"], 1) if entry["invited"] else 0
    return sales


def clean_value(value):
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def safe_filename(value):
    return re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._") or "customer"


def profile_identity(fields):
    for field in ("Mã KH", "Mã khách hàng", "Email", "Điện thoại", "Họ tên"):
        value = fields.get(field, "").strip().lower()
        if value:
            return field, value
    return None


def next_guest_code(profiles):
    highest_number = 0
    for profile in profiles.values():
        customer_code = str(profile.get("fields", {}).get("Mã KH", "")).strip().upper()
        match = re.fullmatch(r"OL(\d+)", customer_code)
        if match:
            highest_number = max(highest_number, int(match.group(1)))
    return f"OL{highest_number + 1:02d}"


def vcard_value(value):
    return str(value).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def make_offline_qr_content(fields, name):
    return json.dumps(
        {"THÔNG TIN KHÁCH HÀNG": {field: value or "Chưa cập nhật" for field, value in fields.items()}},
        ensure_ascii=False,
        indent=2,
    )


def create_qr_image(content, output_path):
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)
    qr.make_image().save(output_path)


def qr_image_stream(content):
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)
    output = BytesIO()
    qr.make_image().save(output, format="PNG")
    output.seek(0)
    return output


def read_customer_file(upload_path, suffix):
    if suffix == ".csv":
        return pd.read_csv(upload_path)
    raw_data = pd.read_excel(upload_path, sheet_name="DS KHÁCH", header=None)
    header_rows = raw_data.index[
        raw_data.apply(lambda row: row.astype(str).str.strip().eq("Họ tên").any(), axis=1)
    ]
    header_index = int(header_rows[0]) if len(header_rows) else 0
    return pd.read_excel(upload_path, sheet_name="DS KHÁCH", header=header_index).dropna(how="all")


def public_base_url():
    return request.host_url.rstrip("/")


CUSTOMER_FIELDS = ["Mã KH", "Họ tên", "Công ty", "Chức vụ", "Điện thoại", "Email", "Nhân viên phụ trách", "Tình trạng"]


@app.get("/")
def index():
    profiles = load_profiles()
    response = make_response(render_template("index.html", profiles=profiles, stats=attendance_stats(profiles)))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.get("/health/storage")
def storage_health():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return {"storage": "local-file", "persistent": False}, 503
    try:
        with psycopg.connect(database_url) as connection:
            connection.execute("SELECT 1")
        return {"storage": "postgresql", "persistent": True}
    except psycopg.Error as error:
        app.logger.exception("Database health check failed")
        return {"storage": "postgresql", "persistent": False, "error": str(error)}, 503


@app.post("/upload")
def upload():
    excel_file = request.files.get("excel_file")
    if not excel_file or not excel_file.filename:
        return "Vui lòng chọn file Excel.", 400
    suffix = Path(excel_file.filename).suffix.lower()
    if suffix not in {".xlsx", ".xls", ".csv"}:
        return "Chỉ hỗ trợ file .xlsx, .xls hoặc .csv.", 400
    upload_path = UPLOAD_DIR / f"customers{suffix}"
    excel_file.save(upload_path)
    invitation_image = request.files.get("invitation_image")
    if invitation_image and invitation_image.filename:
        image_suffix = Path(invitation_image.filename).suffix.lower()
        if image_suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            return "Ảnh thiệp phải là PNG, JPG hoặc WEBP.", 400
        for old_image in DATA_DIR.glob("invitation.*"):
            old_image.unlink()
        invitation_image.save(INVITATION_FILE.with_suffix(image_suffix))
    try:
        dataframe = read_customer_file(upload_path, suffix)
    except Exception as error:
        return f"Không đọc được file: {error}", 400
    if dataframe.empty:
        return "File không có dữ liệu khách hàng.", 400

    profiles = load_profiles()
    identities = {profile_identity(profile["fields"]): customer_id for customer_id, profile in profiles.items()}
    next_number = len(profiles) + 1
    for row_number, (_, row) in enumerate(dataframe.iterrows(), start=1):
        fields = {str(column).strip(): clean_value(value) for column, value in row.items()}
        name = next((value for key, value in fields.items() if "tên" in key.lower() or "name" in key.lower()), f"Khách hàng {row_number}")
        identity = profile_identity(fields)
        customer_id = identities.get(identity) if identity else None
        old_profile = profiles.get(customer_id) if customer_id else None
        if customer_id is None:
            customer_id = uuid.uuid4().hex[:12]
            next_number += 1
        offline_qr = bool(request.form.get("offline_qr"))
        if offline_qr:
            qr_content = make_offline_qr_content(fields, name)
        else:
            qr_content = f"{public_base_url()}{url_for('customer', customer_id=customer_id)}"
        qr_filename = old_profile["qr_filename"] if old_profile else f"{next_number - 1:03d}_{safe_filename(name)}_{customer_id}.png"
        profile = {
            "name": name,
            "fields": fields,
            "qr_filename": qr_filename,
            "checkin_at": old_profile.get("checkin_at") if old_profile else None,
        }
        if offline_qr:
            create_qr_image(qr_content, QR_DIR / qr_filename)
        profiles[customer_id] = profile
        if identity:
            identities[identity] = customer_id

    save_profiles(profiles)
    return redirect(url_for("index"))


@app.route("/dang-ky", methods=["GET", "POST"])
@app.route("/guest_registration", methods=["GET", "POST"])
def guest_registration():
    if request.method == "GET":
        profiles = load_profiles()
        fields = [
            field for field in (list(dict.fromkeys(field for profile in profiles.values() for field in profile["fields"])) or CUSTOMER_FIELDS)
            if field not in {"Mã KH", "Mã khách hàng"}
        ]
        return render_template("guest_registration.html", fields=fields)
    profiles = load_profiles()
    form_fields = [
        field for field in (list(dict.fromkeys(field for profile in profiles.values() for field in profile["fields"])) or CUSTOMER_FIELDS)
        if field not in {"Mã KH", "Mã khách hàng"}
    ]
    fields = {field: request.form.get(field, "").strip() for field in form_fields}
    if not fields["Họ tên"]:
        return render_template("guest_registration.html", fields=form_fields, error="Vui lòng nhập Họ tên."), 400
    fields["Mã KH"] = next_guest_code(profiles)
    customer_id = uuid.uuid4().hex[:12]
    name = fields["Họ tên"]
    qr_filename = f"guest_{safe_filename(name)}_{customer_id}.png"
    profile = {
        "name": name,
        "fields": fields,
        "qr_filename": qr_filename,
        "checkin_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    profiles[customer_id] = profile
    save_profiles(profiles)
    qr_content = f"{public_base_url()}{url_for('customer', customer_id=customer_id)}"
    create_qr_image(qr_content, QR_DIR / qr_filename)
    return redirect(url_for("customer", customer_id=customer_id))


@app.get("/qr-chung")
def common_qr():
    qr_content = f"{public_base_url()}{url_for('guest_registration')}"
    return send_file(
        qr_image_stream(qr_content),
        mimetype="image/png",
        as_attachment=True,
        download_name="qr-chung-dang-ky.png",
        max_age=0,
    )


@app.get("/customer/<customer_id>")
def customer(customer_id):
    profiles = load_profiles()
    profile = profiles.get(customer_id)
    if profile is None:
        abort(404)
    if not profile.get("checkin_at"):
        profile["checkin_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_profiles(profiles)
    invitation = next(iter(DATA_DIR.glob("invitation.*")), None)
    return render_template("customer.html", profile=profile, invitation_exists=invitation is not None)


@app.get("/invitation")
def invitation():
    image = next(iter(DATA_DIR.glob("invitation.*")), None)
    if image is None:
        abort(404)
    return send_from_directory(DATA_DIR, image.name)


@app.post("/customer/<customer_id>/checkin")
def checkin(customer_id):
    profiles = load_profiles()
    profile = profiles.get(customer_id)
    if profile is None:
        abort(404)
    if not profile.get("checkin_at"):
        profile["checkin_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_profiles(profiles)
    return redirect(url_for("customer", customer_id=customer_id))


@app.get("/export-checkin.csv")
def export_checkin():
    rows = []
    for profile in load_profiles().values():
        row = dict(profile["fields"])
        row["Thời gian check-in"] = profile.get("checkin_at") or "Chưa check-in"
        rows.append(row)
    output = StringIO()
    pd.DataFrame(rows).to_csv(output, index=False, encoding="utf-8-sig")
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=du-lieu-check-in.csv"
    return response


@app.get("/export-checkin.xlsx")
def export_checkin_xlsx():
    rows = []
    for profile in load_profiles().values():
        row = dict(profile["fields"])
        row["Thời gian check-in"] = profile.get("checkin_at") or "Chưa check-in"
        rows.append(row)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="Check-in")
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    response.headers["Content-Disposition"] = "attachment; filename=du-lieu-check-in.xlsx"
    return response


@app.get("/qr/<path:filename>")
def qr_image(filename):
    qr_path = QR_DIR / filename
    if not qr_path.exists():
        profiles = load_profiles()
        profile = next((item for item in profiles.values() if item["qr_filename"] == filename), None)
        if profile is None:
            abort(404)
        customer_id = next(key for key, item in profiles.items() if item is profile)
        qr_content = f"{public_base_url()}{url_for('customer', customer_id=customer_id)}"
        create_qr_image(qr_content, qr_path)
    return send_from_directory(QR_DIR, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
