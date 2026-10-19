import sqlite3


DB_PATH = "database.db"


def get_db_connection(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def create_database(db_path=DB_PATH):

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Main municipal reports
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            location TEXT,
            overall_severity_score REAL,
            overall_severity_level TEXT,
            pothole_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Open',
            reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    """)

    # Ensure location column exists if table was created with an older schema
    cursor.execute("PRAGMA table_info(reports)")
    existing_columns = [column[1] for column in cursor.fetchall()]
    if "location" not in existing_columns:
        cursor.execute("ALTER TABLE reports ADD COLUMN location TEXT")

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

    # Repair evidence for municipal reports
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS repair_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL UNIQUE,
            after_image_path TEXT,
            repair_notes TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (report_id) REFERENCES reports(id)
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_database()
    print("Database created/verified successfully.")