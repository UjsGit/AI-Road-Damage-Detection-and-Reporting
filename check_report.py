import sqlite3

conn = sqlite3.connect("database.db")
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
        d.damage_type,
        d.confidence,
        d.severity_score,
        d.severity_level
    FROM reports r
    JOIN detections d
        ON r.id = d.report_id
    ORDER BY r.id DESC
    LIMIT 1
""")

row = cursor.fetchone()

if row:
    print("Report found:")
    print("Report ID:", row[0])
    print("Image:", row[1])
    print("Latitude:", row[2])
    print("Longitude:", row[3])
    print("Location:", row[4])
    print("Overall severity:", row[5], row[6])
    print("Pothole count:", row[7])
    print("Status:", row[8])
    print("Detection type:", row[9])
    print("Confidence:", row[10])
    print("Detection severity:", row[11], row[12])
else:
    print("Report not found.")

conn.close()