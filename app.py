import json
import os
import re
import uuid
from pathlib import Path

import pandas as pd
import qrcode
from qrcode.constants import ERROR_CORRECT_L
from flask import Flask, abort, redirect, render_template, request, send_from_directory, url_for

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
QR_DIR = DATA_DIR / "qr"
UPLOAD_DIR = DATA_DIR / "uploads"
PROFILES_FILE = DATA_DIR / "profiles.json"
for folder in (QR_DIR, UPLOAD_DIR):
    folder.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def load_profiles():
    if not PROFILES_FILE.exists():
        return {}
    return json.loads(PROFILES_FILE.read_text(encoding="utf-8"))


def clean_value(value):
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def safe_filename(value):
    return re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._") or "customer"


def vcard_value(value):
    return str(value).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def make_offline_qr_content(fields, name):
    return json.dumps(
        {"THÔNG TIN KHÁCH HÀNG": {field: value or "Chưa cập nhật" for field, value in fields.items()}},
        ensure_ascii=False,
        indent=2,
    )


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
    return os.getenv("PUBLIC_BASE_URL", request.host_url).rstrip("/")


@app.get("/")
def index():
    return render_template("index.html", profiles=load_profiles())


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
    try:
        dataframe = read_customer_file(upload_path, suffix)
    except Exception as error:
        return f"Không đọc được file: {error}", 400
    if dataframe.empty:
        return "File không có dữ liệu khách hàng.", 400

    for old_qr in QR_DIR.glob("*.png"):
        old_qr.unlink()

    profiles = {}
    for row_number, (_, row) in enumerate(dataframe.iterrows(), start=1):
        customer_id = uuid.uuid4().hex[:12]
        fields = {str(column).strip(): clean_value(value) for column, value in row.items()}
        name = next((value for key, value in fields.items() if "tên" in key.lower() or "name" in key.lower()), f"Khách hàng {row_number}")
        if request.form.get("offline_qr"):
            qr_content = make_offline_qr_content(fields, name)
        else:
            qr_content = f"{public_base_url()}{url_for('customer', customer_id=customer_id)}"
        qr_filename = f"{row_number:03d}_{safe_filename(name)}_{customer_id}.png"
        qr = qrcode.QRCode(
            version=None,
            error_correction=ERROR_CORRECT_L,
            box_size=16,
            border=4,
        )
        qr.add_data(qr_content)
        qr.make(fit=True)
        qr.make_image().save(QR_DIR / qr_filename)
        profiles[customer_id] = {"name": name, "fields": fields, "qr_filename": qr_filename}

    PROFILES_FILE.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
    return redirect(url_for("index"))


@app.get("/customer/<customer_id>")
def customer(customer_id):
    profile = load_profiles().get(customer_id)
    if profile is None:
        abort(404)
    return render_template("customer.html", profile=profile)


@app.get("/qr/<path:filename>")
def qr_image(filename):
    return send_from_directory(QR_DIR, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
