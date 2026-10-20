"""
Administrative CLI script to create an initial municipal officer account.
Usage:
    python create_officer.py --email officer@city.gov --name "Officer Sharma" --password "SecurePass123!"
Or run interactively:
    python create_officer.py
"""

import sys
import re
import argparse
import getpass
import sqlite3
from werkzeug.security import generate_password_hash
from database import DB_PATH, create_database

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")

def validate_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email.strip()))

def validate_password(password: str) -> bool:
    return len(password) >= 8

def create_officer(email: str, name: str, password: str, db_path: str = DB_PATH) -> bool:
    email = email.strip().lower()
    name = name.strip()

    if not validate_email(email):
        print(f"[ERROR] Invalid email format: '{email}'", file=sys.stderr)
        return False

    if not name:
        print("[ERROR] Name cannot be empty.", file=sys.stderr)
        return False

    if not validate_password(password):
        print("[ERROR] Password must be at least 8 characters long.", file=sys.stderr)
        return False

    create_database(db_path)

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, role FROM users WHERE lower(email) = ?", (email,))
        existing = cursor.fetchone()

        if existing:
            print(f"[INFO] User with email '{email}' already exists (ID: {existing[0]}, Role: {existing[1]}).", file=sys.stderr)
            print("[INFO] No duplicate account created.", file=sys.stderr)
            return False

        pw_hash = generate_password_hash(password)
        cursor.execute("""
            INSERT INTO users (email, password_hash, name, role)
            VALUES (?, ?, ?, 'officer')
        """, (email, pw_hash, name))
        conn.commit()
        print(f"[SUCCESS] Municipal officer account created for '{email}' (Name: '{name}').")
        return True
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="Create a municipal officer account.")
    parser.add_argument("--email", help="Officer email address")
    parser.add_argument("--name", help="Officer full name")
    parser.add_argument("--password", help="Officer password (at least 8 characters)")
    parser.add_argument("--db", default=DB_PATH, help=f"Path to SQLite database (default: {DB_PATH})")

    args = parser.parse_args()

    email = args.email
    name = args.name
    password = args.password

    if not email:
        try:
            email = input("Enter officer email: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(1)

    if not name:
        try:
            name = input("Enter officer display name: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(1)

    if not password:
        try:
            password = getpass.getpass("Enter officer password (min 8 chars): ")
            confirm = getpass.getpass("Confirm officer password: ")
            if password != confirm:
                print("[ERROR] Passwords do not match.", file=sys.stderr)
                sys.exit(1)
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(1)

    success = create_officer(email, name, password, args.db)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
