import sqlite3


DB_PATH = "database.db"


def create_database():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Main municipal reports
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            overall_severity_score REAL,
            overall_severity_level TEXT,
            pothole_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Open',
            reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)

    # Individual YOLO detections belonging to a report
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            damage_type TEXT NOT NULL,
            confidence REAL NOT NULL,
            severity_score REAL NOT NULL,
            severity_level TEXT NOT NULL,
            x1 REAL,
            y1 REAL,
            x2 REAL,
            y2 REAL,
            FOREIGN KEY (report_id) REFERENCES reports(id)
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_database()
    print("Database created successfully.")