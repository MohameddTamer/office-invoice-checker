#!/usr/bin/env python3
# Office invoice checker. The office sends a bill for courier days, we count the days that really happened.
# Worked day means present on the attendance sheet and not on leave that day. Everything else is talk.
import csv, hashlib, hmac, io, json, logging, logging.handlers, os, re, secrets, sqlite3, time
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

def _env_int(name, fallback):
    try:
        return int(os.environ.get(name, "") or fallback)
    except ValueError:
        return fallback

DB = os.environ.get("INV_DB", os.path.join(os.path.dirname(__file__), "invoices.db"))
LOG_FILE = os.environ.get("INV_LOG_FILE", os.path.join(os.path.dirname(__file__), "invoice_checker.log"))
BACKUP_DIR = os.environ.get("INV_BACKUP_DIR", os.path.join(os.path.dirname(__file__), "backups"))
TOKENS = {}
TOKEN_TTL = _env_int("INV_TOKEN_TTL", 8 * 3600)
ADMIN_ROLES = ("accountant", "admin")

LOG = logging.getLogger("invoice_checker")
if not LOG.handlers:
    LOG.setLevel(logging.INFO)
    try:
        _handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        LOG.addHandler(_handler)
    except OSError:
        LOG.addHandler(logging.NullHandler())

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000).hex()

def valid_date(s):
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s or ""))

def parse_day(s):
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)

def worked_days(conn, courier_id, frm, to):
    rows = conn.execute(
        "SELECT day FROM attendance WHERE courier_id=? AND present=1 AND day>=? AND day<=?",
        (courier_id, frm, to)).fetchall()
    leave = conn.execute(
        "SELECT from_day, to_day FROM leaves WHERE courier_id=? AND from_day<=? AND to_day>=?",
        (courier_id, to, frm)).fetchall()
    leave_days = set()
    for lv in leave:
        cur = max(parse_day(lv["from_day"]), parse_day(frm))
        end = min(parse_day(lv["to_day"]), parse_day(to))
        while cur <= end:
            leave_days.add(cur.isoformat())
            cur += timedelta(days=1)
    present = {r["day"] for r in rows}
    return len(present - leave_days), len(present & leave_days)

def compute_check(conn, frm, to, rate):
    lines = conn.execute("""
        SELECT il.*, c.name AS courier, o.name AS office
        FROM invoice_lines il
        JOIN couriers c ON c.id = il.courier_id
        JOIN offices o ON o.id = il.office_id
        WHERE il.from_day >= ? AND il.to_day <= ?
        ORDER BY o.name, c.name
    """, (frm, to)).fetchall()
    out_lines = []
    offices = {}
    for ln in lines:
        worked, on_leave_present = worked_days(conn, ln["courier_id"], ln["from_day"], ln["to_day"])
        diff = ln["billed_days"] - worked
        item = {
            "id": ln["id"], "office": ln["office"], "office_id": ln["office_id"],
            "courier": ln["courier"], "courier_id": ln["courier_id"],
            "from_day": ln["from_day"], "to_day": ln["to_day"],
            "billed_days": ln["billed_days"], "worked_days": worked,
            "present_but_on_leave": on_leave_present,
            "diff_days": diff, "diff_money": round(diff * rate, 2),
            "flag": "overbilled" if diff > 0 else ("underbilled" if diff < 0 else "ok"),
        }
        out_lines.append(item)
        o = offices.setdefault(ln["office"], {"office": ln["office"], "billed_days": 0,
                                               "worked_days": 0, "diff_money": 0.0, "overbilled_money": 0.0})
        o["billed_days"] += ln["billed_days"]
        o["worked_days"] += worked
        o["diff_money"] += item["diff_money"]
        if diff > 0:
            o["overbilled_money"] += item["diff_money"]
    office_list = [{**o, "diff_money": round(o["diff_money"], 2),
                    "overbilled_money": round(o["overbilled_money"], 2)} for o in offices.values()]
    return {
        "from": frm, "to": to, "day_rate": rate,
        "lines": out_lines, "offices": office_list,
        "total_overbilled_money": round(sum(l["diff_money"] for l in out_lines if l["diff_days"] > 0), 2),
        "totals": {"billed_days": sum(l["billed_days"] for l in out_lines),
                   "worked_days": sum(l["worked_days"] for l in out_lines),
                   "diff_money": round(sum(l["diff_money"] for l in out_lines), 2),
                   "line_count": len(out_lines)},
    }

