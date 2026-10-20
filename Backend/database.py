import os
from pathlib import Path
from mysql.connector import Error
import mysql.connector
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "OSCore"),
        connection_timeout=3,
    )


def ensure_schema_compatibility():
    """Small idempotent migration for databases created from an earlier OSCore schema."""
    conn = cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SHOW COLUMNS FROM processes")
        cols = {row[0] for row in cursor.fetchall()}
        if "waiting_for" not in cols: cursor.execute("ALTER TABLE processes ADD COLUMN waiting_for VARCHAR(80) NULL")
        if "progress" not in cols: cursor.execute("ALTER TABLE processes ADD COLUMN progress INT NOT NULL DEFAULT 0")
        cursor.execute("SHOW COLUMNS FROM process_events")
        event_cols = {row[0] for row in cursor.fetchall()}
        if "simulation_time" not in event_cols: cursor.execute("ALTER TABLE process_events ADD COLUMN simulation_time INT NOT NULL DEFAULT 0")
        cursor.execute("SHOW INDEX FROM processes")
        indexes = cursor.fetchall()
        if not any(row[2] == "uq_session_pid" for row in indexes):
            cursor.execute("ALTER TABLE processes ADD UNIQUE KEY uq_session_pid (session_uuid,pid)")
        conn.commit(); return True
    except Error as exc:
        print(f"Database schema migration skipped/failed: {exc}");
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


def database_is_available():
    conn = None
    try:
        conn = get_db_connection()
        return conn.is_connected()
    except Error:
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def _execute_many(sql, rows):
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.executemany(sql, rows)
        conn.commit()
        return True
    except Error as exc:
        print(f"Database write failed: {exc}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def create_session(session_uuid):
    conn = cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("INSERT IGNORE INTO simulation_sessions (session_uuid, notes) VALUES (%s, %s)", (session_uuid, "OSCore interactive simulation"))
        conn.commit(); return True
    except Error as exc:
        print(f"Database session not saved: {exc}"); return False
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


def save_event(event_type, description, pid=None, session_id=None, sim_time=0):
    return _execute_many(
        "INSERT INTO process_events (session_id, pid, event_type, description, simulation_time) VALUES (%s,%s,%s,%s,%s)",
        [(session_id, pid, event_type, description, sim_time)],
    )


def persist_snapshot(state):
    """Persist current process/resource state in one transaction."""
    conn = cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor()
        sid = state["session_id"]
        cursor.execute("INSERT IGNORE INTO simulation_sessions (session_uuid, notes) VALUES (%s,%s)", (sid, "OSCore interactive simulation"))
        for p in state["processes"]:
            cursor.execute("""INSERT INTO processes
                (session_uuid,pid,process_name,arrival_time,burst_time,remaining_time,state,waiting_for,progress)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE process_name=VALUES(process_name), arrival_time=VALUES(arrival_time),
                burst_time=VALUES(burst_time), remaining_time=VALUES(remaining_time), state=VALUES(state),
                waiting_for=VALUES(waiting_for), progress=VALUES(progress)""",
                (sid,p["pid"],p["name"],p["arrival_time"],p["burst_time"],p["remaining_time"],p["state"],p.get("waiting_for"),p.get("progress",0)))
        for name, r in state["resources"].items():
            cursor.execute("""INSERT INTO resources (resource_name,capacity,available_instances)
                VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE capacity=VALUES(capacity), available_instances=VALUES(available_instances)""",
                (name,r["capacity"],r["available"]))
        # Keep one current allocation record per session/process/resource.
        cursor.execute("DELETE FROM resource_allocations WHERE session_uuid=%s", (sid,))
        allocations = []
        for name, r in state["resources"].items():
            allocations.extend((sid,pid,name,"HELD") for pid in r["holders"])
        for p in state["processes"]:
            if p.get("waiting_for") and p["state"] == "BLOCKED":
                allocations.append((sid,p["pid"],p["waiting_for"],"WAITING"))
        if allocations:
            cursor.executemany("INSERT INTO resource_allocations (session_uuid,pid,resource_name,allocation_state) VALUES (%s,%s,%s,%s)", allocations)
        conn.commit(); return True
    except Error as exc:
        print(f"Database snapshot not saved: {exc}")
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


def save_deadlock(session_id, detected, pids, recovery_action=None):
    return _execute_many(
        "INSERT INTO deadlock_events (session_uuid,detected,involved_pids,recovery_action) VALUES (%s,%s,%s,%s)",
        [(session_id, bool(detected), ",".join(map(str,pids or [])), recovery_action)],
    )


def fetch_events(limit=100, session_id=None):
    conn = cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        if session_id:
            cursor.execute("SELECT id,session_id,pid,event_type,description,simulation_time,created_at FROM process_events WHERE session_id=%s ORDER BY id DESC LIMIT %s", (session_id,int(limit)))
        else:
            cursor.execute("SELECT id,session_id,pid,event_type,description,simulation_time,created_at FROM process_events ORDER BY id DESC LIMIT %s", (int(limit),))
        rows = cursor.fetchall()
        for row in rows:
            if row.get("created_at"): row["created_at"] = row["created_at"].isoformat(sep=" ", timespec="seconds")
        return rows
    except Error as exc:
        print(f"Could not fetch database events: {exc}"); return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()


def fetch_session_processes(session_id):
    conn = cursor = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT pid,process_name AS name,arrival_time,burst_time,remaining_time,state,waiting_for,progress FROM processes WHERE session_uuid=%s ORDER BY pid", (session_id,))
        return cursor.fetchall()
    except Error as exc:
        print(f"Could not fetch processes: {exc}"); return []
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()
