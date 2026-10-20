import os
import sys
import shutil
import sqlite3
import io
from pathlib import Path
from PIL import Image

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

print(f"[TEST ENV] Python executable: {sys.executable}")
print(f"[TEST ENV] Python version: {sys.version}")

import app as app_module
from database import create_database, DB_PATH as PROD_DB_PATH
from create_officer import create_officer
from werkzeug.security import check_password_hash

TEST_DB = "temp_phase2_test.db"
TEST_UPLOAD_DIR = Path("temp_uploads_test_phase2")


def setup_test_env():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if TEST_UPLOAD_DIR.exists():
        shutil.rmtree(TEST_UPLOAD_DIR)
    TEST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    create_database(TEST_DB)
    app_module.app.config["DATABASE"] = TEST_DB
    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = True
    app_module.UPLOAD_FOLDER = TEST_UPLOAD_DIR
    app_module.REPAIR_FOLDER = TEST_UPLOAD_DIR / "repair"
    app_module.REPAIR_FOLDER.mkdir(parents=True, exist_ok=True)


def cleanup_test_env():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if TEST_UPLOAD_DIR.exists():
        shutil.rmtree(TEST_UPLOAD_DIR)


def create_dummy_image_bytes():
    buf = io.BytesIO()
    img = Image.new("RGB", (320, 240), color=(128, 128, 128))
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf


