# -*- coding: utf-8 -*-
"""
OTP Panel Bot v6.0 - SUPER FAST & CLEAN
=========================================================
Button:
  P1 Console  -> WealthoraPrime live traffic
  P2 Console  -> FastXOTPs live traffic
  P1 Number   -> fetch numbers
  P2 Number   -> fetch numbers
  Number Checker -> WA check
  WP Checker  -> Phone code login
  WP Disconnect -> disconnect
=========================================================
"""

import os, re, time, threading, logging, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed

import telebot
from telebot import types
from neonize.client import NewClient
from neonize.events import ConnectedEv, DisconnectedEv

# ─────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────
BOT_TOKEN = (
    os.environ.get("WA_CHECKER_BOT_TOKEN") or
    os.environ.get("TELEGRAM_BOT_TOKEN", "")
)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8523774444"))

P1_BASE = os.environ.get("WEALTHORA_API_BASE",
          "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api")
P1_KEY  = os.environ.get("WEALTHORA_API_KEY", "MWFG9WNAHZQ")
P1_HDRS = {"mauthapi": P1_KEY}

P2_BASE = os.environ.get("FASTXOTPS_API_BASE", "https://fastxotps.com")
P2_KEY  = os.environ.get("FASTXOTPS_API_KEY", "MURAD_69548E938AF8F1D4E0587220")
P2_HDRS = {"X-API-Key": P2_KEY, "Content-Type": "application/json"}

if not BOT_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN env var is required.")

