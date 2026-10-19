import sqlite3


DB_PATH = "database.db"


def add_repair_evidence_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

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

    print("Repair evidence table created successfully.")


if __name__ == "__main__":
    add_repair_evidence_table()