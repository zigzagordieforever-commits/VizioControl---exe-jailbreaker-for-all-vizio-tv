"""
Vizio Control v2 - one-window desktop app for Vizio SmartCast TVs.

From get-air/vizio (+ pyvizio / openHAB research):
  discovery, PIN pairing, remote, inputs, settings (HASHVAL-safe), apps, Conjure URL launch.
New in v2:
  * App launching fixed: merges Vizio's two cloud catalogs, always sends MESSAGE,
    tries NAME_SPACE/MESSAGE variants and verifies with /app/current.
  * "Vizio OS": a TV-friendly home page served from this PC, with a virtual cursor,
    a proxy browser, and live control from the PC (mouse/keyboard pad) or the remote.
  * Banners / full-screen messages pushed to the TV page.
  * Settings editor, volume slider, sleep timer, custom app configs.
Standard library only.
"""
import json
import os
import queue
import random
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import struct
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

APP_NAME = "VizioControl"
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
PROFILES_FILE = os.path.join(DATA_DIR, "profiles.json")
SITES_DIR = os.path.join(DATA_DIR, "sites")
CATALOG_URLS = [
    "https://scfs.vizio.com/appservice/vizio_apps_prod.json",
    "https://scfs.vizio.com/appservice/app_availability_prod.json",
]
PORTS = (7345, 9000)
CONJURE_APP_ID, CONJURE_NS = "17", 4
HUB_PORT = 4173    # Vizio OS page + SSE + proxy
SITE_PORT = 4174   # plain static hosting (folders / GitHub repos)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
SETTINGS_BASE = "/menu_native/dynamic/tv_settings/"

KEYS = {
    "Power On": (11, 1), "Power Off": (11, 0), "Power Toggle": (11, 2),
    "Vol +": (5, 1), "Vol -": (5, 0), "Mute": (5, 4),
    "Ch +": (8, 1), "Ch -": (8, 0), "Prev Ch": (8, 2),
    "Up": (3, 8), "Down": (3, 0), "Left": (3, 1), "Right": (3, 7), "OK": (3, 2),
    "Back": (4, 0), "Home": (4, 15), "Menu": (4, 8), "Info": (4, 6),
    "Exit": (9, 0), "SmartCast": (4, 3), "Input": (7, 1),
    "Rewind": (2, 1), "Play": (2, 3), "Pause": (2, 2), "FF": (2, 0),
}

# Used only when the cloud catalogs can't be reached (values from pyvizio/openHAB data).
BUILTIN_APPS = {
    "Netflix": [{"APP_ID": "1", "NAME_SPACE": 3, "MESSAGE": "None"}],
    "YouTube": [{"APP_ID": "1", "NAME_SPACE": 5, "MESSAGE": "None"}],
    "Hulu": [{"APP_ID": "3", "NAME_SPACE": 4, "MESSAGE": None}],
    "Plex": [{"APP_ID": "9", "NAME_SPACE": 4, "MESSAGE": "https://plex.tv/web/tv/vizio-smartcast"},
             {"APP_ID": "9", "NAME_SPACE": 2, "MESSAGE": "None"}],
    "CBS News": [{"APP_ID": "42", "NAME_SPACE": 2, "MESSAGE": "None"}],
    "Crackle": [{"APP_ID": "5", "NAME_SPACE": 4, "MESSAGE": None},
                {"APP_ID": "5", "NAME_SPACE": 2, "MESSAGE": "None"}],
}

# TV-friendly web pages made by other people (not verified on every Vizio firmware).
TV_PRESETS = [
    "https://www.youtube.com/tv",
    "https://plex.tv/web/tv/vizio-smartcast",
    "https://pluto.tv",
    "https://www.twitch.tv",
]


# ----------------------------------------------------------------- protocol
class TVError(Exception):
    pass


_VERBOSE = [False]


def store_verbose():
    return _VERBOSE[0]


def norm_host(host):
    host = host.strip().replace("https://", "").replace("http://", "").rstrip("/")
    if ":" not in host:
        host += ":7345"
    return host


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


LOGO_B64 = "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"
import collections
import itertools
import contextlib
import traceback
import io

APP_VERSION = "1.1.1"
CAPTURE_DIR = os.path.join(DATA_DIR, "captures")
PLUGIN_DIR = os.path.join(DATA_DIR, "plugins")
_SEQ = itertools.count(1)
TRAFFIC = collections.deque(maxlen=3000)   # every packet/request this app sends to or gets from the TV
NOISE = ("/events", "/stream", "/screen.img", "/screen.png", "/api/tiles", "/adcheck")
PROBE_PORTS = [22, 23, 80, 443, 1900, 5555, 6466, 6467, 7345, 8008, 8009, 8060, 8443, 9000, 9080]
APP_CATS = [
    ("Streaming video", ("netflix", "youtube", "hulu", "disney", "prime", "amazon", "max", "hbo", "peacock", "paramount",
                         "apple", "tubi", "pluto", "vudu", "crackle", "plex", "discovery", "starz", "showtime",
                         "crunchyroll", "freevee", "mubi", "criterion", "cbs", "nbc", "abc", "fox", "roku", "tv")),
    ("Live TV & sports", ("espn", "fubo", "sling", "philo", "cnn", "news", "sport", "mlb", "nfl", "nba", "nhl", "dazn", "live")),
    ("Music & audio", ("spotify", "pandora", "iheart", "tidal", "music", "radio", "tunein", "podcast", "audio")),
    ("Games & kids", ("game", "twitch", "kid", "pbs", "cartoon", "nick")),
]
EXTRA_KEYS = {"CC": (4, 4), "Mute On": (5, 3), "Mute Off": (5, 2)}
KEYS.update(EXTRA_KEYS)
DEFAULT_KEYMAP = {"Up": "Up", "Down": "Down", "Left": "Left", "Right": "Right", "Return": "OK", "Escape": "Back",
                  "BackSpace": "Back", "Home": "Home", "m": "Mute", "plus": "Vol +", "equal": "Vol +", "minus": "Vol -",
                  "Prior": "Ch +", "Next": "Ch -", "space": "Play", "p": "Power Toggle", "i": "Info", "F1": "Menu",
                  "F2": "Input", "F3": "SmartCast", "F4": "Exit"}
DEFAULT_MACROS = {
    "Goodnight": ["log:Goodnight", "key:Power Off"],
    "Movie night": ["key:Power On", "wait:4", "key:Home", "wait:1", "app:Netflix"],
    "Game mode": ["key:Power On", "wait:3", "input:HDMI-1"],
    "Quiet": ["key:Vol -", "key:Vol -", "key:Vol -", "key:Vol -", "key:Vol -"],
}

TOOL_GUIDE = """TOOL MAKER - ADVANCED GUIDE
============================
A tool/plugin is a .py file in %APPDATA%\\VizioControl\\plugins, loaded at startup and on 'Save & run'.
It must define: def register(ctx): ...   ctx is passed in; use it for everything (never import this app's module).

CTX API
  ctx.tv()                 -> connected TV object or None (check before using)
  ctx.log(msg)              -> prints to the main log box
  ctx.key(name)             -> presses a named remote key, e.g. ctx.key("Vol +")  (see ctx.KEYS for all names)
  ctx.request(method, path, body=None)  -> raw TV API call, e.g. ctx.request("GET", "/app/current")
  ctx.launch_url(url)       -> opens a URL on the TV via Vizio OS
  ctx.add_button(label, fn) -> adds a button to the Tools tab; fn runs in a background thread automatically
  ctx.hub                   -> the Hub object (Vizio OS server): ctx.hub.broadcast({...}) sends to the TV page
  ctx.store                 -> the saved-settings dict (persisted automatically after your plugin returns)
  ctx.TV                    -> the TV class itself, if you want to open a second connection or subclass it
  ctx.KEYS                  -> dict of all {name: (codeset, code)} remote keys

WRITING TO THE TV PAGE (banners, custom overlays)
  ctx.hub.broadcast({"t": "banner", "title": "Hi", "text": "From my plugin", "kind": "info", "pos": "top", "secs": 5})

CHANGING APP BEHAVIOUR AT RUNTIME
  Your plugin runs in the same process, so you can monkeypatch anything, e.g.:
    def register(ctx):
        orig = ctx.TV.key
        def traced(self, name):
            ctx.log("key pressed: " + name)
            return orig(self, name)
        ctx.TV.key = traced

EXAMPLE: a tool that nudges volume to a target level
    def register(ctx):
        def normalize():
            tv = ctx.tv()
            if not tv:
                return ctx.log("Connect to a TV first")
            for _ in range(5):
                tv.key("Vol -")
            ctx.log("Volume reset to a known baseline")
        ctx.add_button("Normalize volume", normalize)

DEBUGGING A TOOL
  Use the Developer > Console tab: it shares the same process, so 'tv', 'hub' and 'store' are already there,
  and you can paste snippets before saving them into a plugin file.

LIMITS
  Plugins run with full Python access (no sandbox) - only install tools from sources you trust.
  A plugin that raises an exception is skipped with the traceback logged; fix it and 'Save & run' again.
"""

PLUGIN_TEMPLATE = '''# Vizio Control plugin. Saved in the plugins folder, loaded at startup (Tool Maker tab: Run).
# ctx.tv() -> connected TV or None | ctx.log(msg) | ctx.key("Vol +") | ctx.request("GET", "/app/current")
# ctx.launch_url(url) | ctx.hub | ctx.store | ctx.TV (class: monkeypatch it to change app behavior)
# ctx.add_button(label, fn) puts a button in the Tools tab.
def register(ctx):
    def hello():
        ctx.log("Hello from my tool. Current app: %s" % ctx.request("GET", "/app/current"))
    ctx.add_button("Hello tool", hello)
'''


def bmp_bytes(w, h, bgr):
    """Uncompressed top-down 24-bit BMP. Screen capture is already BGR, so no per-pixel work at all."""
    n = len(bgr)
    return (b"BM" + struct.pack("<IHHI", 54 + n, 0, 0, 54)
            + struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 24, 0, n, 2835, 2835, 0, 0) + bgr)


