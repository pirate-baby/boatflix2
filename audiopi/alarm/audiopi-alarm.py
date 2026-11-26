#!/usr/bin/env python3
"""audiopi alarm hub: Klaxon relay for allowlisted alarms, float to Signal K.

False alarms are worse than useless here, so the relay closes ONLY for alarms
named in the config's [klaxon] allowlist (and not silenced):
  * http_alarms: names accepted on POST /alarm/<name> (e.g. "anchor" from
    AvNav). Any other name is refused and changes nothing. An "on" holds for
    http_alarm_ttl seconds; the sender must keep re-sending it, so a lost
    "off" (sender died, network down) can't leave the Klaxon stuck on.
  * signalk_paths: exact Signal K notification paths, sounding when their
    state is alarm/emergency with "sound" in method. Default: none.
Nothing else sounds it: not other Signal K notifications, not a missing
plotter, not the floats.

Float switches are published to Signal K as notifications. They never drive
the relay: the float sounds the Klaxon through its own hardwired path.

HTTP API (LAN):
  POST /alarm/<name>   body or ?state= "on" / "off" (allowlisted names only)
  POST /silence        release the relay until a new alarm appears
  GET  /status         JSON

The Klaxon is wired fail-silent (relay NO contact), so every error path ends
with the relay released.
"""
import asyncio
import json
import logging
import signal
import sys
import time
import tomllib

import aiohttp
from aiohttp import web
from gpiozero import Button, OutputDevice

log = logging.getLogger("audiopi-alarm")


def load_config(path):
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    cfg.setdefault("relay_pin", 5)
    cfg.setdefault("debounce", 0.5)
    k = cfg.setdefault("klaxon", {})
    k["http_alarms"] = set(k.get("http_alarms", []))
    k["signalk_paths"] = set(k.get("signalk_paths", []))
    cfg.setdefault("resync_window", 3.0)
    cfg.setdefault("http_alarm_ttl", 30)
    cfg.setdefault("http", {}).setdefault("port", 8080)
    cfg["http"].setdefault("bind", "0.0.0.0")
    cfg.setdefault("floats", [])
    cfg.setdefault("signalk", [])
    return cfg


