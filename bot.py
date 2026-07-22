"""
OTP Panel Bot  v5.0  â€” ULTRA FAST
=========================================================
P1  : WealthoraPrime    â†’ success-otp     (1s global poll)
P2  : FastXOTPs        â†’ success-otp-info (1s global poll)
WA  : neonize â€“ PairPhone code (no QR), per-user session
Admin : ADMIN_ID â†’ /stats  /status
=========================================================
âœ…  Global P2 poller  â€” 1 à¦Ÿà¦¾ thread, à¦¸à¦¬ user-à¦à¦° à¦œà¦¨à§à¦¯, 1s interval
âœ…  Global P1 poller  â€” 1 à¦Ÿà¦¾ thread, à¦¸à¦¬ user-à¦à¦° à¦œà¦¨à§à¦¯, 1s interval
âœ…  70â€“80 concurrent user support
âœ…  OTP panel-à¦ à¦†à¦¸à¦¾à¦° â‰¤1s à¦ user à¦ªà¦¾à¦¯à¦¼
âœ…  à¦¨à¦®à§à¦¬à¦° fetch â€” 6à¦Ÿà¦¾ parallel (fast)
âœ…  WA Checker unchanged (working)
"""

import os
import re
import time
import threading
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed

import telebot
from telebot import types
from neonize.client import NewClient
from neonize.events import ConnectedEv, DisconnectedEv

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  CONFIG
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BOT_TOKEN = (
    os.environ.get("WA_CHECKER_BOT_TOKEN")
    or os.environ.get("TELEGRAM_BOT_TOKEN", "")
)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8523774444"))

P1_BASE = os.environ.get(
    "WEALTHORA_API_BASE",
    "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api",
)
P1_KEY  = os.environ.get("WEALTHORA_API_KEY", "MWFG9WNAHZQ")
P1_HDRS = {"mauthapi": P1_KEY}

P2_BASE = os.environ.get("FASTXOTPS_API_BASE", "https://fastxotps.com")
P2_KEY  = os.environ.get("FASTXOTPS_API_KEY", "MURAD_69548E938AF8F1D4E0587220")
P2_HDRS = {"X-API-Key": P2_KEY, "Content-Type": "application/json"}

if not BOT_TOKEN:
    raise SystemExit("âŒ  TELEGRAM_BOT_TOKEN env var is required.")

logging.basicConfig(level=logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown",
                      num_threads=80)   # 70-80 user handle à¦•à¦°à¦¤à§‡

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  HTTP SESSIONS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _make_session(pool_conn=50, pool_max=100, retries=2,
                  force_list=(502, 503, 504)) -> requests.Session:
    s = requests.Session()
    retry = Retry(total=retries, backoff_factor=0.2,
                  status_forcelist=list(force_list))
    adapter = HTTPAdapter(pool_connections=pool_conn,
                          pool_maxsize=pool_max,
                          max_retries=retry)
    s.mount("http://",  adapter)
    s.mount("https://", adapter)
    return s

# General session (P1 + misc)
_session = _make_session(pool_conn=50, pool_max=100)

# P2 session â€” no retry, fast fail
_p2_sess  = _make_session(pool_conn=10, pool_max=20,
                           retries=0, force_list=())

def _get(url, params=None, headers=None, timeout=8):
    try:
        return _session.get(url, params=params, headers=headers,
                            timeout=timeout).json()
    except Exception as e:
        return {"error": str(e)}

def _post(url, data=None, headers=None, timeout=8):
    try:
        return _session.post(url, json=data or {}, headers=headers,
                             timeout=timeout).json()
    except Exception as e:
        return {"error": str(e)}

def p1_get(path, params=None):
    return _get(f"{P1_BASE}{path}", params=params, headers=P1_HDRS)

def p1_post(path, data=None):
    return _post(f"{P1_BASE}{path}", data=data, headers=P1_HDRS)

def p2_post(path, data=None):
    return _post(f"{P2_BASE}/api{path}", data=data or {}, headers=P2_HDRS)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  GLOBAL STATE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
wa_clients  = {}   # chat_id â†’ NewClient
wa_statuses = {}   # chat_id â†’ "disconnected"|"connecting"|"connected"
otp_stats   = {}   # chat_id â†’ int
bot_start   = time.time()

user_names  = {}
names_lock  = threading.Lock()

user_state  = {}
state_lock  = threading.Lock()

active_watches: dict = {}
watch_lock = threading.Lock()

DEFAULT_SERVICES = {"whatsapp", "facebook", "telegram"}
SVC_ICON = {"whatsapp": "ðŸ’¬", "facebook": "ðŸ“˜", "telegram": "âœˆï¸"}

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  GLOBAL OTP WATCH REGISTRIES
#  à¦ªà§à¦°à¦¤à¦¿à¦Ÿà¦¿ entry: plain_number â†’ info dict
#  info = {chat_id, full, country, service, range_id, deadline, panel}
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_p1_registry: dict = {}   # plain â†’ info
_p2_registry: dict = {}   # plain â†’ info
_p1_reg_lock = threading.Lock()
_p2_reg_lock = threading.Lock()

def _register_numbers(panel: str, results: list, range_id: str,
                      chat_id: int, duration: int = 600):
    """à¦¨à¦®à§à¦¬à¦°à¦—à§à¦²à§‹ global poller registry-à¦¤à§‡ add à¦•à¦°à§‡à¥¤"""
    deadline = time.time() + duration
    lock = _p1_reg_lock if panel == "p1" else _p2_reg_lock
    reg  = _p1_registry  if panel == "p1" else _p2_registry
    with lock:
        for n in results:
            plain = n["plain"].lstrip("+")
            reg[plain] = {
                "chat_id":  chat_id,
                "full":     n["full"],
                "country":  n.get("country", ""),
                "service":  n.get("service", ""),
                "range_id": range_id,
                "deadline": deadline,
            }