logging.basicConfig(level=logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown", num_threads=80)

# ─────────────────────────────────────────────────────────────
#  HTTP SESSIONS
# ─────────────────────────────────────────────────────────────
def _make_session(pool_conn=50, pool_max=100, retries=2,
                  force_list=(502, 503, 504)):
    s = requests.Session()
    retry = Retry(total=retries, backoff_factor=0.15,
                  status_forcelist=list(force_list))
    adapter = HTTPAdapter(pool_connections=pool_conn,
                          pool_maxsize=pool_max,
                          max_retries=retry)
    s.mount("http://",  adapter)
    s.mount("https://", adapter)
    return s

_sess   = _make_session()
_p2sess = _make_session(pool_conn=10, pool_max=20, retries=0, force_list=())

def p1_get(path, params=None):
    try:
        return _sess.get(f"{P1_BASE}{path}", params=params,
                         headers=P1_HDRS, timeout=8).json()
    except Exception as e:
        return {"error": str(e)}

def p1_post(path, data=None):
    try:
        return _sess.post(f"{P1_BASE}{path}", json=data or {},
                          headers=P1_HDRS, timeout=8).json()
    except Exception as e:
        return {"error": str(e)}

def p2_post(path, data=None):
    try:
        return _p2sess.post(f"{P2_BASE}/api{path}", json=data or {},
                            headers=P2_HDRS, timeout=6).json()
    except Exception as e:
        return {"error": str(e)}

def p2_get_otps():
    try:
        r = _p2sess.get(f"{P2_BASE}/api/success-otp-info",
                        params={"api_key": P2_KEY}, timeout=5)
        if r.status_code != 200: return []
        return (r.json().get("data") or {}).get("otps", []) or []
    except:
        return []

# ─────────────────────────────────────────────────────────────
#  GLOBAL STATE
# ─────────────────────────────────────────────────────────────
wa_clients  = {}
wa_statuses = {}
otp_stats   = {}
bot_start   = time.time()

user_names = {}; names_lock = threading.Lock()
user_state = {}; state_lock  = threading.Lock()

_p1_registry = {}; _p1_reg_lock = threading.Lock()
_p2_registry = {}; _p2_reg_lock = threading.Lock()

SVC_ICON = {"whatsapp": "\U0001f4ac", "facebook": "\U0001f4d8", "telegram": "\u2708\ufe0f"}
DEFAULT_SVCS = {"whatsapp", "facebook", "telegram"}

_FLAG = {
    "ivory coast": "\U0001f1e8\U0001f1ee",
    "cameroon": "\U0001f1e8\U0001f1f2",
    "madagascar": "\U0001f1f2\U0001f1ec",
    "nigeria": "\U0001f1f3\U0001f1ec",
    "ghana": "\U0001f1ec\U0001f1ed",
    "kenya": "\U0001f1f0\U0001f1ea",
    "ethiopia": "\U0001f1ea\U0001f1f9",
    "tanzania": "\U0001f1f9\U0001f1ff",
    "uganda": "\U0001f1fa\U0001f1ec",
    "senegal": "\U0001f1f8\U0001f1f3",
    "mali": "\U0001f1f2\U0001f1f1",
    "burkina faso": "\U0001f1e7\U0001f1eb",
    "guinea": "\U0001f1ec\U0001f1f3",
    "togo": "\U0001f1f9\U0001f1ec",
    "benin": "\U0001f1e7\U0001f1ef",
    "niger": "\U0001f1f3\U0001f1ea",
    "chad": "\U0001f1f9\U0001f1e9",
    "angola": "\U0001f1e6\U0001f1f4",
    "mozambique": "\U0001f1f2\U0001f1ff",
    "zambia": "\U0001f1ff\U0001f1f2",
    "zimbabwe": "\U0001f1ff\U0001f1fc",
    "botswana": "\U0001f1e7\U0001f1fc",
    "namibia": "\U0001f1f3\U0001f1e6",
    "south africa": "\U0001f1ff\U0001f1e6",
    "rwanda": "\U0001f1f7\U0001f1fc",
    "burundi": "\U0001f1e7\U0001f1ee",
    "congo": "\U0001f1e8\U0001f1ec",
    "dr congo": "\U0001f1e8\U0001f1e9",
    "gabon": "\U0001f1ec\U0001f1e6",
    "malawi": "\U0001f1f2\U0001f1fc",
    "mauritius": "\U0001f1f2\U0001f1fa",
    "cape verde": "\U0001f1e8\U0001f1fb",
    "sierra leone": "\U0001f1f8\U0001f1f1",
    "eritrea": "\U0001f1ea\U0001f1f7",
    "somalia": "\U0001f1f8\U0001f1f4",
    "mauritania": "\U0001f1f2\U0001f1f7",
    "egypt": "\U0001f1ea\U0001f1ec",
    "morocco": "\U0001f1f2\U0001f1e6",
    "algeria": "\U0001f1e9\U0001f1ff",
    "tunisia": "\U0001f1f9\U0001f1f3",
    "libya": "\U0001f1f1\U0001f1fe",
    "india": "\U0001f1ee\U0001f1f3",
    "pakistan": "\U0001f1f5\U0001f1f0",
    "bangladesh": "\U0001f1e7\U0001f1e9",
    "indonesia": "\U0001f1ee\U0001f1e9",
    "philippines": "\U0001f1f5\U0001f1ed",
    "vietnam": "\U0001f1fb\U0001f1f3",
    "thailand": "\U0001f1f9\U0001f1ed",
    "malaysia": "\U0001f1f2\U0001f1fe",
    "myanmar": "\U0001f1f2\U0001f1f2",
    "cambodia": "\U0001f1f0\U0001f1ed",
    "sri lanka": "\U0001f1f1\U0001f1f0",
    "nepal": "\U0001f1f3\U0001f1f5",
    "ukraine": "\U0001f1fa\U0001f1e6",
    "russia": "\U0001f1f7\U0001f1fa",
    "brazil": "\U0001f1e7\U0001f1f7",
    "argentina": "\U0001f1e6\U0001f1f7",
    "colombia": "\U0001f1e8\U0001f1f4",
    "mexico": "\U0001f1f2\U0001f1fd",
    "peru": "\U0001f1f5\U0001f1ea",
    "chile": "\U0001f1e8\U0001f1f1",
    "venezuela": "\U0001f1fb\U0001f1ea",
    "united states": "\U0001f1fa\U0001f1f8",
    "united kingdom": "\U0001f1ec\U0001f1e7",
    "france": "\U0001f1eb\U0001f1f7",
    "germany": "\U0001f1e9\U0001f1ea",
    "spain": "\U0001f1ea\U0001f1f8",
    "china": "\U0001f1e8\U0001f1f3",
    "japan": "\U0001f1ef\U0001f1f5",
    "south korea": "\U0001f1f0\U0001f1f7",
    "saudi arabia": "\U0001f1f8\U0001f1e6",
    "turkey": "\U0001f1f9\U0001f1f7",
    "iran": "\U0001f1ee\U0001f1f7",
    "iraq": "\U0001f1ee\U0001f1f6",
    "afghanistan": "\U0001f1e6\U0001f1eb",
}

# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────
def _flag(c):
    return _FLAG.get((c or "").strip().lower(), "\U0001f30d")

def _svc_icon(s):
    return SVC_ICON.get((s or "").lower(), "\U0001f4f2")

def _resolve_svc(service="", range_id=""):
    v = (service or "").strip().lower()
    if "facebook" in v or v == "fb": return "Facebook"
    if "telegram" in v or v == "tg": return "Telegram"
    r = (range_id or "").lower()
    if "fb" in r or "facebook" in r: return "Facebook"
    if "tg" in r or "telegram" in r: return "Telegram"
    return "WhatsApp"

def _save_user(m):
    try:
        u = getattr(m, "from_user", m)
        if not u: return
        uid = u.id
        label = (f"@{u.username}" if u.username else
                 (u.first_name or "") + (" " + u.last_name if u.last_name else ""))
        with names_lock: user_names[uid] = label or str(uid)
    except: pass

def _get_label(uid):
    with names_lock: return user_names.get(uid, str(uid))

def time_ago(ms):
    s = max(0, int(time.time() - ms / 1000))
    if s < 60:   return f"{s}s ago"
    if s < 3600: return f"{s // 60}m ago"
    return f"{s // 3600}h ago"

def uptime_str():
    s = int(time.time() - bot_start)
    h, m = divmod(s // 60, 60)
    return f"{h}h {m}m"

def extract_otp(text):
    m = re.search(r"\b(\d{3}[- ]\d{3})\b", text)
    if m: return m.group(1).replace(" ", "-")
    m = re.search(r"\b(\d{4,7})\b", text)
    if m: return m.group(1)
    return "???"

def safe_delete(chat_id, msg_id):
    try: bot.delete_message(chat_id, msg_id)
    except: pass

def edit_safe(chat_id, msg_id, text, kb=None):
    try:
        if kb:
            bot.edit_message_text(text, chat_id, msg_id,
                                  reply_markup=kb, parse_mode="Markdown")
        else:
            bot.edit_message_text(text, chat_id, msg_id, parse_mode="Markdown")
    except: pass

def get_wa_status(cid):
    return wa_statuses.get(cid, "disconnected")

def _num_matches(api_num, plain):
    a = str(api_num).strip().lstrip("+")
    p = str(plain).strip().lstrip("+")
    if a == p: return True
    sl = min(len(a), len(p), 9)
    return sl >= 7 and a[-sl:] == p[-sl:]

# ─────────────────────────────────────────────────────────────
#  OTP REGISTRY
# ─────────────────────────────────────────────────────────────
def _register(panel, numbers, range_id, chat_id, dur=600):
    deadline = time.time() + dur
    registry = _p1_registry if panel == "p1" else _p2_registry
    lock     = _p1_reg_lock  if panel == "p1" else _p2_reg_lock
    with lock:
        for n in numbers:
            plain = n["plain"].lstrip("+")
            registry[plain] = {
                "chat_id":  chat_id,
                "full":     n["full"],
                "country":  n.get("country", ""),
                "service":  n.get("service", ""),
                "range_id": range_id,
                "deadline": deadline,
            }

def _inc_otp(cid):
    otp_stats[cid] = otp_stats.get(cid, 0) + 1

def _notify_otp(chat_id, full_num, otp_code, country="", service="", range_id=""):
    _inc_otp(chat_id)
    svc  = _resolve_svc(service=service, range_id=range_id)
    icon = _svc_icon(svc)
    ctry = (country or "Unknown").title()
    header = f"{_flag(country)}|`{full_num}`| {icon} {svc} COUNTRY: {ctry}"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        f"OTP: {otp_code}", copy_text=types.CopyTextButton(text=otp_code)))
    try:
        bot.send_message(chat_id, header, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        print(f"[OTP-NOTIFY] {e}")

# ─────────────────────────────────────────────────────────────
#  GLOBAL P1 POLLER
# ─────────────────────────────────────────────────────────────
def _fetch_p1_otps():
    try:
        resp = p1_get("/success-otp")
        otps = (resp.get("data") or {}).get("otps", [])
        return otps if isinstance(otps, list) else []
    except:
        return []

def _global_p1_poller():
    seen = {str(o.get("otp_id", "")) for o in _fetch_p1_otps() if o.get("otp_id")}
    print(f"[P1-POLLER] started. pre-seen={len(seen)}")
    while True:
        time.sleep(1)
        try:
            with _p1_reg_lock:
                if not _p1_registry: continue
                now = time.time()
                for k in [k for k, v in list(_p1_registry.items()) if v["deadline"] < now]:
                    del _p1_registry[k]

            for o in _fetch_p1_otps():
                oid = str(o.get("otp_id") or "")
                if not oid or oid in seen:
                    continue
                seen.add(oid)
                api_num = str(o.get("number", "")).strip()
                code    = extract_otp(str(o.get("message", "")))
                if not code or code == "???":
                    continue
                with _p1_reg_lock:
                    for plain, info in list(_p1_registry.items()):
                        if _num_matches(api_num, plain):
                            print(f"[P1-POLLER] OTP {info['full']} otp={code}")
                            threading.Thread(
                                target=_notify_otp,
                                args=(info["chat_id"],),
                                kwargs=dict(
                                    full_num=info["full"],
                                    otp_code=code,
                                    country=info["country"],
                                    service=info.get("service", ""),
                                    range_id=info["range_id"],
                                ),
                                daemon=True,
                            ).start()
                            del _p1_registry[plain]
                            break
        except Exception as e:
            print(f"[P1-POLLER] err: {e}")

# ─────────────────────────────────────────────────────────────
#  GLOBAL P2 POLLER
# ─────────────────────────────────────────────────────────────
def _global_p2_poller():
    seen = {str(o.get("otp_id", "")) for o in p2_get_otps() if o.get("otp_id")}
    print(f"[P2-POLLER] started. pre-seen={len(seen)}")
    while True:
        time.sleep(1)
        try:
            with _p2_reg_lock:
                if not _p2_registry: continue
                now = time.time()
                for k in [k for k, v in list(_p2_registry.items()) if v["deadline"] < now]:
                    del _p2_registry[k]

            for o in p2_get_otps():
                oid = str(o.get("otp_id") or "")
                if not oid or oid in seen:
                    continue
                seen.add(oid)
                api_num = str(o.get("number", "")).strip().lstrip("+")
                otp_val = str(o.get("otp") or "")
                msg_txt = str(o.get("message") or "")
                code    = otp_val or extract_otp(msg_txt)
                if not code or code == "???":
                    continue
                with _p2_reg_lock:
                    for plain, info in list(_p2_registry.items()):
                        if _num_matches(api_num, plain):
                            print(f"[P2-POLLER] OTP {info['full']} otp={code}")
                            threading.Thread(
                                target=_notify_otp,
                                args=(info["chat_id"],),
                                kwargs=dict(
                                    full_num=info["full"],
                                    otp_code=code,
                                    country=info["country"],
                                    service=info["service"],
                                    range_id=info["range_id"],
                                ),
                                daemon=True,
                            ).start()
                            del _p2_registry[plain]
                            break
        except Exception as e:
            print(f"[P2-POLLER] err: {e}")

# ─────────────────────────────────────────────────────────────
#  PER-USER WHATSAPP CLIENT
# ─────────────────────────────────────────────────────────────
def _session_path(chat_id):
    return f"wa_session_{chat_id}"

def _clear_session(chat_id):
    base = _session_path(chat_id)
    for ext in ("", ".db", ".db-shm", ".db-wal"):
        fp = base + ext
        if os.path.exists(fp):
            try: os.remove(fp)
            except: pass

def _build_wa_client(chat_id):
    c = NewClient(_session_path(chat_id))

    @c.event(ConnectedEv)
    def _on_conn(client, event):
        wa_statuses[chat_id] = "connected"
        print(f"[WA] connected: {chat_id}")
        try:
            bot.send_message(
                chat_id,
                "*WhatsApp connected!*\n\nYou can now check numbers.",
                reply_markup=_main_kb(chat_id),
            )
        except: pass

    @c.event(DisconnectedEv)
    def _on_disc(client, event):
        wa_statuses[chat_id] = "disconnected"
        print(f"[WA] disconnected: {chat_id}")
        time.sleep(5)
        if os.path.exists(_session_path(chat_id) + ".db"):
            threading.Thread(
                target=_reconnect_silent, args=(chat_id,), daemon=True).start()

    return c

def _reconnect_silent(chat_id):
    if get_wa_status(chat_id) != "disconnected": return
    wa_statuses[chat_id] = "connecting"
    client = _build_wa_client(chat_id)
    wa_clients[chat_id] = client
    try:
        client.connect()
    except Exception as e:
        wa_statuses[chat_id] = "disconnected"
        print(f"[WA] reconnect fail {chat_id}: {e}")

def connect_with_code(chat_id, phone):
    if get_wa_status(chat_id) == "connected":
        bot.send_message(chat_id, "*WhatsApp already connected!*",
                         reply_markup=_main_kb(chat_id))
        return
    if get_wa_status(chat_id) == "connecting":
        bot.send_message(chat_id, "Code is being generated, please wait...")
        return

    _clear_session(chat_id)
    wa_statuses[chat_id] = "connecting"
    client = _build_wa_client(chat_id)
    wa_clients[chat_id] = client

    @client.qr
    def _on_qr(cl, qr_data):
        try:
            code = cl.PairPhone(phone, False)
            bot.send_message(
                chat_id,
                f"*WhatsApp Pairing Code:*\n\n`{code}`\n\n"
                "Go to WhatsApp:\n"
                "*Settings -> Linked Devices -> Link with Phone Number*\n\n"
                "Enter this 8-digit code.\n"
                "It will connect automatically after entry.",
                parse_mode="Markdown",
            )
        except Exception as e:
            wa_statuses[chat_id] = "disconnected"
            wa_clients.pop(chat_id, None)
            bot.send_message(
                chat_id,
                f"Connection failed:\n`{e}`\n\nPress *WP Checker* again.",
                reply_markup=_main_kb(chat_id),
                parse_mode="Markdown",
            )

    threading.Thread(target=client.connect, daemon=True).start()

def disconnect_wa(chat_id):
    client = wa_clients.pop(chat_id, None)
    if client:
        try: client.disconnect()
        except: pass
    wa_statuses[chat_id] = "disconnected"
    _clear_session(chat_id)
    bot.send_message(chat_id, "WhatsApp disconnected.",
                     reply_markup=_main_kb(chat_id))

# ─────────────────────────────────────────────────────────────
#  KEYBOARDS
# ─────────────────────────────────────────────────────────────
def _main_kb(chat_id=None):
    st = get_wa_status(chat_id) if chat_id else "disconnected"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(types.KeyboardButton("P1 Console"),
           types.KeyboardButton("P2 Console"))
    kb.row(types.KeyboardButton("P1 Number"),
           types.KeyboardButton("P2 Number"))
    kb.add(types.KeyboardButton("Number Checker"))
    if st == "connected":
        kb.row(types.KeyboardButton("WP Checker ON"),
               types.KeyboardButton("WP Disconnect"))
    else:
        kb.add(types.KeyboardButton("WP Checker"))
    return kb

def _console_kb(panel):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "Refresh", callback_data=f"cr|{panel}"))
    return kb