def run_all_tests():
    print("=" * 70)
    print("STARTING PHASE 2 AUTHENTICATION & ACCESS CONTROL VERIFICATION TESTS")
    print("=" * 70)

    # 0. Snapshot production DB counts
    prod_conn = sqlite3.connect(PROD_DB_PATH)
    pc = prod_conn.cursor()
    pc.execute("SELECT count(*) FROM reports")
    prod_reports_before = pc.fetchone()[0]
    pc.execute("SELECT count(*) FROM detections")
    prod_detections_before = pc.fetchone()[0]
    pc.execute("SELECT count(*) FROM repair_evidence")
    prod_evidence_before = pc.fetchone()[0]
    prod_conn.close()
    print(f"[PROD CHECK] Production baseline: {prod_reports_before} reports, {prod_detections_before} detections, {prod_evidence_before} repair evidence.")

    setup_test_env()
    client = app_module.app.test_client()

    try:
        # --------------------------------------------------
        # 1. Database Schema & Migration Idempotency
        # --------------------------------------------------
        print("\n--- Test 1: Database Schema & Migration Idempotency ---")
        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        tc.execute("PRAGMA table_info(users)")
        user_cols = {col[1]: col[2] for col in tc.fetchall()}
        assert "email" in user_cols, "users table missing email column"
        assert "password_hash" in user_cols, "users table missing password_hash column"
        assert "role" in user_cols, "users table missing role column"

        tc.execute("PRAGMA table_info(reports)")
        rep_cols = [col[1] for col in tc.fetchall()]
        assert "user_id" in rep_cols, "reports table missing user_id foreign key column"
        tconn.close()

        # Re-run migration to test idempotency
        create_database(TEST_DB)
        print("PASS: Schema contains users and reports.user_id; migration is idempotent.")

        # --------------------------------------------------
        # 2. CSRF Helper and Session Setup
        # --------------------------------------------------
        print("\n--- Test 2: CSRF Protection & Token Validation ---")
        # Direct POST without CSRF token must fail with 403
        res = client.post("/register", data={
            "name": "Attacker",
            "email": "attacker@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!"
        })
        assert res.status_code == 403, f"Expected 403 for missing CSRF on POST /register, got {res.status_code}"

        # Fetch token from GET /register
        res = client.get("/register")
        assert res.status_code == 200
        with client.session_transaction() as sess:
            token = sess.get("_csrf_token")
        assert token and len(token) == 64, "CSRF token not generated in session"

        # Tampered CSRF token must fail with 403
        res = client.post("/register", data={
            "name": "Attacker",
            "email": "attacker@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "csrf_token": "corrupted_token_value_12345"
        })
        assert res.status_code == 403, "Tampered CSRF token was not rejected"
        print("PASS: Missing and tampered CSRF tokens strictly rejected with HTTP 403.")

        # --------------------------------------------------
        # 3. Citizen Registration & Validation
        # --------------------------------------------------
        print("\n--- Test 3: Citizen Registration & Validation ---")
        # Password too short
        res = client.post("/register", data={
            "name": "Short Pass",
            "email": "short@example.com",
            "password": "123",
            "confirm_password": "123",
            "csrf_token": token
        })
        assert res.status_code == 400
        assert b"at least 8 characters" in res.data

        # Password mismatch
        res = client.post("/register", data={
            "name": "Mismatch Pass",
            "email": "mismatch@example.com",
            "password": "Password123!",
            "confirm_password": "DifferentPass123!",
            "csrf_token": token
        })
        assert res.status_code == 400
        assert b"do not match" in res.data

        # Invalid email
        res = client.post("/register", data={
            "name": "Invalid Email",
            "email": "not-an-email",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "csrf_token": token
        })
        assert res.status_code == 400
        assert b"valid email" in res.data

        # Successful registration of Citizen A
        res = client.post("/register", data={
            "name": "Citizen Ramesh",
            "email": "ramesh@example.com",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
            "csrf_token": token
        }, follow_redirects=True)
        assert res.status_code == 200
        assert b"My Reported Potholes" in res.data or b"My Reports" in res.data

        # Verify Citizen A in DB
        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        tc.execute("SELECT id, email, password_hash, role FROM users WHERE email = 'ramesh@example.com'")
        user_row = tc.fetchone()
        assert user_row is not None
        citizen_a_id = user_row[0]
        assert user_row[3] == "citizen", f"Expected citizen role, got {user_row[3]}"
        assert check_password_hash(user_row[2], "SecurePassword123!"), "Password hash verification failed"
        assert not user_row[2].startswith("SecurePassword"), "Password was stored in plaintext!"
        tconn.close()

        # Duplicate email registration rejected
        with client.session_transaction() as sess:
            token = sess.get("_csrf_token")
        res = client.post("/register", data={
            "name": "Ramesh Duplicate",
            "email": "ramesh@example.com",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
            "csrf_token": token
        })
        assert res.status_code == 400
        assert b"already exists" in res.data

        # Attempt role escalation via registration tampering (send role=officer)
        res = client.post("/register", data={
            "name": "Hacker Officer",
            "email": "hacker@example.com",
            "password": "HackerPassword123!",
            "confirm_password": "HackerPassword123!",
            "role": "officer",
            "csrf_token": token
        }, follow_redirects=True)
        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        tc.execute("SELECT role FROM users WHERE email = 'hacker@example.com'")
        hacker_role = tc.fetchone()[0]
        tconn.close()
        assert hacker_role == "citizen", f"Public registration permitted officer role escalation! Got {hacker_role}"
        print("PASS: Registration input validation, hashing, duplicate prevention, and citizen role locking verified.")

        # --------------------------------------------------
        # 4. Officer Creation via CLI Utility
        # --------------------------------------------------
        print("\n--- Test 4: Municipal Officer Provisioning via CLI Utility ---")
        officer_email = "officer.sharma@city.gov.in"
        created = create_officer(officer_email, "Officer Sharma", "MunicipalAdmin2026!", db_path=TEST_DB)
        assert created is True, "create_officer failed to provision officer"

        # Duplicate officer creation rejected
        duplicate_created = create_officer(officer_email, "Officer Sharma Duplicate", "MunicipalAdmin2026!", db_path=TEST_DB)
        assert duplicate_created is False, "create_officer allowed duplicate creation"

        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        tc.execute("SELECT id, role FROM users WHERE email = ?", (officer_email,))
        officer_row = tc.fetchone()
        assert officer_row is not None and officer_row[1] == "officer"
        officer_id = officer_row[0]
        tconn.close()
        print("PASS: Officer successfully created with role 'officer' and duplicate guard.")

        # --------------------------------------------------
        # 5. Authentication, Session Fixation & Logout
        # --------------------------------------------------
        print("\n--- Test 5: Authentication, Session Management & Safe Redirects ---")
        # Fresh client to test login
        auth_client = app_module.app.test_client()
        auth_client.get("/login")
        with auth_client.session_transaction() as sess:
            login_token = sess.get("_csrf_token")

        # Wrong password
        res = auth_client.post("/login", data={
            "email": "ramesh@example.com",
            "password": "WrongPassword!",
            "csrf_token": login_token
        })
        assert res.status_code == 401
        assert b"Invalid email or password" in res.data

        # Successful login
        with auth_client.session_transaction() as sess:
            sess["pre_login_marker"] = "should_be_cleared"
            login_token = sess.get("_csrf_token")

        res = auth_client.post("/login", data={
            "email": "ramesh@example.com",
            "password": "SecurePassword123!",
            "csrf_token": login_token
        }, follow_redirects=False)
        assert res.status_code == 302
        assert res.headers["Location"].endswith("/my-reports")

        with auth_client.session_transaction() as sess:
            assert sess.get("user_id") == citizen_a_id
            assert "pre_login_marker" not in sess, "Session fixation vulnerability: pre-login session was not cleared!"

        # Open redirect prevention test
        with auth_client.session_transaction() as sess:
            token = sess.get("_csrf_token")
        res = auth_client.post("/login", data={
            "email": "ramesh@example.com",
            "password": "SecurePassword123!",
            "next": "https://attacker-controlled-site.com/steal-creds",
            "csrf_token": token
        }, follow_redirects=False)
        assert not res.headers["Location"].startswith("https://attacker-controlled-site.com"), "Open redirect vulnerability detected!"

        # Logout test
        res = auth_client.get("/logout", follow_redirects=True)
        assert res.status_code == 200
        with auth_client.session_transaction() as sess:
            assert "user_id" not in sess
        print("PASS: Login rejection, session fixation reset, open redirect prevention, and logout verified.")

        # --------------------------------------------------
        # 6. Role-Based Access Control (RBAC) Enforcement
        # --------------------------------------------------
        print("\n--- Test 6: Role-Based Access Control (RBAC) Enforcement ---")
        anon_client = app_module.app.test_client()
        citizen_client = app_module.app.test_client()
        officer_client = app_module.app.test_client()

        # Log in citizen_client
        citizen_client.get("/login")
        with citizen_client.session_transaction() as sess:
            ctok = sess.get("_csrf_token")
        citizen_client.post("/login", data={
            "email": "ramesh@example.com",
            "password": "SecurePassword123!",
            "csrf_token": ctok
        })

        # Log in officer_client
        officer_client.get("/login")
        with officer_client.session_transaction() as sess:
            otok = sess.get("_csrf_token")
        officer_client.post("/login", data={
            "email": officer_email,
            "password": "MunicipalAdmin2026!",
            "csrf_token": otok
        })

        # Municipal Dashboard (/municipal):
        # Anonymous -> redirected to login
        res = anon_client.get("/municipal")
        assert res.status_code == 302 and "/login" in res.headers["Location"]
        # Citizen -> 403 Forbidden
        res = citizen_client.get("/municipal")
        assert res.status_code == 403
        # Officer -> 200 OK
        res = officer_client.get("/municipal")
        assert res.status_code == 200
        print("PASS: Municipal portal (/municipal) strictly restricted to officers.")

        # GET /reports (List all municipal reports):
        # Anonymous -> 401
        res = anon_client.get("/reports")
        assert res.status_code == 401
        # Citizen -> 403
        res = citizen_client.get("/reports")
        assert res.status_code == 403
        # Officer -> 200
        res = officer_client.get("/reports")
        assert res.status_code == 200
        print("PASS: Reports list (/reports) strictly restricted to officers.")

        # --------------------------------------------------
        # 7. Report Submission & Ownership Binding
        # --------------------------------------------------
        print("\n--- Test 7: Report Submission via /predict & Ownership Binding ---")
        # Create Citizen B
        client.get("/register")
        with client.session_transaction() as sess:
            btok = sess.get("_csrf_token")
        client.post("/register", data={
            "name": "Citizen Priya",
            "email": "priya@example.com",
            "password": "PriyaPassword123!",
            "confirm_password": "PriyaPassword123!",
            "csrf_token": btok
        })
        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        tc.execute("SELECT id FROM users WHERE email = 'priya@example.com'")
        citizen_b_id = tc.fetchone()[0]
        tconn.close()

        # Anonymous cannot /predict:
        # 1. Missing CSRF is blocked with 403
        img_buf = create_dummy_image_bytes()
        res = anon_client.post("/predict", data={"image": (img_buf, "test.jpg")})
        assert res.status_code == 403, f"Expected 403 for missing CSRF, got {res.status_code}"

        # 2. Even with valid session CSRF token, unauthenticated caller is rejected with 401
        anon_client.get("/")
        with anon_client.session_transaction() as sess:
            anon_token = sess.get("_csrf_token")
        img_buf_2 = create_dummy_image_bytes()
        res = anon_client.post("/predict", data={"image": (img_buf_2, "test.jpg")}, headers={"X-CSRF-Token": anon_token})
        assert res.status_code == 401, f"Anonymous predict with CSRF must return 401, got {res.status_code}"

        # Insert reports directly for Citizen A, Citizen B, and Legacy (user_id = NULL)
        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        # Report 1 for Citizen A
        tc.execute("""
            INSERT INTO reports (image_path, latitude, longitude, location, overall_severity_score, overall_severity_level, pothole_count, status, user_id)
            VALUES ('uploads/test_a.jpg', 13.0827, 80.2707, 'Anna Salai, Chennai', 7.5, 'HIGH', 2, 'Open', ?)
        """, (citizen_a_id,))
        rep_a_id = tc.lastrowid

        # Report 2 for Citizen B
        tc.execute("""
            INSERT INTO reports (image_path, latitude, longitude, location, overall_severity_score, overall_severity_level, pothole_count, status, user_id)
            VALUES ('uploads/test_b.jpg', 12.9716, 77.5946, 'MG Road, Bangalore', 4.2, 'MEDIUM', 1, 'In Progress', ?)
        """, (citizen_b_id,))
        rep_b_id = tc.lastrowid

        # Report 3 Legacy (user_id = NULL)
        tc.execute("""
            INSERT INTO reports (image_path, latitude, longitude, location, overall_severity_score, overall_severity_level, pothole_count, status, user_id)
            VALUES ('uploads/legacy.jpg', 28.6139, 77.2090, 'Connaught Place, Delhi', 8.9, 'HIGH', 3, 'Open', NULL)
        """,)
        rep_legacy_id = tc.lastrowid
        tconn.commit()
        tconn.close()

        # Citizen A checks /my-reports -> only sees rep_a_id
        res = citizen_client.get("/my-reports")
        assert res.status_code == 200
        assert "Anna Salai, Chennai" in res.text
        assert "MG Road, Bangalore" not in res.text, "Citizen A can see Citizen B's report in /my-reports!"
        assert "Connaught Place, Delhi" not in res.text, "Citizen A can see legacy report in /my-reports!"
        assert f">#{rep_a_id}</span>" in res.text
        assert f">#{rep_b_id}</span>" not in res.text

        # Direct single report access check GET /reports/<id>:
        # Citizen A can access their own report
        res = citizen_client.get(f"/reports/{rep_a_id}")
        assert res.status_code == 200
        # Citizen A accessing Citizen B's report -> 403 Forbidden
        res = citizen_client.get(f"/reports/{rep_b_id}")
        assert res.status_code == 403, f"Citizen A must be 403 on Citizen B report, got {res.status_code}"
        # Citizen A accessing legacy report (unowned) -> 403 Forbidden
        res = citizen_client.get(f"/reports/{rep_legacy_id}")
        assert res.status_code == 403
        # Officer can access all reports
        assert officer_client.get(f"/reports/{rep_a_id}").status_code == 200
        assert officer_client.get(f"/reports/{rep_b_id}").status_code == 200
        assert officer_client.get(f"/reports/{rep_legacy_id}").status_code == 200
        print("PASS: Report ownership strictly isolated between citizens; officer maintains triage visibility.")

        # --------------------------------------------------
        # 8. Status Update & Repair Evidence Authorization
        # --------------------------------------------------
        print("\n--- Test 8: Status Updates & Repair Evidence RBAC ---")
        with officer_client.session_transaction() as sess:
            officer_csrf = sess.get("_csrf_token")
        with citizen_client.session_transaction() as sess:
            citizen_csrf = sess.get("_csrf_token")

        # Citizen cannot update status (403)
        res = citizen_client.put(
            f"/reports/{rep_a_id}/status",
            json={"status": "Resolved"},
            headers={"X-CSRF-Token": citizen_csrf}
        )
        assert res.status_code == 403, f"Citizen status update must be 403, got {res.status_code}"

        # Officer updates status (200)
        res = officer_client.put(
            f"/reports/{rep_a_id}/status",
            json={"status": "In Progress"},
            headers={"X-CSRF-Token": officer_csrf}
        )
        assert res.status_code == 200 and res.json["status"] == "In Progress"

        # Citizen cannot upload repair evidence (403)
        img_buf = create_dummy_image_bytes()
        res = citizen_client.post(
            f"/reports/{rep_a_id}/repair-evidence",
            data={"after_image": (img_buf, "after.jpg"), "repair_notes": "Citizen repair"},
            headers={"X-CSRF-Token": citizen_csrf}
        )
        assert res.status_code == 403, f"Citizen repair upload must be 403, got {res.status_code}"

        # Officer uploads repair evidence (201)
        img_buf = create_dummy_image_bytes()
        res = officer_client.post(
            f"/reports/{rep_a_id}/repair-evidence",
            data={"after_image": (img_buf, "after.jpg"), "repair_notes": "Patch applied by Ward 7 crew"},
            headers={"X-CSRF-Token": officer_csrf}
        )
        assert res.status_code == 201

        # Citizen A can read evidence for their own report (200)
        res = citizen_client.get(f"/reports/{rep_a_id}/repair-evidence")
        assert res.status_code == 200
        assert res.json["repair_notes"] == "Patch applied by Ward 7 crew"

        # Citizen A cannot read evidence for Citizen B's report (403)
        res = citizen_client.get(f"/reports/{rep_b_id}/repair-evidence")
        assert res.status_code == 403
        print("PASS: Status updates and evidence upload restricted to officers; evidence view respects ownership.")

        # --------------------------------------------------
        # 9. Public Markers Endpoint
        # --------------------------------------------------
        print("\n--- Test 9: Public Map Markers Privacy Check ---")
        res = anon_client.get("/reports/public-markers")
        assert res.status_code == 200
        markers = res.json
        assert len(markers) == 3, f"Expected 3 markers, got {len(markers)}"
        # Verify no sensitive user text or user_id leaked
        for m in markers:
            assert "latitude" in m and "longitude" in m and "overall_severity_level" in m
            assert "user_id" not in m, "user_id leaked in public markers!"
            assert "notes" not in m, "notes leaked in public markers!"
        print("PASS: Public map markers return geographic data without leaking user information.")

        # --------------------------------------------------
        # 10. Production Database Integrity Check
        # --------------------------------------------------
        print("\n--- Test 10: Production Database Integrity Check ---")
        prod_conn = sqlite3.connect(PROD_DB_PATH)
        pc = prod_conn.cursor()
        pc.execute("SELECT count(*) FROM reports")
        prod_reports_after = pc.fetchone()[0]
        pc.execute("SELECT count(*) FROM detections")
        prod_detections_after = pc.fetchone()[0]
        pc.execute("SELECT count(*) FROM repair_evidence")
        prod_evidence_after = pc.fetchone()[0]
        prod_conn.close()

        assert prod_reports_before == prod_reports_after, f"Production reports changed from {prod_reports_before} to {prod_reports_after}!"
        assert prod_detections_before == prod_detections_after, f"Production detections changed!"
        assert prod_evidence_before == prod_evidence_after, f"Production evidence changed!"
        print(f"PASS: Production database database.db was untouched ({prod_reports_after} reports, {prod_detections_after} detections, {prod_evidence_after} repair evidence intact).")

        print("\n" + "=" * 70)
        print("ALL 10 VERIFICATION TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)

    finally:
        cleanup_test_env()


if __name__ == "__main__":
    run_all_tests()