def _unregister(panel: str, plains: set):
    lock = _p1_reg_lock if panel == "p1" else _p2_reg_lock
    reg  = _p1_registry  if panel == "p1" else _p2_registry
    with lock:
        for p in plains:
            reg.pop(p, None)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  USERNAME / UTILITY HELPERS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _save_user(msg_or_user):
    try:
        u = getattr(msg_or_user, "from_user", msg_or_user) or msg_or_user
        if u is None: return
        uid = u.id
        if u.username:
            label = f"@{u.username}"
        elif u.first_name:
            label = u.first_name + (f" {u.last_name}" if u.last_name else "")
        else:
            label = str(uid)
        with names_lock:
            user_names[uid] = label
    except Exception:
        pass

def _get_label(chat_id: int) -> str:
    with names_lock:
        return user_names.get(chat_id, str(chat_id))

def time_ago(ms: float) -> str:
    s = max(0, int(time.time() - ms / 1000))
    if s < 60:   return f"{s}s ago"
    if s < 3600: return f"{s // 60}m ago"
    return f"{s // 3600}h ago"

def uptime_str() -> str:
    s = int(time.time() - bot_start)
    h, m = divmod(s // 60, 60)
    return f"{h}h {m}m"

def extract_otp(text: str) -> str:
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

def _inc_otp(chat_id):
    otp_stats[chat_id] = otp_stats.get(chat_id, 0) + 1

def get_wa_status(chat_id) -> str:
    return wa_statuses.get(chat_id, "disconnected")

# â”€â”€â”€ flags â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_FLAG = {
    "ivory coast":"ðŸ‡¨ðŸ‡®","cameroon":"ðŸ‡¨ðŸ‡²","madagascar":"ðŸ‡²ðŸ‡¬","nigeria":"ðŸ‡³ðŸ‡¬",
    "ghana":"ðŸ‡¬ðŸ‡­","kenya":"ðŸ‡°ðŸ‡ª","ethiopia":"ðŸ‡ªðŸ‡¹","tanzania":"ðŸ‡¹ðŸ‡¿","uganda":"ðŸ‡ºðŸ‡¬",
    "senegal":"ðŸ‡¸ðŸ‡³","mali":"ðŸ‡²ðŸ‡±","burkina faso":"ðŸ‡§ðŸ‡«","guinea":"ðŸ‡¬ðŸ‡³","togo":"ðŸ‡¹ðŸ‡¬",
    "benin":"ðŸ‡§ðŸ‡¯","niger":"ðŸ‡³ðŸ‡ª","chad":"ðŸ‡¹ðŸ‡©","angola":"ðŸ‡¦ðŸ‡´","mozambique":"ðŸ‡²ðŸ‡¿",
    "zambia":"ðŸ‡¿ðŸ‡²","zimbabwe":"ðŸ‡¿ðŸ‡¼","botswana":"ðŸ‡§ðŸ‡¼","namibia":"ðŸ‡³ðŸ‡¦",
    "south africa":"ðŸ‡¿ðŸ‡¦","rwanda":"ðŸ‡·ðŸ‡¼","burundi":"ðŸ‡§ðŸ‡®","congo":"ðŸ‡¨ðŸ‡¬",
    "dr congo":"ðŸ‡¨ðŸ‡©","gabon":"ðŸ‡¬ðŸ‡¦","malawi":"ðŸ‡²ðŸ‡¼","mauritius":"ðŸ‡²ðŸ‡º",
    "cape verde":"ðŸ‡¨ðŸ‡»","sierra leone":"ðŸ‡¸ðŸ‡±","eritrea":"ðŸ‡ªðŸ‡·","somalia":"ðŸ‡¸ðŸ‡´",
    "mauritania":"ðŸ‡²ðŸ‡·","egypt":"ðŸ‡ªðŸ‡¬","morocco":"ðŸ‡²ðŸ‡¦","algeria":"ðŸ‡©ðŸ‡¿",
    "tunisia":"ðŸ‡¹ðŸ‡³","libya":"ðŸ‡±ðŸ‡¾","india":"ðŸ‡®ðŸ‡³","pakistan":"ðŸ‡µðŸ‡°","bangladesh":"ðŸ‡§ðŸ‡©",
    "indonesia":"ðŸ‡®ðŸ‡©","philippines":"ðŸ‡µðŸ‡­","vietnam":"ðŸ‡»ðŸ‡³","thailand":"ðŸ‡¹ðŸ‡­",
    "malaysia":"ðŸ‡²ðŸ‡¾","myanmar":"ðŸ‡²ðŸ‡²","cambodia":"ðŸ‡°ðŸ‡­","sri lanka":"ðŸ‡±ðŸ‡°",
    "nepal":"ðŸ‡³ðŸ‡µ","ukraine":"ðŸ‡ºðŸ‡¦","russia":"ðŸ‡·ðŸ‡º","brazil":"ðŸ‡§ðŸ‡·","argentina":"ðŸ‡¦ðŸ‡·",
    "colombia":"ðŸ‡¨ðŸ‡´","mexico":"ðŸ‡²ðŸ‡½","peru":"ðŸ‡µðŸ‡ª","chile":"ðŸ‡¨ðŸ‡±","venezuela":"ðŸ‡»ðŸ‡ª",
    "united states":"ðŸ‡ºðŸ‡¸","united kingdom":"ðŸ‡¬ðŸ‡§","france":"ðŸ‡«ðŸ‡·","germany":"ðŸ‡©ðŸ‡ª",
    "spain":"ðŸ‡ªðŸ‡¸","china":"ðŸ‡¨ðŸ‡³","japan":"ðŸ‡¯ðŸ‡µ","south korea":"ðŸ‡°ðŸ‡·",
    "saudi arabia":"ðŸ‡¸ðŸ‡¦","turkey":"ðŸ‡¹ðŸ‡·","iran":"ðŸ‡®ðŸ‡·","iraq":"ðŸ‡®ðŸ‡¶","afghanistan":"ðŸ‡¦ðŸ‡«",
}
def _flag(c: str) -> str:
    return _FLAG.get((c or "").strip().lower(), "ðŸŒ")

