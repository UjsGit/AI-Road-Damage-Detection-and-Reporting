import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute("DELETE FROM detections")
cursor.execute("DELETE FROM reports")

conn.commit()
conn.close()

print("Test database records deleted.")