def ssdp_dump(wait=3.0):
    msg = (b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n')
    out, end = [], time.time() + wait
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
        sk.settimeout(0.5)
        sk.sendto(msg, ("239.255.255.250", 1900))
        while time.time() < end:
            try:
                data, addr = sk.recvfrom(4096)
                out.append((addr[0], data.decode("utf-8", "replace")))
            except socket.timeout:
                pass
            except OSError:
                break
    return out


def probe_ports(ip, ports=PROBE_PORTS):
    def one(p):
        with socket.socket() as s:
            s.settimeout(0.5)
            return p, s.connect_ex((ip, p)) == 0
    with ThreadPoolExecutor(16) as ex:
        return [p for p, ok in ex.map(one, ports) if ok]


def mask(tok):
    return (tok[:3] + "…" + tok[-2:]) if tok and len(tok) > 6 else "…"


FMT_CHOICES = {"None (raw, fastest)": "bmp", "Fast PNG (lossless, compressed)": "png", "JPEG (needs Pillow)": "jpg"}


def encode_frame(w, h, bgr, fmt):
    if fmt == "bmp":
        return bmp_bytes(w, h, bgr), "image/bmp"
    if fmt == "jpg":
        try:
            from PIL import Image
            b = BytesIO()
            Image.frombytes("RGB", (w, h), bgr, "raw", "BGR").save(b, "JPEG", quality=82)
            return b.getvalue(), "image/jpeg"
        except Exception:
            pass
    rgb = bytearray(bgr)
    rgb[0::3], rgb[2::3] = bgr[2::3], bgr[0::3]
    return png_bytes(w, h, bytes(rgb)), "image/png"



class TV:
    """SmartCast client. Certificate relaxation is used only for the TV's own host."""

    def __init__(self, host, token=None):
        self.host = norm_host(host)
        self.token = token
        self.ctx = _ctx()
        self.lock = threading.Lock()

    @property
    def ip(self):
        return self.host.split(":")[0]

    def request(self, method, path, body=None, timeout=6):
        t0 = time.time()
        rec = {"id": next(_SEQ), "t": t0, "dir": "PC→TV", "method": method, "url": f"https://{self.host}{path}",
               "req": body, "token": self.token}
        try:
            res = self._request(method, path, body, timeout)
            rec.update(status="OK", resp=res)
            return res
        except Exception as e:
            rec.update(status="ERR", resp=str(e))
            raise
        finally:
            rec["ms"] = int((time.time() - t0) * 1000)
            TRAFFIC.append(rec)

    def key_raw(self, codeset, code, action="KEYPRESS"):
        self.request("PUT", "/key_command/", {"KEYLIST": [{"CODESET": codeset, "CODE": code, "ACTION": action}]})

    def type_text(self, text):
        # codeset 0 + ASCII code types characters into the TV's on-screen keyboard fields
        self.request("PUT", "/key_command/", {"KEYLIST": [{"CODESET": 0, "CODE": ord(c), "ACTION": "KEYPRESS"} for c in text]})

    def _request(self, method, path, body=None, timeout=6):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"https://{self.host}{path}", data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("AUTH", self.token)
        with self.lock:
            try:
                with urllib.request.urlopen(req, timeout=timeout, context=self.ctx) as r:
                    raw = r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", "replace")
                try:
                    j = json.loads(raw)
                    res = j.get("STATUS", {}).get("DETAIL") or j.get("STATUS", {}).get("RESULT")
                    raise TVError(f"HTTP {e.code}: {res}")
                except ValueError:
                    raise TVError(f"HTTP {e.code}")
            except (urllib.error.URLError, socket.timeout, OSError) as e:
                raise TVError(f"Can't reach TV: {getattr(e, 'reason', e)}")
        try:
            j = json.loads(raw)
        except ValueError:
            raise TVError("TV sent a non-JSON reply")
        st = j.get("STATUS", {})
        result = str(st.get("RESULT", "SUCCESS")).upper()
        if result != "SUCCESS":
            raise TVError(f"{result}: {st.get('DETAIL', '')}".strip(": "))
        return j

    def begin_pair(self, device_id, device_name):
        j = self.request("PUT", "/pairing/start", {"DEVICE_NAME": device_name, "DEVICE_ID": device_id})
        return j["ITEM"]["PAIRING_REQ_TOKEN"]

    def finish_pair(self, challenge, pin, device_id):
        j = self.request("PUT", "/pairing/pair", {
            "DEVICE_ID": device_id, "CHALLENGE_TYPE": 1,
            "RESPONSE_VALUE": str(pin).strip(), "PAIRING_REQ_TOKEN": challenge})
        self.token = j["ITEM"]["AUTH_TOKEN"]
        return self.token

    def key(self, name):
        cs, code = KEYS[name]
        self.request("PUT", "/key_command/", {"KEYLIST": [{"CODESET": cs, "CODE": code, "ACTION": "KEYPRESS"}]})

    def power_state(self):
        return self.request("GET", "/state/device/power_mode")["ITEMS"][0]["VALUE"] == 1

    def device_info(self):
        return self.request("GET", "/state/device/deviceinfo")

    def inputs(self):
        j = self.request("GET", SETTINGS_BASE + "devices/name_input")
        out = []
        for it in j.get("ITEMS", []):
            v = it.get("VALUE")
            name = (v.get("NAME") if isinstance(v, dict) else None) or it.get("NAME") or it.get("CNAME")
            out.append((name, it.get("CNAME")))
        return out

    def current_input(self):
        it = self.request("GET", SETTINGS_BASE + "devices/current_input")["ITEMS"][0]
        return it.get("VALUE"), it.get("HASHVAL")

    def set_input(self, cname):
        _, h = self.current_input()  # always a fresh hash
        self.request("PUT", SETTINGS_BASE + "devices/current_input",
                     {"REQUEST": "MODIFY", "VALUE": cname, "HASHVAL": h})

    # settings: fresh HASHVAL each write, one retry on HASHVAL errors
    def get_setting(self, section, name=None):
        path = SETTINGS_BASE + section + ("/" + name if name else "")
        return self.request("GET", path)

    def set_setting(self, section, name, value):
        path = SETTINGS_BASE + section + "/" + name
        for attempt in (0, 1):
            h = self.request("GET", path)["ITEMS"][0].get("HASHVAL")
            try:
                self.request("PUT", path, {"REQUEST": "MODIFY", "VALUE": value, "HASHVAL": h})
                return
            except TVError as e:
                if "HASHVAL" in str(e).upper() and attempt == 0:
                    continue
                raise

    # apps: MESSAGE is ALWAYS sent (null when unused) - the TV rejects configs without it
    def launch(self, cfg):
        self.request("PUT", "/app/launch", {"VALUE": {
            "NAME_SPACE": int(cfg["NAME_SPACE"]), "APP_ID": str(cfg["APP_ID"]),
            "MESSAGE": cfg.get("MESSAGE")}})

    def launch_url(self, url):
        self.launch({"APP_ID": CONJURE_APP_ID, "NAME_SPACE": CONJURE_NS, "MESSAGE": url})

    def current_app(self):
        return self.request("GET", "/app/current").get("ITEM", {}).get("VALUE")


def probe(host, timeout=1.2):
    try:
        req = urllib.request.Request(f"https://{host}/state/device/deviceinfo")
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
            json.loads(r.read().decode("utf-8", "replace"))
        return True
    except urllib.error.HTTPError as e:
        try:
            return "STATUS" in json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return False
    except Exception:
        return False


def local_ip(target="8.8.8.8"):
    """The PC address that routes toward `target` (so the TV can reach us)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target, 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def ssdp_hosts(wait=3.0):
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\n"
           "MX: 2\r\nST: urn:dial-multiscreen-org:service:dial:1\r\n\r\n").encode()
    found = set()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.5)
    try:
        s.sendto(msg, ("239.255.255.250", 1900))
        end = time.time() + wait
        while time.time() < end:
            try:
                _, addr = s.recvfrom(4096)
                found.add(addr[0])
            except socket.timeout:
                pass
            except OSError:
                break
    except OSError:
        pass
    finally:
        s.close()
    return found


def discover(progress=None):
    ips = set(ssdp_hosts())
    me = local_ip()
    prefix = ".".join(me.split(".")[:3])
    ips.update(f"{prefix}.{i}" for i in range(1, 255))
    ips.discard(me)
    cands = [f"{ip}:{p}" for ip in sorted(ips, key=lambda x: tuple(map(int, x.split("."))))
             for p in PORTS]
    found, done = [], [0]

    def work(h):
        ok = probe(h)
        done[0] += 1
        if progress and done[0] % 100 == 0:
            progress(f"Scanning... {done[0]}/{len(cands)}")
        return h if ok else None

    with ThreadPoolExecutor(max_workers=96) as ex:
        for r in ex.map(work, cands):
            if r:
                found.append(r)
    return found


# ------------------------------------------------------------- app catalog
def _get_json(url):
    for u in (url, url.replace("https://", "http://")):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=8) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception:
            continue
    return None


def _norm_id(v):
    if isinstance(v, list):
        v = v[0] if v else None
    return None if v is None else str(v)


def _collect(node, name, ids, out):
    """Walk any JSON shape and collect (name, id, config) for dicts holding APP_ID+NAME_SPACE."""
    if isinstance(node, list):
        for x in node:
            _collect(x, name, ids, out)
    elif isinstance(node, dict):
        n = node["name"] if isinstance(node.get("name"), str) else name
        i = _norm_id(node.get("id")) or ids
        if "APP_ID" in node and "NAME_SPACE" in node:
            try:
                out.append((n, i, {"APP_ID": str(node["APP_ID"]), "NAME_SPACE": int(node["NAME_SPACE"]),
                                   "MESSAGE": node.get("MESSAGE")}))
            except (TypeError, ValueError):
                pass
        else:
            for v in node.values():
                if isinstance(v, (list, dict)):
                    _collect(v, n, i, out)


def _collect_names(node, names):
    if isinstance(node, list):
        for x in node:
            _collect_names(x, names)
    elif isinstance(node, dict):
        i = _norm_id(node.get("id"))
        if i and isinstance(node.get("name"), str):
            names[i] = node["name"]
        for v in node.values():
            if isinstance(v, (list, dict)):
                _collect_names(v, names)


def _add_cfg(apps, name, cfg):
    lst = apps.setdefault(name, [])
    if cfg not in lst:
        lst.append(cfg)


def fetch_catalog():
    """Returns {app name: [config, ...]}. Vizio splits ids/names and NAME_SPACE/MESSAGE across two files."""
    names, found = {}, []
    for url in CATALOG_URLS:
        data = _get_json(url)
        if data is not None:
            _collect(data, None, None, found)
            _collect_names(data, names)
    apps = {}
    for n, i, cfg in found:
        name = n or names.get(i or "")
        if name:
            _add_cfg(apps, name, cfg)
    for n, cfgs in BUILTIN_APPS.items():
        for c in cfgs:
            _add_cfg(apps, n, dict(c))
    return apps


def candidate_configs(cfgs, preferred=None):
    """Ordered launch attempts: known configs, MESSAGE null/'None' variants, then NAME_SPACE +-1."""
    out = []

    def add(c):
        c = {"APP_ID": str(c["APP_ID"]), "NAME_SPACE": int(c["NAME_SPACE"]), "MESSAGE": c.get("MESSAGE")}
        if c not in out:
            out.append(c)

    if preferred:
        add(preferred)
    for c in cfgs:
        m = c.get("MESSAGE")
        for mm in [m] + (["None"] if m is None else [None] if m == "None" else []):
            add({**c, "MESSAGE": mm})
    for c in cfgs:
        m = c.get("MESSAGE")
        for d in (-1, 1):
            if int(c["NAME_SPACE"]) + d >= 0:
                for mm in [m] + (["None"] if m is None else [None] if m == "None" else []):
                    add({**c, "NAME_SPACE": int(c["NAME_SPACE"]) + d, "MESSAGE": mm})
    return out[:12]


def launch_verified(tv, cfgs, preferred=None, log=print, wait=3.5):
    """Try configs until /app/current reports the app. Returns the working config or None."""
    for cfg in candidate_configs(cfgs, preferred):
        log(f"Trying APP_ID={cfg['APP_ID']} NAME_SPACE={cfg['NAME_SPACE']} MESSAGE={cfg['MESSAGE']!r}")
        tv.launch(cfg)
        t0 = time.time()
        while time.time() - t0 < wait:
            time.sleep(1.0)
            try:
                cur = tv.current_app()
            except TVError:
                continue
            if cur and str(cur.get("APP_ID")) == cfg["APP_ID"]:
                return cfg
    return None


# ------------------------------------------------------------------- ad blocker
FILTER_LISTS = [
    "https://easylist.to/easylist/easylist.txt",
    "https://easylist.to/easylist/easyprivacy.txt",
    "https://ublockorigin.github.io/uAssets/filters/filters.txt",
]
ADBLOCK_CACHE = os.path.join(DATA_DIR, "adblock.json")
BUILTIN_AD_DOMAINS = {
    "doubleclick.net", "googlesyndication.com", "googleadservices.com", "adservice.google.com",
    "adnxs.com", "taboola.com", "outbrain.com", "amazon-adsystem.com", "scorecardresearch.com",
    "criteo.com", "pubmatic.com", "rubiconproject.com", "moatads.com", "adsrvr.org", "2mdn.net",
}


class AdBlock:
    """uBlock-style blocking for pages shown through Vizio OS: EasyList-format filter lists
    (||domain^ network rules + generic ##selector hiding rules)."""

    def __init__(self):
        self.domains = set(BUILTIN_AD_DOMAINS)
        self.selectors = []
        self.enabled = True

    def load_cache(self):
        try:
            with open(ADBLOCK_CACHE, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.domains |= set(d.get("domains", []))
            self.selectors = d.get("selectors", [])
        except Exception:
            pass

    def parse(self, text):
        doms, sels = set(), []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("||"):
                m = re.match(r"^\|\|([a-z0-9.-]+)\^(\$[^,]*(,[^,]*)*)?$", line)
                if m and "domain=" not in line and "~" not in line and "." in m.group(1):
                    doms.add(m.group(1))
            elif line.startswith("##") and len(line) < 120:
                sel = line[2:]
                if not any(x in sel for x in (":-abp", ":has", ":xpath", "+js(", "{", "\\", ":matches", ":style")):
                    sels.append(sel)
        return doms, sels

    def update(self, urls, log=print):
        doms, sels = set(BUILTIN_AD_DOMAINS), []
        ok = 0
        for u in urls:
            try:
                with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=30) as r:
                    d, s = self.parse(r.read().decode("utf-8", "replace"))
                doms |= d
                sels += s
                ok += 1
                log(f"Loaded filter list ({len(d)} domains, {len(s)} hiding rules): {u}")
            except Exception as e:
                log(f"Filter list failed: {u} ({e})")
        if ok:
            self.domains = doms
            self.selectors = list(dict.fromkeys(sels))
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(ADBLOCK_CACHE, "w", encoding="utf-8") as f:
                json.dump({"domains": sorted(doms), "selectors": self.selectors}, f)
        return ok

    def blocked(self, url_or_host):
        h = url_or_host
        if "/" in h:
            h = urllib.parse.urlparse(h).hostname or ""
        parts = h.lower().split(".")
        return any(".".join(parts[i:]) in self.domains for i in range(len(parts) - 1))

    def css(self):
        sels = self.selectors[:2000]
        return "".join(",".join(sels[i:i + 5]) + "{display:none!important}" for i in range(0, len(sels), 5))

    def strip_html(self, html, base):
        def bad(u):
            return bool(u) and self.blocked(urllib.parse.urljoin(base, u))

        def attr(attrs, name):
            m = re.search(r"\b" + name + r"\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", attrs, re.I)
            return (m.group(1) or m.group(2) or m.group(3)) if m else None

        html = re.sub(r"<(script|iframe)\b([^>]*)>(.*?)</\1\s*>",
                      lambda m: "" if bad(attr(m.group(2), "src")) else m.group(0), html, flags=re.I | re.S)
        return re.sub(r"<(img|link|embed|source)\b([^>]*)>",
                      lambda m: "" if bad(attr(m.group(2), "src" if m.group(1).lower() != "link" else "href"))
                      else m.group(0), html, flags=re.I)


SHIM_AD = r"""<script>(function(){var C={},O=location.protocol+'//'+location.host;
function bad(u){var h;try{h=new URL(u,document.baseURI).hostname}catch(e){return false}
 if(C[h]===undefined){try{var x=new XMLHttpRequest();x.open('GET',O+'/adcheck?h='+encodeURIComponent(h),false);x.send();C[h]=x.responseText==='1'}catch(e){C[h]=false}}return C[h]}
[[HTMLScriptElement,'src'],[HTMLIFrameElement,'src'],[HTMLImageElement,'src']].forEach(function(p){
 var d=Object.getOwnPropertyDescriptor(p[0].prototype,p[1]);if(!d||!d.set)return;
 Object.defineProperty(p[0].prototype,p[1],{get:d.get,set:function(v){if(bad(v))return;d.set.call(this,v)},configurable:true})});
var sa=Element.prototype.setAttribute;
Element.prototype.setAttribute=function(k,v){if(k==='src'&&/^(SCRIPT|IFRAME|IMG)$/.test(this.tagName)&&bad(v))return;return sa.call(this,k,v)};
})();</script>"""


# ----------------------------------------------------------------- Vizio OS hub
OS_HTML = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Vizio OS</title>
<style>
*{box-sizing:border-box}html,body{margin:0;height:100%;background:#0b1020;color:#fff;font-family:Segoe UI,Arial,sans-serif;overflow:hidden}
#home{padding:4vh 5vw;height:100%;overflow:auto}h1{font-weight:300;font-size:4.5vh;margin:0 0 3vh}
#clock{float:right;font-size:3.5vh;opacity:.7}
#grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(24vw,1fr));gap:2vw}
.tile{background:linear-gradient(135deg,#1f2a52,#3b2a63);border-radius:1.2vw;padding:3vh 2vw;font-size:3vh;cursor:pointer;min-height:17vh;display:flex;align-items:flex-end;word-break:break-all}
.tile:hover{outline:.5vh solid #6cf}
#browser{display:none;position:absolute;inset:0;flex-direction:column}
#bar{display:flex;gap:1vw;padding:1vh 1vw;background:#111a33;align-items:center}
#bar button{font-size:2.6vh;padding:1vh 2vw;border:0;border-radius:.8vw;background:#2b3a6b;color:#fff;cursor:pointer}
#url{flex:1;font-size:2.6vh;padding:1vh 1vw;border-radius:.8vw;border:0}
#ifr{flex:1;border:0;background:#fff;width:100%}
#cur{position:fixed;left:0;top:0;width:26px;height:26px;background:#ffe14d;z-index:99999;pointer-events:none;display:none;
 clip-path:polygon(0 0,0 100%,28% 76%,48% 100%,62% 92%,44% 68%,80% 68%)}
.banner{position:fixed;left:50%;transform:translateX(-50%);min-width:40vw;max-width:80vw;padding:2vh 3vw;border-radius:1vw;
 font-size:3.4vh;z-index:99998;box-shadow:0 1vh 4vh rgba(0,0,0,.6);text-align:center}
.banner b{display:block;font-size:2.6vh;opacity:.85;margin-bottom:.5vh}
.banner.top{top:3vh}.banner.bottom{bottom:3vh}.banner.center{top:50%;transform:translate(-50%,-50%)}
.banner.full{inset:0;left:0;transform:none;max-width:none;min-width:0;display:flex;flex-direction:column;justify-content:center;border-radius:0;font-size:8vh}
.info{background:#1c6dd0}.success{background:#1f9d55}.warning{background:#d98e04;color:#111}.alert{background:#c62828}
#conn{position:fixed;right:1vw;bottom:1vh;font-size:2vh;opacity:.5;z-index:99990}
</style></head><body>
<div id="home"><span id="clock"></span><h1>Vizio OS</h1><div id="grid"></div></div>
<div id="browser"><div id="bar"><button onclick="goHome()">Home</button><button onclick="nav('back')">Back</button>
<button onclick="nav('reload')">Reload</button><input id="url"><button onclick="openUrl(url.value)">Go</button></div>
<iframe id="ifr"></iframe></div>
<div id="cur"></div><div id="conn">connecting...</div>
<script>
var cx=innerWidth/2,cy=innerHeight/2,cur=document.getElementById('cur'),url=document.getElementById('url');
function ifr(){return document.getElementById('ifr')}
function showCur(){cur.style.display='block';cur.style.left=cx+'px';cur.style.top=cy+'px'}
function mv(dx,dy){cx=Math.max(0,Math.min(innerWidth-2,cx+dx));cy=Math.max(0,Math.min(innerHeight-2,cy+dy));showCur()}
function under(){cur.style.display='none';var e=document.elementFromPoint(cx,cy);cur.style.display='block';return e}
function fire(el,d){['mousedown','mouseup'].forEach(function(t){el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:d.defaultView}))});el.click()}
function doClick(){var el=under();if(!el)return;
 if(el===ifr()){try{var r=el.getBoundingClientRect(),d=el.contentDocument,i=d.elementFromPoint(cx-r.left,cy-r.top);if(i){if(i.focus)i.focus();fire(i,d)}}catch(e){}}
 else{if(el.focus)el.focus();el.click()}}
function doScroll(dy){var el=under();
 if(el===ifr()){try{ifr().contentWindow.scrollBy(0,dy)}catch(e){}}else{document.getElementById('home').scrollBy(0,dy)}}
function openUrl(u){u=(u||'').trim();if(!u)return;if(!/^[a-z]+:\/\//i.test(u))u='https://'+u;
 document.getElementById('home').style.display='none';document.getElementById('browser').style.display='flex';
 url.value=u;ifr().src='/proxy?u='+encodeURIComponent(u)}
function goHome(){ifr().src='about:blank';document.getElementById('browser').style.display='none';document.getElementById('home').style.display='block'}
function nav(a){if(a==='back'){try{ifr().contentWindow.history.back()}catch(e){}}else if(a==='reload'){try{ifr().contentWindow.location.reload()}catch(e){}}}
window.addEventListener('message',function(e){if(e.data&&e.data.t==='loaded')url.value=e.data.u});
function typeKey(k){var d=document,el=d.activeElement;
 if(!el||el===d.body||el===ifr()){try{d=ifr().contentDocument;el=d.activeElement}catch(e){return}}
 if(!el||el===d.body)return;
 try{if('value' in el){var s=el.selectionStart,e=el.selectionEnd;if(s==null){s=e=el.value.length}
  if(k.length===1){el.value=el.value.slice(0,s)+k+el.value.slice(e);el.setSelectionRange(s+1,s+1)}
  else if(k==='Backspace'){if(s!==e){el.value=el.value.slice(0,s)+el.value.slice(e);el.setSelectionRange(s,s)}else if(s>0){el.value=el.value.slice(0,s-1)+el.value.slice(s);el.setSelectionRange(s-1,s-1)}}
  else if(k==='ArrowLeft')el.setSelectionRange(Math.max(0,s-1),Math.max(0,s-1));
  else if(k==='ArrowRight')el.setSelectionRange(s+1,s+1);
  else if(k==='Enter'){if(el===url){openUrl(url.value);return}var f=el.form;if(f){if(f.requestSubmit)f.requestSubmit();else f.submit()}}
  el.dispatchEvent(new Event('input',{bubbles:true}))}}catch(x){}
 var o={key:k,bubbles:true};el.dispatchEvent(new KeyboardEvent('keydown',o));el.dispatchEvent(new KeyboardEvent('keyup',o))}
function banner(m){var b=document.createElement('div');
 b.className='banner '+(m.pos||'top')+' '+(m.kind||'info')+(m.full?' full':'');
 b.innerHTML='';if(m.title){var t=document.createElement('b');t.textContent=m.title;b.appendChild(t)}
 var p=document.createElement('span');p.textContent=m.text||'';b.appendChild(p);document.body.appendChild(b);
 var secs=Math.max(1,+m.secs||6);setTimeout(function(){if(b.parentNode)b.parentNode.removeChild(b)},secs*1000)}
function clearBanners(){[].slice.call(document.querySelectorAll('.banner')).forEach(function(b){b.remove()})}
function handle(m){switch(m.t){
 case 'move':mv(m.dx,m.dy);break;case 'click':doClick();break;case 'scroll':doScroll(m.dy);break;
 case 'key':typeKey(m.key);break;case 'banner':banner(m);break;case 'clear':clearBanners();break;
 case 'nav':if(m.a==='home')goHome();else if(m.a==='open')openUrl(m.u);else nav(m.a);break}}
var es=new EventSource('/events');es.onopen=function(){document.getElementById('conn').textContent='PC linked'};
es.onerror=function(){document.getElementById('conn').textContent='reconnecting...'};
es.onmessage=function(ev){try{handle(JSON.parse(ev.data))}catch(e){}};
var rep=0;
document.addEventListener('keydown',function(e){var k=e.key,step=e.repeat?Math.min(90,20+(++rep)*6):(rep=0,20),a=document.activeElement;
 var typing=a&&a.tagName==='INPUT';
 if(k==='ArrowUp')mv(0,-step);else if(k==='ArrowDown')mv(0,step);else if(k==='ArrowLeft'&&!typing)mv(-step,0);
 else if(k==='ArrowRight'&&!typing)mv(step,0);else if(k==='Enter'){if(typing&&a===url)openUrl(url.value);else doClick()}
 else if(k==='Escape'||(k==='Backspace'&&!typing))nav('back');else return;e.preventDefault()});
fetch('/api/tiles').then(function(r){return r.json()}).then(function(list){var g=document.getElementById('grid');
 list.forEach(function(t){var d=document.createElement('div');d.className='tile';d.textContent=t.name;d.onclick=function(){openUrl(t.url)};g.appendChild(d)})});
setInterval(function(){document.getElementById('clock').textContent=new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})},1000);
var q=new URLSearchParams(location.search).get('u');if(!q&&location.hash.indexOf('#u=')===0)q=decodeURIComponent(location.hash.slice(3));
if(q)openUrl(q);
</script></body></html>"""

# Injected into proxied pages so links/forms stay inside the proxy and the TV page can follow along.
SHIM = r"""<script>(function(){var P=location.protocol+'//'+location.host+'/proxy?u=';
function go(u){location.href=P+encodeURIComponent(u)}
document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a[href]');if(!a)return;
 var h=a.href;if(!/^https?:/i.test(h))return;e.preventDefault();go(h)},true);
document.addEventListener('submit',function(e){var f=e.target;if((f.method||'get').toLowerCase()!=='get')return;
 e.preventDefault();var u=new URL(f.action||document.baseURI,document.baseURI);
 new FormData(f).forEach(function(v,k){u.searchParams.set(k,v)});go(u.href)},true);
try{window.open=function(u){if(u)go(new URL(u,document.baseURI).href);return null}}catch(e){}
try{parent.postMessage({t:'loaded',u:document.baseURI},'*')}catch(e){}})();</script>"""


RES_CHOICES = {"640x360": 640, "960x540": 960, "1280x720": 1280, "1600x900": 1600, "1920x1080": 1920,
               "2560x1440": 2560, "3840x2160 (4K)": 3840, "Native (full)": 7680}
SCREEN_HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>PC screen</title></head>
<body style="margin:0;background:#000;height:100vh;display:flex;align-items:center;justify-content:center;overflow:hidden">
<img id="s" alt="" style="max-width:100vw;max-height:100vh">
<div id="m" style="position:fixed;left:1vw;bottom:1vh;color:#fff;font:2vh Segoe UI,Arial;opacity:.6">PC screen - view only</div>
<script>
var s=document.getElementById('s'),m=document.getElementById('m'),mode='stream',gen=0,fails=0;
function apply(f){var st=s.style;st.objectFit='';st.width='';st.height='';st.maxWidth='100vw';st.maxHeight='100vh';
 if(f==='fill'){st.width='100vw';st.height='100vh';st.objectFit='cover'}
 else if(f==='stretch'){st.width='100vw';st.height='100vh';st.objectFit='fill'}
 else if(f==='native'){st.maxWidth='none';st.maxHeight='none'}
 else{st.objectFit='contain'}}
function stream(){var g=++gen;s.onload=null;s.onerror=function(){if(g!==gen)return;
 if(++fails>2){mode='poll';poll()}else setTimeout(stream,800)};s.src='/stream?t='+Date.now()}
function poll(){var g=++gen;s.onerror=null;(function f(){if(g!==gen)return;var n=new Image();
 n.onload=function(){s.src=n.src;setTimeout(f,15)};
 n.onerror=function(){m.textContent='Waiting for PC screen...';setTimeout(f,1000)};n.src='/screen.img?t='+Date.now()})()}
var es=new EventSource('/events');
es.onmessage=function(e){try{var d=JSON.parse(e.data);if(d.t==='screen'){apply(d.fit);
 if(d.mode&&d.mode!==mode){mode=d.mode;fails=0;mode==='stream'?stream():poll()}}}catch(x){}};
stream();
</script></body></html>"""


