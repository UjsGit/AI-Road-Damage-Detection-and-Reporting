import os
import secrets
import re
import uuid
import sqlite3
import requests
from pathlib import Path
from functools import wraps
from urllib.parse import urlparse, urljoin
from PIL import Image
from flask import (
    Flask, request, jsonify, render_template,
    session, redirect, url_for, g, send_from_directory, abort
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from ultralytics import YOLO

from severity import calculate_severity


def load_env_file():
    """Load configuration from .env into os.environ if not already present."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return
    except ImportError:
        pass

    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and (
                (value.startswith('"') and value.endswith('"')) or
                (value.startswith("'") and value.endswith("'"))
            ):
                value = value[1:-1]
            os.environ.setdefault(key, value)


load_env_file()

flask_env = os.environ.get("FLASK_ENV", "development").lower()
secret_key = os.environ.get("FLASK_SECRET_KEY")

INSECURE_DEV_SECRETS = {
    "dev-secret-key-change-in-production-roadsafety2026",
    "dev_secret_key_change_in_production_pothole_2026",
    "dev_secret_key_change_in_production",
    "secret",
    "changeme"
}

if flask_env == "production":
    if not secret_key or secret_key in INSECURE_DEV_SECRETS:
        raise RuntimeError(
            "CRITICAL SECURITY ERROR: FLASK_SECRET_KEY must be set to a secure, "
            "non-default secret in production (FLASK_ENV=production). Refusing to start."
        )
else:
    if not secret_key:
        secret_key = "dev-insecure-secret-key-local-development-only"

app = Flask(__name__)
app.secret_key = secret_key
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


# --------------------------------------------------
# Configuration
# --------------------------------------------------

MODEL_PATH = r"models\India_only_best.pt"
DB_PATH = "database.db"
UPLOAD_FOLDER = Path("uploads")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

REPAIR_FOLDER = UPLOAD_FOLDER / "repair"
REPAIR_FOLDER.mkdir(parents=True, exist_ok=True)

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")


def get_db():
    db_path = app.config.get("DATABASE", DB_PATH)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def reverse_geocode(latitude, longitude):
    if latitude is None or longitude is None:
        return None

    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": latitude,
        "lon": longitude,
        "format": "jsonv2",
        "addressdetails": 1,
        "zoom": 18
    }
    headers = {
        "User-Agent": "PotholeDetectionProject/1.0"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
        data = response.json()
        return data.get("display_name")
    except requests.RequestException:
        return None


# --------------------------------------------------
# Current User & CSRF Protection
# --------------------------------------------------

def get_current_user():
    if hasattr(g, "current_user"):
        return g.current_user

    user_id = session.get("user_id")
    if not user_id:
        g.current_user = None
        return None

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, name, role FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            g.current_user = {
                "id": row["id"],
                "email": row["email"],
                "name": row["name"],
                "role": row["role"]
            }
        else:
            session.pop("user_id", None)
            g.current_user = None
        return g.current_user
    finally:
        conn.close()


def generate_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


@app.context_processor
def inject_template_globals():
    return {
        "csrf_token": generate_csrf_token,
        "current_user": get_current_user()
    }


def is_safe_url(target):
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


@app.before_request
def csrf_protect():
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # Allow testing bypass if explicitly configured
        if app.config.get("TESTING") and app.config.get("WTF_CSRF_ENABLED") is False:
            return

        session_token = session.get("_csrf_token")
        request_token = (
            request.headers.get("X-CSRF-Token")
            or request.form.get("csrf_token")
        )
        if not request_token and request.is_json:
            json_data = request.get_json(silent=True)
            if isinstance(json_data, dict):
                request_token = json_data.get("csrf_token")

        if not session_token or not request_token or not secrets.compare_digest(session_token, request_token):
            if request.is_json or request.path.startswith(("/predict", "/reports")):
                return jsonify({"error": "CSRF verification failed"}), 403
            return render_template("login.html", error="Security session expired. Please try again."), 403


# --------------------------------------------------
# Role-Based Access Control Decorators
# --------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.is_json or request.path.startswith(("/predict", "/reports")):
                return jsonify({"error": "Authentication required"}), 401
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("login", next=next_url))
        return f(*args, **kwargs)
    return decorated_function


def officer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.is_json or request.path.startswith(("/reports", "/predict")):
                return jsonify({"error": "Authentication required"}), 401
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("login", next=next_url))
        if user["role"] != "officer":
            if request.is_json or request.path.startswith(("/reports", "/predict")):
                return jsonify({"error": "Forbidden: Municipal officer access required"}), 403
            return render_template("login.html", error="Access denied. Officer privileges required.", next_url=request.path), 403
        return f(*args, **kwargs)
    return decorated_function


# --------------------------------------------------
# Load model
# --------------------------------------------------

model = YOLO(MODEL_PATH)


# --------------------------------------------------
# Authentication Routes
# --------------------------------------------------

@app.route("/register", methods=["GET"])
def register():
    if get_current_user():
        return redirect(url_for("my_reports"))
    return render_template("register.html")


@app.route("/register", methods=["POST"])
def handle_register():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name:
        return render_template("register.html", error="Name is required.", name=name, email=email), 400
    if not email or not EMAIL_REGEX.match(email):
        return render_template("register.html", error="Please enter a valid email address.", name=name, email=email), 400
    if len(password) < 8:
        return render_template("register.html", error="Password must be at least 8 characters long.", name=name, email=email), 400
    if password != confirm_password:
        return render_template("register.html", error="Passwords do not match.", name=name, email=email), 400

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE lower(email) = ?", (email,))
        if cursor.fetchone():
            return render_template("register.html", error="An account with this email already exists.", name=name, email=email), 400

        # Public registration strictly creates citizen accounts
        pw_hash = generate_password_hash(password)
        cursor.execute("""
            INSERT INTO users (email, password_hash, name, role)
            VALUES (?, ?, ?, 'citizen')
        """, (email, pw_hash, name))
        conn.commit()
        user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        return render_template("register.html", error="An account with this email already exists.", name=name, email=email), 400
    finally:
        conn.close()

    # Session fixation prevention: reset session and log in
    session.clear()
    session["user_id"] = user_id
    generate_csrf_token()
    return redirect(url_for("my_reports"))


@app.route("/login", methods=["GET"])
def login():
    if get_current_user():
        if g.current_user["role"] == "officer":
            return redirect(url_for("municipal_dashboard"))
        return redirect(url_for("my_reports"))
    next_url = request.args.get("next", "")
    return render_template("login.html", next_url=next_url)


@app.route("/login", methods=["POST"])
def handle_login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    next_url = request.form.get("next", "").strip()

    if not email or not password:
        return render_template("login.html", error="Email and password are required.", email=email, next_url=next_url), 400

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, password_hash, name, role FROM users WHERE lower(email) = ?", (email,))
        user = cursor.fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Invalid email or password.", email=email, next_url=next_url), 401

        # Prevent session fixation
        session.clear()
        session["user_id"] = user["id"]
        generate_csrf_token()

        if next_url and is_safe_url(next_url):
            return redirect(next_url)

        if user["role"] == "officer":
            return redirect(url_for("municipal_dashboard"))
        return redirect(url_for("my_reports"))
    finally:
        conn.close()


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("login", message="You have been signed out."))


# --------------------------------------------------
# Home & Citizen Report History
# --------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/my-reports")
@login_required
def my_reports():
    user = get_current_user()
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                r.id,
                r.image_path,
                r.latitude,
                r.longitude,
                r.location,
                r.overall_severity_score,
                r.overall_severity_level,
                r.pothole_count,
                r.status,
                r.reported_at,
                e.after_image_path,
                e.repair_notes
            FROM reports r
            LEFT JOIN repair_evidence e ON r.id = e.report_id
            WHERE r.user_id = ?
            ORDER BY r.reported_at DESC
        """, (user["id"],))

        rows = cursor.fetchall()
        reports = []
        for row in rows:
            rep = dict(row)
            rep["image_filename"] = Path(rep["image_path"]).name if rep.get("image_path") else None
            rep["after_filename"] = Path(rep["after_image_path"]).name if rep.get("after_image_path") else None
            reports.append(rep)

        return render_template("my_reports.html", reports=reports)
    finally:
        conn.close()


