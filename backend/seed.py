#!/usr/bin/env python3
# Demo seed. The billing period is 2026-10-05 to 2026-10-18, fourteen days.
# Attendance patterns below are written out on purpose so the expected check numbers can be verified by hand.
import os, secrets, sqlite3, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from app import hash_pw, DB

START = date(2026, 10, 5)
DAYS = [START + timedelta(days=i) for i in range(14)]

if os.path.exists(DB):
    os.remove(DB)
conn = sqlite3.connect(DB)
conn.executescript("""
CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, salt TEXT, pw_hash TEXT, role TEXT);
CREATE TABLE offices (id INTEGER PRIMARY KEY, name TEXT, contact TEXT);
CREATE TABLE couriers (id INTEGER PRIMARY KEY, name TEXT, office_id INTEGER);
CREATE TABLE attendance (day TEXT, courier_id INTEGER, present INTEGER, PRIMARY KEY (day, courier_id));
CREATE TABLE leaves (id INTEGER PRIMARY KEY, courier_id INTEGER, from_day TEXT, to_day TEXT, type TEXT);
CREATE TABLE invoice_lines (id INTEGER PRIMARY KEY, office_id INTEGER, courier_id INTEGER,
                            from_day TEXT, to_day TEXT, billed_days INTEGER,
                            UNIQUE(office_id, courier_id, from_day, to_day));
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
""")
salt = secrets.token_bytes(16)
conn.execute("INSERT INTO users VALUES (1, 'accounts', ?, ?, 'accountant')",
             (salt.hex(), hash_pw("demo1234", salt)))
salt = secrets.token_bytes(16)
conn.execute("INSERT INTO users VALUES (2, 'viewer', ?, ?, 'viewer')",
             (salt.hex(), hash_pw("viewer1234", salt)))
conn.execute("INSERT INTO settings VALUES ('day_rate', '450')")
offices = [(1, "North Gate Office", "Mr Hany (invented)"), (2, "Delta Lines", "Mrs Salwa (invented)"),
           (3, "Sahel Partners", "Mr Adham (invented)")]
conn.executemany("INSERT INTO offices VALUES (?, ?, ?)", offices)
couriers = [(1, "Karim S.", 1), (2, "Omar E.", 1), (3, "Mahmoud R.", 2),
            (4, "Youssef A.", 2), (5, "Hassan M.", 3)]
conn.executemany("INSERT INTO couriers VALUES (?, ?, ?)", couriers)

absent = {
    1: {"2026-10-10"},
    2: {"2026-10-06", "2026-10-17"},
    3: set(),
    4: {"2026-10-05", "2026-10-09", "2026-10-14", "2026-10-18"},
    5: {"2026-10-11"},
}
for cid, off_days in absent.items():
    for d in DAYS:
        conn.execute("INSERT INTO attendance VALUES (?, ?, ?)",
                     (d.isoformat(), cid, 0 if d.isoformat() in off_days else 1))
leaves = [
    (1, "2026-10-12", "2026-10-13", "annual"),
    (5, "2026-10-07", "2026-10-09", "sick"),
]
conn.executemany("INSERT INTO leaves (courier_id, from_day, to_day, type) VALUES (?, ?, ?, ?)", leaves)
frm, to = "2026-10-05", "2026-10-18"
lines = [
    (1, 1, frm, to, 12),   # Karim really worked 11, one extra day on the bill
    (1, 2, frm, to, 12),   # Omar is exact
    (2, 3, frm, to, 16),   # Mahmoud worked 14, two extra days
    (2, 4, frm, to, 9),    # Youssef worked 10, the bill is a day short and that gets flagged too
    (3, 5, frm, to, 13),   # Hassan worked 10 once his leave is deducted, three extra days
]
conn.executemany("INSERT INTO invoice_lines (office_id, courier_id, from_day, to_day, billed_days) VALUES (?, ?, ?, ?, ?)", lines)
conn.commit(); conn.close()
print("Seeded", DB)