def _number_kb(numbers, wa_res, panel, range_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for n in numbers:
        v    = wa_res.get(n["full"])
        icon = "R" if v is True else ("G" if v is False else "-")
        kb.add(types.InlineKeyboardButton(
            f"[{icon}] {n['full']}",
            copy_text=types.CopyTextButton(text=n["full"])))
    kb.row(
        types.InlineKeyboardButton(
            "Change Number", callback_data=f"nb|{panel}|{range_id}"),
        types.InlineKeyboardButton(
            "Close", callback_data="cb"),
    )
    return kb

def _card_header(range_id, panel, count, failed=0, service=""):
    label    = "P1" if panel == "p1" else "P2"
    svc_name = service or _resolve_svc(range_id=range_id)
    icon     = _svc_icon(svc_name)
    h = f"{icon} *{svc_name.upper()}* [{label}]  -  {count} numbers"
    if failed: h += f"  ({failed} missed)"
    h += "\nOTP will appear in your inbox when received"
    return h

# ─────────────────────────────────────────────────────────────
#  CONSOLE
# ─────────────────────────────────────────────────────────────
def _fmt_p1(hits):
    groups = {}
    for h in hits:
        sid = str(h.get("sid", "")).lower()
        if sid in DEFAULT_SVCS:
            groups.setdefault(sid, []).append(h)
    if not groups: return "No live data."
    lines = []
    for sid in ("whatsapp", "facebook", "telegram"):
        if sid not in groups: continue
        lines.append(f"\n================\n"
                     f"{SVC_ICON.get(sid, '')} *{sid.capitalize()}*")
        for h in groups[sid][:10]:
            lines.append(f"`{h.get('range', '')}` - "
                         f"_{time_ago(h.get('time', time.time() * 1000))}_")
    lines.append(f"\n================\n_{time.strftime('%H:%M:%S')}_")
    return "\n".join(lines)

def _fmt_p2(services):
    order = {"whatsapp": 0, "facebook": 1, "telegram": 2}
    filt  = sorted(
        [s for s in services if str(s.get("sid", "")).lower() in DEFAULT_SVCS],
        key=lambda s: order.get(str(s.get("sid", "")).lower(), 9))
    if not filt: return "No live data."
    lines = []
    for svc in filt:
        sid = str(svc.get("sid", "")).lower()
        ago = time_ago(svc.get("last_at", time.time() * 1000))
        lines.append(f"\n================\n"
                     f"{SVC_ICON.get(sid, '')} *{sid.capitalize()}* - _{ago}_")
        for r in svc.get("ranges", [])[:8]:
            lines.append(f"  `{r}`")
    lines.append(f"\n================\n_{time.strftime('%H:%M:%S')}_")
    return "\n".join(lines)

def _send_console(chat_id, panel, edit_id=None):
    if panel == "p1":
        resp = p1_get("/console")
        hits = resp.get("data", {}).get("hits", [])
        text = "*P1 - WealthoraPrime*\n" + _fmt_p1(hits)
    else:
        resp = p2_post("/liveaccess")
        svcs = resp.get("services", [])
        text = "*P2 - FastXOTPs*\n" + _fmt_p2(svcs)
    kb = _console_kb(panel)
    if edit_id:
        try:
            bot.edit_message_text(text, chat_id, edit_id,
                                  reply_markup=kb, parse_mode="Markdown")
            return
        except: pass
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────
#  FETCH NUMBERS
# ─────────────────────────────────────────────────────────────
def _fetch_one(panel, range_id):
    if panel == "p1":
        resp    = p1_post("/getnum", {"range": range_id})
        code    = resp.get("meta", {}).get("code")
        data    = resp.get("data", {}) or {}
        full    = str(data.get("full_number", ""))
        plain   = str(data.get("no_plus_number") or full.lstrip("+"))
        country = str(data.get("country") or "")
        service = str(data.get("service") or data.get("sid") or "")
        if full and code == 200:
            return dict(full=full, plain=plain, country=country,
                        service=service, rid=None, otp_now=False, otp_msg="")
        return None

    resp    = p2_post("/getnum", {"range": range_id})
    data    = resp.get("data", resp) or {}
    if not isinstance(data, dict): data = {}

    full    = (data.get("full_number") or data.get("number")
               or resp.get("full_number") or resp.get("number") or "")
    plain   = str(data.get("no_plus_number") or str(full).lstrip("+"))
    country = str(data.get("country") or resp.get("country") or "")
    service = str(data.get("service") or data.get("sid")
                  or resp.get("service") or resp.get("sid") or "")
    rid     = str(resp.get("rid") or data.get("rid") or "")
    otp_now = bool(data.get("otp_now") or resp.get("otp_now"))
    otp_msg = str(data.get("otp_message") or data.get("message")
                  or resp.get("otp_message") or resp.get("message") or "")

    if full:
        return dict(full=full, plain=plain, country=country,
                    service=service, rid=rid, otp_now=otp_now, otp_msg=otp_msg)
    return None

def get_6_numbers(chat_id, panel, range_id, edit_msg_id=None):
    label   = "P1" if panel == "p1" else "P2"
    loading = f"Fetching numbers from `{range_id}` [{label}]..."

    if edit_msg_id:
        edit_safe(chat_id, edit_msg_id, loading)
        st_id = edit_msg_id
    else:
        st    = bot.send_message(chat_id, loading, parse_mode="Markdown")
        st_id = st.message_id

    results, failed = [], 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(_fetch_one, panel, range_id) for _ in range(6)]
        for f in as_completed(futs):
            info = f.result()
            if info: results.append(info)
            else:    failed += 1

    if not results:
        err = f"No numbers found from `{range_id}` [{label}].\n_Range empty or API error._"
        if edit_msg_id: edit_safe(chat_id, st_id, err)
        else:
            safe_delete(chat_id, st_id)
            bot.send_message(chat_id, err, parse_mode="Markdown")
        return

    batch_svc = results[0].get("service", "") if results else ""
    wa_res    = _wa_bulk(chat_id, results)
    header    = _card_header(range_id, panel, len(results), failed, service=batch_svc)
    kb        = _number_kb(results, wa_res, panel, range_id)

    if edit_msg_id:
        try:
            bot.edit_message_text(header, chat_id, st_id,
                                  reply_markup=kb, parse_mode="Markdown")
        except:
            bot.send_message(chat_id, header, reply_markup=kb, parse_mode="Markdown")
    else:
        safe_delete(chat_id, st_id)
        bot.send_message(chat_id, header, reply_markup=kb, parse_mode="Markdown")

    _register(panel, results, range_id, chat_id, dur=600)

    if panel == "p2":
        for n in results:
            if n.get("otp_now") and n.get("otp_msg"):
                code = extract_otp(n["otp_msg"])
                if code and code != "???":
                    _notify_otp(chat_id, full_num=n["full"], otp_code=code,
                                country=n.get("country", ""), service=n.get("service", ""),
                                range_id=range_id)
                    with _p2_reg_lock:
                        _p2_registry.pop(n["plain"].lstrip("+"), None)