def _resolve_service(sid="", service="", range_id="") -> str:
    for raw in [sid, service]:
        v = (raw or "").strip().lower()
        if not v: continue
        if "facebook" in v or v == "fb":  return "Facebook"
        if "telegram" in v or v == "tg":  return "Telegram"
        if "whatsapp" in v or v == "wa":  return "WhatsApp"
    r = (range_id or "").lower()
    if "fb" in r or "facebook" in r: return "Facebook"
    if "tg" in r or "telegram" in r: return "Telegram"
    return "WhatsApp"

def _svc_icon(svc: str) -> str:
    return SVC_ICON.get(svc.lower(), "ðŸ“²")

def _num_matches(api_num: str, watch: set) -> bool:
    a = api_num.strip().lstrip("+")
    for w in watch:
        wc = w.strip().lstrip("+")
        if a == wc: return True
        sl = min(len(a), len(wc), 9)
        if sl >= 7 and a[-sl:] == wc[-sl:]: return True
    return False

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  OTP NOTIFICATION
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _notify_otp(chat_id, full_num, otp_code,
                country="", service="", range_id=""):
    _inc_otp(chat_id)
    svc_name = _resolve_service(service=service, range_id=range_id)
    icon     = _svc_icon(svc_name)
    ctry     = (country or "Unknown").title()
    header   = (f"{_flag(country)}|`{full_num}`| "
                f"{icon} {svc_name} ðŸŒCOUNTRY: {ctry}")
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        f"ðŸ”‘  {otp_code}",
        copy_text=types.CopyTextButton(text=otp_code)))
    try:
        bot.send_message(chat_id, header,
                         reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        print(f"[OTP-NOTIFY] {e}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  GLOBAL P2 POLLER  â€” à¦à¦•à¦Ÿà¦¾à¦‡ thread, à¦¸à¦¬ user-à¦à¦° à¦œà¦¨à§à¦¯
#  interval: 1 second  |  endpoint: /api/success-otp-info
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _fetch_p2_otps() -> list:
    try:
        r = _p2_sess.get(
            f"{P2_BASE}/api/success-otp-info",
            params={"api_key": P2_KEY},
            timeout=5,
        )
        if r.status_code != 200:
            return []
        data = r.json().get("data", {}) or {}
        return data.get("otps", []) or []
    except Exception as e:
        print(f"[P2-FETCH] {e}")
        return []

def _global_p2_poller():
    """Bot start à¦¹à¦“à¦¯à¦¼à¦¾à¦° à¦¸à¦®à¦¯à¦¼ à¦¯à§‡à¦¸à¦¬ OTP à¦‡à¦¤à¦¿à¦®à¦§à§à¦¯à§‡ à¦†à¦›à§‡ à¦¸à§‡à¦—à§à¦²à§‹ skip à¦•à¦°à¦¿à¥¤"""
    seen: set = {str(o.get("otp_id","")) for o in _fetch_p2_otps()
                 if o.get("otp_id")}
    print(f"[P2-POLLER] à¦¶à§à¦°à§à¥¤ pre-seen={len(seen)}")

    while True:
        time.sleep(1)          # â† 1 à¦¸à§‡à¦•à§‡à¦¨à§à¦¡ interval
        try:
            with _p2_reg_lock:
                if not _p2_registry:
                    continue   # à¦•à§‹à¦¨à§‹ active user à¦¨à§‡à¦‡ â†’ API call à¦¬à¦¾à¦à¦šà¦¾à¦“
                # expired entries à¦¸à¦°à¦¾à¦“
                now = time.time()
                for k in [k for k, v in _p2_registry.items()
                           if v["deadline"] < now]:
                    del _p2_registry[k]

            for o in _fetch_p2_otps():
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
                        if _num_matches(api_num, {plain}):
                            print(f"[P2-POLLER] âœ… {info['full']} otp={code}")
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

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  GLOBAL P1 POLLER  â€” à¦à¦•à¦Ÿà¦¾à¦‡ thread, à¦¸à¦¬ user-à¦à¦° à¦œà¦¨à§à¦¯
#  interval: 1 second  |  endpoint: /success-otp
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _fetch_p1_otps() -> list:
    try:
        resp = p1_get("/success-otp")
        otps = (resp.get("data") or {}).get("otps", [])
        return otps if isinstance(otps, list) else []
    except:
        return []

def _global_p1_poller():
    seen: set = {str(o.get("otp_id","")) for o in _fetch_p1_otps()
                 if o.get("otp_id")}
    print(f"[P1-POLLER] à¦¶à§à¦°à§à¥¤ pre-seen={len(seen)}")

    while True:
        time.sleep(1)          # â† 1 à¦¸à§‡à¦•à§‡à¦¨à§à¦¡ interval
        try:
            with _p1_reg_lock:
                if not _p1_registry:
                    continue
                now = time.time()
                for k in [k for k, v in _p1_registry.items()
                           if v["deadline"] < now]:
                    del _p1_registry[k]

            for o in _fetch_p1_otps():
                oid = str(o.get("otp_id") or "")
                if not oid or oid in seen:
                    continue
                seen.add(oid)

                api_num = str(o.get("number","")).strip()
                api_sid = str(o.get("sid") or o.get("service") or "")
                code    = extract_otp(str(o.get("message","")))
                if not code or code == "???":
                    continue

                with _p1_reg_lock:
                    for plain, info in list(_p1_registry.items()):
                        if _num_matches(api_num, {plain}):
                            print(f"[P1-POLLER] âœ… {info['full']} otp={code}")
                            threading.Thread(
                                target=_notify_otp,
                                args=(info["chat_id"],),
                                kwargs=dict(
                                    full_num=info["full"],
                                    otp_code=code,
                                    country=info["country"],
                                    service=info.get("service") or api_sid,
                                    range_id=info["range_id"],
                                ),
                                daemon=True,
                            ).start()
                            del _p1_registry[plain]
                            break

        except Exception as e:
            print(f"[P1-POLLER] err: {e}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  PER-USER WHATSAPP CLIENT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _session_path(chat_id: int) -> str:
    return f"wa_session_{chat_id}"

def _clear_session(chat_id: int):
    base = _session_path(chat_id)
    for ext in ("", ".db", ".db-shm", ".db-wal"):
        fp = base + ext
        if os.path.exists(fp):
            try: os.remove(fp)
            except: pass

def _build_wa_client(chat_id: int) -> NewClient:
    c = NewClient(_session_path(chat_id))

    @c.event(ConnectedEv)
    def _on_conn(client, event):
        wa_statuses[chat_id] = "connected"
        print(f"[WA] âœ… connected: {chat_id}")
        try:
            bot.send_message(
                chat_id,
                "âœ… *WhatsApp à¦¸à¦‚à¦¯à§à¦•à§à¦¤ à¦¹à¦¯à¦¼à§‡à¦›à§‡!*\n\nà¦à¦–à¦¨ à¦¨à¦®à§à¦¬à¦° à¦šà§‡à¦• à¦•à¦°à¦¾ à¦¯à¦¾à¦¬à§‡à¥¤",
                reply_markup=_main_kb(chat_id),
            )
        except: pass

    @c.event(DisconnectedEv)
    def _on_disc(client, event):
        wa_statuses[chat_id] = "disconnected"
        print(f"[WA] âš ï¸ disconnected: {chat_id}")
        time.sleep(5)
        if os.path.exists(_session_path(chat_id) + ".db"):
            threading.Thread(
                target=_reconnect_silent, args=(chat_id,), daemon=True).start()

    return c

def _reconnect_silent(chat_id: int):
    if get_wa_status(chat_id) != "disconnected": return
    wa_statuses[chat_id] = "connecting"
    client = _build_wa_client(chat_id)
    wa_clients[chat_id] = client
    try:
        client.connect()
    except Exception as e:
        wa_statuses[chat_id] = "disconnected"
        print(f"[WA] reconnect fail {chat_id}: {e}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  PAIR PHONE  â€” neonize 0.4.x  â€” TESTED & CONFIRMED WORKING
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def connect_with_code(chat_id: int, phone: str):
    if get_wa_status(chat_id) == "connected":
        bot.send_message(chat_id, "âœ… *WhatsApp à¦‡à¦¤à¦¿à¦®à¦§à§à¦¯à§‡ à¦¸à¦‚à¦¯à§à¦•à§à¦¤!*",
                         reply_markup=_main_kb(chat_id))
        return
    if get_wa_status(chat_id) == "connecting":
        bot.send_message(chat_id, "â³ à¦•à§‹à¦¡ à¦¤à§ˆà¦°à¦¿ à¦¹à¦šà§à¦›à§‡, à¦à¦•à¦Ÿà§ à¦…à¦ªà§‡à¦•à§à¦·à¦¾ à¦•à¦°à§à¦¨...")
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
                f"ðŸ”‘ *WhatsApp Pairing Code:*\n\n`{code}`\n\n"
                "WhatsApp à¦ à¦¯à¦¾à¦¨:\n"
                "âš™ï¸ *Settings â†’ Linked Devices â†’ Link with Phone Number*\n\n"
                "à¦à¦‡ à§®-digit à¦•à§‹à¦¡ à¦¦à¦¿à¦¨à¥¤\n"
                "â³ à¦¦à§‡à¦“à¦¯à¦¼à¦¾à¦° à¦ªà¦° à¦¸à§à¦¬à¦¯à¦¼à¦‚à¦•à§à¦°à¦¿à¦¯à¦¼à¦­à¦¾à¦¬à§‡ à¦¸à¦‚à¦¯à§à¦•à§à¦¤ à¦¹à¦¬à§‡à¥¤",
                parse_mode="Markdown",
            )
        except Exception as e:
            wa_statuses[chat_id] = "disconnected"
            wa_clients.pop(chat_id, None)
            bot.send_message(
                chat_id,
                f"âŒ à¦¸à¦‚à¦¯à§‹à¦— à¦¬à§à¦¯à¦°à§à¦¥:\n`{e}`\n\nà¦†à¦¬à¦¾à¦° *âŒ WA Checker* à¦šà¦¾à¦ªà§à¦¨à¥¤",
                reply_markup=_main_kb(chat_id),
                parse_mode="Markdown",
            )

    threading.Thread(target=client.connect, daemon=True).start()


def disconnect_wa(chat_id: int):
    client = wa_clients.pop(chat_id, None)
    if client:
        try: client.disconnect()
        except: pass
    wa_statuses[chat_id] = "disconnected"
    _clear_session(chat_id)
    bot.send_message(chat_id, "âœ… WhatsApp à¦¸à¦‚à¦¯à§‹à¦— à¦¬à¦¿à¦šà§à¦›à¦¿à¦¨à§à¦¨ à¦¹à¦¯à¦¼à§‡à¦›à§‡à¥¤",
                     reply_markup=_main_kb(chat_id))

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  KEYBOARDS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _main_kb(chat_id=None):
    st = get_wa_status(chat_id) if chat_id else "disconnected"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(types.KeyboardButton("ðŸ”´ P1 Console"),
           types.KeyboardButton("ðŸ”µ P2 Console"))
    kb.row(types.KeyboardButton("ðŸ“ž P1 à¦¨à¦¾à¦®à§à¦¬à¦¾à¦°"),
           types.KeyboardButton("ðŸ“ž P2 à¦¨à¦¾à¦®à§à¦¬à¦¾à¦°"))
    kb.add(types.KeyboardButton("ðŸ” à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦šà§‡à¦•à¦¾à¦°"))
    if st == "connected":
        kb.row(types.KeyboardButton("âœ… WA Checker"),
               types.KeyboardButton("ðŸ”Œ WA à¦¡à¦¿à¦¸à¦•à¦¾à¦¨à§‡à¦•à§à¦Ÿ"))
    else:
        kb.add(types.KeyboardButton("âŒ WA Checker"))
    return kb

def _console_kb(panel: str):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "ðŸ”„ Refresh", callback_data=f"cr|{panel}"))
    return kb

def _number_kb(numbers, wa_res, panel, range_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for n in numbers:
        v    = wa_res.get(n["full"])
        icon = "ðŸ”´" if v is True else ("ðŸŸ¢" if v is False else "â¬œ")
        kb.add(types.InlineKeyboardButton(
            f"{icon}  {n['full']}",
            copy_text=types.CopyTextButton(text=n["full"])))
    kb.row(
        types.InlineKeyboardButton(
            "ðŸ”„ à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦šà§‡à¦žà§à¦œ", callback_data=f"nb|{panel}|{range_id}"),
        types.InlineKeyboardButton(
            "âŒ à¦¬à¦¨à§à¦§", callback_data="cb"),
    )
    return kb

def _card_header(range_id, panel, count, failed=0, service=""):
    label    = "P1" if panel == "p1" else "P2"
    svc_name = service or _resolve_service(range_id=range_id)
    icon     = _svc_icon(svc_name)
    h = f"{icon} *{svc_name.upper()}* [{label}]  â€”  {count}à¦Ÿà¦¿ à¦¨à¦¾à¦®à§à¦¬à¦¾à¦°"
    if failed: h += f"  _(âš ï¸ {failed} à¦®à¦¿à¦¸)_"
    h += "\nâ³ _OTP à¦†à¦¸à¦²à§‡ à¦†à¦ªà¦¨à¦¾à¦° inbox-à¦ à¦¦à§‡à¦–à¦¾à¦¬à§‡_"
    return h

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  CONSOLE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _fmt_p1(hits):
    groups = {}
    for h in hits:
        sid = str(h.get("sid", "")).lower()
        if sid in DEFAULT_SERVICES:
            groups.setdefault(sid, []).append(h)
    if not groups: return "âš ï¸ à¦•à§‹à¦¨à§‹ à¦²à¦¾à¦‡à¦­ à¦¡à§‡à¦Ÿà¦¾ à¦¨à§‡à¦‡à¥¤"
    lines = []
    for sid in ("whatsapp", "facebook", "telegram"):
        if sid not in groups: continue
        lines.append(f"\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
                     f"{SVC_ICON.get(sid,'ðŸ“²')} *{sid.capitalize()}*")
        for h in groups[sid][:10]:
            lines.append(f"`{h.get('range','')}` â€” "
                         f"_{time_ago(h.get('time', time.time()*1000))}_")
    lines.append(f"\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\nðŸ”„ _{time.strftime('%H:%M:%S')}_")
    return "\n".join(lines)

def _fmt_p2(services):
    order = {"whatsapp":0,"facebook":1,"telegram":2}
    filt  = sorted(
        [s for s in services if str(s.get("sid","")).lower() in DEFAULT_SERVICES],
        key=lambda s: order.get(str(s.get("sid","")).lower(), 9))
    if not filt: return "âš ï¸ à¦•à§‹à¦¨à§‹ à¦²à¦¾à¦‡à¦­ à¦¡à§‡à¦Ÿà¦¾ à¦¨à§‡à¦‡à¥¤"
    lines = []
    for svc in filt:
        sid = str(svc.get("sid","")).lower()
        ago = time_ago(svc.get("last_at", time.time()*1000))
        lines.append(f"\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
                     f"{SVC_ICON.get(sid,'ðŸ“²')} *{sid.capitalize()}* â€” _{ago}_")
        for r in svc.get("ranges",[])[:8]:
            lines.append(f"  `{r}`")
    lines.append(f"\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\nðŸ”„ _{time.strftime('%H:%M:%S')}_")
    return "\n".join(lines)

def _send_console(chat_id, panel, edit_id=None):
    if panel == "p1":
        resp = p1_get("/console")
        hits = resp.get("data", {}).get("hits", [])
        text = "ðŸ”´ *P1 â€” WealthoraPrime*\n" + _fmt_p1(hits)
    else:
        resp = p2_post("/liveaccess")
        svcs = resp.get("services", [])
        text = "ðŸ”µ *P2 â€” FastXOTPs*\n" + _fmt_p2(svcs)
    kb = _console_kb(panel)
    if edit_id:
        try:
            bot.edit_message_text(text, chat_id, edit_id,
                                  reply_markup=kb, parse_mode="Markdown")
            return
        except: pass
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  FETCH NUMBERS  (6à¦Ÿà¦¾ parallel â€” fast)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _fetch_one(panel: str, range_id: str):
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
                        service=service, rid=None,
                        otp_now=False, otp_msg="")
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

    print(f"[P2-FETCH] full={full} rid={rid} otp_now={otp_now}")

    if full:
        return dict(full=full, plain=plain, country=country,
                    service=service, rid=rid,
                    otp_now=otp_now, otp_msg=otp_msg)
    return None

def get_6_numbers(chat_id, panel, range_id, edit_msg_id=None):
    label   = "P1" if panel == "p1" else "P2"
    loading = f"â³ `{range_id}` [{label}] à¦¥à§‡à¦•à§‡ à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦†à¦¨à¦¾ à¦¹à¦šà§à¦›à§‡..."

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
        err = (f"âŒ `{range_id}` [{label}] à¦¥à§‡à¦•à§‡ à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦ªà¦¾à¦“à¦¯à¦¼à¦¾ à¦¯à¦¾à¦¯à¦¼à¦¨à¦¿à¥¤\n"
               "_à¦°à§‡à¦žà§à¦œ à¦–à¦¾à¦²à¦¿ à¦¬à¦¾ API errorà¥¤_")
        if edit_msg_id: edit_safe(chat_id, st_id, err)
        else:
            safe_delete(chat_id, st_id)
            bot.send_message(chat_id, err, parse_mode="Markdown")
        return

    batch_svc = results[0].get("service","") if results else ""
    wa_res    = _wa_bulk(chat_id, results)
    header    = _card_header(range_id, panel, len(results),
                              failed, service=batch_svc)
    kb        = _number_kb(results, wa_res, panel, range_id)

    if edit_msg_id:
        try:
            bot.edit_message_text(header, chat_id, st_id,
                                  reply_markup=kb, parse_mode="Markdown")
        except:
            bot.send_message(chat_id, header,
                             reply_markup=kb, parse_mode="Markdown")
    else:
        safe_delete(chat_id, st_id)
        bot.send_message(chat_id, header,
                         reply_markup=kb, parse_mode="Markdown")

    # active_watches update (cleanup reference)
    plains = {n["plain"].lstrip("+") for n in results}
    with watch_lock:
        existing = active_watches.get(chat_id, set())
        active_watches[chat_id] = existing | plains

    def _cleanup():
        time.sleep(605)
        with watch_lock:
            cur = active_watches.get(chat_id, set())
            active_watches[chat_id] = cur - plains
    threading.Thread(target=_cleanup, daemon=True).start()

    # â”€â”€ Global registry-à¦¤à§‡ register à¦•à¦°à§‹ â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _register_numbers(panel, results, range_id, chat_id, duration=600)

    # P2: otp_now=True à¦¹à¦²à§‡ à¦¸à¦¾à¦¥à§‡ à¦¸à¦¾à¦¥à§‡ notify à¦•à¦°à§‹
    if panel == "p2":
        for n in results:
            if n.get("otp_now") and n.get("otp_msg"):
                code = extract_otp(n["otp_msg"])
                if code and code != "???":
                    _notify_otp(
                        chat_id,
                        full_num=n["full"],
                        otp_code=code,
                        country=n.get("country",""),
                        service=n.get("service",""),
                        range_id=range_id,
                    )
                    # registry à¦¥à§‡à¦•à§‡ à¦¸à¦°à¦¾à¦“ (à¦‡à¦¤à¦¿à¦®à¦§à§à¦¯à§‡ deliver à¦¹à¦¯à¦¼à§‡ à¦—à§‡à¦›à§‡)
                    with _p2_reg_lock:
                        _p2_registry.pop(n["plain"].lstrip("+"), None)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  WA CHECK
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _wa_bulk(chat_id, numbers):
    result = {n["full"]: None for n in numbers}
    client = wa_clients.get(chat_id)
    if not client or get_wa_status(chat_id) != "connected": return result
    try:
        cleaned   = [n["plain"].lstrip("+") for n in numbers]
        jids      = [f"+{c}@s.whatsapp.net" for c in cleaned]
        responses = client.is_on_whatsapp(*jids)
        for i, n in enumerate(numbers):
            matched = next(
                (r for r in responses if cleaned[i] in r.Query), None)
            result[n["full"]] = (
                bool(matched.IsIn) if matched
                else (bool(responses[i].IsIn)
                      if i < len(responses) else None))
    except Exception as e:
        print(f"[WA-BULK] {e}")
    return result

def _wa_check(chat_id, numbers):
    result  = {n: None for n in numbers}
    client  = wa_clients.get(chat_id)
    if not client or get_wa_status(chat_id) != "connected": return result
    cleaned = [n.replace("+","").replace(" ","").replace("-","")
               for n in numbers]
    jids    = [f"+{c}@s.whatsapp.net" for c in cleaned]
    try:
        responses = client.is_on_whatsapp(*jids)
        for i, n in enumerate(numbers):
            matched = next(
                (r for r in responses if cleaned[i] in r.Query), None)
            result[n] = (
                bool(matched.IsIn) if matched
                else (bool(responses[i].IsIn)
                      if i < len(responses) else None))
    except Exception as e:
        print(f"[WA-CHECK] {e}")
    return result

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  BUTTON LABELS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_ALL_BTN = {
    "ðŸ”´ P1 Console","ðŸ”µ P2 Console",
    "ðŸ“ž P1 à¦¨à¦¾à¦®à§à¦¬à¦¾à¦°","ðŸ“ž P2 à¦¨à¦¾à¦®à§à¦¬à¦¾à¦°",
    "ðŸ” à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦šà§‡à¦•à¦¾à¦°",
    "âœ… WA Checker","âŒ WA Checker",
    "ðŸ”Œ WA à¦¡à¦¿à¦¸à¦•à¦¾à¦¨à§‡à¦•à§à¦Ÿ",
}

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  /start
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    _save_user(msg)
    bot.send_message(
        msg.chat.id,
        "ðŸ¤– *OTP Panel Bot v5*\n\n"
        "ðŸ”´ P1 / ðŸ”µ P2 Console â€” à¦²à¦¾à¦‡à¦­ à¦Ÿà§à¦°à§à¦¯à¦¾à¦«à¦¿à¦•\n"
        "ðŸ“ž P1 / ðŸ“ž P2 à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° â€” à¦°à§‡à¦žà§à¦œ â†’ à§¬à¦Ÿà¦¿ à¦¨à¦¾à¦®à§à¦¬à¦¾à¦°\n"
        "ðŸ” à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦šà§‡à¦•à¦¾à¦° â€” WhatsApp check\n"
        "âŒ WA Checker â€” Phone code à¦¦à¦¿à¦¯à¦¼à§‡ à¦²à¦—à¦‡à¦¨ (QR à¦¨à§‡à¦‡)\n"
        "ðŸ”Œ WA à¦¡à¦¿à¦¸à¦•à¦¾à¦¨à§‡à¦•à§à¦Ÿ â€” à¦¸à¦‚à¦¯à§‹à¦— à¦¬à¦¨à§à¦§\n\n"
        "âš¡ OTP à¦†à¦¸à¦¾à¦®à¦¾à¦¤à§à¦° â‰¤à§§ à¦¸à§‡à¦•à§‡à¦¨à§à¦¡à§‡ à¦ªà¦¾à¦¬à§‡à¦¨",
        reply_markup=_main_kb(msg.chat.id),
    )

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  /stats  (admin only)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.message_handler(commands=["stats"])
def cmd_stats(msg):
    if msg.chat.id != ADMIN_ID: return
    if not otp_stats:
        bot.send_message(msg.chat.id, "ðŸ“Š à¦à¦–à¦¨à§‹ à¦•à§‹à¦¨à§‹ OTP à¦°à¦¿à¦¸à¦¿à¦­ à¦¹à¦¯à¦¼à¦¨à¦¿à¥¤")
        return
    text  = "ðŸ“Š *OTP Statistics*\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
    total = 0
    for uid, cnt in sorted(otp_stats.items(), key=lambda x: -x[1]):
        with names_lock:
            uname = user_names.get(uid, "")
        if uname.startswith("@"):
            link = f"[{uname}](tg://user?id={uid})"
        else:
            link = f"[{uname or uid}](tg://user?id={uid})"
        text  += f"ðŸ‘¤ {link} â€” *{cnt}* OTP\n"
        total += cnt
    text += f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\nðŸ“‹ à¦®à§‹à¦Ÿ: *{total}* OTP"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown",
                     disable_web_page_preview=True)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  /status  (admin only)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.message_handler(commands=["status"])
