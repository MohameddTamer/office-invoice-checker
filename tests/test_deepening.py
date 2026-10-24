#!/usr/bin/env python3
# Deepening checks for the invoice checker. Run: python3 tests/test_deepening.py
# Boots the real server on its own port against a throwaway database in a temp folder.
import json, os, sqlite3, subprocess, sys, tempfile, time, urllib.request, urllib.error

ROOT = os.path.join(os.path.dirname(__file__), "..")
PORT = "8193"
BASE = f"http://127.0.0.1:{PORT}"
CHECKS = 0

def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond:
        raise AssertionError(f"check {CHECKS} failed: {msg}")
    print(f"ok {CHECKS}: {msg}")

def call(method, path, body=None, token=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, method=method, data=data,
        headers={"Content-Type": ctype, **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except json.JSONDecodeError:
            return e.code, {}

def wait_up():
    for _ in range(50):
        try:
            with urllib.request.urlopen(BASE + "/", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False

HEADER = "office_id,courier_id,from_day,to_day,billed_days\n"
GOOD_CSV = HEADER + (
    "1,1,2026-10-19,2026-10-25,6\n"
    "2,3,2026-10-19,2026-10-25,7\n"
)
MIXED_CSV = HEADER + (
    "3,5,2026-10-19,2026-10-25,5\n"
    "1,1,2026-10-05,2026-10-18,12\n"
    "1,2,2026-10-19,2026-10-25,six\n"
    "1,2,19-10-2026,2026-10-25,5\n"
    "1,2,2026-10-25,2026-10-19,5\n"
    "1,2,2026-10-19,2026-10-25,99\n"
    "99,2,2026-10-19,2026-10-25,5\n"
    "1,99,2026-10-19,2026-10-25,5\n"
    "2,1,2026-10-19,2026-10-25,5\n"
)

def main():
    tmp = tempfile.mkdtemp(prefix="invoice-deep-")
    db_path = os.path.join(tmp, "deep.db")
    log_path = os.path.join(tmp, "deep.log")
    backup_dir = os.path.join(tmp, "backups")
    env = dict(os.environ, PORT=PORT, INV_DB=db_path, INV_LOG_FILE=log_path, INV_BACKUP_DIR=backup_dir)
    subprocess.run([sys.executable, "seed.py"], cwd=os.path.join(ROOT, "backend"), env=env, check=True)
    srv = subprocess.Popen([sys.executable, "app.py"], cwd=os.path.join(ROOT, "backend"), env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        check(wait_up(), "server boots on the PORT from the environment")
        check(os.path.exists(db_path), "seed wrote the database at the INV_DB from the environment")

        code, body = call("GET", "/api/check?from=2026-10-05&to=2026-10-18")
        check(code == 401, "check without a token is 401")
        check(isinstance(body.get("error"), str) and body.get("code") == 401, "unauthenticated error carries a message and its code")

        code, viewer = call("POST", "/api/login", {"username": "viewer", "password": "viewer1234"})
        check(code == 200 and viewer.get("role") == "viewer", "viewer account logs in with the viewer role")
        code, body = call("POST", "/api/admin/backup", {}, token=viewer["token"])
        check(code == 403, "viewer cannot take a backup")
        code, body = call("POST", "/api/import/invoice-lines", raw=GOOD_CSV.encode(), token=viewer["token"], ctype="text/csv")
        check(code == 403, "viewer cannot import invoice lines")
        code, body = call("GET", "/api/admin/config", token=viewer["token"])
        check(code == 403, "viewer cannot read the admin config")

        code, body = call("POST", "/api/login", {"username": "accounts", "password": "demo1234"})
        check(code == 200, "accounts user logs in")
        tok = body["token"]

        code, cfg = call("GET", "/api/admin/config", token=tok)
        check(code == 200, "accountant can read the admin config")
        check(all(k in cfg for k in ("token_ttl_seconds", "db_file", "log_file", "backup_dir")), "config reports ttl, db, log and backup settings")
        check(cfg["db_file"] == os.path.basename(db_path), "config names the database file the environment chose")
        check(cfg["log_file"] == os.path.basename(log_path), "config names the log file the environment chose")
        check(cfg["backup_dir"] == os.path.basename(backup_dir), "config names the backup dir the environment chose")

        code, rep = call("GET", "/api/report?from=2026-10-05&to=2026-10-18", token=tok)
        check(code == 200 and rep.get("report") is True, "report endpoint answers and flags itself as the report")
        check(rep["totals"]["line_count"] == 5, "report covers the five seeded invoice lines")
        check(rep["totals"]["billed_days"] == 62 and rep["totals"]["worked_days"] == 57, "report totals match the hand worked seed numbers")
        check(rep["total_overbilled_money"] == 2700.0, "report overbilled total matches the paper figure at the seeded rate")
        check(len(rep["offices"]) == 3, "report breaks the period down by all three offices")
        code, body = call("GET", "/api/report?from=2026-10-18&to=2026-10-05", token=tok)
        check(code == 400 and body.get("code") == 400, "backwards report range is a structured 400")
        code, body = call("GET", "/api/nope", token=tok)
        check(code == 404 and body.get("code") == 404, "unknown api path is a structured 404")

        code, body = call("POST", "/api/import/invoice-lines", raw=GOOD_CSV.encode(), ctype="text/csv")
        check(code == 401, "import without a token is 401")

        code, rep1 = call("POST", "/api/import/invoice-lines", raw=GOOD_CSV.encode(), token=tok, ctype="text/csv")
        check(code == 200, "clean csv import succeeds")
        check(rep1["inserted"] == 2, "clean import inserts both invoice lines")
        check(rep1["skipped_duplicates"] == [] and rep1["rejected_rows"] == [], "clean import skips and rejects nothing")
        check(rep1["total_rows"] == 2, "import report counts the data rows")
        code, chk = call("GET", "/api/check?from=2026-10-19&to=2026-10-25", token=tok)
        got = {l["courier"]: l["billed_days"] for l in chk["lines"]}
        check(got.get("Karim S.") == 6 and got.get("Mahmoud R.") == 7, "imported lines show up in the check for their period")

        code, rep2 = call("POST", "/api/import/invoice-lines", raw=GOOD_CSV.encode(), token=tok, ctype="text/csv")
        check(code == 200 and rep2["inserted"] == 0, "repeating the same import inserts nothing twice")
        named = sorted((d["office_id"], d["courier_id"], d["from_day"]) for d in rep2["skipped_duplicates"])
        check(named == [(1, 1, "2026-10-19"), (2, 3, "2026-10-19")], "duplicates are named by office, courier and period start")

        code, rep3 = call("POST", "/api/import/invoice-lines", raw=MIXED_CSV.encode(), token=tok, ctype="text/csv")
        check(code == 200, "mixed csv import answers with a report instead of failing whole")
        check(rep3["inserted"] == 1, "the one valid new row in the mixed file is inserted")
        check(rep3["skipped_duplicates"] == [{"office_id": 1, "courier_id": 1, "from_day": "2026-10-05", "to_day": "2026-10-18"}], "the seeded line repeated in the file is named as a duplicate")
        check(len(rep3["rejected_rows"]) == 7, "the seven broken rows are all rejected, none swallowed")
        check(all(isinstance(r["row"], int) and r["row"] >= 2 for r in rep3["rejected_rows"]), "rejected rows carry their csv line number")
        check(all(r["reason"] for r in rep3["rejected_rows"]), "every rejected row says why")
        reasons = " | ".join(r["reason"] for r in rep3["rejected_rows"])
        check("whole numbers" in reasons, "the word instead of a number for billed_days is called out")
        check("YYYY-MM-DD" in reasons, "the day written backwards is called out")
        check("to_day is before from_day" in reasons, "the backwards period is called out")
        check("between 0 and 62" in reasons, "the billed days past the cap are called out")
        check("office_id 99 not found" in reasons, "the unknown office is called out")
        check("courier_id 99 not found" in reasons, "the unknown courier is called out")
        check("does not belong to that office" in reasons, "the courier billed by the wrong office is called out")

        code, body = call("POST", "/api/import/invoice-lines", raw=b"office_id,courier_id\n1,1\n", token=tok, ctype="text/csv")
        check(code == 400, "a csv missing required columns is refused")
        check("billed_days" in body.get("missing_columns", []) and "from_day" in body.get("missing_columns", []), "the missing column names are listed")

        code, body = call("POST", "/api/admin/backup", {}, token=tok)
        check(code == 200, "accountant backup succeeds")
        name = body.get("backup_file", "")
        check(name.startswith("invoices-") and name.endswith(".db"), "backup name is timestamped and named in the reply")
        dest = os.path.join(backup_dir, name)
        check(os.path.exists(dest), "the backup file exists in the configured INV_BACKUP_DIR")
        check(body.get("size") == os.path.getsize(dest) and body["size"] > 0, "reported backup size matches the file")
        bconn = sqlite3.connect(dest)
        integrity = bconn.execute("PRAGMA integrity_check").fetchone()[0]
        backup_count = bconn.execute("SELECT COUNT(*) FROM invoice_lines").fetchone()[0]
        bconn.close()
        check(integrity == "ok", "backup database passes integrity_check")
        live = sqlite3.connect(db_path)
        live_count = live.execute("SELECT COUNT(*) FROM invoice_lines").fetchone()[0]
        live.close()
        check(backup_count == live_count, "backup holds every invoice line the live database holds")

        check(os.path.exists(log_path) and os.path.getsize(log_path) > 0, "the app wrote its rotating log file at INV_LOG_FILE")
        with open(log_path, encoding="utf-8") as fh:
            log_text = fh.read()
        check("backup" in log_text or "import" in log_text, "the log recorded the import or backup work")

        print(f"Invoice checker deepening tests passed ({CHECKS} checks)")
    finally:
        srv.terminate()

if __name__ == "__main__":
    main()