# ─────────────────────────────────────────────────────────────
#  WA CHECK
# ─────────────────────────────────────────────────────────────
def _wa_bulk(chat_id, numbers):
    result = {n["full"]: None for n in numbers}
    client = wa_clients.get(chat_id)
    if not client or get_wa_status(chat_id) != "connected": return result
    try:
        cleaned   = [n["plain"].lstrip("+") for n in numbers]
        jids      = [f"+{c}@s.whatsapp.net" for c in cleaned]
        responses = client.is_on_whatsapp(*jids)
        for i, n in enumerate(numbers):
            matched = next((r for r in responses if cleaned[i] in r.Query), None)
            result[n["full"]] = (
                bool(matched.IsIn) if matched
                else (bool(responses[i].IsIn) if i < len(responses) else None))
    except Exception as e:
        print(f"[WA-BULK] {e}")
    return result

def _wa_check(chat_id, numbers):
    result  = {n: None for n in numbers}
    client  = wa_clients.get(chat_id)
    if not client or get_wa_status(chat_id) != "connected": return result
    cleaned = [n.replace("+", "").replace(" ", "").replace("-", "") for n in numbers]
    jids    = [f"+{c}@s.whatsapp.net" for c in cleaned]
    try:
        responses = client.is_on_whatsapp(*jids)
        for i, n in enumerate(numbers):
            matched = next((r for r in responses if cleaned[i] in r.Query), None)
            result[n] = (
                bool(matched.IsIn) if matched
                else (bool(responses[i].IsIn) if i < len(responses) else None))
    except Exception as e:
        print(f"[WA-CHECK] {e}")
    return result