def cmd_status(msg):
    if msg.chat.id != ADMIN_ID: return
    connected  = [cid for cid, st in wa_statuses.items() if st == "connected"]
    connecting = [cid for cid, st in wa_statuses.items() if st == "connecting"]
    with watch_lock:
        watching = sum(len(v) for v in active_watches.values())
    with _p2_reg_lock:
        p2_active = len(_p2_registry)
    with _p1_reg_lock:
        p1_active = len(_p1_registry)
    total_otp = sum(otp_stats.values()) if otp_stats else 0
    text = (
        "ðŸ–¥ *Bot Status  v5*\nâ”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
        f"â± Uptime: `{uptime_str()}`\n"
        f"ðŸ‘¥ WA Connected: `{len(connected)}`\n"
        f"ðŸ”„ WA Connecting: `{len(connecting)}`\n"
        f"ðŸ‘ Active watches: `{watching}`\n"
        f"ðŸ”µ P2 watching: `{p2_active}` à¦¨à¦®à§à¦¬à¦°\n"
        f"ðŸ”´ P1 watching: `{p1_active}` à¦¨à¦®à§à¦¬à¦°\n"
        f"ðŸ“¨ Total OTPs: `{total_otp}`\n"
        f"â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\n"
    )
    if connected:
        text += "*Connected users:*\n"
        for cid in connected:
            cnt   = otp_stats.get(cid, 0)
            label = _get_label(cid)
            text += f"  â€¢ `{cid}` ({label}) â€” {cnt} OTP\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown",
                     disable_web_page_preview=True)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  CONSOLE BUTTONS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.message_handler(func=lambda m: m.text == "ðŸ”´ P1 Console")
