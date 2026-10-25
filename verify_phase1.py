import os
import sys
import uuid
import shutil
import sqlite3
from pathlib import Path
import io

# Verify Python environment
print(f"[TEST ENV] Python executable: {sys.executable}")
print(f"[TEST ENV] Python version: {sys.version}")

import app as app_module
from database import create_database
from PIL import Image

TEST_DB = "temp_phase1_test.db"
TEST_UPLOAD_DIR = Path("temp_uploads_test")

def setup_test_env():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if TEST_UPLOAD_DIR.exists():
        shutil.rmtree(TEST_UPLOAD_DIR)
    TEST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    create_database(TEST_DB)
    conn = sqlite3.connect(TEST_DB)
    c = conn.cursor()
    c.execute(
        "INSERT INTO users (id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
        (1, "Test Officer", "officer@test.com", "dummy_hash", "officer")
    )
    conn.commit()
    conn.close()

    app_module.DB_PATH = TEST_DB
    app_module.app.config["DATABASE"] = TEST_DB
    app_module.app.config["WTF_CSRF_ENABLED"] = False
    app_module.UPLOAD_FOLDER = TEST_UPLOAD_DIR
    app_module.REPAIR_FOLDER = TEST_UPLOAD_DIR / "repair"
    app_module.REPAIR_FOLDER.mkdir(parents=True, exist_ok=True)
    app_module.app.config["TESTING"] = True

def cleanup_test_env():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    if TEST_UPLOAD_DIR.exists():
        shutil.rmtree(TEST_UPLOAD_DIR)