# ─────────────────────────────────────────────────────────────
#  BUTTON LABELS
# ─────────────────────────────────────────────────────────────
_ALL_BTN = {
    "P1 Console", "P2 Console",
    "P1 Number", "P2 Number",
    "Number Checker",
    "WP Checker", "WP Checker ON",
    "WP Disconnect",
}

# ─────────────────────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    _save_user(msg)
    bot.send_message(
        msg.chat.id,
        "*OTP Panel Bot v6.0*\n\n"
        "P1 Console / P2 Console - Live traffic\n"
        "P1 Number / P2 Number - Range -> 6 numbers\n"
        "Number Checker - WhatsApp check\n"
        "WP Checker - Phone code login (no QR)\n"
        "WP Disconnect - Disconnect\n\n"
        "OTP delivered within 1 second of arrival",
        reply_markup=_main_kb(msg.chat.id),
    )

# ─────────────────────────────────────────────────────────────
#  /stats  (admin only)
# ─────────────────────────────────────────────────────────────
@bot.message_handler(commands=["stats"])
def cmd_stats(msg):
    if msg.chat.id != ADMIN_ID: return
    if not otp_stats:
        bot.send_message(msg.chat.id, "No OTPs received yet.")
        return
    text  = "*OTP Statistics*\n================\n"
    total = 0
    for uid, cnt in sorted(otp_stats.items(), key=lambda x: -x[1]):
        with names_lock:
            uname = user_names.get(uid, "")
        link   = f"[{uname or uid}](tg://user?id={uid})"
        text  += f"{link} - *{cnt}* OTP\n"
        total += cnt
    text += f"================\nTotal: *{total}* OTP"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown",
                     disable_web_page_preview=True)