def btn_p1_console(msg):
    _save_user(msg)
    threading.Thread(target=_send_console,
                     args=(msg.chat.id,"p1"), daemon=True).start()

@bot.message_handler(func=lambda m: m.text == "ðŸ”µ P2 Console")
def btn_p2_console(msg):
    _save_user(msg)
    threading.Thread(target=_send_console,
                     args=(msg.chat.id,"p2"), daemon=True).start()

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  NUMBER BUTTONS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.message_handler(func=lambda m: m.text == "ðŸ“ž P1 à¦¨à¦¾à¦®à§à¦¬à¦¾à¦°")
def btn_p1_num(msg):
    _save_user(msg)
    with state_lock:
        user_state[msg.chat.id] = {"mode": "wait_range_p1"}
    bot.send_message(msg.chat.id,
                     "ðŸ“ *P1* à¦°à§‡à¦žà§à¦œ à¦²à¦¿à¦–à§à¦¨  (à¦¯à§‡à¦®à¦¨: `22501XXX`)",
                     parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "ðŸ“ž P2 à¦¨à¦¾à¦®à§à¦¬à¦¾à¦°")
def btn_p2_num(msg):
    _save_user(msg)
    with state_lock:
        user_state[msg.chat.id] = {"mode": "wait_range_p2"}
    bot.send_message(msg.chat.id,
                     "ðŸ“ *P2* à¦°à§‡à¦žà§à¦œ à¦²à¦¿à¦–à§à¦¨  (à¦¯à§‡à¦®à¦¨: `26134XXX`)",
                     parse_mode="Markdown")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  âŒ / âœ… WA CHECKER BUTTON
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.message_handler(
    func=lambda m: m.text in ("âœ… WA Checker", "âŒ WA Checker"))
