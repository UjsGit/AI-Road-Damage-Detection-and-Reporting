import sqlite3

DB_PATH = "database.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check existing columns
cursor.execute("PRAGMA table_info(reports)")
existing_columns = [column[1] for column in cursor.fetchall()]

# Add latitude
if "latitude" not in existing_columns:
    cursor.execute("""
        ALTER TABLE reports
        ADD COLUMN latitude REAL
    """)

# Add longitude
if "longitude" not in existing_columns:
    cursor.execute("""
        ALTER TABLE reports
        ADD COLUMN longitude REAL
    """)

# Add readable location
if "location" not in existing_columns:
    cursor.execute("""
        ALTER TABLE reports
        ADD COLUMN location TEXT
    """)

conn.commit()
conn.close()

print("✅ Location fields added successfully.")