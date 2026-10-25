"""
Phase 3 Verification Test Suite
Tests real email notification workflows using isolated database and mocked SMTP transport.
Never sends real emails or touches the production database.
"""

import os
import sys
import shutil
import sqlite3
import smtplib
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

print(f"[TEST ENV] Python executable: {sys.executable}")
print(f"[TEST ENV] Python version: {sys.version}")

import app as app_module
from database import create_database, DB_PATH as PROD_DB_PATH
from create_officer import create_officer
import mailer

TEST_DB = "temp_phase3_test.db"
TEST_UPLOAD_DIR = Path("temp_uploads_test_phase3")


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


def run_all_tests():
    print("=" * 70)
    print("STARTING PHASE 3 EMAIL NOTIFICATION & RBAC VERIFICATION TESTS")
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
        # 1. Database Schema Check for resolution_notified_at
        # --------------------------------------------------
        print("\n--- Test 1: Database Migration: resolution_notified_at column ---")
        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        tc.execute("PRAGMA table_info(reports)")
        rep_cols = [col[1] for col in tc.fetchall()]
        assert "resolution_notified_at" in rep_cols, "reports table missing resolution_notified_at column"
        tconn.close()

        # Idempotency re-run
        create_database(TEST_DB)
        print("PASS: Schema contains resolution_notified_at column; migration is idempotent.")

        # --------------------------------------------------
        # 2. Seed Users & Reports in Isolated DB
        # --------------------------------------------------
        print("\n--- Test 2: Seed Test Users & Reports ---")
        officer_email = "officer.phase3@city.gov.in"
        created = create_officer(officer_email, "Officer Three", "MunicipalAdmin2026!", db_path=TEST_DB)
        assert created is True

        # Register Citizen
        client.get("/register")
        with client.session_transaction() as sess:
            reg_token = sess.get("_csrf_token")
        citizen_email = "citizen.phase3@example.com"
        res = client.post("/register", data={
            "name": "Citizen Three",
            "email": citizen_email,
            "password": "CitizenPassword123!",
            "confirm_password": "CitizenPassword123!",
            "csrf_token": reg_token
        }, follow_redirects=True)
        assert res.status_code == 200

        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        tc.execute("SELECT id FROM users WHERE email = ?", (citizen_email,))
        citizen_id = tc.fetchone()[0]
        tc.execute("SELECT id FROM users WHERE email = ?", (officer_email,))
        officer_id = tc.fetchone()[0]

        # Insert 3 test reports:
        # Report 1: Owned by citizen, status Open
        tc.execute("""
            INSERT INTO reports (image_path, latitude, longitude, location, overall_severity_score, overall_severity_level, pothole_count, status, user_id)
            VALUES ('uploads/test1.jpg', 13.0827, 80.2707, 'Gandhi Road, Chennai', 7.2, 'HIGH', 2, 'Open', ?)
        """, (citizen_id,))
        rep1_id = tc.lastrowid

        # Report 2: Historical unowned report (user_id = NULL), status Open
        tc.execute("""
            INSERT INTO reports (image_path, latitude, longitude, location, overall_severity_score, overall_severity_level, pothole_count, status, user_id)
            VALUES ('uploads/test2.jpg', 12.9716, 77.5946, 'Brigade Road, Bangalore', 4.5, 'MEDIUM', 1, 'Open', NULL)
        """,)
        rep2_id = tc.lastrowid

        # Report 3: Owned by citizen, already Resolved
        tc.execute("""
            INSERT INTO reports (image_path, latitude, longitude, location, overall_severity_score, overall_severity_level, pothole_count, status, user_id, resolution_notified_at)
            VALUES ('uploads/test3.jpg', 28.6139, 77.2090, 'Janpath, Delhi', 8.1, 'HIGH', 3, 'Resolved', ?, '2026-10-01 10:00:00')
        """, (citizen_id,))
        rep3_id = tc.lastrowid

        tconn.commit()
        tconn.close()
        print("PASS: Users and test reports seeded successfully.")

        # Log in officer client
        officer_client = app_module.app.test_client()
        officer_client.get("/login")
        with officer_client.session_transaction() as sess:
            login_token = sess.get("_csrf_token")
        res = officer_client.post("/login", data={
            "email": officer_email,
            "password": "MunicipalAdmin2026!",
            "csrf_token": login_token
        }, follow_redirects=True)
        assert res.status_code == 200

        with officer_client.session_transaction() as sess:
            officer_csrf = sess.get("_csrf_token")

        # --------------------------------------------------
        # 3. Ordinary Status Change (Open -> In Progress)
        # --------------------------------------------------
        print("\n--- Test 3: Ordinary Status Change (Open -> In Progress) Sends No Email ---")
        with patch("smtplib.SMTP") as mock_smtp:
            res = officer_client.put(
                f"/reports/{rep1_id}/status",
                json={"status": "In Progress"},
                headers={"X-CSRF-Token": officer_csrf}
            )
            assert res.status_code == 200
            data = res.get_json()
            assert data["status"] == "In Progress"
            assert data["email_status"] == "not_applicable", f"Expected not_applicable, got {data['email_status']}"
            mock_smtp.assert_not_called()
        print("PASS: Non-resolution status changes do not trigger email sending.")

        # --------------------------------------------------
        # 4. Status Transition to Resolved with SMTP Unconfigured
        # --------------------------------------------------
        print("\n--- Test 4: Resolution Transition with Unconfigured SMTP ---")
        # Ensure SMTP_SERVER is empty
        os.environ["SMTP_SERVER"] = ""
        res = officer_client.put(
            f"/reports/{rep1_id}/status",
            json={"status": "Resolved"},
            headers={"X-CSRF-Token": officer_csrf}
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "Resolved"
        assert data["email_status"] == "not_configured"

        # Verify DB status updated to Resolved, but resolution_notified_at is still NULL
        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        tc.execute("SELECT status, resolution_notified_at FROM reports WHERE id = ?", (rep1_id,))
        row = tc.fetchone()
        assert row[0] == "Resolved", f"Status should be Resolved, got {row[0]}"
        assert row[1] is None, f"resolution_notified_at should be NULL when unconfigured, got {row[1]}"
        tconn.close()
        print("PASS: Report updated to Resolved; missing SMTP handled gracefully with not_configured status.")

        # --------------------------------------------------
        # 5. Historical Report with user_id NULL Transition to Resolved
        # --------------------------------------------------
        print("\n--- Test 5: Historical Report (user_id = NULL) Transition to Resolved ---")
        os.environ["SMTP_SERVER"] = "smtp.example.com"
        with patch("smtplib.SMTP") as mock_smtp:
            res = officer_client.put(
                f"/reports/{rep2_id}/status",
                json={"status": "Resolved"},
                headers={"X-CSRF-Token": officer_csrf}
            )
            assert res.status_code == 200
            data = res.get_json()
            assert data["status"] == "Resolved"
            assert data["email_status"] == "no_reporter"
            mock_smtp.assert_not_called()

        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        tc.execute("SELECT status FROM reports WHERE id = ?", (rep2_id,))
        assert tc.fetchone()[0] == "Resolved"
        tconn.close()
        print("PASS: Historical report with user_id = NULL updated cleanly with no_reporter status.")

        # --------------------------------------------------
        # 6. Simulated SMTP Failure Preserves Status Update
        # --------------------------------------------------
        print("\n--- Test 6: Simulated SMTP Failure Preserves Status Update ---")
        # Reset rep1 status to In Progress
        tconn = sqlite3.connect(TEST_DB)
        tconn.execute("UPDATE reports SET status = 'In Progress', resolution_notified_at = NULL WHERE id = ?", (rep1_id,))
        tconn.commit()
        tconn.close()

        with patch("smtplib.SMTP", side_effect=smtplib.SMTPConnectError(111, "Connection refused")):
            res = officer_client.put(
                f"/reports/{rep1_id}/status",
                json={"status": "Resolved"},
                headers={"X-CSRF-Token": officer_csrf}
            )
            assert res.status_code == 200
            data = res.get_json()
            assert data["status"] == "Resolved", "Status update was undone on SMTP error!"
            assert data["email_status"] == "failed"

        # Check DB: status is Resolved, resolution_notified_at remains NULL
        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        tc.execute("SELECT status, resolution_notified_at FROM reports WHERE id = ?", (rep1_id,))
        row = tc.fetchone()
        assert row[0] == "Resolved", "Database status update was lost!"
        assert row[1] is None, "resolution_notified_at was wrongly set on failed send!"
        tconn.close()
        print("PASS: Report status remains Resolved when SMTP fails; resolution_notified_at left unset for retry.")

        # --------------------------------------------------
        # 7. Successful Resolution Email with Mocked SMTP
        # --------------------------------------------------
        print("\n--- Test 7: Successful Resolution Notification with Mocked SMTP ---")
        # Reset rep1 to In Progress so transition to Resolved triggers email
        tconn = sqlite3.connect(TEST_DB)
        tconn.execute("UPDATE reports SET status = 'In Progress', resolution_notified_at = NULL WHERE id = ?", (rep1_id,))
        tconn.commit()
        tconn.close()

        mock_smtp_instance = MagicMock()
        with patch("smtplib.SMTP", return_value=mock_smtp_instance):
            res = officer_client.put(
                f"/reports/{rep1_id}/status",
                json={"status": "Resolved"},
                headers={"X-CSRF-Token": officer_csrf}
            )
            assert res.status_code == 200
            data = res.get_json()
            assert data["status"] == "Resolved"
            assert data["email_status"] == "sent"

            # Verify send_message was called on mock
            assert mock_smtp_instance.send_message.called
            sent_msg = mock_smtp_instance.send_message.call_args[0][0]
            assert sent_msg["To"] == citizen_email
            assert f"#{rep1_id}" in sent_msg["Subject"]
            assert "RESOLVED" in sent_msg["Subject"].upper()

        # Verify DB resolution_notified_at is now set
        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        tc.execute("SELECT status, resolution_notified_at FROM reports WHERE id = ?", (rep1_id,))
        row = tc.fetchone()
        assert row[0] == "Resolved"
        assert row[1] is not None, "resolution_notified_at was not recorded on successful send!"
        tconn.close()
        print(f"PASS: Resolution email accepted by SMTP for recipient '{citizen_email}'; timestamp recorded.")

        # --------------------------------------------------
        # 8. Duplicate Prevention: Saving Resolved Report Again
        # --------------------------------------------------
        print("\n--- Test 8: Duplicate Prevention (Saving Resolved Report Again) ---")
        with patch("smtplib.SMTP") as mock_smtp:
            res = officer_client.put(
                f"/reports/{rep1_id}/status",
                json={"status": "Resolved"},
                headers={"X-CSRF-Token": officer_csrf}
            )
            assert res.status_code == 200
            data = res.get_json()
            assert data["email_status"] == "already_notified"
            mock_smtp.assert_not_called()

            # Even if status moves to In Progress and back to Resolved after notification
            officer_client.put(
                f"/reports/{rep1_id}/status",
                json={"status": "In Progress"},
                headers={"X-CSRF-Token": officer_csrf}
            )
            res = officer_client.put(
                f"/reports/{rep1_id}/status",
                json={"status": "Resolved"},
                headers={"X-CSRF-Token": officer_csrf}
            )
            assert res.status_code == 200
            data = res.get_json()
            assert data["email_status"] == "already_notified"
            mock_smtp.assert_not_called()

        print("PASS: Already-notified report never receives duplicate resolution emails.")

        # --------------------------------------------------
        # 9. Manual Notify Reporter Action (/reports/<id>/notify-reporter)
        # --------------------------------------------------
        print("\n--- Test 9: Manual 'Notify Reporter' Endpoint & RBAC ---")
        # Anon -> 401
        anon_client = app_module.app.test_client()
        res = anon_client.post(f"/reports/{rep1_id}/notify-reporter")
        assert res.status_code in (401, 403)

        # Citizen -> 403
        citizen_client = app_module.app.test_client()
        citizen_client.get("/login")
        with citizen_client.session_transaction() as sess:
            ctok = sess.get("_csrf_token")
        citizen_client.post("/login", data={
            "email": citizen_email,
            "password": "CitizenPassword123!",
            "csrf_token": ctok
        })
        res = citizen_client.post(
            f"/reports/{rep1_id}/notify-reporter",
            headers={"X-CSRF-Token": ctok}
        )
        assert res.status_code == 403

        # Officer on already notified report -> 400 already_notified
        res = officer_client.post(
            f"/reports/{rep1_id}/notify-reporter",
            headers={"X-CSRF-Token": officer_csrf}
        )
        assert res.status_code == 400
        assert res.get_json()["email_status"] == "already_notified"

        # Officer on unowned report -> 400 no_reporter
        res = officer_client.post(
            f"/reports/{rep2_id}/notify-reporter",
            headers={"X-CSRF-Token": officer_csrf}
        )
        assert res.status_code == 400
        assert res.get_json()["email_status"] == "no_reporter"

        # Create fresh report 4 for citizen that failed notification
        tconn = sqlite3.connect(TEST_DB)
        tc = tconn.cursor()
        tc.execute("""
            INSERT INTO reports (image_path, location, status, user_id, resolution_notified_at)
            VALUES ('uploads/test4.jpg', 'Kamarajar Salai', 'Resolved', ?, NULL)
        """, (citizen_id,))
        rep4_id = tc.lastrowid
        tconn.commit()
        tconn.close()

        # Officer manually triggers notification on report 4 -> succeeds
        mock_smtp_instance = MagicMock()
        with patch("smtplib.SMTP", return_value=mock_smtp_instance):
            res = officer_client.post(
                f"/reports/{rep4_id}/notify-reporter",
                headers={"X-CSRF-Token": officer_csrf}
            )
            assert res.status_code == 200
            assert res.get_json()["email_status"] == "sent"

        # Second manual call on report 4 -> blocked by duplicate guard
        res = officer_client.post(
            f"/reports/{rep4_id}/notify-reporter",
            headers={"X-CSRF-Token": officer_csrf}
        )
        assert res.status_code == 400
        assert res.get_json()["email_status"] == "already_notified"

        print("PASS: Manual notify-reporter respects role checks, ownership, and duplicate guards.")

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
        print("ALL 10 PHASE 3 VERIFICATION TESTS PASSED SUCCESSFULLY!")
        print("=" * 70)

    finally:
        cleanup_test_env()


if __name__ == "__main__":
    run_all_tests()
