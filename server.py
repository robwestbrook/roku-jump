"""Roku channel-number jumper.

Phone page -> type a channel number -> this server sends remote-key presses to the
Roku TV (ECP, port 8060) to scroll the Live TV guide to that channel and tune it.

Run:  python3 server.py        (then open http://<this-computer-ip>:8766 on the phone)
"""
import csv, json, os, re, socket, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8766"))
TV_IP = os.environ.get("TV_IP", "192.168.1.146")
PAGE_ROWS = 6          # Fwd / Rev move one screen = 6 rows (measured)
PAGE_DELAY = 0.25      # seconds between Fwd/Rev presses (0.4 verified reliable; 0.25 to beat the guide timeout - verify)
STEP_DELAY = 0.2       # seconds between Up/Down presses (>=0.15 needed; faster drops presses)
DRY_RUN = os.environ.get("DRY_RUN") == "1"

STATE_PATH = os.path.join(HERE, "state.json")
lock = threading.Lock()
status = {"busy": False, "msg": "Ready."}


# ---------- lineup ----------
def load_lineup():
    rows = []
    with open(os.path.join(HERE, "lineup.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({"row": int(r["row"]), "number": int(r["number"]), "name": r["name"]})
    return rows

LINEUP = load_lineup()
ROW_OF = {c["number"]: c["row"] for c in LINEUP}
NUMBERS = sorted(ROW_OF)


# ---------- state ----------
def load_state():
    try:
        return json.load(open(STATE_PATH))
    except Exception:
        return {"current": None, "recent": []}

def save_state(s):
    json.dump(s, open(STATE_PATH, "w"))


# ---------- TV ----------
def key(k):
    if DRY_RUN:
        return
    req = urllib.request.Request(f"http://{TV_IP}:8060/keypress/{k}", method="POST")
    urllib.request.urlopen(req, timeout=5).read()

def press(k, n, delay):
    for _ in range(n):
        key(k)
        time.sleep(0 if DRY_RUN else delay)


# ---------- planning ----------
def plan(current, target):
    """Return list of (key, count, delay) to move the highlight from current to target."""
    delta = ROW_OF[target] - ROW_OF[current]
    steps = []
    if delta == 0:
        return steps
    big, small = ("Fwd", "Down") if delta > 0 else ("Rev", "Up")
    d = abs(delta)
    pages, rem = divmod(d, PAGE_ROWS)
    if pages:
        steps.append((big, pages, PAGE_DELAY))
    if rem:
        steps.append((small, rem, STEP_DELAY))
    return steps

def nearest(n):
    below = [x for x in NUMBERS if x <= n]
    above = [x for x in NUMBERS if x >= n]
    return (below[-1] if below else None, above[0] if above else None)


def run_jump(target, open_guide):
    st = load_state()
    cur = st["current"]
    try:
        if open_guide:
            status["msg"] = "Opening guide..."
            key("Left")                       # opens the overlay on "Top Picks for You"
            time.sleep(0 if DRY_RUN else 1.8)
            key("Down")                       # highlights the channel that is playing now
            time.sleep(0 if DRY_RUN else 1.0)
        steps = plan(cur, target)
        for k, count, delay in steps:
            status["msg"] = f"Moving: {k} x{count}"
            press(k, count, delay)
        status["msg"] = "Tuning channel..."
        time.sleep(0 if DRY_RUN else 0.8)
        key("Select")
        st["current"] = target
        st["recent"] = ([target] + [x for x in st["recent"] if x != target])[:8]
        save_state(st)
        name = next(c["name"] for c in LINEUP if c["number"] == target)
        status["msg"] = f"Done: {target} {name}"
    except Exception as e:
        status["msg"] = f"Failed: {e}"
    finally:
        status["busy"] = False
        lock.release()


# ---------- web ----------
PAGE = open(os.path.join(HERE, "index.html"), encoding="utf-8").read().encode()

class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif u.path == "/lineup.json":
            self._send(200, LINEUP)
        elif u.path == "/state":
            self._send(200, {**load_state(), **status})
        elif u.path == "/status":
            self._send(200, {**status, "current": load_state()["current"]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            n = int(q.get("n", [""])[0])
        except ValueError:
            return self._send(400, {"error": "Enter a channel number."})
        if u.path == "/setcurrent":
            if n not in ROW_OF:
                lo, hi = nearest(n)
                return self._send(400, {"error": f"No channel {n}. Nearest: {lo}, {hi}."})
            st = load_state()
            st["current"] = n
            save_state(st)
            return self._send(200, {"ok": True})
        if u.path == "/go":
            if n not in ROW_OF:
                lo, hi = nearest(n)
                return self._send(400, {"error": f"No channel {n}. Nearest: {lo} or {hi}."})
            st = load_state()
            if st["current"] is None:
                return self._send(400, {"error": "Set the channel you're on now first."})
            if not lock.acquire(blocking=False):
                return self._send(409, {"error": "Already moving. Wait for it to finish."})
            status["busy"] = True
            status["msg"] = "Starting..."
            open_guide = q.get("open", ["1"])[0] == "1"
            threading.Thread(target=run_jump, args=(n, open_guide), daemon=True).start()
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ip = "?"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.1.1", 80))
        ip = s.getsockname()[0]
    except Exception:
        pass
    print(f"Roku jump on http://{ip}:{PORT}  (TV {TV_IP}, dry_run={DRY_RUN})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
