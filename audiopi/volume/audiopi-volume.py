#!/usr/bin/env python3
"""audiopi volume: a small LAN web page for the stereo's volume.

Serves http://audiopi.local/ with a master slider and mute for the stereo
(PipeWire's default sink) and one slider and mute per connected stream
(boatflix's MPD, salonviewscreen, ...). Talks to PipeWire through pactl, so it
runs as the audiopi user with that user's XDG_RUNTIME_DIR.

Volumes are capped at 100%: no software boost past unity.

API:
  GET  /api/state                         {"master": {...}, "streams": [...]}
  POST /api/volume  {"id": "master"|N, "volume": 0-100}
  POST /api/mute    {"id": "master"|N, "muted": true|false}
"""
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 80


def pactl(*args, as_json=False):
    cmd = ["pactl"] + (["-f", "json"] if as_json else []) + list(args)
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=True).stdout
    return json.loads(out) if as_json else out


def percent(vol):
    vals = [int(c["value_percent"].rstrip("%")) for c in vol.values()]
    return round(sum(vals) / len(vals)) if vals else 0


def state():
    default = pactl("get-default-sink").strip()
    sinks = pactl("list", "sinks", as_json=True)
    sink = next((s for s in sinks if s["name"] == default), None)
    master = None
    if sink:
        master = {"id": "master", "name": "Stereo", "volume": percent(sink["volume"]),
                  "muted": sink["mute"]}
    streams = []
    for s in pactl("list", "sink-inputs", as_json=True):
        p = s.get("properties", {})
        host = p.get("application.process.host", "")
        app = p.get("application.name", "")
        if app == "PipeWire" and "Tunnel" in p.get("media.name", ""):
            app = "PipeWire tunnel"
        streams.append({"id": s["index"], "name": host or app or f"stream {s['index']}",
                        "detail": app if host else p.get("media.name", ""),
                        "volume": percent(s["volume"]), "muted": s["mute"],
                        "corked": s.get("corked", False)})
    streams.sort(key=lambda x: x["name"])
    return {"master": master, "streams": streams}


def set_volume(target, vol):
    vol = max(0, min(100, int(vol)))
    if target == "master":
        pactl("set-sink-volume", "@DEFAULT_SINK@", f"{vol}%")
    else:
        pactl("set-sink-input-volume", str(int(target)), f"{vol}%")


def set_mute(target, muted):
    flag = "1" if muted else "0"
    if target == "master":
        pactl("set-sink-mute", "@DEFAULT_SINK@", flag)
    else:
        pactl("set-sink-input-mute", str(int(target)), flag)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>audiopi volume</title>
