#!/usr/bin/env python3
# End to end check for the invoice checker. Run: python3 tests/test_api.py
# Expected numbers are worked out by hand in seed.py comments, the api has to agree with the paper, not the other way round.
import json, os, subprocess, sys, time, urllib.request, urllib.error

ROOT = os.path.join(os.path.dirname(__file__), "..")
PORT = "8093"
BASE = f"http://127.0.0.1:{PORT}"
Q = "/api/check?from=2026-10-05&to=2026-10-18"

def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

def main():
    env = dict(os.environ, PORT=PORT)
    subprocess.run([sys.executable, "seed.py"], cwd=os.path.join(ROOT, "backend"), check=True)
    srv = subprocess.Popen([sys.executable, "app.py"], cwd=os.path.join(ROOT, "backend"), env=env)
    try:
        time.sleep(1.2)
        code, _ = call("GET", Q)
        assert code == 401, code
        code, _ = call("POST", "/api/login", {"username": "accounts", "password": "bad"})
        assert code == 401, code
        code, body = call("POST", "/api/login", {"username": "accounts", "password": "demo1234"})
        assert code == 200, body
        tok = body["token"]
        code, settings = call("GET", "/api/settings", token=tok)
        assert settings["day_rate"] == 450.0, settings
        code, check = call("GET", Q, token=tok)
        assert code == 200, check
        by_courier = {l["courier"]: l for l in check["lines"]}
        expected = {
            "Karim S.": (12, 11, 1, 450.0, "overbilled"),
            "Omar E.": (12, 12, 0, 0.0, "ok"),
            "Mahmoud R.": (16, 14, 2, 900.0, "overbilled"),
            "Youssef A.": (9, 10, -1, -450.0, "underbilled"),
            "Hassan M.": (13, 10, 3, 1350.0, "overbilled"),
        }
        for name, (billed, worked, diff, money, flag) in expected.items():
            l = by_courier[name]
            assert (l["billed_days"], l["worked_days"], l["diff_days"], l["diff_money"], l["flag"]) == \
                   (billed, worked, diff, money, flag), (name, l)
        assert by_courier["Karim S."]["present_but_on_leave"] == 2
        assert by_courier["Hassan M."]["present_but_on_leave"] == 3
        assert check["total_overbilled_money"] == 2700.0, check
        offices = {o["office"]: o for o in check["offices"]}
        assert offices["North Gate Office"]["overbilled_money"] == 450.0
        assert offices["Delta Lines"]["overbilled_money"] == 900.0
        assert offices["Sahel Partners"]["overbilled_money"] == 1350.0
        # a narrower range must change the picture: no invoice lines live fully inside it
        code, narrow = call("GET", "/api/check?from=2026-10-06&to=2026-10-17", token=tok)
        assert narrow["lines"] == [] and narrow["total_overbilled_money"] == 0.0, narrow
        # rate change moves the money, not the days
        code, body = call("POST", "/api/settings", {"day_rate": 500}, token=tok)
        assert code == 200, body
        code, check2 = call("GET", Q, token=tok)
        assert check2["total_overbilled_money"] == 3000.0, check2
        # a courier billed by the wrong office is refused
        code, body = call("POST", "/api/invoice-lines",
                          {"office_id": 2, "courier_id": 1, "from_day": "2026-10-05",
                           "to_day": "2026-10-18", "billed_days": 5}, token=tok)
        assert code == 400, body
        with urllib.request.urlopen(BASE + "/") as r:
            assert r.status == 200
        print("Invoice checker api tests passed")
    finally:
        srv.terminate()

if __name__ == "__main__":
    main()