def btn_wa(msg):
    _save_user(msg)
    chat_id = msg.chat.id
    status  = get_wa_status(chat_id)
    if status == "connected":
        bot.send_message(chat_id, "âœ… *WhatsApp à¦‡à¦¤à¦¿à¦®à¦§à§à¦¯à§‡ à¦¸à¦‚à¦¯à§à¦•à§à¦¤!*",
                         reply_markup=_main_kb(chat_id))
        return
    if status == "connecting":
        bot.send_message(chat_id, "â³ à¦•à§‹à¦¡ à¦¤à§ˆà¦°à¦¿ à¦¹à¦šà§à¦›à§‡, à¦à¦•à¦Ÿà§ à¦…à¦ªà§‡à¦•à§à¦·à¦¾ à¦•à¦°à§à¦¨...")
        return
    with state_lock:
        user_state[chat_id] = {"mode": "wait_phone"}
    bot.send_message(
        chat_id,
        "ðŸ“± *WhatsApp à¦¨à¦®à§à¦¬à¦°* à¦¦à¦¿à¦¨ (à¦¦à§‡à¦¶à§‡à¦° à¦•à§‹à¦¡ à¦¸à¦¹)\n\n"
        "à¦‰à¦¦à¦¾à¦¹à¦°à¦£: `+8801712345678`",
        parse_mode="Markdown",
    )

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  ðŸ”Œ DISCONNECT BUTTON
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.message_handler(func=lambda m: m.text == "ðŸ”Œ WA à¦¡à¦¿à¦¸à¦•à¦¾à¦¨à§‡à¦•à§à¦Ÿ")
def btn_disconnect(msg):
    _save_user(msg)
    threading.Thread(target=disconnect_wa,
                     args=(msg.chat.id,), daemon=True).start()

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  ðŸ” NUMBER CHECKER
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.message_handler(func=lambda m: m.text == "ðŸ” à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦šà§‡à¦•à¦¾à¦°")
def btn_checker(msg):
    _save_user(msg)
    chat_id = msg.chat.id
    if get_wa_status(chat_id) != "connected":
        bot.send_message(chat_id,
                         "âŒ *WhatsApp à¦¸à¦‚à¦¯à§à¦•à§à¦¤ à¦¨à§‡à¦‡à¥¤*\n\n"
                         "à¦ªà§à¦°à¦¥à¦®à§‡ *âŒ WA Checker* à¦šà¦¾à¦ªà§à¦¨à¥¤",
                         reply_markup=_main_kb(chat_id))
        return
    with state_lock:
        user_state[chat_id] = {"mode": "wait_check_numbers"}
    bot.send_message(chat_id,
                     "ðŸ” *à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦šà§‡à¦•à¦¾à¦°*\n\n"
                     "ðŸ“ž à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦ªà¦¾à¦ à¦¾à¦¨ (à¦ªà§à¦°à¦¤à¦¿ à¦²à¦¾à¦‡à¦¨à§‡ à¦à¦•à¦Ÿà¦¿, à¦¸à¦°à§à¦¬à§‹à¦šà§à¦š à§¨à§¦à¦Ÿà¦¿):",
                     parse_mode="Markdown")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  FREE TEXT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(msg):
    _save_user(msg)
    chat_id = msg.chat.id
    text    = msg.text.strip()
    if text.startswith("/") or text in _ALL_BTN: return

    with state_lock:
        mode = user_state.get(chat_id, {}).get("mode", "idle")

    # â”€â”€ wait_phone â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if mode == "wait_phone":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        phone = text.replace(" ", "").replace("-", "")
        if not phone.startswith("+"):
            phone = "+" + phone
        if not re.match(r"^\+\d{7,15}$", phone):
            bot.send_message(
                chat_id,
                "âŒ *à¦¨à¦®à§à¦¬à¦° à¦¸à¦ à¦¿à¦• à¦¨à¦¯à¦¼à¥¤*\n\nà¦¦à§‡à¦¶à§‡à¦° à¦•à§‹à¦¡ à¦¸à¦¹ à¦¦à¦¿à¦¨à¥¤\nà¦‰à¦¦à¦¾à¦¹à¦°à¦£: `+8801712345678`",
                parse_mode="Markdown",
            )
            return
        bot.send_message(chat_id,
                         f"â³ `{phone}` à¦à¦° à¦œà¦¨à§à¦¯ pairing code à¦¤à§ˆà¦°à¦¿ à¦¹à¦šà§à¦›à§‡...",
                         parse_mode="Markdown")
        threading.Thread(
            target=connect_with_code, args=(chat_id, phone), daemon=True
        ).start()

    # â”€â”€ wait_range_p1 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    elif mode == "wait_range_p1":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        threading.Thread(
            target=get_6_numbers, args=(chat_id, "p1", text), daemon=True
        ).start()

    # â”€â”€ wait_range_p2 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    elif mode == "wait_range_p2":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        threading.Thread(
            target=get_6_numbers, args=(chat_id, "p2", text), daemon=True
        ).start()

    # â”€â”€ wait_check_numbers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    elif mode == "wait_check_numbers":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        lines = [l.strip() for l in text.splitlines() if l.strip()][:20]
        if not lines:
            bot.send_message(chat_id, "âŒ à¦•à§‹à¦¨à§‹ à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦ªà¦¾à¦“à¦¯à¦¼à¦¾ à¦¯à¦¾à¦¯à¦¼à¦¨à¦¿à¥¤")
            return
        loading = bot.send_message(
            chat_id, f"â³ {len(lines)}à¦Ÿà¦¿ à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦šà§‡à¦• à¦¹à¦šà§à¦›à§‡...", parse_mode="Markdown"
        )
        def _do_check():
            results = _wa_check(chat_id, lines)
            out = []
            for n, is_on in results.items():
                if is_on is True:   icon = "ðŸ”´ WhatsApp à¦†à¦›à§‡"
                elif is_on is False: icon = "ðŸŸ¢ WhatsApp à¦¨à§‡à¦‡"
                else:               icon = "â¬œ à¦šà§‡à¦• à¦¹à¦¯à¦¼à¦¨à¦¿"
                out.append(f"`{n}` â€” {icon}")
            safe_delete(chat_id, loading.message_id)
            bot.send_message(
                chat_id,
                "ðŸ” *à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦šà§‡à¦•à¦¾à¦° à¦«à¦²à¦¾à¦«à¦²:*\n\n" + "\n".join(out),
                parse_mode="Markdown",
            )
        threading.Thread(target=_do_check, daemon=True).start()

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  CALLBACK QUERY HANDLER
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
        bot.answer_callback_query(call.id, "ðŸ”„ Refreshing...")
        threading.Thread(
            target=_send_console, args=(chat_id, panel, msg_id), daemon=True
        ).start()
        return

    if data.startswith("nb|"):
        parts    = data.split("|", 2)
        panel    = parts[1]
        range_id = parts[2]
        bot.answer_callback_query(call.id, "ðŸ”„ à¦¨à¦¤à§à¦¨ à¦¨à¦¾à¦®à§à¦¬à¦¾à¦° à¦†à¦¨à¦¾ à¦¹à¦šà§à¦›à§‡...")
        threading.Thread(
            target=get_6_numbers,
            args=(chat_id, panel, range_id, msg_id),
            daemon=True,
        ).start()
        return

    bot.answer_callback_query(call.id)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  MAIN
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if __name__ == "__main__":
    print(f"ðŸ¤– OTP Panel Bot v5.0 à¦šà¦¾à¦²à§ à¦¹à¦šà§à¦›à§‡... (admin={ADMIN_ID})")

    # Global pollers â€” daemon thread, à¦à¦•à¦Ÿà¦¾à¦‡ à¦ªà§à¦°à¦¤à¦¿à¦Ÿà¦¾à¦° à¦œà¦¨à§à¦¯
    threading.Thread(target=_global_p2_poller, daemon=True,
                     name="P2-GlobalPoller").start()
    threading.Thread(target=_global_p1_poller, daemon=True,
                     name="P1-GlobalPoller").start()

    bot.infinity_polling(timeout=30, long_polling_timeout=20)
