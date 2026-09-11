import sqlite3


DB_PATH = "database.db"


conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()


# Insert one test municipal report
cursor.execute("""
    INSERT INTO reports (
        image_path,
        latitude,
        longitude,
        overall_severity_score,
        overall_severity_level,
        pothole_count,
        status,
        notes
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (
    "test_images/road3.jpg",
    None,
    None,
    0.782,
    "HIGH",
    1,
    "Open",
    "Test report"
))


report_id = cursor.lastrowid


# Insert the corresponding YOLO detection
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
    "Pothole",
    0.202,
    0.782,
    "HIGH",
    7.1,
    165.0,
    466.3,
    375.4
))


conn.commit()


print("Test report inserted.")
print("Report ID:", report_id)


conn.close()