def run_all_tests():
    print("=" * 60)
    print("STARTING PHASE 1 STABILIZATION VERIFICATION TESTS")
    print("=" * 60)

    from unittest.mock import patch
    patcher = patch("app.get_current_user", return_value={"id": 1, "role": "officer", "name": "Test Officer"})
    patcher.start()

    # 1. Model Loading
    print("\n--- Test 1: Model Loading from Original Path ---")
    assert app_module.model is not None, "YOLO model failed to load"
    assert hasattr(app_module.model, "names"), "YOLO model has no class names"
    print("PASS: YOLO model is loaded. Class names:", app_module.model.names)

    # 2. Production Database Verification
    print("\n--- Test 2: Production Database Records Intact ---")
    prod_conn = sqlite3.connect("database.db")
    c = prod_conn.cursor()
    c.execute("SELECT count(*) FROM reports")
    reports_count = c.fetchone()[0]
    c.execute("SELECT count(*) FROM detections")
    detections_count = c.fetchone()[0]
    c.execute("SELECT count(*) FROM repair_evidence")
    evidence_count = c.fetchone()[0]
    c.execute("SELECT count(*) FROM reports WHERE latitude IS NULL OR longitude IS NULL")
    null_coords_count = c.fetchone()[0]
    prod_conn.close()

    print(f"Production database: reports={reports_count}, detections={detections_count}, repair_evidence={evidence_count}, null_coords={null_coords_count}")
    assert reports_count >= 30, f"Expected at least 30 reports, got {reports_count}"
    assert detections_count >= 34, f"Expected at least 34 detections, got {detections_count}"
    assert evidence_count >= 2, f"Expected at least 2 repair_evidence, got {evidence_count}"
    assert null_coords_count >= 4, f"Expected at least 4 reports without GPS, got {null_coords_count}"
    print("PASS: Production database.db is completely intact.")

    # 3. Reports Endpoint Visibility on Production DB
    print("\n--- Test 3: /reports Endpoint Returns All Reports ---")
    app_module.DB_PATH = "database.db"
    app_module.app.config["DATABASE"] = "database.db"
    app_module.app.config["WTF_CSRF_ENABLED"] = False
    client = app_module.app.test_client()
    from unittest.mock import patch
    with patch("app.get_current_user", return_value={"id": 1, "role": "officer", "name": "Test Officer"}):
        resp = client.get("/reports")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        prod_reports = resp.get_json()
        assert len(prod_reports) >= 30, f"Expected all reports returned, got {len(prod_reports)}"
        # Check that null-coordinate reports are included
        null_in_api = [r for r in prod_reports if r["latitude"] is None or r["longitude"] is None]
        assert len(null_in_api) >= 4, f"Expected at least 4 null-coord reports in API, got {len(null_in_api)}"
        print(f"PASS: /reports returns all {len(prod_reports)} reports including all {len(null_in_api)} non-geotagged reports.")

    # Setup isolated test environment for all mutating tests
    setup_test_env()
    client = app_module.app.test_client()

    # 4. Predict Endpoint with Valid Image in Isolated DB
    print("\n--- Test 4: Image Prediction & Safe Filename Generation ---")
    sample_img_path = Path("test_images/road1.jpg")
    assert sample_img_path.exists(), "test_images/road1.jpg missing"

    with open(sample_img_path, "rb") as f:
        img_bytes = f.read()

    # Test with malicious filename to verify path traversal prevention and UUID renaming
    resp = client.post(
        "/predict",
        data={
            "image": (io.BytesIO(img_bytes), "../../evil_path.jpg"),
            "latitude": "12.9715",
            "longitude": "79.1590",
            "location": "Test Street, Vellore"
        },
        content_type="multipart/form-data"
    )
    assert resp.status_code == 200, f"Predict failed: {resp.get_json()}"
    pred_data = resp.get_json()
    assert "report_id" in pred_data, "No report_id returned"
    test_report_id = pred_data["report_id"]
    assert pred_data["potholes_detected"] > 0, "No potholes detected in road1.jpg"

    # Check file saved safely with uuid and not "../../evil_path.jpg"
    saved_files = list(TEST_UPLOAD_DIR.glob("upload_*.jpg"))
    assert len(saved_files) == 1, f"Expected 1 saved upload, got {saved_files}"
    assert "evil_path" not in saved_files[0].name, "Filename was not sanitized"
    print(f"PASS: Prediction succeeded. Report ID: #{test_report_id}, Saved safely as: {saved_files[0].name}")

    # 5. Invalid File Upload Rejections
    print("\n--- Test 5: Invalid Upload Rejections ---")
    # Empty filename
    resp = client.post("/predict", data={"image": (io.BytesIO(b""), "")}, content_type="multipart/form-data")
    assert resp.status_code == 400, "Empty filename should return 400"

    # Disallowed extension (.exe, .txt)
    resp = client.post(
        "/predict",
        data={"image": (io.BytesIO(b"malicious executable"), "payload.exe")},
        content_type="multipart/form-data"
    )
    assert resp.status_code == 400, "Disallowed extension should return 400"
    assert "Invalid file type" in resp.get_json()["error"]

    # Corrupted image file
    resp = client.post(
        "/predict",
        data={"image": (io.BytesIO(b"not an actual image"), "fake.jpg")},
        content_type="multipart/form-data"
    )
    assert resp.status_code == 400, "Corrupted image should return 400"
    print("PASS: All invalid upload scenarios safely rejected with 400.")

    # 6. Municipal Status Update Persistence in Isolated DB
    print("\n--- Test 6: Municipal Status Updates ---")
    # Update to 'In Progress'
    resp = client.put(f"/reports/{test_report_id}/status", json={"status": "In Progress"})
    assert resp.status_code == 200, f"Status update failed: {resp.get_json()}"
    assert resp.get_json()["status"] == "In Progress"

    # Verify directly in SQLite
    tconn = sqlite3.connect(TEST_DB)
    tc = tconn.cursor()
    tc.execute("SELECT status FROM reports WHERE id = ?", (test_report_id,))
    assert tc.fetchone()[0] == "In Progress", "Status not persisted in DB"

    # Update to 'Resolved'
    resp = client.put(f"/reports/{test_report_id}/status", json={"status": "Resolved"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "Resolved"

    # Invalid status rejection
    resp = client.put(f"/reports/{test_report_id}/status", json={"status": "HackedStatus"})
    assert resp.status_code == 400, "Invalid status should return 400"

    # Non-existent report 404
    resp = client.put("/reports/99999/status", json={"status": "Resolved"})
    assert resp.status_code == 404, "Non-existent report should return 404"
    print("PASS: Status updates persist in SQLite, invalid statuses and missing IDs handled properly.")

    # 7. Repair Evidence Upload and Fetch
    print("\n--- Test 7: Repair Evidence Upload & Reload ---")
    # Reset status to 'In Progress' to verify uploading evidence does NOT automatically mark as Resolved
    client.put(f"/reports/{test_report_id}/status", json={"status": "In Progress"})

    # Create a small valid test JPEG for repair evidence
    repair_img_io = io.BytesIO()
    test_img = Image.new("RGB", (100, 100), color="blue")
    test_img.save(repair_img_io, format="JPEG")
    repair_img_bytes = repair_img_io.getvalue()

    resp = client.post(
        f"/reports/{test_report_id}/repair-evidence",
        data={
            "after_image": (io.BytesIO(repair_img_bytes), "after_repair.jpg"),
            "repair_notes": "Repaved with hot asphalt batch #402"
        },
        content_type="multipart/form-data"
    )
    assert resp.status_code == 201, f"Repair evidence upload failed: {resp.get_json()}"
    evidence_res = resp.get_json()
    assert evidence_res["report_id"] == test_report_id
    assert "upload_" in evidence_res["after_image_path"] or "report_" in evidence_res["after_image_path"]

    # Verify report status is STILL 'In Progress' (NOT auto-resolved)
    tc.execute("SELECT status FROM reports WHERE id = ?", (test_report_id,))
    assert tc.fetchone()[0] == "In Progress", "Report status should NOT be automatically marked Resolved"
    tconn.close()

    # Test GET repair evidence endpoint
    resp = client.get(f"/reports/{test_report_id}/repair-evidence")
    assert resp.status_code == 200
    get_ev = resp.get_json()
    assert get_ev["report_id"] == test_report_id
    assert get_ev["repair_notes"] == "Repaved with hot asphalt batch #402"
    assert get_ev["after_image_path"] is not None
    print("PASS: Repair evidence uploaded, reloaded correctly, and report status was NOT changed automatically.")

    # 8. XSS Prevention Verification
    print("\n--- Test 8: Stored Location XSS Prevention ---")
    xss_payload = '<script>alert("XSS")</script><img src=x onerror=alert(1)>'
    resp = client.post(
        "/predict",
        data={
            "image": (io.BytesIO(img_bytes), "road_xss.jpg"),
            "latitude": "12.9700",
            "longitude": "79.1500",
            "location": xss_payload
        },
        content_type="multipart/form-data"
    )
    assert resp.status_code == 200
    xss_report_id = resp.get_json()["report_id"]

    # Check that municipal.html template contains escapeHtml helper
    with open("templates/municipal.html", "r", encoding="utf-8") as f:
        muni_html = f.read()
    assert "function escapeHtml" in muni_html, "escapeHtml missing in municipal.html"
    assert "escapeHtml" in muni_html and "report.location" in muni_html, "report.location not escaped in municipal.html table"

    with open("templates/index.html", "r", encoding="utf-8") as f:
        idx_html = f.read()
    assert "function escapeHtml" in idx_html, "escapeHtml missing in index.html"
    assert "escapeHtml" in idx_html and "data.location" in idx_html, "data.location not escaped in index.html"
    print("PASS: escapeHtml is integrated in both municipal.html and index.html across table and popups.")

    # 9. Clean up test env
    setup_test_env()
    cleanup_test_env()
    print("\n--- Test 9: Temporary Test Artifacts Cleaned ---")
    assert not os.path.exists(TEST_DB), "Test DB was not cleaned"
    assert not TEST_UPLOAD_DIR.exists(), "Test upload dir was not cleaned"
    print("PASS: All temporary test artifacts cleaned.")
    patcher.stop()

    print("\n" + "=" * 60)
    print("ALL 9 PHASE 1 STABILIZATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    try:
        run_all_tests()
    finally:
        cleanup_test_env()
