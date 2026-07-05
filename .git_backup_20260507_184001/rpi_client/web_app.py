#!/usr/bin/env python3
"""Flask Web Application for Mobile Weight Capture.

Mobile-responsive web UI for capturing barrel weights from phone browsers.

Contract:
- RPi is authoritative for: barrel_serial, gross_weight, device_id, operator_id, timestamp, mode
- ERPNext is authoritative for: matching the correct Container Barrels row, tara_weight, net_weight,
  row persistence, and Batch AMB total recalculation
- If tara_weight is sent by client, ERPNext may use it only as a hint; ERPNext should prefer the
  stored child-row taraweight or packaging-derived taraweight

Usage:
    python3 web_app.py
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
import requests

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__, template_folder="templates")
app.config["JSON_SORT_KEYS"] = False

CONFIG = {
    "erpnext_url": os.getenv("ERPNEXT_URL", "http://sandbox.sysmayal.cloud").rstrip("/"),
    "api_key": os.getenv("ERPNEXT_API_KEY", ""),
    "api_secret": os.getenv("ERPNEXT_API_SECRET", ""),
    "device_id": os.getenv("DEVICE_ID", "SCALE-L01"),
    "operator_id": os.getenv("OPERATOR_ID", "iot-bot@amb-wellness.com"),
    "tolerance_profile": os.getenv("TOLERANCE_PROFILE", "PLANT"),
}

DB_PATH = Path(__file__).parent / "weight_buffer.db"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db():
    """Initialize or migrate the SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS weight_buffer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barrel_serial TEXT NOT NULL,
            gross_weight REAL NOT NULL,
            batch_name TEXT DEFAULT '',
            tara_weight REAL DEFAULT NULL,
            mode TEXT DEFAULT 'keyboard',
            device_id TEXT NOT NULL,
            operator_id TEXT DEFAULT '',
            timestamp TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0,
            last_error TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS submission_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barrel_serial TEXT NOT NULL,
            gross_weight REAL NOT NULL,
            batch_name TEXT DEFAULT '',
            tara_weight REAL DEFAULT NULL,
            resolved_tara_weight REAL DEFAULT NULL,
            resolved_net_weight REAL DEFAULT NULL,
            mode TEXT DEFAULT 'keyboard',
            device_id TEXT NOT NULL,
            operator_id TEXT DEFAULT '',
            timestamp TEXT NOT NULL,
            status TEXT DEFAULT 'success',
            response_json TEXT DEFAULT ''
        )
    """)

    conn.commit()

    # Lightweight migrations for older DBs
    def ensure_column(table: str, column: str, ddl: str):
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {row[1] for row in info}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    ensure_column("weight_buffer", "batch_name", "batch_name TEXT DEFAULT ''")
    ensure_column("weight_buffer", "tara_weight", "tara_weight REAL DEFAULT NULL")
    ensure_column("weight_buffer", "mode", "mode TEXT DEFAULT 'keyboard'")
    ensure_column("weight_buffer", "operator_id", "operator_id TEXT DEFAULT ''")
    ensure_column("weight_buffer", "last_error", "last_error TEXT DEFAULT ''")

    ensure_column("submission_history", "batch_name", "batch_name TEXT DEFAULT ''")
    ensure_column("submission_history", "tara_weight", "tara_weight REAL DEFAULT NULL")
    ensure_column("submission_history", "resolved_tara_weight", "resolved_tara_weight REAL DEFAULT NULL")
    ensure_column("submission_history", "resolved_net_weight", "resolved_net_weight REAL DEFAULT NULL")
    ensure_column("submission_history", "mode", "mode TEXT DEFAULT 'keyboard'")
    ensure_column("submission_history", "operator_id", "operator_id TEXT DEFAULT ''")
    ensure_column("submission_history", "response_json", "response_json TEXT DEFAULT ''")

    conn.commit()
    conn.close()


def get_auth_headers() -> Dict[str, str]:
    return {
        "Authorization": f"token {CONFIG['api_key']}:{CONFIG['api_secret']}",
        "Content-Type": "application/json",
    }


def get_pending_count() -> int:
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM weight_buffer").fetchone()[0]
    conn.close()
    return count


def get_last_submission() -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM submission_history ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_history(limit: int = 10) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM submission_history ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_pending() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM weight_buffer ORDER BY created_at ASC, id ASC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def validate_barrel_serial(serial: str) -> bool:
    """Validate that the serial exists in ERPNext, unless auth is not configured."""
    if not CONFIG["api_key"] or not CONFIG["api_secret"]:
        return True

    url = (
        f"{CONFIG['erpnext_url']}/api/method/"
        "raven_ai_agent.raven_ai_agent.api.validate_barrel_serial"
    )
    try:
        resp = requests.get(
            url,
            params={"serial": serial},
            headers=get_auth_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            msg = data.get("message", {})
            return bool(msg.get("valid", False))
    except requests.exceptions.RequestException as exc:
        logger.warning("Validation request failed: %s", exc)

    # Fail-open to avoid blocking plant operations when validation endpoint is unavailable
    return True


def build_weight_payload(
    barrel_serial: str,
    gross_weight: float,
    batch_name: str = "",
    tara_weight: Optional[float] = None,
    mode: str = "keyboard",
    operator_id: Optional[str] = None,
    event_timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    payload = {
        "device_id": CONFIG["device_id"],
        "mode": mode or "keyboard",
        "batch_name": (batch_name or "").strip(),
        "barrel_serial": barrel_serial.strip().upper(),
        "gross_weight": float(gross_weight),
        "tara_weight": float(tara_weight) if tara_weight is not None else None,
        "unit": "kg",
        "tolerance_profile": CONFIG["tolerance_profile"],
        "timestamp": event_timestamp or utc_now_iso(),
        "operator_id": operator_id or CONFIG["operator_id"],
        "source": "rpi_client_web_app",
    }
    return payload


def classify_erpnext_response(resp_json: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize ERPNext response shape into one predictable result."""
    message = resp_json.get("message")
    status = resp_json.get("status")

    if isinstance(message, dict):
        inner_status = message.get("status")
        success = inner_status == "success" or status == "success" or message.get("success") is True
        return {
            "ok": success,
            "data": message,
            "raw": resp_json,
        }

    success = status == "success"
    return {
        "ok": success,
        "data": resp_json,
        "raw": resp_json,
    }