# ─────────────────────────────────────────────────────────────
#  /status  (admin only)
# ─────────────────────────────────────────────────────────────
@bot.message_handler(commands=["status"])
def cmd_status(msg):
    if msg.chat.id != ADMIN_ID: return
    connected  = [cid for cid, st in wa_statuses.items() if st == "connected"]
    connecting = [cid for cid, st in wa_statuses.items() if st == "connecting"]
    with _p2_reg_lock: p2_active = len(_p2_registry)
    with _p1_reg_lock: p1_active = len(_p1_registry)
    total_otp = sum(otp_stats.values()) if otp_stats else 0
    text = (
        "*Bot Status v6.0*\n================\n"
        f"Uptime: `{uptime_str()}`\n"
        f"WA Connected: `{len(connected)}`\n"
        f"WA Connecting: `{len(connecting)}`\n"
        f"P2 watching: `{p2_active}` numbers\n"
        f"P1 watching: `{p1_active}` numbers\n"
        f"Total OTPs: `{total_otp}`\n"
        f"================\n"
    )
    if connected:
        text += "*Connected users:*\n"
        for cid in connected:
            text += f"  `{cid}` ({_get_label(cid)}) - {otp_stats.get(cid, 0)} OTP\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown",
                     disable_web_page_preview=True)