class Hub:
    def __init__(self, cfg):
        self.cfg = cfg
        # Active-low relay board: initial_value=False keeps the pin HIGH (off).
        self.relay = OutputDevice(cfg["relay_pin"], active_high=False, initial_value=False)
        self.floats = [
            {**f, "button": Button(f["pin"], pull_up=True, bounce_time=None),
             "state": None, "pending": None, "since": 0.0}
            for f in cfg["floats"] if f.get("enabled", True)
        ]
        self.own_paths = {f["path"] for f in cfg["floats"]}
        self.sk_alarms = {}        # path -> message, current Signal K view
        self.http_alarms = {}      # name -> since (epoch)
        self.http_seen = {}        # name -> monotonic time of the last "on"
        self.silenced = set()
        self.last_sk = None        # monotonic time a server was last connected
        self.sk_connected = None   # url of the connected server, if any
        self.ws = None
        self.fresh = None          # alarm view being rebuilt after a (re)connect
        self.resync_until = 0.0

    # ---- alarm state -----------------------------------------------------
    def active(self):
        a = {f"signalk:{p}" for p in self.sk_alarms}
        a |= {f"http:{n}" for n in self.http_alarms}
        return a

    def update_relay(self):
        active = self.active()
        if not active:
            self.silenced.clear()
        elif not active <= self.silenced:
            self.silenced.clear()  # a new alarm lifts the silence
        want = bool(active) and not (active <= self.silenced)
        if want != self.relay.value:
            self.relay.value = want
            log.warning("relay %s: active=%s silenced=%s",
                        "ON" if want else "off", sorted(active), sorted(self.silenced))

    def status(self):
        return {
            "relay": bool(self.relay.value),
            "active": sorted(self.active()),
            "silenced": sorted(self.silenced),
            "signalk": {
                "connected": self.sk_connected,
                "seconds_since_connected": None if self.last_sk is None or self.sk_connected
                else round(time.monotonic() - self.last_sk),
                "alarms": self.sk_alarms,
            },
            "http_alarms": self.http_alarms,
            "klaxon_allowlist": {"http_alarms": sorted(self.cfg["klaxon"]["http_alarms"]),
                                 "signalk_paths": sorted(self.cfg["klaxon"]["signalk_paths"])},
            "floats": {f["name"]: f["state"] for f in self.floats},
        }

    # ---- Signal K --------------------------------------------------------
    @staticmethod
    def sounds(value):
        if not isinstance(value, dict):
            return False
        if value.get("state") not in ("alarm", "emergency"):
            return False
        if "sound" not in (value.get("method") or []):
            return False
        return not (value.get("status") or {}).get("silenced", False)

    def float_delta(self, f):
        on = f["state"] == "high"
        value = {
            "state": "emergency" if on else "normal",
            "method": ["visual", "sound"] if on else [],
            "message": f["message"] if on else f["message_clear"],
        }
        return {"context": "vessels.self",
                "updates": [{"values": [{"path": f["path"], "value": value}]}]}

    async def send_float(self, f):
        if self.ws is None or self.ws.closed or f["state"] is None:
            return
        try:
            await self.ws.send_str(json.dumps(self.float_delta(f)))
        except Exception as e:  # reconnect loop will resend on the next connection
            log.warning("could not publish %s: %s", f["path"], e)

    async def signalk_loop(self):
        servers = self.cfg["signalk"]
        if not servers:
            log.error("no [[signalk]] servers configured")
        i = 0
        # The system resolver (getaddrinfo) handles .local names via mDNS;
        # aiohttp's aiodns resolver, used when aiodns is installed, does not.
        connector = aiohttp.TCPConnector(resolver=aiohttp.ThreadedResolver())
        async with aiohttp.ClientSession(connector=connector) as session:
            while True:
                srv = servers[i % len(servers)] if servers else None
                i += 1
                if srv:
                    try:
                        await self.signalk_session(session, srv)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        log.info("signalk %s: %s", srv["url"], e)
                    finally:
                        if self.sk_connected:
                            self.last_sk = time.monotonic()
                            log.warning("signalk disconnected: %s", srv["url"])
                        self.sk_connected = None
                        self.ws = None
                        self.update_relay()
                await asyncio.sleep(2)

    async def signalk_session(self, session, srv):
        url = srv["url"].rstrip("/") + "/signalk/v1/stream?subscribe=none&sendCachedValues=true"
        headers = {"Authorization": f"Bearer {srv['token']}"} if srv.get("token") else {}
        async with session.ws_connect(url, headers=headers, heartbeat=15,
                                      timeout=aiohttp.ClientWSTimeout(ws_close=5)) as ws:
            self.ws = ws
            self.sk_connected = srv["url"]
            self.last_sk = time.monotonic()
            log.warning("signalk connected: %s", srv["url"])
            await ws.send_str(json.dumps({
                "context": "vessels.self",
                "subscribe": [{"path": "notifications.*", "policy": "instant"}],
            }))
            for f in self.floats:
                await self.send_float(f)
            # Rebuild the alarm view from the server's cached values, keeping
            # the old one until the resync window has passed so a switchover
            # doesn't chop an ongoing alarm.
            self.fresh = {}
            self.resync_until = time.monotonic() + self.cfg["resync_window"]
            try:
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        if msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                            break
                        continue
                    self.last_sk = time.monotonic()
                    target = self.fresh if self.fresh is not None else self.sk_alarms
                    self.apply_delta(json.loads(msg.data), target)
                    self.finish_resync()
                    self.update_relay()
            finally:
                self.fresh = None  # ended during resync: keep the previous view

    def finish_resync(self):
        if self.fresh is not None and time.monotonic() >= self.resync_until:
            self.sk_alarms, self.fresh = self.fresh, None
            log.info("signalk resynced: %d sounding alarm(s)", len(self.sk_alarms))

    def apply_delta(self, msg, target):
        if msg.get("errorMessage") or msg.get("requestId"):
            log.info("signalk: %s", msg)
        for upd in msg.get("updates") or []:
            for v in upd.get("values") or []:
                path = v.get("path", "")
                if path not in self.cfg["klaxon"]["signalk_paths"] or path in self.own_paths:
                    continue
                if self.sounds(v.get("value")):
                    if path not in target:
                        log.warning("signalk alarm: %s %s", path, (v["value"] or {}).get("message"))
                    target[path] = (v["value"] or {}).get("message")
                elif path in target:
                    log.warning("signalk alarm cleared: %s", path)
                    target.pop(path)

    async def resync_tick(self):
        """Finish a pending resync even if the server goes quiet."""
        while True:
            await asyncio.sleep(1)
            self.finish_resync()
            self.expire_http()
            self.update_relay()

    def expire_http(self):
        ttl = self.cfg["http_alarm_ttl"]
        for name, seen in list(self.http_seen.items()):
            if time.monotonic() - seen > ttl:
                log.warning("http alarm expired: %s (no refresh for %ds)", name, ttl)
                self.http_alarms.pop(name, None)
                self.http_seen.pop(name, None)

    # ---- floats ----------------------------------------------------------
    async def float_loop(self):
        while True:
            now = time.monotonic()
            for f in self.floats:
                reading = "high" if f["button"].is_pressed else "clear"
                if reading != f["pending"]:
                    f["pending"], f["since"] = reading, now
                elif reading != f["state"] and now - f["since"] >= self.cfg["debounce"]:
                    first = f["state"] is None
                    f["state"] = reading
                    level = logging.INFO if first and reading == "clear" else logging.WARNING
                    log.log(level, "float %s (GPIO%d): %s", f["name"], f["pin"], reading)
                    await self.send_float(f)
            await asyncio.sleep(0.05)

    # ---- HTTP ------------------------------------------------------------
    async def http_alarm(self, req):
        name = req.match_info["name"]
        if name not in self.cfg["klaxon"]["http_alarms"]:
            log.warning("refused http alarm %r from %s: not in [klaxon] http_alarms", name, req.remote)
            return web.json_response({"error": f"{name!r} is not an allowlisted alarm"}, status=403)
        state = (req.query.get("state") or (await req.text())).strip().lower()
        if state not in ("on", "off"):
            return web.json_response({"error": 'send "on" or "off"'}, status=400)
        if state == "on":
            if name not in self.http_alarms:
                log.warning("http alarm on: %s (from %s)", name, req.remote)
            self.http_alarms.setdefault(name, int(time.time()))
            self.http_seen[name] = time.monotonic()
        elif self.http_alarms.pop(name, None) is not None:
            self.http_seen.pop(name, None)
            log.warning("http alarm off: %s (from %s)", name, req.remote)
        self.update_relay()
        return web.json_response(self.status())

    async def http_silence(self, req):
        self.silenced = self.active()
        log.warning("silenced from %s: %s", req.remote, sorted(self.silenced))
        self.update_relay()
        return web.json_response(self.status())

    async def http_status(self, req):
        return web.json_response(self.status())

    async def serve_http(self):
        app = web.Application()
        app.router.add_post("/alarm/{name}", self.http_alarm)
        app.router.add_post("/silence", self.http_silence)
        app.router.add_get("/status", self.http_status)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        await web.TCPSite(runner, self.cfg["http"]["bind"], self.cfg["http"]["port"]).start()
        log.info("http on %s:%d", self.cfg["http"]["bind"], self.cfg["http"]["port"])


async def main(cfg_path):
    cfg = load_config(cfg_path)
    hub = Hub(cfg)
    tasks = []
    try:
        hub.relay.off()
        await hub.serve_http()
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for s in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(s, stop.set)
        tasks = [asyncio.create_task(c) for c in
                 (hub.signalk_loop(), hub.float_loop(), hub.resync_tick())]
        waiter = asyncio.create_task(stop.wait())
        tasks.append(waiter)
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            if t is not waiter and t.exception():
                raise t.exception()
    finally:
        # Stop everything that touches the relay before releasing it.
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        hub.relay.off()
        hub.relay.close()
        log.info("relay off, exiting")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "/etc/audiopi-alarm/config.toml"))
