from flask import Flask, request, jsonify, render_template
from pathlib import Path
from ultralytics import YOLO
from PIL import Image
from werkzeug.utils import secure_filename

from flask import send_from_directory

import sqlite3
import requests

from severity import calculate_severity


app = Flask(__name__)


# --------------------------------------------------
# Configuration
# --------------------------------------------------

MODEL_PATH = r"models\India_only_best.pt"
DB_PATH = "database.db"
UPLOAD_FOLDER = Path("uploads")

REPAIR_FOLDER = UPLOAD_FOLDER / "repair"
REPAIR_FOLDER.mkdir(parents=True, exist_ok=True)

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
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            return None

        data = response.json()

        return data.get("display_name")

    except requests.RequestException:
        return None

# --------------------------------------------------
# Load model
# --------------------------------------------------

model = YOLO(MODEL_PATH)


# --------------------------------------------------
# Home
# --------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# --------------------------------------------------
# Prediction
# --------------------------------------------------

@app.route("/predict", methods=["POST"])
def predict():

    # Check uploaded image
    if "image" not in request.files:
        return jsonify({
            "error": "No image provided"
        }), 400

    image = request.files["image"]

    if image.filename == "":
        return jsonify({
            "error": "No image selected"
        }), 400


    # Get location information
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")
    location = request.form.get("location")

    if latitude and longitude and not location:
        location = reverse_geocode(latitude, longitude)
    #print("REVERSE GEOCODED LOCATION:", location)    


    # --------------------------------------------------
    # Save uploaded image
    # --------------------------------------------------

    UPLOAD_FOLDER.mkdir(exist_ok=True)

    image_path = UPLOAD_FOLDER / image.filename
    image.save(image_path)


    # --------------------------------------------------
    # Get image dimensions
    # --------------------------------------------------

    image_obj = Image.open(image_path)

    image_width, image_height = image_obj.size
    image_area = image_width * image_height


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
    # Save report to database
    # --------------------------------------------------

    conn = sqlite3.connect(DB_PATH)
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
        status
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (
    str(image_path),
    latitude,
    longitude,
    location,
    overall_score,
    overall_level,
    len(detections),
    "Open"
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

@app.route("/reports")
def get_reports():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

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
            reported_at
        FROM reports
        WHERE latitude IS NOT NULL
          AND longitude IS NOT NULL
        ORDER BY reported_at DESC
    """)

    reports = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify(reports)

@app.route("/reports/<int:report_id>/status", methods=["PUT"])
def update_report_status(report_id):
    data = request.get_json()

    new_status = data.get("status")

    allowed_statuses = ["Open", "In Progress", "Resolved"]

    if new_status not in allowed_statuses:
        return jsonify({
            "error": "Invalid status"
        }), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE reports SET status = ? WHERE id = ?",
        (new_status, report_id)
    )

    if cursor.rowcount == 0:
        conn.close()
        return jsonify({
            "error": "Report not found"
        }), 404

    conn.commit()
    conn.close()

    return jsonify({
        "message": "Report status updated successfully",
        "report_id": report_id,
        "status": new_status
    })

@app.route("/reports/<int:report_id>/repair-evidence", methods=["POST"])
def upload_repair_evidence(report_id):
    conn = sqlite3.connect(DB_PATH)
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

        # Keep the original file extension, but use a unique name.
        import uuid
        extension = Path(filename).suffix.lower()

        if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
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
def get_repair_evidence(report_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM reports WHERE id = ?",
            (report_id,)
        )

        if cursor.fetchone() is None:
            return jsonify({"error": "Report not found"}), 404

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
# Municipal Dashboard
# --------------------------------------------------

@app.route("/uploads/repair/<path:filename>")
def serve_repair_image(filename):
    return send_from_directory(REPAIR_FOLDER, filename)

@app.route("/uploads/<path:filename>")
def serve_uploaded_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/municipal")
def municipal_dashboard():
    return render_template("municipal.html")
# --------------------------------------------------
# Run Flask
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)