<style>
  :root {
    --bg: #101418; --card: #1a2027; --text: #e8edf2; --muted: #8a96a3;
    --accent: #4fa3e0; --track: #2c353f; --danger: #e06c5f;
  }
  @media (prefers-color-scheme: light) {
    :root { --bg: #f2f4f6; --card: #ffffff; --text: #1a2027; --muted: #5d6874;
            --accent: #1f74b8; --track: #dde2e7; --danger: #c2453a; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 16px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 34rem; margin: 0 auto; padding: 1.25rem 1rem 3rem; }
  h1 { font-size: 1.1rem; font-weight: 600; margin: 0 0 1rem; color: var(--muted); }
  h2 { font-size: .8rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
       color: var(--muted); margin: 1.75rem 0 .6rem; }
  .card { background: var(--card); border-radius: 14px; padding: 1rem 1rem 1.1rem; margin-bottom: .75rem; }
  .row { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; }
  .name { font-weight: 600; }
  .master .name { font-size: 1.25rem; }
  .detail { color: var(--muted); font-size: .85rem; }
  .pct { font-variant-numeric: tabular-nums; color: var(--muted); min-width: 3.5ch; text-align: right; }
  .master .pct { font-size: 1.25rem; color: var(--text); }
  .controls { display: flex; align-items: center; gap: .85rem; margin-top: .7rem; }
  input[type=range] { flex: 1; min-width: 0; height: 2.75rem; margin: 0; accent-color: var(--accent); background: transparent; }
  button { font: inherit; font-size: .9rem; min-width: 5.2rem; min-height: 2.75rem; border-radius: 10px;
           border: 1px solid var(--track); background: transparent; color: var(--text); cursor: pointer; }
  button[aria-pressed=true] { background: var(--danger); border-color: var(--danger); color: #fff; }
  .muted input[type=range] { opacity: .45; }
  .empty, .status { color: var(--muted); font-size: .9rem; }
  .status { margin-top: 1.5rem; min-height: 1.4em; }
  .status.err { color: var(--danger); }
</style>
</head>
<body>
<main>
  <h1>audiopi</h1>
  <div id="master"></div>
  <h2>Sources</h2>
  <div id="streams"></div>
  <div class="status" id="status" role="status"></div>
</main>
<script>
const $ = (id) => document.getElementById(id);
let dragging = null;          // id of the slider being dragged: don't overwrite it
const pending = {};           // id -> timer for throttled volume sends

function card(s, isMaster) {
  const el = document.createElement("div");
  el.className = "card" + (isMaster ? " master" : "") + (s.muted ? " muted" : "");
  el.dataset.id = s.id;
  el.innerHTML = `
    <div class="row"><div><div class="name"></div><div class="detail"></div></div>
      <div class="pct"></div></div>
    <div class="controls">
      <input type="range" min="0" max="100" step="1">
      <button type="button"></button>
    </div>`;
  el.querySelector(".name").textContent = s.name;
  el.querySelector(".detail").textContent = s.detail || "";
  const range = el.querySelector("input");
  range.setAttribute("aria-label", s.name + " volume");
  range.addEventListener("pointerdown", () => dragging = String(s.id));
  range.addEventListener("input", () => {
    el.querySelector(".pct").textContent = range.value + "%";
    clearTimeout(pending[s.id]);
    pending[s.id] = setTimeout(() => send("/api/volume", {id: s.id, volume: +range.value}), 120);
  });
  range.addEventListener("change", () => {
    dragging = null;
    clearTimeout(pending[s.id]);
    send("/api/volume", {id: s.id, volume: +range.value});
  });
  const btn = el.querySelector("button");
  btn.addEventListener("click", () => send("/api/mute", {id: s.id, muted: btn.getAttribute("aria-pressed") !== "true"}).then(refresh));
  update(el, s);
  return el;
}

function update(el, s) {
  el.classList.toggle("muted", s.muted);
  const btn = el.querySelector("button");
  btn.textContent = s.muted ? "Muted" : "Mute";
  btn.setAttribute("aria-pressed", s.muted);
  if (dragging !== String(s.id)) {
    el.querySelector("input").value = s.volume;
    el.querySelector(".pct").textContent = s.volume + "%";
  }
}

function render(box, items, isMaster) {
  const seen = new Set();
  for (const s of items) {
    seen.add(String(s.id));
    const el = box.querySelector(`[data-id="${s.id}"]`);
    if (el) update(el, s); else box.appendChild(card(s, isMaster));
  }
  for (const el of [...box.querySelectorAll(".card")]) if (!seen.has(el.dataset.id)) el.remove();
  const empty = box.querySelector(".empty");
  if (!items.length && !empty && !isMaster) box.insertAdjacentHTML("beforeend", '<div class="empty">Nothing is playing to audiopi.</div>');
  if (items.length && empty) empty.remove();
}

function status(msg, err) { const s = $("status"); s.textContent = msg || ""; s.classList.toggle("err", !!err); }

async function send(url, body) {
  try {
    const r = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    if (!r.ok) throw new Error((await r.json()).error || r.statusText);
    status("");
  } catch (e) { status("Couldn't change it: " + e.message, true); }
}

async function refresh() {
  try {
    const r = await fetch("/api/state");
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || r.statusText);
    render($("master"), d.master ? [d.master] : [], true);
    render($("streams"), d.streams, false);
    status("");
  } catch (e) { status("Can't reach audiopi's audio: " + e.message, true); }
}

refresh();
setInterval(() => { if (!document.hidden) refresh(); }, 2000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self.reply(200, PAGE, "text/html; charset=utf-8")
        if self.path == "/api/state":
            try:
                return self.reply(200, state())
            except Exception as e:
                return self.reply(503, {"error": str(e)})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
            target = body["id"]
            if target != "master" and not isinstance(target, int):
                raise ValueError("id must be \"master\" or a stream number")
            if self.path == "/api/volume":
                set_volume(target, body["volume"])
            elif self.path == "/api/mute":
                set_mute(target, bool(body["muted"]))
            else:
                return self.reply(404, {"error": "not found"})
            self.reply(200, {"ok": True})
        except subprocess.CalledProcessError as e:
            self.reply(409, {"error": (e.stderr or "pactl failed").strip()})
        except (KeyError, ValueError, TypeError) as e:
            self.reply(400, {"error": str(e)})

    def log_message(self, fmt, *args):
        if self.command == "POST":
            sys.stdout.write("%s %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