# ─────────────────────────────────────────────────────────────
#  CONSOLE BUTTONS
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "P1 Console")
def btn_p1_console(msg):
    _save_user(msg)
    threading.Thread(target=_send_console, args=(msg.chat.id, "p1"), daemon=True).start()

@bot.message_handler(func=lambda m: m.text == "P2 Console")
def btn_p2_console(msg):
    _save_user(msg)
    threading.Thread(target=_send_console, args=(msg.chat.id, "p2"), daemon=True).start()

# ─────────────────────────────────────────────────────────────
#  NUMBER BUTTONS
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "P1 Number")
def btn_p1_num(msg):
    _save_user(msg)
    with state_lock:
        user_state[msg.chat.id] = {"mode": "wait_range_p1"}
    bot.send_message(msg.chat.id, "Enter *P1* range (e.g. `22501XXX`)", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "P2 Number")
def btn_p2_num(msg):
    _save_user(msg)
    with state_lock:
        user_state[msg.chat.id] = {"mode": "wait_range_p2"}
    bot.send_message(msg.chat.id, "Enter *P2* range (e.g. `26134XXX`)", parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────
#  WP CHECKER BUTTON
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text in ("WP Checker", "WP Checker ON"))
def btn_wa(msg):
    _save_user(msg)
    chat_id = msg.chat.id
    status  = get_wa_status(chat_id)
    if status == "connected":
        bot.send_message(chat_id, "*WhatsApp already connected!*",
                         reply_markup=_main_kb(chat_id))
        return
    if status == "connecting":
        bot.send_message(chat_id, "Code is being generated, please wait...")
        return
    with state_lock:
        user_state[chat_id] = {"mode": "wait_phone"}
    bot.send_message(chat_id,
                     "Enter *WhatsApp number* with country code\n\nExample: `+8801712345678`",
                     parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────
#  DISCONNECT BUTTON
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "WP Disconnect")
def btn_disconnect(msg):
    _save_user(msg)
    threading.Thread(target=disconnect_wa, args=(msg.chat.id,), daemon=True).start()