@app.route("/reports/public-markers")
def get_public_markers():
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                id,
                latitude,
                longitude,
                overall_severity_level,
                overall_severity_score,
                status
            FROM reports
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY reported_at DESC
        """)
        markers = [dict(row) for row in cursor.fetchall()]
        return jsonify(markers)
    finally:
        conn.close()


# --------------------------------------------------
# Prediction
# --------------------------------------------------

@app.route("/predict", methods=["POST"])
@login_required
def predict():
    # Check uploaded image
    if "image" not in request.files:
        return jsonify({
            "error": "No image provided"
        }), 400

    image = request.files["image"]

    if not image or image.filename == "":
        return jsonify({
            "error": "No image selected"
        }), 400

    clean_filename = secure_filename(image.filename)
    if not clean_filename:
        return jsonify({
            "error": "Invalid filename"
        }), 400

    extension = Path(clean_filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": "Invalid file type. Allowed formats: JPG, JPEG, PNG, WEBP"
        }), 400

    # Get location information
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")
    location = request.form.get("location")

    if latitude and longitude and not location:
        location = reverse_geocode(latitude, longitude)

    # --------------------------------------------------
    # Save uploaded image
    # --------------------------------------------------

    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    saved_name = f"upload_{uuid.uuid4().hex}{extension}"
    image_path = UPLOAD_FOLDER / saved_name
    image.save(str(image_path))

    # --------------------------------------------------
    # Get image dimensions
    # --------------------------------------------------

    try:
        image_obj = Image.open(image_path)
        image_width, image_height = image_obj.size
        image_area = image_width * image_height
    except Exception:
        if image_path.exists():
            image_path.unlink()
        return jsonify({
            "error": "Uploaded file is not a valid image"
        }), 400

    # --------------------------------------------------
    # Run YOLO
    # --------------------------------------------------

    results = model.predict(
        source=str(image_path),
        conf=0.10,
        classes=[3],
        verbose=False
    )

    # --------------------------------------------------
    # Process detections
    # --------------------------------------------------

    detections = []

    for box in results[0].boxes:
        confidence = float(box.conf[0])
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        box_area = (x2 - x1) * (y2 - y1)

        # Calculate severity
        severity_score, severity_level = calculate_severity(
            class_id=3,
            confidence=confidence,
            box_area=box_area,
            image_area=image_area
        )

        detections.append({
            "damage_type": "Pothole",
            "confidence": round(confidence, 3),
            "box": [
                round(x1, 1),
                round(y1, 1),
                round(x2, 1),
                round(y2, 1)
            ],
            "severity_score": severity_score,
            "severity_level": severity_level
        })

    # --------------------------------------------------
    # No pothole detected
    # --------------------------------------------------

    if not detections:
        return jsonify({
            "potholes_detected": 0,
            "message": "No pothole detected"
        })

    # --------------------------------------------------
    # Determine overall severity
    # --------------------------------------------------

    primary = max(
        detections,
        key=lambda detection: detection["severity_score"]
    )

    overall_score = primary["severity_score"]
    overall_level = primary["severity_level"]

    # --------------------------------------------------
    # Save report to database linked to current citizen
    # --------------------------------------------------

    user = get_current_user()
    user_id = user["id"] if user else None

    conn = get_db()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO reports (
                image_path,
                latitude,
                longitude,
                location,
                overall_severity_score,
                overall_severity_level,
                pothole_count,
                status,
                user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(image_path),
            latitude,
            longitude,
            location,
            overall_score,
            overall_level,
            len(detections),
            "Open",
            user_id
        ))

        report_id = cursor.lastrowid

        # --------------------------------------------------
        # Save individual detections
        # --------------------------------------------------

        for detection, box in zip(detections, results[0].boxes):
            x1, y1, x2, y2 = box.xyxy[0].tolist()

            cursor.execute("""
                INSERT INTO detections (
                    report_id,
                    damage_type,
                    confidence,
                    severity_score,
                    severity_level,
                    x1,
                    y1,
                    x2,
                    y2
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                report_id,
                detection["damage_type"],
                detection["confidence"],
                detection["severity_score"],
                detection["severity_level"],
                x1,
                y1,
                x2,
                y2
            ))

        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception("Failed to save report to database")
        return jsonify({
            "error": "Failed to save report to database"
        }), 500
    finally:
        conn.close()

    # --------------------------------------------------
    # Return result
    # --------------------------------------------------

    return jsonify({
        "report_id": report_id,
        "potholes_detected": len(detections),
        "overall_severity_score": overall_score,
        "overall_severity_level": overall_level,
        "latitude": latitude,
        "longitude": longitude,
        "location": location,
        "detections": detections
    })