def png_bytes(w, h, rgb):
    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


def capture_screen(max_w=1280, raw=False):
    """Windows only: grabs the desktop with GDI, scaled down, as (w, h, RGB bytes)."""
    if os.name != "nt":
        raise TVError("PC screen mirroring needs Windows")
    import ctypes
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    vp, ci = ctypes.c_void_p, ctypes.c_int
    user32.GetDC.restype, user32.GetDC.argtypes = vp, [vp]
    user32.ReleaseDC.argtypes = [vp, vp]
    gdi32.CreateCompatibleDC.restype, gdi32.CreateCompatibleDC.argtypes = vp, [vp]
    gdi32.CreateCompatibleBitmap.restype = vp
    gdi32.CreateCompatibleBitmap.argtypes = [vp, ci, ci]
    gdi32.SelectObject.restype, gdi32.SelectObject.argtypes = vp, [vp, vp]
    gdi32.StretchBlt.argtypes = [vp, ci, ci, ci, ci, vp, ci, ci, ci, ci, ctypes.c_uint32]
    gdi32.GetDIBits.argtypes = [vp, vp, ctypes.c_uint, ctypes.c_uint, vp, vp, ctypes.c_uint]
    gdi32.DeleteObject.argtypes = [vp]
    gdi32.DeleteDC.argtypes = [vp]

    class BMIH(ctypes.Structure):
        _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                    ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16),
                    ("biCompression", ctypes.c_uint32), ("biSizeImage", ctypes.c_uint32),
                    ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
                    ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]

    sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    w = min(max_w, sw) & ~3          # width multiple of 4 -> no DIB row padding
    h = int(sh * w / sw) & ~1
    hdc = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    try:
        gdi32.StretchBlt(mdc, 0, 0, w, h, hdc, 0, 0, sw, sh, 0x00CC0020)  # SRCCOPY
        bi = BMIH()
        bi.biSize, bi.biWidth, bi.biHeight = ctypes.sizeof(BMIH), w, -h    # negative = top-down
        bi.biPlanes, bi.biBitCount = 1, 24
        buf = ctypes.create_string_buffer(w * h * 3)
        if not gdi32.GetDIBits(mdc, bmp, 0, h, ctypes.addressof(buf), ctypes.addressof(bi), 0):
            raise TVError("GetDIBits failed")
        if raw:
            return w, h, buf.raw          # BGR as captured: zero per-pixel work
        rgb = bytearray(buf.raw)
        rgb[0::3], rgb[2::3] = rgb[2::3], rgb[0::3]   # BGR -> RGB
        return w, h, bytes(rgb)
    finally:
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(None, hdc)


def wake_on_lan(mac, broadcast="255.255.255.255"):
    m = re.sub(r"[^0-9a-fA-F]", "", mac or "")
    if len(m) != 12:
        raise TVError("MAC must be 12 hex digits, e.g. AA:BB:CC:DD:EE:FF")
    pkt = b"\xff" * 6 + bytes.fromhex(m) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
        sk.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for _ in range(3):
            sk.sendto(pkt, (broadcast, 9))