# ─────────────────────────────────────────────────────────────
#  NUMBER CHECKER BUTTON
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "Number Checker")
def btn_checker(msg):
    _save_user(msg)
    chat_id = msg.chat.id
    if get_wa_status(chat_id) != "connected":
        bot.send_message(chat_id,
                         "*WhatsApp not connected.*\n\nPress *WP Checker* first.",
                         reply_markup=_main_kb(chat_id))
        return
    with state_lock:
        user_state[chat_id] = {"mode": "wait_check_numbers"}
    bot.send_message(chat_id,
                     "*Number Checker*\n\nSend numbers (one per line, max 20):",
                     parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────
#  FREE TEXT
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(msg):
    _save_user(msg)
    chat_id = msg.chat.id
    text    = msg.text.strip()
    if text.startswith("/") or text in _ALL_BTN: return

    with state_lock:
        mode = user_state.get(chat_id, {}).get("mode", "idle")

    if mode == "wait_phone":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        phone = text.replace(" ", "").replace("-", "")
        if not phone.startswith("+"): phone = "+" + phone
        if not re.match(r"^\+\d{7,15}$", phone):
            bot.send_message(chat_id,
                             "Invalid number. Include country code.\nExample: `+8801712345678`",
                             parse_mode="Markdown")
            return
        bot.send_message(chat_id, f"Generating pairing code for `{phone}`...",
                         parse_mode="Markdown")
        threading.Thread(target=connect_with_code, args=(chat_id, phone), daemon=True).start()

    elif mode == "wait_range_p1":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        threading.Thread(target=get_6_numbers, args=(chat_id, "p1", text), daemon=True).start()

    elif mode == "wait_range_p2":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        threading.Thread(target=get_6_numbers, args=(chat_id, "p2", text), daemon=True).start()

    elif mode == "wait_check_numbers":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        lines = [l.strip() for l in text.splitlines() if l.strip()][:20]
        if not lines:
            bot.send_message(chat_id, "No numbers found.")
            return
        loading = bot.send_message(chat_id, f"Checking {len(lines)} numbers...",
                                   parse_mode="Markdown")
        def _do_check():
            results = _wa_check(chat_id, lines)
            out = []
            for n, is_on in results.items():
                if is_on is True:    icon = "HAS WhatsApp"
                elif is_on is False: icon = "NO WhatsApp"
                else:                icon = "Not checked"
                out.append(f"`{n}` - {icon}")
            safe_delete(chat_id, loading.message_id)
            bot.send_message(chat_id,
                             "*Number Checker Result:*\n\n" + "\n".join(out),
                             parse_mode="Markdown")
        threading.Thread(target=_do_check, daemon=True).start()

# ─────────────────────────────────────────────────────────────
#  CALLBACK QUERY HANDLER
# ─────────────────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    _save_user(call.from_user)
    data    = call.data
    chat_id = call.message.chat.id
    msg_id  = call.message.message_id

    if data == "cb":
        safe_delete(chat_id, msg_id)
        bot.answer_callback_query(call.id)
        return

    if data.startswith("cr|"):
        panel = data.split("|")[1]
        bot.answer_callback_query(call.id, "Refreshing...")
        threading.Thread(target=_send_console, args=(chat_id, panel, msg_id), daemon=True).start()
        return

    if data.startswith("nb|"):
        parts    = data.split("|", 2)
        panel    = parts[1]
        range_id = parts[2]
        bot.answer_callback_query(call.id, "Fetching new numbers...")
        threading.Thread(target=get_6_numbers, args=(chat_id, panel, range_id, msg_id),
                         daemon=True).start()
        return

    bot.answer_callback_query(call.id)

# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"OTP Panel Bot v6.0 starting... (admin={ADMIN_ID})")

    threading.Thread(target=_global_p2_poller, daemon=True, name="P2-GlobalPoller").start()
    threading.Thread(target=_global_p1_poller, daemon=True, name="P1-GlobalPoller").start()

    bot.infinity_polling(timeout=30, long_polling_timeout=20)