# --------------------------------------------------
# Report Inspection & Municipal Endpoints
# --------------------------------------------------

@app.route("/reports")
@officer_required
def get_reports():
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                id,
                image_path,
                latitude,
                longitude,
                location,
                overall_severity_score,
                overall_severity_level,
                pothole_count,
                status,
                reported_at,
                user_id
            FROM reports
            ORDER BY reported_at DESC
        """)

        reports = [dict(row) for row in cursor.fetchall()]
        return jsonify(reports)
    finally:
        conn.close()


@app.route("/reports/<int:report_id>", methods=["GET"])
@login_required
def get_single_report(report_id):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                id, image_path, latitude, longitude, location,
                overall_severity_score, overall_severity_level,
                pothole_count, status, reported_at, notes, user_id
            FROM reports
            WHERE id = ?
        """, (report_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Report not found"}), 404

        user = get_current_user()
        if user["role"] != "officer" and row["user_id"] != user["id"]:
            return jsonify({"error": "Forbidden: You do not have permission to view this report"}), 403

        cursor.execute("""
            SELECT damage_type, confidence, severity_score, severity_level, x1, y1, x2, y2
            FROM detections WHERE report_id = ?
        """, (report_id,))
        detections = [dict(d) for d in cursor.fetchall()]

        rep = dict(row)
        rep["detections"] = detections
        return jsonify(rep)
    finally:
        conn.close()


@app.route("/reports/<int:report_id>/status", methods=["PUT"])
@officer_required
def update_report_status(report_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({
            "error": "Invalid request body"
        }), 400

    new_status = data.get("status")
    allowed_statuses = ["Open", "In Progress", "Resolved"]

    if new_status not in allowed_statuses:
        return jsonify({
            "error": "Invalid status"
        }), 400

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reports SET status = ? WHERE id = ?",
            (new_status, report_id)
        )

        if cursor.rowcount == 0:
            return jsonify({
                "error": "Report not found"
            }), 404

        conn.commit()

        return jsonify({
            "message": "Report status updated successfully",
            "report_id": report_id,
            "status": new_status
        })
    except Exception:
        conn.rollback()
        app.logger.exception("Failed to update status")
        return jsonify({
            "error": "Failed to update report status"
        }), 500
    finally:
        conn.close()


@app.route("/reports/<int:report_id>/repair-evidence", methods=["POST"])
@officer_required
def upload_repair_evidence(report_id):
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT id FROM reports WHERE id = ?",
            (report_id,)
        )

        if cursor.fetchone() is None:
            return jsonify({"error": "Report not found"}), 404

        after_image = request.files.get("after_image")

        if after_image is None or after_image.filename == "":
            return jsonify({
                "error": "After-repair image is required"
            }), 400

        repair_notes = request.form.get("repair_notes", "").strip()
        filename = secure_filename(after_image.filename)

        if not filename:
            return jsonify({"error": "Invalid filename"}), 400

        # Keep original extension with a unique name
        extension = Path(filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            return jsonify({
                "error": "Use a JPG, JPEG, PNG, or WEBP image"
            }), 400

        REPAIR_FOLDER.mkdir(parents=True, exist_ok=True)
        saved_name = f"report_{report_id}_{uuid.uuid4().hex}{extension}"
        image_path = REPAIR_FOLDER / saved_name

        after_image.save(str(image_path))

        cursor.execute("""
            INSERT INTO repair_evidence (
                report_id, after_image_path, repair_notes
            )
            VALUES (?, ?, ?)
            ON CONFLICT(report_id) DO UPDATE SET
                after_image_path = excluded.after_image_path,
                repair_notes = excluded.repair_notes,
                updated_at = CURRENT_TIMESTAMP
        """, (report_id, str(image_path), repair_notes))

        conn.commit()

        return jsonify({
            "message": "Repair evidence uploaded successfully",
            "report_id": report_id,
            "after_image_path": str(image_path),
            "repair_notes": repair_notes
        }), 201

    except Exception:
        conn.rollback()
        app.logger.exception("Repair evidence upload failed")
        return jsonify({
            "error": "Could not save repair evidence"
        }), 500

    finally:
        conn.close()


@app.route("/reports/<int:report_id>/repair-evidence", methods=["GET"])
@login_required
def get_repair_evidence(report_id):
    conn = get_db()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, user_id FROM reports WHERE id = ?",
            (report_id,)
        )
        report = cursor.fetchone()

        if report is None:
            return jsonify({"error": "Report not found"}), 404

        # Server-side ownership enforcement
        user = get_current_user()
        if user["role"] != "officer" and report["user_id"] != user["id"]:
            return jsonify({"error": "Forbidden: You do not have permission to view this evidence"}), 403

        cursor.execute("""
            SELECT after_image_path, repair_notes, updated_at
            FROM repair_evidence
            WHERE report_id = ?
        """, (report_id,))

        evidence = cursor.fetchone()

        if evidence is None:
            return jsonify({
                "report_id": report_id,
                "after_image_path": None,
                "repair_notes": "",
                "updated_at": None
            })

        return jsonify({
            "report_id": report_id,
            "after_image_path": evidence["after_image_path"],
            "repair_notes": evidence["repair_notes"] or "",
            "updated_at": evidence["updated_at"]
        })

    finally:
        conn.close()


# --------------------------------------------------
# Static Assets & Municipal Page
# --------------------------------------------------

@app.route("/uploads/repair/<path:filename>")
def serve_repair_image(filename):
    return send_from_directory(REPAIR_FOLDER, filename)


@app.route("/uploads/<path:filename>")
def serve_uploaded_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/municipal")
@officer_required
def municipal_dashboard():
    return render_template("municipal.html")


# --------------------------------------------------
# Run Flask
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)