class Hub:
    """Serves Vizio OS to the TV, relays PC input/banners over SSE, and proxies pages."""

    def __init__(self):
        self.clients, self.lock = [], threading.Lock()
        self.httpd = None
        self.allowed = set()  # empty = allow all
        self.tiles = lambda: []
        self.adblock = None
        self.inject = lambda: ("", "")
        self.frame = None  # latest PC screen frame (BMP/PNG/JPEG bytes)
        self.ctype = "image/png"
        self.fid = 0
        self.cond = threading.Condition()
        self.mirror_on = False
        self.capture = False

    def set_frame(self, data, ctype="image/png"):
        with self.cond:
            self.frame, self.ctype = data, ctype
            self.fid += 1
            self.cond.notify_all()

    def save(self, url, body):
        try:
            p = urllib.parse.urlparse(url)
            rel = re.sub(r'[<>:"|?*\\]', "_", p.path.strip("/")) or "index"
            if p.path.endswith("/") or "." not in rel.rsplit("/", 1)[-1]:
                rel = rel.rstrip("/") + "/index.html" if p.path.endswith("/") or not p.path else rel
            fp = os.path.join(CAPTURE_DIR, "tv_loaded", p.netloc.replace(":", "_"), *rel.split("/"))
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "wb") as f:
                f.write(body)
        except Exception:
            pass

    def broadcast(self, msg):
        data = json.dumps(msg)
        with self.lock:
            for q in list(self.clients):
                q.put(data)

    def count(self):
        with self.lock:
            return len(self.clients)

    def start(self):
        if self.httpd:
            return
        handler = type("H", (_HubHandler,), {"hub": self})
        self.httpd = ThreadingHTTPServer(("0.0.0.0", HUB_PORT), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    def url(self, target="8.8.8.8"):
        return f"http://{local_ip(target)}:{HUB_PORT}/"


class _HubHandler(BaseHTTPRequestHandler):
    hub = None

    def log_message(self, *a):
        pass

    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def do_GET(self):
        ip = self.client_address[0]
        if self.path.split("?")[0] not in NOISE or store_verbose():
            TRAFFIC.append({"id": next(_SEQ), "t": time.time(), "dir": "TV→PC", "method": "GET", "url": self.path,
                            "req": dict(self.headers), "client": ip, "ms": 0,
                            "status": "403" if (self.hub.allowed and ip not in self.hub.allowed) else "200",
                            "resp": "(served by Vizio Control)"})
        if self.hub.allowed and ip not in self.hub.allowed:
            return self._send(403, b"forbidden", "text/plain")
        u = urllib.parse.urlparse(self.path)
        if u.path == "/":
            return self._send(200, OS_HTML.encode("utf-8"), "text/html; charset=utf-8")
        if u.path == "/events":
            return self._sse()
        if u.path == "/api/tiles":
            return self._send(200, json.dumps(self.hub.tiles()).encode(), "application/json")
        if u.path == "/screen":
            return self._send(200, SCREEN_HTML.encode("utf-8"), "text/html; charset=utf-8")
        if u.path == "/stream":
            return self._stream()
        if u.path in ("/screen.png", "/screen.img"):
            f = self.hub.frame
            return self._send(200, f, self.hub.ctype) if f else self._send(503, b"no frame", "text/plain")
        if u.path == "/adcheck":
            h = urllib.parse.parse_qs(u.query).get("h", [""])[0]
            ab = self.hub.adblock
            return self._send(200, b"1" if ab and ab.enabled and ab.blocked(h) else b"0", "text/plain")
        if u.path == "/proxy":
            return self._proxy(urllib.parse.parse_qs(u.query).get("u", [""])[0])
        self._send(404, b"not found", "text/plain")

    def _stream(self):
        # one open connection, newest frame only: a slow TV drops frames instead of building up lag
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=vcframe")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        last, hub = -1, self.hub
        try:
            while hub.mirror_on:
                with hub.cond:
                    hub.cond.wait_for(lambda: hub.fid != last or not hub.mirror_on, timeout=5)
                    f, ct, last = hub.frame, hub.ctype, hub.fid
                if f is None:
                    continue
                self.wfile.write(b"--vcframe\r\nContent-Type: " + ct.encode() + b"\r\nContent-Length: "
                                 + str(len(f)).encode() + b"\r\n\r\n" + f + b"\r\n")
                self.wfile.flush()
        except OSError:
            pass

    def _sse(self):
        q = queue.Queue()
        with self.hub.lock:
            self.hub.clients.append(q)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(b"retry: 2000\n\n")
            self.wfile.flush()
            while True:
                try:
                    self.wfile.write(f"data: {q.get(timeout=10)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except OSError:
            pass
        finally:
            with self.hub.lock:
                if q in self.hub.clients:
                    self.hub.clients.remove(q)

    def _proxy(self, target):
        p = urllib.parse.urlparse(target)
        if p.scheme not in ("http", "https") or not p.netloc:
            return self._send(400, b"bad url", "text/plain")
        ab = self.hub.adblock
        if ab and ab.enabled and ab.blocked(target):
            return self._send(204, b"", "text/plain")
        req = urllib.request.Request(target, headers={
            "User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"})
        try:
            r = urllib.request.urlopen(req, timeout=15)
            status, hdr, body, final = 200, r.headers, r.read(), r.geturl()
        except urllib.error.HTTPError as e:
            status, hdr, body, final = e.code, e.headers, e.read(), target
        except Exception as e:
            return self._send(502, f"Proxy error: {e}".encode(), "text/plain")
        ctype = hdr.get_content_type()
        if self.hub.capture:
            self.hub.save(final, body)
        if ctype in ("text/html", "application/xhtml+xml"):
            html = body.decode(hdr.get_content_charset() or "utf-8", "replace")
            html = re.sub(r'<meta[^>]+http-equiv=["\']?content-security-policy[^>]*>', "", html, flags=re.I)
            css, js = self.hub.inject()
            if ab and ab.enabled:
                html = ab.strip_html(html, final)
                css += ab.css()
            extra = (f"<style>{css}</style>" if css else "") + (f"<script>{js}</script>" if js else "")
            inject = (f'<base href="{final.replace(chr(34), "%22")}">' + SHIM
                      + (SHIM_AD if ab and ab.enabled else "") + extra)
            m = re.search(r"<head[^>]*>", html, re.I)
            html = html[:m.end()] + inject + html[m.end():] if m else inject + html
            return self._send(status, html.encode("utf-8"), "text/html; charset=utf-8")
        self._send(status, body, hdr.get("Content-Type", "application/octet-stream"))


# ------------------------------------------------------- static hosting
class SiteServer:
    def __init__(self):
        self.httpd = None

    def serve(self, folder, target="8.8.8.8"):
        self.stop()
        self.httpd = ThreadingHTTPServer(("0.0.0.0", SITE_PORT), partial(_QuietHandler, directory=folder))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return f"http://{local_ip(target)}:{SITE_PORT}/"

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def github_to_folder(repo_url):
    u = repo_url.strip().rstrip("/").replace("https://github.com/", "")
    parts = u.split("/")
    if len(parts) < 2:
        raise TVError("Use a URL like https://github.com/owner/repo")
    owner, repo = parts[0], parts[1].replace(".git", "")
    branch = parts[3] if len(parts) >= 4 and parts[2] == "tree" else None
    data = None
    for b in ([branch] if branch else ["main", "master"]):
        try:
            with urllib.request.urlopen(
                    f"https://github.com/{owner}/{repo}/archive/refs/heads/{b}.zip", timeout=30) as r:
                data = r.read()
            break
        except urllib.error.URLError:
            continue
    if data is None:
        raise TVError("Couldn't download that repo (private, or branch not found)")
    dest = os.path.join(SITES_DIR, f"{owner}-{repo}")
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(BytesIO(data)) as z:
        z.extractall(dest)
    top = os.path.join(dest, os.listdir(dest)[0])
    for cand in ("dist", "build", "docs", "public", "."):
        p = os.path.normpath(os.path.join(top, cand))
        if os.path.isfile(os.path.join(p, "index.html")):
            return p
    raise TVError("No index.html found in that repo. Source projects that need a build step "
                  "(npm/gradle) must be built first; pick a folder instead.")


# ---------------------------------------------------------------------- store
def load_store():
    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("tvs", {})
    s.setdefault("urls", [])
    s.setdefault("custom_apps", {})
    s.setdefault("app_ok", {})
    s.setdefault("adblock", True)
    s.setdefault("filter_lists", [])
    s.setdefault("inject_css", "")
    s.setdefault("inject_js", "")
    s.setdefault("schedules", [])
    s.setdefault("mac", "")
    s.setdefault("device_id", "vizio-control-" + "%08x" % random.getrandbits(32))
    s.setdefault("last", None)
    a = s.setdefault("app", {})
    for k, v in (("theme", "light"), ("ontop", False), ("autoreconnect", True), ("hotkeys", True), ("mask", True),
                 ("verbose", False), ("capture", False), ("mirror_fmt", "None (raw, fastest)"), ("mirror_fps", 30),
                 ("mirror_stream", True), ("mirror_res", "960x540")):
        a.setdefault(k, v)
    return s


def save_store(s):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


# ------------------------------------------------------------------------ GUI
CURSOR_MAP = {
    "Up": {"t": "move", "dx": 0, "dy": -60}, "Down": {"t": "move", "dx": 0, "dy": 60},
    "Left": {"t": "move", "dx": -60, "dy": 0}, "Right": {"t": "move", "dx": 60, "dy": 0},
    "OK": {"t": "click"}, "Back": {"t": "nav", "a": "back"}, "Home": {"t": "nav", "a": "home"},
    "Ch +": {"t": "scroll", "dy": -300}, "Ch -": {"t": "scroll", "dy": 300},
}
PAD_KEYS = {"BackSpace": "Backspace", "Return": "Enter", "Tab": "Tab", "Left": "ArrowLeft",
            "Right": "ArrowRight", "Up": "ArrowUp", "Down": "ArrowDown", "space": " "}


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    store = load_store()
    save_store(store)
    server = SiteServer()
    hub = Hub()
    state = {"tv": None, "name": None, "challenge": None, "pair_host": None, "apps": {}, "sleep": None}

    def tiles():
        out = []
        for u in store["urls"]:
            host = urllib.parse.urlparse(u).netloc or u
            out.append({"name": host.replace("www.", ""), "url": u})
        return out

    hub.tiles = tiles
    adb = AdBlock()
    adb.load_cache()
    adb.enabled = store["adblock"]
    hub.adblock = adb
    hub.inject = lambda: (store["inject_css"], store["inject_js"])
    try:
        hub.start()
        hub_ok = True
    except OSError:
        hub_ok = False

    root = tk.Tk()
    root.title("Vizio Control")
    root.geometry("820x700")
    root.minsize(720, 600)
    style = ttk.Style()
    try:
        style.theme_use("vista" if os.name == "nt" else "clam")
    except tk.TclError:
        pass

    status = tk.StringVar(value="Not connected")
    pagestat = tk.StringVar(value="")
    top = ttk.Frame(root)
    top.pack(fill="x")
    ttk.Label(top, textvariable=status, anchor="w", padding=(10, 6), font=("Segoe UI", 10, "bold")).pack(side="left")
    ttk.Label(top, textvariable=pagestat, anchor="e", padding=(10, 6)).pack(side="right")
    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=8)
    logbox = tk.Text(root, height=6, state="disabled", font=("Consolas", 9))
    logbox.pack(fill="x", padx=8, pady=8)

    logq = queue.Queue()

    def log(msg):
        logq.put(time.strftime("%H:%M:%S ") + str(msg) + "\n")

    def drain_log():
        try:
            while True:
                m = logq.get_nowait()
                logbox.config(state="normal")
                logbox.insert("end", m)
                logbox.see("end")
                logbox.config(state="disabled")
        except queue.Empty:
            pass
        root.after(150, drain_log)

    def bg(fn, done=None):
        def run():
            try:
                res = fn()
                if done:
                    root.after(0, lambda: done(res))
            except TVError as e:
                log(f"Error: {e}")
            except Exception as e:
                log(f"Error: {type(e).__name__}: {e}")
        threading.Thread(target=run, daemon=True).start()

    def need_tv():
        if not state["tv"] or not state["tv"].token:
            messagebox.showinfo("Vizio Control", "Connect and pair with a TV first (Connect tab).")
            return None
        return state["tv"]

    def poll_page():
        n = hub.count()
        pagestat.set((f"TV page: linked ({n})" if n else
                      ("TV page: not open" if hub_ok else f"Port {HUB_PORT} busy - TV page disabled"))
                     + ("   |   Mirror " + screen_on["stats"] if screen_on["run"] and screen_on["stats"] else ""))
        root.after(1500, poll_page)

    # ================= Connect
    t1 = ttk.Frame(nb, padding=12)
    nb.add(t1, text="Connect")
    ttk.Label(t1, text="1. Find your TV (same Wi-Fi/network as this PC)").grid(row=0, column=0, sticky="w")
    ttk.Button(t1, text="Scan network", command=lambda: do_scan()).grid(row=0, column=1, padx=6)
    found_list = tk.Listbox(t1, height=4)
    found_list.grid(row=1, column=0, columnspan=3, sticky="ew", pady=4)
    ttk.Label(t1, text="or type TV IP:").grid(row=2, column=0, sticky="w")
    host_var = tk.StringVar()
    ttk.Entry(t1, textvariable=host_var, width=24).grid(row=2, column=1, sticky="w", padx=6)
    ttk.Separator(t1).grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)
    ttk.Label(t1, text="2. Pair: the TV will show a 4-digit code").grid(row=4, column=0, sticky="w")
    ttk.Button(t1, text="Start pairing", command=lambda: do_begin()).grid(row=4, column=1, padx=6)
    ttk.Label(t1, text="Code from TV:").grid(row=5, column=0, sticky="w")
    pin_var = tk.StringVar()
    ttk.Entry(t1, textvariable=pin_var, width=8, font=("Segoe UI", 14)).grid(row=5, column=1, sticky="w", padx=6)
    ttk.Button(t1, text="Finish pairing", command=lambda: do_finish()).grid(row=5, column=2)
    ttk.Separator(t1).grid(row=6, column=0, columnspan=3, sticky="ew", pady=10)
    ttk.Label(t1, text="Saved TVs").grid(row=7, column=0, sticky="w")
    saved_list = tk.Listbox(t1, height=4)
    saved_list.grid(row=8, column=0, columnspan=2, sticky="ew")
    bf = ttk.Frame(t1)
    bf.grid(row=8, column=2, padx=6)
    ttk.Button(bf, text="Connect", command=lambda: use_saved()).pack(fill="x")
    ttk.Button(bf, text="Forget", command=lambda: forget_saved()).pack(fill="x", pady=2)
    t1.columnconfigure(0, weight=1)

    def refresh_saved():
        saved_list.delete(0, "end")
        for n, p in store["tvs"].items():
            saved_list.insert("end", f"{n}  ({p['host']})")

    def set_connected(name, host, token):
        tv = TV(host, token)
        state["tv"], state["name"] = tv, name
        hub.allowed = {tv.ip, "127.0.0.1", local_ip(tv.ip)}
        status.set(f"Connected: {name} ({host})")
        store["last"] = name
        save_store(store)
        log(f"Connected to {name}")
        hub.broadcast({"t": "banner", "title": "Vizio Control", "kind": "success", "pos": "top", "secs": 7,
                       "text": f"Connected to {name}. Vizio OS is active while its page is open on the TV."})
        bg(fetch_catalog, lambda a: (state["apps"].update(a), refresh_apps()))
        bg(tv.inputs, lambda i: fill_inputs(i))

    def do_scan():
        found_list.delete(0, "end")
        log("Scanning network for Vizio TVs (about 10 seconds)...")

        def done(hosts):
            for h in hosts:
                found_list.insert("end", h)
            log(f"Found {len(hosts)} TV(s)." if hosts else
                "No TV found. Make sure it's on (Quick Start enabled) and type its IP manually.")
            if hosts:
                host_var.set(hosts[0])
        bg(lambda: discover(log), done)

    found_list.bind("<<ListboxSelect>>", lambda e: host_var.set(
        found_list.get(found_list.curselection()[0])) if found_list.curselection() else None)

    def do_begin():
        host = host_var.get().strip()
        if not host:
            messagebox.showinfo("Vizio Control", "Scan or type the TV's IP address first.")
            return
        hosts = [norm_host(host)] if ":" in host else [f"{host}:{p}" for p in PORTS]

        def work():
            last = None
            for h in hosts:
                try:
                    return h, TV(h).begin_pair(store["device_id"], "Vizio Control (PC)")
                except TVError as e:
                    last = e
            raise last

        def done(r):
            state["pair_host"], state["challenge"] = r
            log("Look at your TV, then type the 4-digit code and press Finish pairing.")
        bg(work, done)

    def do_finish():
        if state["challenge"] is None:
            messagebox.showinfo("Vizio Control", "Press 'Start pairing' first.")
            return
        pin, host, ch = pin_var.get(), state["pair_host"], state["challenge"]

        def done(token):
            name = f"TV {host.split(':')[0]}"
            store["tvs"][name] = {"host": host, "token": token}
            save_store(store)
            refresh_saved()
            set_connected(name, host, token)
            state["challenge"] = None
        bg(lambda: TV(host).finish_pair(ch, pin, store["device_id"]), done)

    def use_saved():
        sel = saved_list.curselection()
        if sel:
            name = list(store["tvs"])[sel[0]]
            p = store["tvs"][name]
            set_connected(name, p["host"], p["token"])

    def forget_saved():
        sel = saved_list.curselection()
        if sel:
            store["tvs"].pop(list(store["tvs"])[sel[0]], None)
            save_store(store)
            refresh_saved()

    # ================= Remote
    t2 = ttk.Frame(nb, padding=12)
    nb.add(t2, text="Remote")
    cursor_mode = tk.BooleanVar(value=False)

    def press(name):
        if cursor_mode.get() and name in CURSOR_MAP:
            hub.broadcast(CURSOR_MAP[name])
            return
        tv = need_tv()
        if tv:
            bg(lambda: tv.key(name))

    layout = [
        ["Power On", "Power Off", "Power Toggle", "Input"],
        ["Vol +", "Mute", "Ch +", "Home"],
        ["Vol -", "", "Ch -", "Prev Ch"],
        ["", "Up", "", "Menu"],
        ["Left", "OK", "Right", "Info"],
        ["", "Down", "", "Exit"],
        ["Back", "SmartCast", "", ""],
        ["Rewind", "Play", "Pause", "FF"],
    ]
    for r, row in enumerate(layout):
        for c, name in enumerate(row):
            if name:
                ttk.Button(t2, text=name, width=13, command=lambda n=name: press(n)).grid(
                    row=r, column=c, padx=4, pady=4, ipady=4)
    ttk.Checkbutton(t2, variable=cursor_mode, text="Cursor mode: d-pad/OK/Back/Home move the mouse cursor on the "
                    "Vizio OS page instead of the TV's own menus").grid(row=len(layout), column=0, columnspan=4, pady=6, sticky="w")
    sl = ttk.Frame(t2)
    sl.grid(row=len(layout) + 1, column=0, columnspan=4, sticky="w", pady=4)
    ttk.Label(sl, text="Sleep timer (min):").pack(side="left")
    sleep_var = tk.IntVar(value=30)
    ttk.Spinbox(sl, from_=1, to=600, textvariable=sleep_var, width=5).pack(side="left", padx=4)

    def start_sleep():
        tv = need_tv()
        if not tv:
            return
        if state["sleep"]:
            state["sleep"].cancel()
        m = sleep_var.get()
        state["sleep"] = threading.Timer(m * 60, lambda: bg(lambda: tv.key("Power Off")))
        state["sleep"].daemon = True
        state["sleep"].start()
        log(f"TV will turn off in {m} minutes")

    def cancel_sleep():
        if state["sleep"]:
            state["sleep"].cancel()
            state["sleep"] = None
            log("Sleep timer cancelled")

    ttk.Button(sl, text="Start", command=start_sleep).pack(side="left", padx=2)
    ttk.Button(sl, text="Cancel", command=cancel_sleep).pack(side="left", padx=2)
    for k, n in (("<Up>", "Up"), ("<Down>", "Down"), ("<Left>", "Left"), ("<Right>", "Right"),
                 ("<Return>", "OK"), ("<Escape>", "Back"), ("<plus>", "Vol +"), ("<minus>", "Vol -")):
        root.bind(k, lambda e, n=n: press(n) if nb.index("current") == 1 else None)

    # ================= Inputs
    t3 = ttk.Frame(nb, padding=12)
    nb.add(t3, text="Inputs")
    inputs_list = tk.Listbox(t3, height=10)
    inputs_list.pack(fill="both", expand=True)
    inputs_data = []

    def fill_inputs(items):
        inputs_data[:] = items
        inputs_list.delete(0, "end")
        for n, c in items:
            inputs_list.insert("end", f"{n}   [{c}]")

    def refresh_inputs():
        tv = need_tv()
        if tv:
            bg(tv.inputs, fill_inputs)

    def switch_input():
        tv = need_tv()
        sel = inputs_list.curselection()
        if tv and sel:
            n, c = inputs_data[sel[0]]
            bg(lambda: tv.set_input(c), lambda _: log(f"Switched to {n}"))

    bb = ttk.Frame(t3)
    bb.pack(pady=8)
    ttk.Button(bb, text="Refresh", command=refresh_inputs).pack(side="left", padx=4)
    ttk.Button(bb, text="Switch to selected", command=switch_input).pack(side="left", padx=4)

    # ================= Apps
    t4 = ttk.Frame(nb, padding=12)
    nb.add(t4, text="Apps")
    apps_list = ttk.Treeview(t4, show="tree", height=14)
    apps_list.pack(fill="both", expand=True)
    apps_list.tag_configure("cat", foreground="#06c")

    def all_apps():
        d = dict(state["apps"])
        for n, c in store["custom_apps"].items():
            d[n] = [c]
        return d

    def refresh_apps():
        open_now = {apps_list.item(i, "text") for i in apps_list.get_children() if apps_list.item(i, "open")}
        apps_list.delete(*apps_list.get_children())
        names = sorted(all_apps(), key=str.lower)
        groups = [("Favorites", [n for n in names if n in store["app_ok"]])]
        left = [n for n in names if n not in store["app_ok"]]
        for title, kws in APP_CATS:
            g = [n for n in left if any(k in n.lower() for k in kws)]
            groups.append((title, g))
            left = [n for n in left if n not in g]
        groups.append(("Other", left))
        for title, g in groups:
            if not g:
                continue
            fid = apps_list.insert("", "end", text=f"📁 {title}  ({len(g)})", tags=("cat",), open=(title in open_now or not open_now))
            for n in g:
                apps_list.insert(fid, "end", text=n)

    def launch_app():
        tv = need_tv()
        sel = apps_list.selection()
        if not (tv and sel) or apps_list.parent(sel[0]) == "":
            return
        n = apps_list.item(sel[0], "text")
        cfgs = all_apps()[n]

        def work():
            ok = launch_verified(tv, cfgs, store["app_ok"].get(n), log)
            if ok:
                store["app_ok"][n] = ok
                save_store(store)
                log(f"{n} launched (APP_ID={ok['APP_ID']}, NAME_SPACE={ok['NAME_SPACE']})")
            else:
                log(f"{n}: the TV never reported it running. It may not be installed on this TV, "
                    "or use 'Learn current app' after opening it with your remote, then Save.")
        bg(work)

    def reload_catalog():
        bg(fetch_catalog, lambda a: (state["apps"].update(a), refresh_apps(), log(f"{len(a)} apps in catalog")))

    ba = ttk.Frame(t4)
    ba.pack(pady=6)
    ttk.Button(ba, text="Launch selected", command=launch_app).pack(side="left", padx=4)
    apps_list.bind("<Double-1>", lambda e: launch_app())
    ttk.Button(ba, text="Reload catalog", command=reload_catalog).pack(side="left", padx=4)
    cf = ttk.LabelFrame(t4, text="Custom app config", padding=6)
    cf.pack(fill="x")
    aid, ans, amsg = tk.StringVar(), tk.StringVar(value="4"), tk.StringVar()
    for i, (lbl, var, w) in enumerate((("APP_ID", aid, 8), ("NAME_SPACE", ans, 5), ("MESSAGE", amsg, 34))):
        ttk.Label(cf, text=lbl).grid(row=0, column=i * 2, padx=2)
        ttk.Entry(cf, textvariable=var, width=w).grid(row=0, column=i * 2 + 1, padx=2)

    def cfg_from_fields():
        m = amsg.get().strip()
        return {"APP_ID": aid.get().strip(), "NAME_SPACE": int(ans.get()), "MESSAGE": m or None}

    def launch_custom():
        tv = need_tv()
        if tv:
            try:
                c = cfg_from_fields()
            except ValueError:
                return messagebox.showerror("Vizio Control", "NAME_SPACE must be a number.")
            bg(lambda: tv.launch(c), lambda _: log(f"Sent {c}"))

    def save_custom():
        try:
            c = cfg_from_fields()
        except ValueError:
            return messagebox.showerror("Vizio Control", "NAME_SPACE must be a number.")
        n = simpledialog.askstring("Save app", "Name for this app:")
        if n and c["APP_ID"]:
            store["custom_apps"][n] = c
            save_store(store)
            refresh_apps()

    def learn_current():
        tv = need_tv()
        if tv:
            def done(v):
                if not v:
                    return log("No app is running right now.")
                aid.set(str(v.get("APP_ID", "")))
                ans.set(str(v.get("NAME_SPACE", "")))
                m = v.get("MESSAGE")
                amsg.set("" if m in (None, "None") else str(m))
                log(f"Current app config: {json.dumps(v)}")
            bg(tv.current_app, done)

    cb = ttk.Frame(t4)
    cb.pack(pady=4)
    ttk.Button(cb, text="Learn current app", command=learn_current).pack(side="left", padx=3)
    ttk.Button(cb, text="Launch config", command=launch_custom).pack(side="left", padx=3)
    ttk.Button(cb, text="Save as app...", command=save_custom).pack(side="left", padx=3)
    for n, c in BUILTIN_APPS.items():
        state["apps"][n] = [dict(x) for x in c]
    refresh_apps()

    # ================= URLs & Vizio OS
    t5 = ttk.Frame(nb, padding=12)
    nb.add(t5, text="URLs & OS")
    ttk.Label(t5, wraplength=760, text="Direct launch opens the page in the TV's own browser. 'With PC control' "
              "opens it inside Vizio OS (served from this PC) so your mouse/keyboard/remote can drive it and banners "
              "can appear. Heavy web apps may not work through the proxy; launch those directly.").pack(anchor="w")
    uf = ttk.Frame(t5)
    uf.pack(fill="x", pady=6)
    url_var = tk.StringVar()
    ttk.Entry(uf, textvariable=url_var).pack(side="left", fill="x", expand=True)
    ttk.Button(uf, text="Add", command=lambda: add_url()).pack(side="left", padx=4)
    ttk.Button(uf, text="Add TV-friendly presets", command=lambda: add_presets()).pack(side="left")
    urls_list = tk.Listbox(t5, height=6)
    urls_list.pack(fill="x")
    ub = ttk.Frame(t5)
    ub.pack(pady=6)

    def refresh_urls():
        urls_list.delete(0, "end")
        for u in store["urls"]:
            urls_list.insert("end", u)

    def add_url(u=None):
        u = (u or url_var.get()).strip()
        if u:
            if "://" not in u:
                u = "http://" + u
            if u not in store["urls"]:
                store["urls"].append(u)
                save_store(store)
            url_var.set("")
            refresh_urls()

    def add_presets():
        for u in TV_PRESETS:
            add_url(u)

    def sel_url():
        s = urls_list.curselection()
        return urls_list.get(s[0]) if s else (url_var.get().strip() or None)

    def tv_target():
        return state["tv"].ip if state["tv"] else "8.8.8.8"

    def launch_sel():
        tv, u = need_tv(), sel_url()
        if tv and u:
            bg(lambda: tv.launch_url(u), lambda _: log(f"Launched {u} directly"))

    def launch_wrapped(u=None):
        tv = need_tv()
        if not tv:
            return
        if not hub_ok:
            return messagebox.showerror("Vizio Control", f"Port {HUB_PORT} is in use; can't serve Vizio OS.")
        u = u or sel_url()
        page = hub.url(tv.ip) + (("?u=" + urllib.parse.quote(u, safe="")) if u else "")
        bg(lambda: tv.launch_url(page), lambda _: log(f"Launched with PC control: {page}"))

    def remove_url():
        s = urls_list.curselection()
        if s:
            store["urls"].pop(s[0])
            save_store(store)
            refresh_urls()

    ttk.Button(ub, text="Launch directly", command=launch_sel).pack(side="left", padx=4)
    ttk.Button(ub, text="Launch with PC control", command=lambda: launch_wrapped()).pack(side="left", padx=4)
    ttk.Button(ub, text="Open Vizio OS home", command=lambda: launch_wrapped("")).pack(side="left", padx=4)
    ttk.Button(ub, text="Remove", command=remove_url).pack(side="left", padx=4)
    ttk.Button(ub, text="Mirror PC screen", command=lambda: mirror_pc()).pack(side="left", padx=4)
    ttk.Button(ub, text="Stop mirror", command=lambda: stop_mirror()).pack(side="left", padx=4)
    mf = ttk.Frame(t5)
    mf.pack(fill="x", pady=4)
    ttk.Label(mf, text="PC capture resolution:").pack(side="left")
    cap_res = tk.StringVar(value=store["app"]["mirror_res"])
    ttk.Combobox(mf, textvariable=cap_res, width=18, state="readonly",
                 values=list(RES_CHOICES)).pack(side="left", padx=4)
    ttk.Label(mf, text="TV display:").pack(side="left", padx=(10, 0))
    tv_fit = tk.StringVar(value="Fit")
    ttk.Combobox(mf, textvariable=tv_fit, width=10, state="readonly",
                 values=["Fit", "Fill", "Stretch", "1:1"]).pack(side="left", padx=4)

    def apply_mirror_settings():
        A = store["app"]
        screen_on["maxw"] = RES_CHOICES[cap_res.get()]
        screen_on["fit"] = {"Fit": "contain", "Fill": "fill", "Stretch": "stretch", "1:1": "native"}[tv_fit.get()]
        screen_on["fmt"] = FMT_CHOICES[fmt_var.get()]
        screen_on["fps"] = max(1, min(60, int(fps_var.get())))
        screen_on["stream"] = bool(stream_var.get())
        A.update(mirror_res=cap_res.get(), mirror_fmt=fmt_var.get(), mirror_fps=screen_on["fps"], mirror_stream=screen_on["stream"])
        save_store(store)
        hub.broadcast({"t": "screen", "fit": screen_on["fit"], "mode": "stream" if screen_on["stream"] else "poll"})
        log(f"Mirror settings: {cap_res.get()}, {fmt_var.get()}, {screen_on['fps']} fps max, {'stream' if screen_on['stream'] else 'poll'}, TV display {tv_fit.get()}")

    ttk.Button(mf, text="Apply", command=apply_mirror_settings).pack(side="left", padx=4)
    mf2 = ttk.Frame(t5)
    mf2.pack(fill="x", pady=2)
    ttk.Label(mf2, text="Compression:").pack(side="left")
    fmt_var = tk.StringVar(value=store["app"]["mirror_fmt"] if store["app"]["mirror_fmt"] in FMT_CHOICES else "None (raw, fastest)")
    ttk.Combobox(mf2, textvariable=fmt_var, width=30, state="readonly", values=list(FMT_CHOICES)).pack(side="left", padx=4)
    ttk.Label(mf2, text="Max FPS:").pack(side="left", padx=(10, 0))
    fps_var = tk.IntVar(value=store["app"]["mirror_fps"])
    ttk.Spinbox(mf2, from_=1, to=60, textvariable=fps_var, width=4).pack(side="left", padx=4)
    stream_var = tk.BooleanVar(value=store["app"]["mirror_stream"])
    ttk.Checkbutton(mf2, text="Direct stream (no polling)", variable=stream_var).pack(side="left", padx=8)
    ttk.Label(t5, wraplength=760, foreground="#555", text="Raw = no encoding or compression: the PC sends exactly what it captured "
              "(fastest CPU, needs bandwidth: 1080p is ~6 MB/frame, so use Ethernet/5 GHz for 1080p+). Use Tools > Mirror Benchmark "
              "to pick the best setting. Press Apply while mirroring to change settings live.").pack(fill="x")
    refresh_urls()

    ttk.Separator(t5).pack(fill="x", pady=6)
    ttk.Label(t5, wraplength=760, text=f"Host something from this PC (port {SITE_PORT}; allow it in Windows "
              "Firewall if asked):").pack(anchor="w")
    hb = ttk.Frame(t5)
    hb.pack(fill="x", pady=4)
    gh_var = tk.StringVar()
    ttk.Entry(hb, textvariable=gh_var).pack(side="left", fill="x", expand=True)
    wrap_var = tk.BooleanVar(value=False)

    def host_and_launch(folder_fn):
        tv = need_tv()
        if not tv:
            return

        def work():
            url = server.serve(folder_fn(), tv.ip)
            log(f"Hosting at {url}")
            if wrap_var.get() and hub_ok:
                url = hub.url(tv.ip) + "?u=" + urllib.parse.quote(url, safe="")
            tv.launch_url(url)
            return url
        bg(work, lambda u: log(f"Launched {u}"))

    ttk.Button(hb, text="GitHub repo -> TV", command=lambda: host_and_launch(
        lambda: github_to_folder(gh_var.get()))).pack(side="left", padx=4)
    hb2 = ttk.Frame(t5)
    hb2.pack(pady=2)

    def pick_folder():
        d = filedialog.askdirectory(title="Folder containing index.html")
        if d:
            host_and_launch(lambda: d)

    ttk.Button(hb2, text="Host a folder -> TV", command=pick_folder).pack(side="left", padx=4)
    ttk.Button(hb2, text="Stop hosting", command=lambda: (server.stop(), log("Stopped hosting"))).pack(side="left", padx=4)
    ttk.Checkbutton(hb2, variable=wrap_var, text="with PC control").pack(side="left", padx=8)
    ttk.Label(t5, text="Or paste HTML and send it to the TV:").pack(anchor="w", pady=(6, 0))
    html_box = tk.Text(t5, height=5, font=("Consolas", 9))
    html_box.pack(fill="both", expand=True)
    html_box.insert("1.0", "<h1 style='color:white;background:#123;font-size:6em'>Hello from my PC!</h1>")

    def paste_html():
        content = html_box.get("1.0", "end")

        def folder():
            d = os.path.join(SITES_DIR, "pasted")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
                f.write(content)
            return d
        host_and_launch(folder)

    ttk.Button(t5, text="Send pasted HTML to TV", command=paste_html).pack(pady=4)

    # ================= Control Pad (PC mouse + keyboard -> TV page)
    t6 = ttk.Frame(nb, padding=12)
    nb.add(t6, text="Control Pad")
    ttk.Label(t6, wraplength=760, text="Use your PC mouse and keyboard on the TV page (Vizio OS, or any site opened "
              "'with PC control'). It runs over your network - Vizio's local API has no Bluetooth keyboard/mouse "
              "feature, so this is the working alternative.").pack(anchor="w")
    cv = tk.Canvas(t6, bg="#16213a", highlightthickness=0, height=260)
    cv.pack(fill="both", expand=True, pady=8)
    cv_text = cv.create_text(10, 10, anchor="nw", fill="white", font=("Segoe UI", 13), text=(
        "Click here to capture your mouse + keyboard.\n\n"
        "Move = TV cursor     Left click = click     Right click = Back\n"
        "Wheel = scroll       Type = text into the focused field\n"
        "Esc = release"))
    cap = {"on": False, "ax": 0, "ay": 0}
    SENS = 2.0

    def center():
        return cv.winfo_width() // 2, cv.winfo_height() // 2

    def capture():
        cap["on"] = True
        cv.config(cursor="none", bg="#1d3a2a")
        cv.focus_set()
        x, y = center()
        cv.event_generate("<Motion>", warp=True, x=x, y=y)

    def release(_e=None):
        cap["on"] = False
        cv.config(cursor="arrow", bg="#16213a")

    def on_motion(e):
        if not cap["on"]:
            return
        x, y = center()
        dx, dy = e.x - x, e.y - y
        if dx or dy:
            cap["ax"] += dx
            cap["ay"] += dy
            cv.event_generate("<Motion>", warp=True, x=x, y=y)

    def flush():
        if cap["ax"] or cap["ay"]:
            hub.broadcast({"t": "move", "dx": cap["ax"] * SENS, "dy": cap["ay"] * SENS})
            cap["ax"] = cap["ay"] = 0
        root.after(25, flush)

    def on_click(_e):
        if not cap["on"]:
            capture()
        else:
            hub.broadcast({"t": "click"})

    def on_key(e):
        if e.keysym == "Escape":
            return release()
        if not cap["on"]:
            return
        k = PAD_KEYS.get(e.keysym) or (e.char if e.char and e.char.isprintable() else None)
        if k:
            hub.broadcast({"t": "key", "key": k})
        return "break"

    cv.bind("<Motion>", on_motion)
    cv.bind("<Button-1>", on_click)
    cv.bind("<Button-3>", lambda e: cap["on"] and hub.broadcast({"t": "nav", "a": "back"}))
    cv.bind("<MouseWheel>", lambda e: cap["on"] and hub.broadcast({"t": "scroll", "dy": -e.delta / 120 * 90}))
    cv.bind("<Key>", on_key)
    cv.bind("<FocusOut>", release)
    nb.bind("<<NotebookTabChanged>>", lambda e: release())

    # ================= Banners
    t7 = ttk.Frame(nb, padding=12)
    nb.add(t7, text="Banners")
    ttk.Label(t7, wraplength=760, text="Show banners or full-screen messages on the TV. Vizio has no notification "
              "API, so these appear on the Vizio OS page (and on sites opened 'with PC control') while it's open on the TV."
              ).grid(row=0, column=0, columnspan=4, sticky="w")
    b_title, b_secs = tk.StringVar(), tk.IntVar(value=6)
    b_pos, b_kind = tk.StringVar(value="top"), tk.StringVar(value="info")
    ttk.Label(t7, text="Title").grid(row=1, column=0, sticky="w", pady=4)
    ttk.Entry(t7, textvariable=b_title, width=40).grid(row=1, column=1, columnspan=3, sticky="w")
    ttk.Label(t7, text="Message").grid(row=2, column=0, sticky="nw")
    b_text = tk.Text(t7, height=4, width=50)
    b_text.grid(row=2, column=1, columnspan=3, sticky="w")
    ttk.Label(t7, text="Seconds").grid(row=3, column=0, sticky="w", pady=4)
    ttk.Spinbox(t7, from_=1, to=300, textvariable=b_secs, width=5).grid(row=3, column=1, sticky="w")
    ttk.Combobox(t7, textvariable=b_pos, values=["top", "bottom", "center"], width=8, state="readonly").grid(row=3, column=2)
    ttk.Combobox(t7, textvariable=b_kind, values=["info", "success", "warning", "alert"], width=8, state="readonly").grid(row=3, column=3)

    def send_banner(full=False):
        if not hub.count():
            log("The TV page isn't open yet. Use 'URLs & OS' -> 'Open Vizio OS home' first.")
        hub.broadcast({"t": "banner", "title": b_title.get(), "text": b_text.get("1.0", "end").strip(),
                       "secs": b_secs.get(), "pos": b_pos.get(), "kind": b_kind.get(), "full": full})

    bz = ttk.Frame(t7)
    bz.grid(row=4, column=0, columnspan=4, pady=10, sticky="w")
    ttk.Button(bz, text="Send banner", command=lambda: send_banner(False)).pack(side="left", padx=4)
    ttk.Button(bz, text="Full-screen message", command=lambda: send_banner(True)).pack(side="left", padx=4)
    ttk.Button(bz, text="Clear", command=lambda: hub.broadcast({"t": "clear"})).pack(side="left", padx=4)

    # ================= Settings
    t8 = ttk.Frame(nb, padding=12)
    nb.add(t8, text="Settings")
    vf = ttk.Frame(t8)
    vf.pack(fill="x")
    ttk.Label(vf, text="Volume").pack(side="left")
    vol = tk.IntVar(value=20)
    ttk.Scale(vf, from_=0, to=100, variable=vol, length=300).pack(side="left", padx=8)
    vlabel = ttk.Label(vf, text="20", width=4)
    vlabel.pack(side="left")
    vol.trace_add("write", lambda *a: vlabel.config(text=str(vol.get())))

    def read_volume():
        tv = need_tv()
        if tv:
            bg(lambda: tv.get_setting("audio", "volume")["ITEMS"][0]["VALUE"], lambda v: vol.set(int(v)))

    def apply_volume():
        tv = need_tv()
        if tv:
            v = int(vol.get())
            bg(lambda: tv.set_setting("audio", "volume", v), lambda _: log(f"Volume set to {v}"))

    ttk.Button(vf, text="Read", command=read_volume).pack(side="left", padx=2)
    ttk.Button(vf, text="Apply", command=apply_volume).pack(side="left", padx=2)
    ttk.Separator(t8).pack(fill="x", pady=8)
    sf = ttk.Frame(t8)
    sf.pack(fill="x")
    sec_var = tk.StringVar(value="audio")
    ttk.Combobox(sf, textvariable=sec_var, values=["audio", "picture", "system", "network", "channels", "timers"],
                 width=12).pack(side="left")
    set_list = tk.Listbox(t8, height=10, font=("Consolas", 9))
    set_data = []

    def load_section():
        tv = need_tv()
        if tv:
            sec = sec_var.get()

            def done(j):
                set_data[:] = [(sec, it) for it in j.get("ITEMS", []) if it.get("CNAME")]
                set_list.delete(0, "end")
                for _, it in set_data:
                    set_list.insert("end", f"{it.get('NAME') or it['CNAME']} = {it.get('VALUE')}   [{it['CNAME']}]")
                log(f"{len(set_data)} settings in '{sec}'")
            bg(lambda: tv.get_setting(sec), done)

    ttk.Button(sf, text="Load section", command=load_section).pack(side="left", padx=6)
    ttk.Label(t8, text="Wrong low-level values can misconfigure your TV. Change one thing at a time.",
              foreground="#a00").pack(anchor="w", pady=(6, 0))
    set_list.pack(fill="both", expand=True)
    ef = ttk.Frame(t8)
    ef.pack(fill="x", pady=6)
    ttk.Label(ef, text="Double-click a setting to change it.").pack(side="left")

    def edit_setting(_e=None):
        tv, sel = need_tv(), set_list.curselection()
        if not (tv and sel):
            return
        sec, it = set_data[sel[0]]
        cur = "" if it.get("VALUE") is None else str(it.get("VALUE"))
        raw = simpledialog.askstring("Change setting", f"{it.get('NAME') or it['CNAME']}\n({it['CNAME']})",
                                     initialvalue=cur, parent=root)
        if raw is None or raw.strip() == cur:
            return
        raw = raw.strip()
        val = int(raw) if re.fullmatch(r"-?\d+", raw) else raw
        if messagebox.askyesno("Vizio Control", f"Set {it['CNAME']} to {val!r}?"):
            bg(lambda: tv.set_setting(sec, it["CNAME"], val),
               lambda _: (log(f"{it['CNAME']} = {val!r}"), load_section()))

    set_list.bind("<Double-Button-1>", edit_setting)

    def show_info():
        tv = need_tv()
        if tv:
            def work():
                info = tv.device_info()
                return {"power_on": tv.power_state(), "input": tv.current_input()[0],
                        "app": tv.current_app(), "device": info.get("ITEMS", info)}
            bg(work, lambda d: log("TV info: " + json.dumps(d)[:900]))

    ttk.Button(ef, text="TV info", command=show_info).pack(side="right")

    # ================= Schedule + Wake
    t11 = ttk.Frame(nb, padding=12)
    nb.add(t11, text="Schedule")
    ttk.Label(t11, wraplength=760, text="Scheduled actions run daily while this app is open. Wake-on-LAN turns "
              "the TV on over the network: enable it on the TV and enter its MAC address (Settings or your router "
              "list). Wake-on-LAN only works on TVs that support it.").pack(anchor="w")
    sched_list = tk.Listbox(t11, height=8)
    sched_list.pack(fill="both", expand=True, pady=6)

    def refresh_sched():
        sched_list.delete(0, "end")
        for e in store["schedules"]:
            sched_list.insert("end", f"{e['at']}  {e['act']}  {e.get('target', '')}")

    at_var, act_var, tgt_var = tk.StringVar(value="20:00"), tk.StringVar(value="Power On"), tk.StringVar()
    sf3 = ttk.Frame(t11)
    sf3.pack(fill="x")
    ttk.Entry(sf3, textvariable=at_var, width=7).pack(side="left")
    ttk.Combobox(sf3, textvariable=act_var, values=["Power On", "Power Off", "Launch URL"],
                 width=12, state="readonly").pack(side="left", padx=4)
    ttk.Entry(sf3, textvariable=tgt_var, width=30).pack(side="left")

    def add_sched():
        at = at_var.get().strip()
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", at):
            return messagebox.showerror("Vizio Control", "Time must be HH:MM (24-hour), e.g. 19:30")
        if act_var.get() == "Launch URL" and not tgt_var.get().strip():
            return messagebox.showerror("Vizio Control", "Enter the URL to launch.")
        store["schedules"].append({"at": at, "act": act_var.get(), "target": tgt_var.get().strip()})
        save_store(store)
        refresh_sched()

    def del_sched():
        sel = sched_list.curselection()
        if sel:
            store["schedules"].pop(sel[0])
            save_store(store)
            refresh_sched()

    ttk.Button(sf3, text="Add", command=add_sched).pack(side="left", padx=4)
    ttk.Button(sf3, text="Remove", command=del_sched).pack(side="left")
    wf = ttk.Frame(t11)
    wf.pack(fill="x", pady=8)
    mac_var = tk.StringVar(value=store["mac"])
    ttk.Label(wf, text="TV MAC:").pack(side="left")
    ttk.Entry(wf, textvariable=mac_var, width=20).pack(side="left", padx=4)

    def wake():
        store["mac"] = mac_var.get().strip()
        save_store(store)
        try:
            wake_on_lan(store["mac"])
            log("Wake-on-LAN packet sent. The TV can take ~10-20 seconds to answer.")
        except TVError as e:
            messagebox.showerror("Vizio Control", str(e))

    ttk.Button(wf, text="Wake TV", command=wake).pack(side="left", padx=4)
    refresh_sched()

    def run_scheduled(e):
        tv = state["tv"]
        if not tv or not tv.token:
            return log(f"Scheduled '{e['act']}' skipped: not connected")
        try:
            if e["act"] == "Launch URL":
                tv.launch_url(e["target"])
            else:
                tv.key(e["act"])
            log(f"Scheduled: {e['act']} {e.get('target', '')} ran")
        except TVError as x:
            log(f"Scheduled '{e['act']}' failed: {x}")

    def scheduler():
        fired = {}
        while True:
            day, hhmm = time.strftime("%Y-%m-%d"), time.strftime("%H:%M")
            for idx, e in enumerate(list(store["schedules"])):
                key = f"{idx}:{e['at']}:{e['act']}"
                if e["at"] == hhmm and fired.get(key) != day:
                    fired[key] = day
                    run_scheduled(e)
            time.sleep(20)

    # ================= PC screen mirror
    A0 = store["app"]
    screen_on = {"run": False, "maxw": RES_CHOICES.get(A0["mirror_res"], 960), "fit": "contain",
                 "fmt": FMT_CHOICES.get(A0["mirror_fmt"], "bmp"), "fps": int(A0["mirror_fps"]),
                 "stream": bool(A0["mirror_stream"]), "stats": ""}

    def screen_loop():
        errors, last_crc, frames, sent = 0, None, 0, 0
        t0 = time.time()
        w = h = 0
        while screen_on["run"]:
            t = time.time()
            try:
                w, h, bgr = capture_screen(screen_on["maxw"], raw=True)
                crc = zlib.adler32(bgr)
                if crc != last_crc:            # skip identical frames: idle desktop = zero traffic
                    last_crc = crc
                    data, ct = encode_frame(w, h, bgr, screen_on["fmt"])
                    hub.set_frame(data, ct)
                    frames += 1
                    sent += len(data)
                errors = 0
            except Exception as e:
                errors += 1
                log(f"Mirror frame error ({errors}/5): {e}")
                if errors >= 5:
                    screen_on["run"] = False
                    hub.mirror_on = False
                    hub.set_frame(None)
                    log("Mirror stopped after repeated errors")
                    break
                time.sleep(1)
                continue
            dt = time.time() - t0
            if dt >= 2:
                screen_on["stats"] = f"{w}x{h} {frames / dt:.1f} fps {sent / dt / 125000:.0f} Mbit/s"
                frames, sent, t0 = 0, 0, time.time()
            time.sleep(max(0.0, 1.0 / screen_on["fps"] - (time.time() - t)))

    def mirror_pc():
        tv = need_tv()
        if not tv:
            return
        if not hub_ok:
            return messagebox.showerror("Vizio Control", f"Port {HUB_PORT} is in use; can't mirror.")
        if os.name != "nt":
            return messagebox.showinfo("Vizio Control", "PC screen mirroring needs Windows.")
        if not screen_on["run"]:
            screen_on["run"] = True
            hub.mirror_on = True
            threading.Thread(target=screen_loop, daemon=True).start()
        page = hub.url(tv.ip) + "screen"

        def done(_):
            log(f"PC screen on the TV: {page}")
            root.after(4000, lambda: hub.broadcast({"t": "screen", "fit": screen_on["fit"],
                                                    "mode": "stream" if screen_on["stream"] else "poll"}))
        bg(lambda: tv.launch_url(page), done)

    def stop_mirror():
        screen_on["run"] = False
        hub.mirror_on = False
        hub.set_frame(None)
        log("Mirror stopped")

    # ================= Extensions
    t10 = ttk.Frame(nb, padding=12)
    nb.add(t10, text="Extensions")
    ttk.Label(t10, wraplength=760, text="The TV's browser can't install Chrome/uBlock extensions, so this app does the "
              "job itself for pages opened 'with PC control': ad/tracker blocking from uBlock-style filter lists "
              "(EasyList, EasyPrivacy, uBlock filters) plus your own CSS/JS (like a mini Tampermonkey). Pages "
              "launched directly in the TV's browser, and ads inside the TV's apps, are not affected.").pack(anchor="w")
    ad_var = tk.BooleanVar(value=store["adblock"])
    ad_status = tk.StringVar()

    def ad_label():
        ad_status.set(f"{len(adb.domains)} blocked domains, {len(adb.selectors)} hiding rules")

    def toggle_ad():
        adb.enabled = ad_var.get()
        store["adblock"] = adb.enabled
        save_store(store)

    def update_lists():
        log("Downloading filter lists...")
        bg(lambda: adb.update(FILTER_LISTS + store["filter_lists"], log), lambda n: (ad_label(), log(f"{n} list(s) loaded")))

    def add_list():
        u = simpledialog.askstring("Filter list", "URL of an EasyList/uBlock-format filter list:")
        if u and u.startswith("http"):
            store["filter_lists"].append(u.strip())
            save_store(store)
            update_lists()

    af2 = ttk.Frame(t10)
    af2.pack(fill="x", pady=8)
    ttk.Checkbutton(af2, text="Ad blocker", variable=ad_var, command=toggle_ad).pack(side="left")
    ttk.Button(af2, text="Update lists", command=update_lists).pack(side="left", padx=8)
    ttk.Button(af2, text="Add list URL...", command=add_list).pack(side="left")
    ttk.Label(af2, textvariable=ad_status).pack(side="left", padx=10)
    ad_label()
    ttk.Label(t10, text="Custom CSS (applied to every proxied page)").pack(anchor="w")
    css_box = tk.Text(t10, height=4, font=("Consolas", 9))
    css_box.pack(fill="x")
    css_box.insert("1.0", store["inject_css"])
    ttk.Label(t10, text="Custom JavaScript (runs on every proxied page)").pack(anchor="w", pady=(6, 0))
    js_box = tk.Text(t10, height=5, font=("Consolas", 9))
    js_box.pack(fill="x")
    js_box.insert("1.0", store["inject_js"])

    def save_inject():
        store["inject_css"] = css_box.get("1.0", "end").strip()
        store["inject_js"] = js_box.get("1.0", "end").strip()
        save_store(store)
        log("Custom CSS/JS saved (reload the page on the TV to apply)")

    ttk.Button(t10, text="Save CSS/JS", command=save_inject).pack(pady=6)
    if not adb.selectors:
        update_lists()

    # ================= Advanced
    t9 = ttk.Frame(nb, padding=12)
    nb.add(t9, text="Advanced")
    af = ttk.Frame(t9)
    af.pack(fill="x")
    method_var = tk.StringVar(value="GET")
    ttk.Combobox(af, textvariable=method_var, values=["GET", "PUT"], width=5, state="readonly").pack(side="left")
    path_var = tk.StringVar(value="/state/device/deviceinfo")
    ttk.Combobox(af, textvariable=path_var, values=[
        "/state/device/deviceinfo", "/state/device/power_mode", "/app/current",
        SETTINGS_BASE + "devices/name_input", SETTINGS_BASE + "devices/current_input",
        SETTINGS_BASE + "audio", SETTINGS_BASE + "picture", SETTINGS_BASE + "system",
        SETTINGS_BASE + "system/system_information/tv_information/version",
    ]).pack(side="left", fill="x", expand=True, padx=4)
    ttk.Label(t9, text="PUT body (JSON). Wrong low-level settings can misconfigure your TV.",
              foreground="#a00").pack(anchor="w", pady=(6, 0))
    body_box = tk.Text(t9, height=4, font=("Consolas", 9))
    body_box.pack(fill="x")
    out_box = tk.Text(t9, font=("Consolas", 9))

    def run_raw():
        tv = need_tv()
        if not tv:
            return
        m, p = method_var.get(), path_var.get()
        body = None
        if m == "PUT":
            try:
                body = json.loads(body_box.get("1.0", "end") or "{}")
            except ValueError:
                return messagebox.showerror("Vizio Control", "Body isn't valid JSON.")

        def show(j):
            out_box.delete("1.0", "end")
            out_box.insert("1.0", json.dumps(j, indent=2))
        bg(lambda: tv.request(m, p, body), show)

    ttk.Button(t9, text="Send", command=run_raw).pack(pady=6)
    out_box.pack(fill="both", expand=True)

    # ================= v1.1: helpers
    S = store["app"]
    _VERBOSE[0] = S["verbose"]
    ENTRY_TYPES = (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, ttk.Spinbox)

    def new_tab(title):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text=title)
        return f

    def textbox(parent, h=10, **kw):
        fr = ttk.Frame(parent)
        t = tk.Text(fr, height=h, font=("Consolas", 9), wrap="none", **kw)
        sb = ttk.Scrollbar(fr, command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        t.pack(side="left", fill="both", expand=True)
        return fr, t

    def put(t, s):
        t.delete("1.0", "end")
        t.insert("1.0", s)

    # ================= TV Remote (XRT260 / XRT270 / XRT270R / XRT290 layout + keyboard mapping)
    tr = new_tab("TV Remote")
    keymap = store.setdefault("keymap", dict(DEFAULT_KEYMAP))
    left = ttk.Frame(tr)
    left.pack(side="left", anchor="n")
    rows = [["Power Toggle", "", "Input"],
            ["@Netflix", "@YouTube", "@Prime Video"], ["@Hulu", "@Disney+", "@Max"],
            ["Vol +", "Mute", "Ch +"], ["Vol -", "CC", "Ch -"],
            ["Menu", "Up", "Info"], ["Left", "OK", "Right"], ["Back", "Down", "Home"],
            ["Exit", "SmartCast", "Prev Ch"], ["Rewind", "Play", "FF"], ["", "Pause", ""]]

    def app_shortcut(name):
        tv = need_tv()
        if not tv:
            return
        match = [n for n in all_apps() if name.lower().split()[0] in n.lower()]
        if not match:
            return log(f"No '{name}' in the app list yet - open the Apps tab and reload the catalog.")
        n = match[0]
        bg(lambda: launch_verified(tv, all_apps()[n], store["app_ok"].get(n), log))

    for r, row in enumerate(rows):
        for c, name in enumerate(row):
            if not name:
                continue
            if name.startswith("@"):
                ttk.Button(left, text=name[1:], width=12, command=lambda n=name[1:]: app_shortcut(n)).grid(row=r, column=c, padx=3, pady=3, ipady=2)
            else:
                ttk.Button(left, text=name, width=12, command=lambda n=name: press(n)).grid(row=r, column=c, padx=3, pady=3, ipady=2)
    right = ttk.Frame(tr)
    right.pack(side="left", fill="both", expand=True, padx=14)
    ttk.Label(right, wraplength=430, text="Works with the XRT260, XRT270/270R and XRT290 layouts: every button the TV's "
              "local API accepts is here. The coloured app buttons on the real remote are launched through the app list "
              "(the API has no key code for them). Your keyboard drives the TV while this tab is open.").pack(anchor="w")
    tf = ttk.Frame(right)
    tf.pack(fill="x", pady=6)
    ttk.Label(tf, text="Type on TV:").pack(side="left")
    type_var = tk.StringVar()
    te = ttk.Entry(tf, textvariable=type_var)
    te.pack(side="left", fill="x", expand=True, padx=4)

    def type_on_tv():
        tv = need_tv()
        if tv and type_var.get():
            txt = type_var.get()
            bg(lambda: tv.type_text(txt), lambda _: type_var.set(""))
    te.bind("<Return>", lambda e: type_on_tv())
    ttk.Button(tf, text="Send", command=type_on_tv).pack(side="left")
    ttk.Label(right, text="Keyboard / paired-remote key map (click Learn, then press the key):").pack(anchor="w", pady=(8, 2))
    km_list = tk.Listbox(right, height=9, font=("Consolas", 9))
    km_list.pack(fill="x")
    lf = ttk.Frame(right)
    lf.pack(fill="x", pady=4)
    learn_act = tk.StringVar(value="OK")
    ttk.Combobox(lf, textvariable=learn_act, values=list(KEYS), state="readonly", width=14).pack(side="left")
    learning = {"on": False}
    learn_msg = tk.StringVar()

    def refresh_km():
        km_list.delete(0, "end")
        for k, a in sorted(keymap.items(), key=lambda kv: kv[1]):
            km_list.insert("end", f"{k:<12} -> {a}")

    def start_learn():
        learning["on"] = True
        learn_msg.set("Press a key now...")
        root.focus_set()

    def del_km():
        s = km_list.curselection()
        if s:
            keymap.pop(km_list.get(s[0]).split()[0], None)
            save_store(store)
            refresh_km()

    def open_bt():
        try:
            os.startfile("ms-settings:bluetooth")
        except Exception:
            messagebox.showinfo("Vizio Control", "Open your OS Bluetooth settings and pair the remote.")
    ttk.Button(lf, text="Learn", command=start_learn).pack(side="left", padx=4)
    ttk.Button(lf, text="Delete mapping", command=del_km).pack(side="left")
    ttk.Button(lf, text="Bluetooth settings", command=open_bt).pack(side="left", padx=4)
    ttk.Label(right, textvariable=learn_msg, foreground="#06c").pack(anchor="w")
    ttk.Label(right, wraplength=430, foreground="#555", text="Bluetooth honesty: Vizio remotes normally pair to the TV, not "
              "to a PC, and their protocol isn't documented. If Windows pairs yours as a keyboard/HID device, its buttons "
              "arrive here as keys and 'Learn' maps them; otherwise use the on-screen remote or keyboard.").pack(anchor="w")
    refresh_km()

    def on_key(e):
        if learning["on"]:
            learning["on"] = False
            keymap[e.keysym] = learn_act.get()
            save_store(store)
            refresh_km()
            learn_msg.set(f"{e.keysym} -> {learn_act.get()}")
            return "break"
        if not S["hotkeys"] or nb.select() != str(tr) or isinstance(root.focus_get(), ENTRY_TYPES):
            return
        act = keymap.get(e.keysym)
        if act in KEYS:
            press(act)
            return "break"
    root.bind("<Key>", on_key, add="+")

    # ================= Scenes & Macros
    sm = new_tab("Scenes & Macros")
    macros = store.setdefault("macros", {k: list(v) for k, v in DEFAULT_MACROS.items()})
    ml = tk.Listbox(sm, height=12, exportselection=False)
    ml.pack(side="left", fill="y")
    mr = ttk.Frame(sm)
    mr.pack(side="left", fill="both", expand=True, padx=8)
    ttk.Label(mr, wraplength=520, text="One step per line:  key:Vol +  |  wait:1.5  |  input:HDMI-1  |  app:Netflix  |  "
              "url:https://...  |  type:hello  |  setting:picture|brightness|50  |  log:text  |  # comment").pack(anchor="w")
    mf_, mbox = textbox(mr, 10)
    mf_.pack(fill="both", expand=True)

    def refresh_macros():
        ml.delete(0, "end")
        for n in macros:
            ml.insert("end", n)

    def sel_macro(_=None):
        s = ml.curselection()
        if s:
            put(mbox, "\n".join(macros[ml.get(s[0])]))

    def save_macro():
        s = ml.curselection()
        if s:
            macros[ml.get(s[0])] = [x for x in mbox.get("1.0", "end").splitlines() if x.strip()]
            save_store(store)
            log("Scene saved")

    def new_macro():
        n = simpledialog.askstring("Vizio Control", "Scene name:")
        if n:
            macros[n] = ["log:" + n]
            save_store(store)
            refresh_macros()

    def del_macro():
        s = ml.curselection()
        if s:
            macros.pop(ml.get(s[0]), None)
            save_store(store)
            refresh_macros()

    def run_steps(steps):
        tv = need_tv()
        if not tv:
            return

        def work():
            for st in steps:
                st = st.strip()
                if not st or st.startswith("#"):
                    continue
                op, _, arg = st.partition(":")
                op, arg = op.strip().lower(), arg.strip()
                if op == "key":
                    tv.key(arg)
                elif op == "wait":
                    time.sleep(float(arg))
                elif op == "input":
                    tv.set_input(arg)
                elif op == "url":
                    tv.launch_url(arg)
                elif op == "app":
                    launch_verified(tv, all_apps()[arg], store["app_ok"].get(arg), log)
                elif op == "type":
                    tv.type_text(arg)
                elif op == "setting":
                    a, b, c = arg.split("|")
                    tv.set_setting(a, b, c)
                elif op == "log":
                    log(arg)
                else:
                    log(f"Unknown step: {st}")
            log("Scene finished")
        bg(work)

    def run_macro():
        save_macro()
        s = ml.curselection()
        if s:
            run_steps(macros[ml.get(s[0])])
    ml.bind("<<ListboxSelect>>", sel_macro)
    mb = ttk.Frame(mr)
    mb.pack(fill="x", pady=4)
    for t_, c_ in (("Run", run_macro), ("Save", save_macro), ("New", new_macro), ("Delete", del_macro)):
        ttk.Button(mb, text=t_, command=c_).pack(side="left", padx=3)
    refresh_macros()

    # ================= Tools: 5 main tools + plugin buttons
    tl = new_tab("Tools")
    plug_btns = ttk.LabelFrame(tl, text="Plugin tools (from the Tool Maker)", padding=6)
    tool_out = tk.StringVar()

    def tool_frame(title):
        f = ttk.LabelFrame(tl, text=title, padding=6)
        f.pack(fill="x", pady=3)
        return f

    # 1 Cast File
    f1 = tool_frame("1. Cast File - play a local video/image/audio on the TV through its browser")

    def cast_file():
        tv = need_tv()
        p = filedialog.askopenfilename() if tv else None
        if not p:
            return
        d = os.path.join(SITES_DIR, "cast")
        os.makedirs(d, exist_ok=True)
        for old in os.listdir(d):
            try:
                os.remove(os.path.join(d, old))
            except OSError:
                pass
        import shutil
        name = os.path.basename(p)
        shutil.copy(p, os.path.join(d, name))
        url = server.serve(d, tv.ip) + urllib.parse.quote(name)
        log(f"Casting {name}: {url}")
        bg(lambda: tv.launch_url(url))
    ttk.Button(f1, text="Choose file and cast", command=cast_file).pack(side="left")
    ttk.Label(f1, text="  Needs a format the TV browser supports (MP4/H.264, JPG, PNG, MP3).").pack(side="left")

    # 2 Health monitor
    f2 = tool_frame("2. TV Health Monitor - latency, power, input and current app over time")
    hm = {"run": False}
    hb_fr, hbox = textbox(f2, 5)

    def health_loop(tv):
        n = 0
        while hm["run"]:
            t = time.time()
            try:
                pw = tv.power_state()
                ms = int((time.time() - t) * 1000)
                app = tv.current_app() if pw else None
                line = f"{time.strftime('%H:%M:%S')}  {ms:4d} ms  power={'on' if pw else 'off'}  app={(app or {}).get('NAME_SPACE', '-')}/{(app or {}).get('APP_ID', '-')}"
            except Exception as e:
                line = f"{time.strftime('%H:%M:%S')}  FAIL {e}"
            root.after(0, lambda l=line: (hbox.insert("end", l + "\n"), hbox.see("end")))
            n += 1
            time.sleep(3)

    def toggle_health():
        tv = need_tv()
        if not tv:
            return
        hm["run"] = not hm["run"]
        if hm["run"]:
            threading.Thread(target=health_loop, args=(tv,), daemon=True).start()
    hbf = ttk.Frame(f2)
    hbf.pack(fill="x")
    ttk.Button(hbf, text="Start / stop", command=toggle_health).pack(side="left")
    ttk.Button(hbf, text="Clear", command=lambda: hbox.delete("1.0", "end")).pack(side="left", padx=4)
    hb_fr.pack(fill="x")

    # 3 Settings backup
    f3 = tool_frame("3. TV Settings Backup / Restore (picture + audio restore is experimental)")
    BK_SECTIONS = ["picture", "audio", "system", "network", "timers", "channels", "devices", "cast"]

    def backup_settings():
        tv = need_tv()
        if not tv:
            return

        def work():
            out = {}
            for sec in BK_SECTIONS:
                try:
                    out[sec] = tv.get_setting(sec)
                except Exception as e:
                    out[sec] = {"error": str(e)}
            return out

        def done(o):
            p = filedialog.asksaveasfilename(defaultextension=".json", initialfile="vizio_settings_backup.json")
            if p:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(o, f, indent=2)
                log(f"Backup saved: {p}")
        bg(work, done)

    def restore_settings():
        tv = need_tv()
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")]) if tv else None
        if not p or not messagebox.askyesno("Vizio Control", "Write the backed-up picture/audio values back to the TV?"):
            return
        data = json.load(open(p, encoding="utf-8"))

        def work():
            n = 0
            for sec in ("picture", "audio"):
                for it in data.get(sec, {}).get("ITEMS", []):
                    v, cn = it.get("VALUE"), it.get("CNAME")
                    if cn and isinstance(v, (int, str)) and "READONLY" not in str(it.get("TYPE", "")).upper():
                        try:
                            tv.set_setting(sec, cn, v)
                            n += 1
                        except Exception:
                            pass
            log(f"Restored {n} settings")
        bg(work)
    ttk.Button(f3, text="Back up to file", command=backup_settings).pack(side="left")
    ttk.Button(f3, text="Restore from file", command=restore_settings).pack(side="left", padx=4)

    # 4 Mirror benchmark
    f4 = tool_frame("4. Mirror Benchmark - finds the best resolution/format for your PC and link")
    link_var = tk.IntVar(value=200)
    ttk.Label(f4, text="Real PC->TV link speed (Mbit/s; Wi-Fi ~100-300, Ethernet ~900):").pack(side="left")
    ttk.Spinbox(f4, from_=10, to=2000, textvariable=link_var, width=6).pack(side="left", padx=4)
    bench_out = tk.StringVar()

    def run_bench():
        if os.name != "nt":
            return log("Benchmark needs Windows (screen capture).")
        link = max(1, link_var.get()) * 125000.0

        def work():
            res = []
            for mw in (640, 960, 1280, 1600, 1920, 2560):
                for fmt, name in (("bmp", "raw"), ("png", "png")):
                    tc = te_ = 0.0
                    size = 0
                    for _ in range(3):
                        t = time.time()
                        w, h, bgr = capture_screen(mw, raw=True)
                        tc += time.time() - t
                        t = time.time()
                        d, _ct = encode_frame(w, h, bgr, fmt)
                        te_ += time.time() - t
                        size = len(d)
                    cpu_fps = 3.0 / max(tc + te_, 1e-6)
                    fps = min(cpu_fps, link / size)
                    res.append((fps, f"{w}x{h} {name:>3}: {size / 1e6:5.2f} MB/frame, PC {cpu_fps:5.1f} fps, link {link / size:5.1f} fps -> ~{fps:4.1f} fps"))
            good = [r for r in res if r[0] >= 20] or res
            best = max(good, key=lambda r: int(r[1].split("x")[0]))
            return "\n".join(r[1] for r in res) + "\n\nBest with >=20 fps: " + best[1].split(":")[0]
        bg(work, lambda s: (bench_out.set(s), log("Benchmark done - see Tools tab")))
    ttk.Button(f4, text="Run (about 10 s)", command=run_bench).pack(side="left", padx=4)
    ttk.Label(tl, textvariable=bench_out, font=("Consolas", 8), justify="left").pack(anchor="w")

    # 5 Quick scenes launcher
    f5 = tool_frame("5. One-click Scenes (edit them in the Scenes & Macros tab)")
    scene_fr = ttk.Frame(f5)
    scene_fr.pack(fill="x")

    def refresh_scene_buttons():
        for w in scene_fr.winfo_children():
            w.destroy()
        for n in macros:
            ttk.Button(scene_fr, text=n, command=lambda n=n: run_steps(macros[n])).pack(side="left", padx=3)
    refresh_scene_buttons()
    ml.bind("<FocusOut>", lambda e: refresh_scene_buttons(), add="+")
    plug_btns.pack(fill="x", pady=3)

    # ================= Developer: packet inspector, network debugger, console, tool maker, file grabber
    dv = new_tab("Developer")
    dnb = ttk.Notebook(dv)
    dnb.pack(fill="both", expand=True)

    # --- Packet Inspector / Network Debugger
    pk = ttk.Frame(dnb, padding=6)
    dnb.add(pk, text="Packet Inspector")
    pf = ttk.Frame(pk)
    pf.pack(fill="x")
    flt = tk.StringVar()
    paused = tk.BooleanVar(value=False)
    ttk.Label(pf, text="Filter:").pack(side="left")
    ttk.Entry(pf, textvariable=flt, width=22).pack(side="left", padx=4)
    ttk.Checkbutton(pf, text="Pause", variable=paused).pack(side="left")
    ptree = ttk.Treeview(pk, columns=("t", "dir", "m", "u", "s", "ms"), show="headings", height=9)
    for c_, w_ in (("t", 70), ("dir", 60), ("m", 50), ("u", 380), ("s", 60), ("ms", 50)):
        ptree.heading(c_, text=c_.upper())
        ptree.column(c_, width=w_, anchor="w")
    ptree.pack(fill="x", pady=4)
    pd_fr, pdetail = textbox(pk, 10)
    pd_fr.pack(fill="both", expand=True)
    shown = {"last": 0}
    recs = {}

    def all_traffic():
        return sorted(list(TRAFFIC), key=lambda r: r["id"])

    def pump():
        if not paused.get():
            for r in all_traffic():
                if r["id"] > shown["last"]:
                    shown["last"] = r["id"]
                    recs[str(r["id"])] = r
                    txt = f"{r['method']} {r['url']} {r.get('status', '')}"
                    if flt.get().lower() in txt.lower():
                        ptree.insert("", "end", iid=str(r["id"]), values=(
                            time.strftime("%H:%M:%S", time.localtime(r["t"])), r["dir"], r["method"],
                            r["url"], r.get("status", ""), r.get("ms", "")))
                        ptree.yview_moveto(1)
            kids = ptree.get_children()
            for k in kids[:-1500]:
                ptree.delete(k)
        root.after(400, pump)

    def show_pkt(_=None):
        s = ptree.selection()
        if not s:
            return
        r = recs.get(s[0])
        hdr = {"Content-Type": "application/json", "AUTH": r["token"] if (r.get("token") and not S["mask"]) else mask(r.get("token"))} if r["dir"] == "PC→TV" else r.get("req")
        put(pdetail, f"{r['method']} {r['url']}\nclient/side: {r.get('client', 'this PC')}\nheaders:\n{json.dumps(hdr, indent=2)}\n\n"
                     f"--- body sent ---\n{json.dumps(r.get('req') if r['dir'] == 'PC→TV' else '', indent=2)}\n\n"
                     f"--- response ({r.get('status')}, {r.get('ms')} ms, {len(json.dumps(r.get('resp', ''), default=str))} bytes) ---\n"
                     f"{json.dumps(r.get('resp'), indent=2, default=str)}")
    ptree.bind("<<TreeviewSelect>>", show_pkt)

    def replay():
        s = ptree.selection()
        tv = need_tv()
        if s and tv and recs[s[0]]["dir"] == "PC→TV":
            r = recs[s[0]]
            bg(lambda: tv.request(r["method"], r["url"].split(tv.host, 1)[1], r.get("req")), lambda j: put(pdetail, json.dumps(j, indent=2)))

    def export_traffic():
        p = filedialog.asksaveasfilename(defaultextension=".json", initialfile="vizio_traffic.json")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(all_traffic(), f, indent=2, default=lambda o: "***" if o is None else str(o))
            log(f"Exported {len(TRAFFIC)} packets")

    def clear_pk():
        TRAFFIC.clear()
        recs.clear()
        ptree.delete(*ptree.get_children())
    pbb = ttk.Frame(pk)
    pbb.pack(fill="x")
    for t_, c_ in (("Replay selected", replay), ("Export JSON", export_traffic), ("Clear", clear_pk)):
        ttk.Button(pbb, text=t_, command=c_).pack(side="left", padx=3)
    ttk.Label(pbb, text="Shows PC->TV API calls and TV->PC page requests. Traffic that never touches this PC can't be seen.",
              foreground="#555").pack(side="left", padx=6)
    pump()

    # --- Network debugger (probe)
    nd = ttk.Frame(dnb, padding=6)
    dnb.add(nd, text="Network Debugger")
    nd_fr, ndout = textbox(nd, 14)

    def net_probe():
        tv = need_tv()
        if not tv:
            return

        def work():
            lines = [f"TV {tv.ip}"]
            t = time.time()
            ports = probe_ports(tv.ip)
            lines.append(f"Open TCP ports ({time.time() - t:.1f}s): {ports}")
            for ip, txt in ssdp_dump(3.0):
                if ip == tv.ip:
                    lines.append(f"\nSSDP reply from {ip}:\n{txt.strip()}")
            for p in ("/state/device/deviceinfo", "/state/device/power_mode", "/app/current"):
                try:
                    lines.append(f"\nGET {p}\n" + json.dumps(tv.request("GET", p), indent=2))
                except Exception as e:
                    lines.append(f"\nGET {p} -> {e}")
            return "\n".join(lines)
        bg(work, lambda s: put(ndout, s))
    ttk.Button(nd, text="Probe TV (ports, SSDP/UPnP, device info)", command=net_probe).pack(anchor="w")
    ttk.Label(nd, wraplength=700, foreground="#555", text="Live view of everything the TV sends to or asks of this PC is in "
              "Packet Inspector. To see the TV's traffic to the internet you'd need a router/mirror-port capture (Wireshark); a PC can't see it.").pack(anchor="w")
    nd_fr.pack(fill="both", expand=True)

    # --- BLE Remote (experimental)
    br = ttk.Frame(dnb, padding=6)
    dnb.add(br, text="BLE Remote")
    ttk.Label(br, wraplength=740, justify="left", text=
              "Honest status: the XRT260 / XRT270 / XRT270R pair over Bluetooth Low Energy using a proprietary GATT "
              "service (VIZIO BLE RCU, by Kyung In Electronics) - not a standard keyboard/media-key profile. Windows "
              "has no driver that turns its button presses into key events, so there is no 'just works' fix; nobody "
              "has published the characteristic layout. What this tab CAN do: scan for the remote, connect to it, "
              "subscribe to every GATT characteristic that supports notifications, and show the raw bytes each "
              "button press sends. That's the real first step to mapping it - press each button once, watch which "
              "bytes change, and 'Learn raw' saves that mapping so matching future presses show up as a named key "
              "below. Needs: a Bluetooth LE adapter on this PC, and 'pip install bleak' (one-time, not bundled).").pack(anchor="w")
    blf = ttk.Frame(br)
    blf.pack(fill="x", pady=6)
    ble_out_fr, ble_out = textbox(br, 12)
    ble_state = {"dev": None, "learning": None, "map": store.setdefault("ble_map", {})}

    def ble_import():
        try:
            import bleak
            return bleak
        except ImportError:
            return None

    def ble_scan():
        bleak = ble_import()
        if not bleak:
            return messagebox.showinfo("Vizio Control", "Run 'pip install bleak' first (needs a BLE-capable adapter).")

        def work():
            import asyncio

            async def go():
                devs = await bleak.BleakScanner.discover(timeout=6.0)
                return [(d.address, d.name or "?") for d in devs]
            return asyncio.run(go())

        def done(devs):
            ble_pick["values"] = [f"{n}  ({a})" for a, n in devs]
            if devs:
                ble_pick.current(0)
            log(f"BLE scan: {len(devs)} device(s) found. Put the remote in pairing mode (hold MIC+MUTE) before scanning if it's not listed.")
        bg(work, done)

    def ble_connect():
        bleak = ble_import()
        sel = ble_pick.get()
        if not (bleak and sel):
            return
        addr = sel.split("(")[-1].rstrip(")")

        def work():
            import asyncio

            async def go():
                client = bleak.BleakClient(addr)
                await client.connect(timeout=10.0)
                lines = [f"Connected: {addr}"]
                for svc in client.services:
                    lines.append(f"\nService {svc.uuid}")
                    for ch in svc.characteristics:
                        lines.append(f"  char {ch.uuid}  props={ch.properties}")

                def cb(handle, data):
                    b = data.hex()
                    root.after(0, lambda: on_notify(handle, b))
                for svc in client.services:
                    for ch in svc.characteristics:
                        if "notify" in ch.properties or "indicate" in ch.properties:
                            try:
                                asyncio.get_event_loop().run_until_complete(client.start_notify(ch.uuid, cb))
                            except Exception:
                                pass
                ble_state["client"], ble_state["loop"] = client, asyncio.get_event_loop()
                return "\n".join(lines)
            return asyncio.run(go())
        bg(work, lambda s: put(ble_out, s + "\n\nListening for button presses...\n"))

    def on_notify(handle, hexdata):
        if ble_state["learning"]:
            name = ble_state["learning"]
            ble_state["map"][hexdata] = name
            save_store(store)
            ble_state["learning"] = None
            learn_ble_msg.set(f"Mapped {hexdata} -> {name}")
        act = ble_state["map"].get(hexdata)
        ble_out.insert("end", f"{time.strftime('%H:%M:%S')}  handle={handle}  {hexdata}" + (f"   -> {act}" if act else "") + "\n")
        ble_out.see("end")
        if act and act in KEYS:
            press(act)

    def ble_learn():
        ble_state["learning"] = ble_learn_act.get()
        learn_ble_msg.set("Press the remote button now...")
    ttk.Button(blf, text="Scan", command=ble_scan).pack(side="left")
    ble_pick = ttk.Combobox(blf, width=34, state="readonly")
    ble_pick.pack(side="left", padx=4)
    ttk.Button(blf, text="Connect & listen", command=ble_connect).pack(side="left", padx=4)
    blf2 = ttk.Frame(br)
    blf2.pack(fill="x")
    ble_learn_act = tk.StringVar(value="OK")
    ttk.Combobox(blf2, textvariable=ble_learn_act, values=list(KEYS), state="readonly", width=14).pack(side="left")
    ttk.Button(blf2, text="Learn raw -> key", command=ble_learn).pack(side="left", padx=4)
    learn_ble_msg = tk.StringVar()
    ttk.Label(blf2, textvariable=learn_ble_msg, foreground="#06c").pack(side="left", padx=6)
    ble_out_fr.pack(fill="both", expand=True)

    # --- Console
    co = ttk.Frame(dnb, padding=6)
    dnb.add(co, text="Console")
    co_fr, cout = textbox(co, 14)
    co_fr.pack(fill="both", expand=True)
    cin = tk.StringVar()
    ce = ttk.Entry(co, textvariable=cin, font=("Consolas", 10))
    ce.pack(fill="x", pady=4)
    hist = {"l": [], "i": 0}

    def cprint(s):
        cout.insert("end", str(s) + "\n")
        cout.see("end")

    def ctx_globals():
        return {"tv": state["tv"], "hub": hub, "store": store, "state": state, "log": log, "root": root, "TRAFFIC": TRAFFIC,
                "KEYS": KEYS, "TV": TV, "json": json, "time": time, "run_steps": run_steps, "press": press, "all_apps": all_apps}

    def run_console(_=None):
        line = cin.get().strip()
        if not line:
            return
        hist["l"].append(line)
        hist["i"] = len(hist["l"])
        cin.set("")
        cprint(">>> " + line)
        tv = state["tv"]

        def work():
            parts = line.split(None, 2)
            cmd = parts[0].lower()
            if cmd in ("get", "put") and len(parts) >= 2 and tv:
                body = json.loads(parts[2]) if len(parts) > 2 else None
                return json.dumps(tv.request(cmd.upper(), parts[1], body), indent=2)
            if cmd == "key" and tv and len(parts) >= 2:
                tv.key(line.split(None, 1)[1])
                return "sent"
            if cmd == "help":
                return "get /path | put /path {json} | key Vol + | any Python (vars: tv hub store state log TRAFFIC KEYS TV run_steps press)"
            g = ctx_globals()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    r = eval(line, g)
                    if r is not None:
                        print(repr(r))
                except SyntaxError:
                    exec(line, g)
            return buf.getvalue().rstrip()

        def run():
            try:
                res = work()
            except Exception:
                res = traceback.format_exc(limit=2)
            root.after(0, lambda: cprint(res))
        threading.Thread(target=run, daemon=True).start()
    ce.bind("<Return>", run_console)
    ce.bind("<Up>", lambda e: (hist.__setitem__("i", max(0, hist["i"] - 1)), cin.set(hist["l"][hist["i"]] if hist["l"] else "")))
    cprint("Developer console. Type 'help'. Python runs in-process: you can change the running app.")

    # --- Tool Maker (plugins)
    tm = ttk.Frame(dnb, padding=6)
    dnb.add(tm, text="Tool Maker")
    os.makedirs(PLUGIN_DIR, exist_ok=True)
    pl_list = tk.Listbox(tm, width=22, exportselection=False)
    pl_list.pack(side="left", fill="y")
    tmr = ttk.Frame(tm)
    tmr.pack(side="left", fill="both", expand=True, padx=6)
    te_fr, tedit = textbox(tmr, 16)
    te_fr.pack(fill="both", expand=True)
    cur_plugin = {"name": None}

    class Ctx:
        def tv(self):
            return state["tv"]

        def log(self, m):
            log(m)

        def key(self, n):
            return state["tv"].key(n)

        def request(self, m, p, b=None):
            return state["tv"].request(m, p, b)

        def launch_url(self, u):
            return state["tv"].launch_url(u)

        def add_button(self, label, fn):
            ttk.Button(plug_btns, text=label, command=lambda: bg(fn)).pack(side="left", padx=3)
    ctx = Ctx()
    ctx.TV, ctx.hub, ctx.store = TV, hub, store

    def refresh_plugins():
        pl_list.delete(0, "end")
        for n in sorted(os.listdir(PLUGIN_DIR)):
            if n.endswith(".py"):
                pl_list.insert("end", n)

    def load_plugin(name):
        try:
            src = open(os.path.join(PLUGIN_DIR, name), encoding="utf-8").read()
            g = {"__name__": "vc_plugin_" + name[:-3]}
            exec(compile(src, name, "exec"), g)
            g["register"](ctx)
            log(f"Plugin loaded: {name}")
        except Exception:
            log(f"Plugin {name} failed:\n" + traceback.format_exc(limit=3))

    def sel_plugin(_=None):
        s = pl_list.curselection()
        if s:
            cur_plugin["name"] = pl_list.get(s[0])
            put(tedit, open(os.path.join(PLUGIN_DIR, cur_plugin["name"]), encoding="utf-8").read())

    def save_plugin():
        if cur_plugin["name"]:
            with open(os.path.join(PLUGIN_DIR, cur_plugin["name"]), "w", encoding="utf-8") as f:
                f.write(tedit.get("1.0", "end"))
            log(f"Saved {cur_plugin['name']}")

    def new_plugin():
        n = simpledialog.askstring("Vizio Control", "Tool file name (letters/numbers):")
        if n:
            n = re.sub(r"[^A-Za-z0-9_]", "", n) + ".py"
            with open(os.path.join(PLUGIN_DIR, n), "w", encoding="utf-8") as f:
                f.write(PLUGIN_TEMPLATE)
            refresh_plugins()

    def run_plugin():
        save_plugin()
        if cur_plugin["name"]:
            load_plugin(cur_plugin["name"])

    def del_plugin():
        if cur_plugin["name"] and messagebox.askyesno("Vizio Control", f"Delete {cur_plugin['name']}?"):
            os.remove(os.path.join(PLUGIN_DIR, cur_plugin["name"]))
            cur_plugin["name"] = None
            put(tedit, "")
            refresh_plugins()
    pl_list.bind("<<ListboxSelect>>", sel_plugin)
    tmb = ttk.Frame(tmr)
    tmb.pack(fill="x", pady=3)
    def show_guide():
        top = tk.Toplevel(root)
        top.title("Tool Maker - Advanced Guide")
        top.geometry("760x600")
        fr, gb = textbox(top, 30)
        fr.pack(fill="both", expand=True, padx=8, pady=8)
        put(gb, TOOL_GUIDE)
        gb.configure(state="disabled")
    for t_, c_ in (("New tool", new_plugin), ("Save", save_plugin), ("Save & run", run_plugin), ("Delete", del_plugin),
                   ("Advanced guide", show_guide),
                   ("Open folder", lambda: os.startfile(PLUGIN_DIR) if os.name == "nt" else log(PLUGIN_DIR))):
        ttk.Button(tmb, text=t_, command=c_).pack(side="left", padx=3)
    refresh_plugins()
    for n in sorted(os.listdir(PLUGIN_DIR)):
        if n.endswith(".py"):
            load_plugin(n)

    # --- File Grabber
    fg = ttk.Frame(dnb, padding=6)
    dnb.add(fg, text="File Grabber")
    cap_on = tk.BooleanVar(value=S["capture"])
    fg_list = tk.Listbox(fg, height=12, font=("Consolas", 9))

    def set_capture():
        S["capture"] = cap_on.get()
        hub.capture = S["capture"]
        save_store(store)

    def refresh_caps():
        fg_list.delete(0, "end")
        for dp, _dn, fn in os.walk(CAPTURE_DIR):
            for f in fn:
                fg_list.insert("end", os.path.relpath(os.path.join(dp, f), CAPTURE_DIR))

    def dump_catalog():
        def work():
            d = os.path.join(CAPTURE_DIR, "vizio_catalog")
            os.makedirs(d, exist_ok=True)
            n = 0
            for u in CATALOG_URLS:
                try:
                    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=15) as r:
                        with open(os.path.join(d, u.rsplit("/", 1)[1]), "wb") as f:
                            f.write(r.read())
                        n += 1
                except Exception as e:
                    log(f"{u}: {e}")
            return n
        bg(work, lambda n: (log(f"Saved {n} catalog files (app IDs, namespaces, launch configs)"), refresh_caps()))

    def grab_path():
        tv = need_tv()
        p = simpledialog.askstring("Vizio Control", "TV API path to save (e.g. /menu_native/dynamic/tv_settings/system):") if tv else None
        if p:
            def work():
                j = tv.request("GET", p)
                fp = os.path.join(CAPTURE_DIR, "tv_api", re.sub(r"[^A-Za-z0-9_.-]", "_", p.strip("/")) + ".json")
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(j, f, indent=2)
                return fp
            bg(work, lambda fp: (log(f"Saved {fp}"), refresh_caps()))

    def open_caps():
        os.makedirs(CAPTURE_DIR, exist_ok=True)
        os.startfile(CAPTURE_DIR) if os.name == "nt" else log(CAPTURE_DIR)
    ttk.Checkbutton(fg, variable=cap_on, command=set_capture,
                    text="Save every page/script/asset the TV loads through this PC's proxy and OS server").pack(anchor="w")
    gb = ttk.Frame(fg)
    gb.pack(fill="x", pady=4)
    for t_, c_ in (("Dump Vizio app catalog", dump_catalog), ("Save a TV API path", grab_path), ("Refresh", refresh_caps), ("Open folder", open_caps)):
        ttk.Button(gb, text=t_, command=c_).pack(side="left", padx=3)
    ttk.Label(fg, wraplength=700, foreground="#555", text="Honest limit: SmartCast has no file-system API, so installed app packages can't be pulled "
              "off the TV. This grabs what the TV fetches from this PC (HTML/JS/CSS of web apps you launch), Vizio's app catalog "
              "with launch configs, and any TV API response, so you can study how apps are wired.").pack(anchor="w")
    fg_list.pack(fill="both", expand=True)
    hub.capture = S["capture"]
    refresh_caps()

    # ================= App Settings
    st_ = new_tab("App Settings")

    def setting_check(key, text, cmd=None):
        v = tk.BooleanVar(value=S[key])

        def chg():
            S[key] = v.get()
            save_store(store)
            if cmd:
                cmd()
        ttk.Checkbutton(st_, text=text, variable=v, command=chg).pack(anchor="w", pady=2)

    def apply_theme():
        dark = S["theme"] == "dark"
        bgc, fgc, fld = ("#14181f", "#e8ecf2", "#1d232d") if dark else ("#f0f0f0", "#000000", "#ffffff")
        try:
            style.theme_use("clam" if dark or os.name != "nt" else "vista")
        except tk.TclError:
            pass
        if dark:
            style.configure(".", background=bgc, foreground=fgc, fieldbackground=fld)
            style.configure("TNotebook.Tab", background="#222a36", foreground=fgc)
            style.map("TNotebook.Tab", background=[("selected", "#2d3748")])
            style.configure("Treeview", background=fld, foreground=fgc, fieldbackground=fld)
        root.configure(bg=bgc)

        def walk(w):
            for c in w.winfo_children():
                if c.winfo_class() in ("Text", "Listbox", "Entry"):   # classic tk widgets only (ttk ones are styled)
                    try:
                        c.configure(bg=fld, fg=fgc)
                        if c.winfo_class() != "Listbox":
                            c.configure(insertbackground=fgc)
                    except tk.TclError:
                        pass
                walk(c)
        walk(root)
    th = tk.StringVar(value=S["theme"])
    thf = ttk.Frame(st_)
    thf.pack(anchor="w", pady=2)
    ttk.Label(thf, text="Theme:").pack(side="left")
    for v_ in ("light", "dark"):
        ttk.Radiobutton(thf, text=v_.title(), value=v_, variable=th,
                        command=lambda: (S.__setitem__("theme", th.get()), save_store(store), apply_theme())).pack(side="left", padx=4)
    setting_check("ontop", "Keep Vizio Control on top of other windows", lambda: root.attributes("-topmost", S["ontop"]))
    setting_check("autoreconnect", "Auto-reconnect: re-check the TV every 30 s and log when it drops / comes back")
    setting_check("hotkeys", "Keyboard remote: use the key map on the TV Remote tab")
    setting_check("mask", "Mask the pairing token in Packet Inspector")
    setting_check("verbose", "Verbose: also log TV page polling requests in Packet Inspector", lambda: _VERBOSE.__setitem__(0, S["verbose"]))
    setting_check("capture", "Save TV-loaded files to the captures folder (same as File Grabber)")
    ttk.Label(st_, text="Default mirror settings are set on the 'Mirror & URLs' tab and remembered.", foreground="#555").pack(anchor="w", pady=4)
    ttk.Button(st_, text="Open data folder", command=lambda: os.startfile(DATA_DIR) if os.name == "nt" else log(DATA_DIR)).pack(anchor="w", pady=2)
    ttk.Label(st_, text=f"Vizio Control v{APP_VERSION}", foreground="#555").pack(anchor="w", pady=8)

    # keep-alive / auto-reconnect
    ka = {"ok": True}

    def keepalive():
        tv = state["tv"]
        if S["autoreconnect"] and tv and tv.token:
            def chk():
                try:
                    tv.power_state()
                    if not ka["ok"]:
                        log("TV is back online")
                    ka["ok"] = True
                except Exception:
                    if ka["ok"]:
                        log("TV unreachable - will keep retrying (turn it on / check Wi-Fi)")
                    ka["ok"] = False
                    if store.get("mac") and not ka.get("wol"):
                        ka["wol"] = True
                        try:
                            wake_on_lan(store["mac"])
                        except Exception:
                            pass
            threading.Thread(target=chk, daemon=True).start()
        root.after(30000, keepalive)
    root.after(30000, keepalive)

    # ================= order tabs so they make sense
    nb.tab(t5, text="Mirror & URLs")
    nb.tab(t8, text="TV Settings")
    nb.tab(t9, text="Advanced API")
    for tab in (t1, t2, tr, t3, t4, t5, t6, t7, t8, t10, t11, sm, tl, dv, t9, st_):
        nb.insert("end", tab)
    try:
        root.iconphoto(True, tk.PhotoImage(data=LOGO_B64))
    except Exception:
        pass
    root.attributes("-topmost", bool(S["ontop"]))
    apply_theme()

    refresh_saved()
    poll_page()
    flush()
    drain_log()
    threading.Thread(target=scheduler, daemon=True).start()
    last = store.get("last")
    if last in store["tvs"]:
        p = store["tvs"][last]
        set_connected(last, p["host"], p["token"])
    root.protocol("WM_DELETE_WINDOW", lambda: (server.stop(), hub.stop(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