def buffer_submission(payload: Dict[str, Any], last_error: str = ""):
    """Buffer submission for later retry with full original context."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO weight_buffer
        (
            barrel_serial, gross_weight, batch_name, tara_weight, mode,
            device_id, operator_id, timestamp, retry_count, last_error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (
            payload["barrel_serial"],
            payload["gross_weight"],
            payload.get("batch_name", ""),
            payload.get("tara_weight"),
            payload.get("mode", "keyboard"),
            payload.get("device_id", CONFIG["device_id"]),
            payload.get("operator_id", CONFIG["operator_id"]),
            payload.get("timestamp", utc_now_iso()),
            (last_error or "")[:500],
        ),
    )
    conn.commit()
    conn.close()


def save_submission(
    payload: Dict[str, Any],
    status: str,
    response_json: Optional[Dict[str, Any]] = None,
):
    response_json = response_json or {}
    resolved = response_json.get("message", response_json)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO submission_history
        (
            barrel_serial, gross_weight, batch_name, tara_weight,
            resolved_tara_weight, resolved_net_weight, mode,
            device_id, operator_id, timestamp, status, response_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["barrel_serial"],
            payload["gross_weight"],
            payload.get("batch_name", ""),
            payload.get("tara_weight"),
            resolved.get("tara_weight"),
            resolved.get("net_weight"),
            payload.get("mode", "keyboard"),
            payload.get("device_id", CONFIG["device_id"]),
            payload.get("operator_id", CONFIG["operator_id"]),
            payload.get("timestamp", utc_now_iso()),
            status,
            json.dumps(response_json, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


def submit_to_erpnext(
    barrel_serial: str,
    gross_weight: float,
    batch_name: str = "",
    tara_weight: Optional[float] = None,
    mode: str = "keyboard",
    operator_id: Optional[str] = None,
    event_timestamp: Optional[str] = None,
    buffer_on_failure: bool = True,
) -> Dict[str, Any]:
    """Submit weight event to ERPNext.

    Important:
    - gross_weight is authoritative from device
    - tara_weight is only a hint; ERPNext should resolve authoritative tara from row/item
    """
    payload = build_weight_payload(
        barrel_serial=barrel_serial,
        gross_weight=gross_weight,
        batch_name=batch_name,
        tara_weight=tara_weight,
        mode=mode,
        operator_id=operator_id,
        event_timestamp=event_timestamp,
    )

    if not CONFIG["api_key"] or not CONFIG["api_secret"]:
        msg = "API credentials not configured"
        logger.warning(msg)
        if buffer_on_failure:
            buffer_submission(payload, last_error=msg)
        return {"status": "buffered", "message": msg, "payload": payload}

    url = f"{CONFIG['erpnext_url']}/api/method/amb_w_spc.api.sensor_skill.receive_weight_event"

    try:
        resp = requests.post(
            url,
            json=payload,
            headers=get_auth_headers(),
            timeout=15,
        )

        try:
            resp_json = resp.json()
        except ValueError:
            resp_json = {
                "status": "error",
                "message": f"Non-JSON response: HTTP {resp.status_code}",
                "raw_text": resp.text[:1000],
            }

        normalized = classify_erpnext_response(resp_json)

        if resp.status_code == 200 and normalized["ok"]:
            save_submission(payload, "success", resp_json)
            data = normalized["data"]
            return {
                "status": "success",
                "barrel_serial": payload["barrel_serial"],
                "gross_weight": payload["gross_weight"],
                "tara_weight": data.get("tara_weight"),
                "net_weight": data.get("net_weight"),
                "batch_name": data.get("batch_name", payload.get("batch_name", "")),
                "container_name": data.get("container_name"),
                "row_name": data.get("row_name"),
                "timestamp": payload["timestamp"],
                "message": data.get("message", "Weight event saved"),
                "server_response": resp_json,
            }

        error_msg = ""
        if isinstance(resp_json.get("message"), dict):
            error_msg = resp_json["message"].get("message") or str(resp_json["message"])
        else:
            error_msg = str(resp_json.get("message") or f"HTTP {resp.status_code}")

        logger.error("ERPNext API error: HTTP %s - %s", resp.status_code, error_msg)

        if buffer_on_failure:
            buffer_submission(payload, last_error=error_msg)

        save_submission(payload, "buffered" if buffer_on_failure else "error", resp_json)

        return {
            "status": "buffered" if buffer_on_failure else "error",
            "message": error_msg,
            "timestamp": payload["timestamp"],
            "server_response": resp_json,
        }

    except requests.exceptions.RequestException as exc:
        logger.error("Submission failed: %s", exc)
        if buffer_on_failure:
            buffer_submission(payload, last_error=str(exc))
        return {
            "status": "buffered" if buffer_on_failure else "error",
            "message": str(exc),
            "timestamp": payload["timestamp"],
        }


def retry_pending() -> Dict[str, Any]:
    """Retry all pending submissions using full original payload context."""
    pending = get_pending()
    results = {"success": 0, "failed": 0, "total": len(pending), "items": []}

    for item in pending:
        result = submit_to_erpnext(
            barrel_serial=item["barrel_serial"],
            gross_weight=item["gross_weight"],
            batch_name=item.get("batch_name", ""),
            tara_weight=item.get("tara_weight"),
            mode=item.get("mode", "keyboard"),
            operator_id=item.get("operator_id") or CONFIG["operator_id"],
            event_timestamp=item.get("timestamp"),
            buffer_on_failure=False,
        )

        conn = sqlite3.connect(DB_PATH)
        if result["status"] == "success":
            conn.execute("DELETE FROM weight_buffer WHERE id = ?", (item["id"],))
            results["success"] += 1
        else:
            conn.execute(
                """
                UPDATE weight_buffer
                SET retry_count = retry_count + 1,
                    last_error = ?
                WHERE id = ?
                """,
                ((result.get("message") or "")[:500], item["id"]),
            )
            results["failed"] += 1
        conn.commit()
        conn.close()

        results["items"].append({
            "id": item["id"],
            "barrel_serial": item["barrel_serial"],
            "status": result["status"],
            "message": result.get("message", ""),
        })

    return results


init_db()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/submit-weight", methods=["POST"])
def api_submit_weight():
    """Submit barrel serial + weight to ERPNext.

    Expected JSON:
    {
        "barrel_serial": "BRL-0701059263-1-C001-011",
        "gross_weight": 220.1,
        "batch_name": "LOTE-26-16-0022",
        "tara_weight": 20,
        "mode": "scale",
        "operator_id": "user@amb-wellness.com",
        "timestamp": "2026-04-18T19:55:00Z"
    }
    """
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    barrel_serial = str(data.get("barrel_serial", "")).strip().upper()
    gross_weight = data.get("gross_weight")
    batch_name = str(data.get("batch_name", "")).strip()
    tara_weight = data.get("tara_weight", None)
    mode = str(data.get("mode", "keyboard")).strip().lower() or "keyboard"
    operator_id = str(data.get("operator_id", "")).strip() or CONFIG["operator_id"]
    event_timestamp = data.get("timestamp") or utc_now_iso()

    if not barrel_serial:
        return jsonify({"status": "error", "message": "Barrel serial required"}), 400

    if gross_weight is None:
        return jsonify({"status": "error", "message": "Weight required"}), 400

    try:
        gross_weight = float(gross_weight)
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Invalid weight format"}), 400

    if tara_weight in ("", None):
        tara_weight = None
    else:
        try:
            tara_weight = float(tara_weight)
        except (ValueError, TypeError):
            return jsonify({"status": "error", "message": "Invalid tara format"}), 400

    if not validate_barrel_serial(barrel_serial):
        return jsonify({
            "status": "error",
            "message": f"Barrel {barrel_serial} not found"
        }), 404

    if gross_weight < 0.5 or gross_weight > 500:
        return jsonify({
            "status": "error",
            "message": f"Weight {gross_weight} out of range (0.5-500 kg)"
        }), 400

    result = submit_to_erpnext(
        barrel_serial=barrel_serial,
        gross_weight=gross_weight,
        batch_name=batch_name,
        tara_weight=tara_weight,
        mode=mode,
        operator_id=operator_id,
        event_timestamp=event_timestamp,
        buffer_on_failure=True,
    )

    # 200 for success or buffered, 4xx only for input validation problems above
    return jsonify(result), 200


@app.route("/api/barrels/<serial>", methods=["GET"])
def api_validate_barrel(serial: str):
    serial = serial.strip().upper()

    if not validate_barrel_serial(serial):
        return jsonify({
            "status": "error",
            "message": f"Barrel {serial} not found"
        }), 404

    return jsonify({
        "status": "success",
        "barrel_serial": serial,
        "valid": True
    })


@app.route("/api/status", methods=["GET"])
def api_status():
    last = get_last_submission()
    pending = get_pending_count()

    return jsonify({
        "device_id": CONFIG["device_id"],
        "connected": True,
        "last_submission": last,
        "pending_count": pending,
        "erpnext_url": CONFIG["erpnext_url"],
    })


@app.route("/api/pending", methods=["GET"])
def api_pending():
    pending = get_pending()
    return jsonify({
        "status": "success",
        "count": len(pending),
        "items": pending
    })


@app.route("/api/retry-pending", methods=["POST"])
def api_retry_pending():
    results = retry_pending()
    return jsonify({
        "status": "success",
        "results": results
    })


@app.route("/api/history", methods=["GET"])
def api_history():
    limit = request.args.get("limit", 10, type=int)
    history = get_history(limit=limit)
    return jsonify({
        "status": "success",
        "count": len(history),
        "items": history
    })


def main():
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    logger.info("Starting Flask server on %s:%s", host, port)
    logger.info("ERPNext URL: %s", CONFIG["erpnext_url"])
    logger.info("Device ID: %s", CONFIG["device_id"])

    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