class H(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _session(self):
        tok = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        s = TOKENS.get(tok)
        return s if s and s["expires"] > time.time() else None

    def _auth(self):
        s = self._session()
        return s["user"] if s else None

    def _error(self, code, message):
        return self._send(code, {"error": message, "code": code})

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20000:
            return None
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return None

    def _rate(self, conn, override):
        if override:
            try:
                r = float(override)
                if r > 0:
                    return r
            except ValueError:
                pass
        row = conn.execute("SELECT value FROM settings WHERE key='day_rate'").fetchone()
        return float(row["value"]) if row else 0.0

    def _post_impl(self):
        path = urlparse(self.path).path
        if path in ("/api/import/invoice-lines", "/api/admin/backup"):
            sess = self._session()
            if not sess:
                return self._error(401, "login required")
            if path == "/api/admin/backup":
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                return self._backup(sess)
            return self._import_lines(sess)
        data = self._body()
        if data is None:
            return self._error(400, "bad body")
        if path == "/api/login":
            user = str(data.get("username", ""))[:40]
            pw = str(data.get("password", ""))[:100]
            conn = db()
            row = conn.execute("SELECT * FROM users WHERE username=?", (user,)).fetchone()
            conn.close()
            if not row or not hmac.compare_digest(hash_pw(pw, bytes.fromhex(row["salt"])), row["pw_hash"]):
                return self._error(401, "wrong username or password")
            tok = secrets.token_urlsafe(32)
            TOKENS[tok] = {"user": user, "role": row["role"], "expires": time.time() + TOKEN_TTL}
            return self._send(200, {"token": tok, "user": user, "role": row["role"]})
        if not self._auth():
            return self._error(401, "login required")
        sess = self._session()
        if sess and sess.get("role") == "viewer":
            conn = db(); conn.close()
            return self._error(403, "viewer accounts are read-only")
        conn = db()
        if path == "/api/settings":
            rate = data.get("day_rate")
            if not isinstance(rate, (int, float)) or rate <= 0 or rate > 100000:
                conn.close()
                return self._error(400, "day_rate must be a positive number")
            conn.execute("INSERT INTO settings (key, value) VALUES ('day_rate', ?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(rate),))
            conn.commit(); conn.close()
            return self._send(200, {"ok": True, "day_rate": rate})
        if path == "/api/invoice-lines":
            office_id = data.get("office_id")
            courier_id = data.get("courier_id")
            frm, to = str(data.get("from_day", "")), str(data.get("to_day", ""))
            billed = data.get("billed_days")
            if not valid_date(frm) or not valid_date(to) or parse_day(to) < parse_day(frm):
                conn.close()
                return self._error(400, "a valid from_day and to_day are required")
            if not isinstance(billed, int) or billed < 0 or billed > 62:
                conn.close()
                return self._error(400, "billed_days must be between 0 and 62")
            owner = conn.execute("SELECT office_id FROM couriers WHERE id=?", (courier_id,)).fetchone()
            if not owner:
                conn.close()
                return self._error(404, "courier not found")
            if owner["office_id"] != office_id:
                conn.close()
                return self._error(400, "courier does not belong to that office")
            try:
                cur = conn.execute(
                    "INSERT INTO invoice_lines (office_id, courier_id, from_day, to_day, billed_days) VALUES (?, ?, ?, ?, ?)",
                    (office_id, courier_id, frm, to, billed))
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                return self._error(400, "an invoice line already exists for that courier and period")
            new_id = cur.lastrowid
            conn.close()
            return self._send(201, {"ok": True, "id": new_id})
        conn.close()
        return self._error(404, "not found")

    def _get_impl(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            fpath = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
            with open(fpath, "rb") as fh:
                body = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return self.wfile.write(body)
        if not path.startswith("/api/"):
            return self._error(404, "not found")
        if not self._auth():
            return self._error(401, "login required")
        q = parse_qs(parsed.query)
        conn = db()
        if path == "/api/offices":
            offices = []
            for o in conn.execute("SELECT * FROM offices ORDER BY name"):
                couriers = [dict(c) for c in conn.execute(
                    "SELECT id, name FROM couriers WHERE office_id=? ORDER BY name", (o["id"],))]
                offices.append({**dict(o), "couriers": couriers})
            conn.close()
            return self._send(200, {"offices": offices})
        if path == "/api/settings":
            rate = self._rate(conn, None)
            conn.close()
            return self._send(200, {"day_rate": rate})
        if path == "/api/check":
            frm = (q.get("from") or [""])[0]
            to = (q.get("to") or [""])[0]
            if not valid_date(frm) or not valid_date(to) or parse_day(to) < parse_day(frm):
                conn.close()
                return self._error(400, "from and to dates are required, in order")
            rate = self._rate(conn, (q.get("rate") or [None])[0])
            payload = compute_check(conn, frm, to, rate)
            conn.close()
            return self._send(200, payload)
        if path == "/api/report":
            frm = (q.get("from") or [""])[0]
            to = (q.get("to") or [""])[0]
            if not valid_date(frm) or not valid_date(to) or parse_day(to) < parse_day(frm):
                conn.close()
                return self._error(400, "from and to dates are required, in order")
            rate = self._rate(conn, (q.get("rate") or [None])[0])
            payload = compute_check(conn, frm, to, rate)
            payload["report"] = True
            conn.close()
            return self._send(200, payload)
        if path == "/api/admin/config":
            sess = self._session()
            if not sess or sess.get("role") not in ADMIN_ROLES:
                conn.close()
                return self._error(403, "config is admin only")
            payload = {"token_ttl_seconds": TOKEN_TTL, "db_file": os.path.basename(DB),
                       "log_file": os.path.basename(LOG_FILE), "backup_dir": os.path.basename(BACKUP_DIR)}
            conn.close()
            return self._send(200, payload)
        conn.close()
        return self._error(404, "not found")


    def do_POST(self):
        try:
            self._post_impl()
        except ValueError:
            LOG.exception("bad value in POST %s", self.path)
            self._error(400, "bad value in request")
        except Exception:
            LOG.exception("failed POST %s", self.path)
            self._error(500, "internal error")

    def do_GET(self):
        try:
            self._get_impl()
        except ValueError:
            LOG.exception("bad value in GET %s", self.path)
            self._error(400, "bad value in request")
        except Exception:
            LOG.exception("failed GET %s", self.path)
            self._error(500, "internal error")

    def _backup(self, sess):
        if sess.get("role") not in ADMIN_ROLES:
            return self._error(403, "backup is admin only")
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        name = f"invoices-{stamp}.db"
        dest = os.path.join(BACKUP_DIR, name)
        src = db()
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()
        LOG.info("backup written by %s: %s", sess["user"], name)
        return self._send(200, {"ok": True, "backup_file": name, "size": os.path.getsize(dest)})

    def _import_lines(self, sess):
        if sess.get("role") not in ADMIN_ROLES:
            return self._error(403, "import is admin only")
        n = int(self.headers.get("Content-Length") or 0)
        if n > 500_000:
            return self._error(413, "csv body too large")
        raw = self.rfile.read(n) if n else b""
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return self._error(400, "csv body must be utf-8 text")
        reader = csv.DictReader(io.StringIO(text))
        required = ["office_id", "courier_id", "from_day", "to_day", "billed_days"]
        if reader.fieldnames is None:
            return self._error(400, "empty csv")
        present = [h.strip() for h in reader.fieldnames if h]
        missing = [c for c in required if c not in present]
        if missing:
            return self._send(400, {"error": "missing columns: " + ", ".join(missing),
                                    "code": 400, "missing_columns": missing})
        report = {"inserted": 0, "skipped_duplicates": [], "rejected_rows": [], "total_rows": 0}
        conn = db()
        try:
            for lineno, row in enumerate(reader, start=2):
                vals = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
                if not any(vals.values()):
                    continue
                report["total_rows"] += 1
                try:
                    office_id = int(vals["office_id"]); courier_id = int(vals["courier_id"])
                    billed = int(vals["billed_days"])
                except ValueError:
                    report["rejected_rows"].append(
                        {"row": lineno, "reason": "office_id, courier_id and billed_days must be whole numbers"})
                    continue
                frm, to = vals["from_day"], vals["to_day"]
                if not valid_date(frm) or not valid_date(to):
                    report["rejected_rows"].append(
                        {"row": lineno, "reason": "from_day and to_day must be YYYY-MM-DD dates"})
                    continue
                try:
                    in_order = parse_day(to) >= parse_day(frm)
                except ValueError:
                    in_order = False
                if not in_order:
                    report["rejected_rows"].append({"row": lineno, "reason": "to_day is before from_day"})
                    continue
                if billed < 0 or billed > 62:
                    report["rejected_rows"].append({"row": lineno, "reason": "billed_days must be between 0 and 62"})
                    continue
                if not conn.execute("SELECT id FROM offices WHERE id = ?", (office_id,)).fetchone():
                    report["rejected_rows"].append({"row": lineno, "reason": f"office_id {office_id} not found"})
                    continue
                owner = conn.execute("SELECT office_id FROM couriers WHERE id = ?", (courier_id,)).fetchone()
                if not owner:
                    report["rejected_rows"].append({"row": lineno, "reason": f"courier_id {courier_id} not found"})
                    continue
                if owner["office_id"] != office_id:
                    report["rejected_rows"].append(
                        {"row": lineno, "reason": "courier does not belong to that office"})
                    continue
                if conn.execute("SELECT id FROM invoice_lines WHERE office_id = ? AND courier_id = ?"
                                " AND from_day = ? AND to_day = ?",
                                (office_id, courier_id, frm, to)).fetchone():
                    report["skipped_duplicates"].append(
                        {"office_id": office_id, "courier_id": courier_id, "from_day": frm, "to_day": to})
                    continue
                conn.execute("INSERT INTO invoice_lines (office_id, courier_id, from_day, to_day, billed_days)"
                             " VALUES (?, ?, ?, ?, ?)", (office_id, courier_id, frm, to, billed))
                report["inserted"] += 1
            conn.commit()
        finally:
            conn.close()
        LOG.info("csv import by %s: %s", sess["user"], report)
        return self._send(200, report)

    def log_message(self, *args):
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8083"))
    LOG.info("starting on port %s with db %s", port, DB)
    print(f"Office invoice checker on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
