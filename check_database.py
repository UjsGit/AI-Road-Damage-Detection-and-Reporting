import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(reports)")

columns = cursor.fetchall()

print("Reports table columns:")

for column in columns:
    print(f"- {column[1]} ({column[2]})")

conn.close()