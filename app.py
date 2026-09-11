from flask import Flask, request, jsonify, render_template
from pathlib import Path
from ultralytics import YOLO
from PIL import Image
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


# --------------------------------------------------
# Municipal Dashboard
# --------------------------------------------------

@app.route("/municipal")
def municipal_dashboard():
    return render_template("municipal.html")
# --------------------------------------------------
# Run Flask
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)