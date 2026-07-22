ঋ"""
OTP Panel Bot v6.0 — SUPER FAST & CLEAN
=========================================================
বাটন:
  🔴 P1 Console  → WealthoraPrime লাইভ ট্র্যাফিক
  🔵 P2 Console  → FastXOTPs লাইভ ট্র্যাফিক
  📲 OLD নাম্বার → P1 parallel → WA check → ৫টা নাম্বার
  🔍 নাম্বার চেকার → WA আছে কিনা
  ❌/✅ WP Checker → Phone code login
  🔌 WP Disconnect → সংযোগ বন্ধ
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
    raise SystemExit("❌  TELEGRAM_BOT_TOKEN env var দরকার।")

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
wa_clients  = {}   # chat_id → NewClient
wa_statuses = {}   # chat_id → "disconnected"|"connecting"|"connected"
otp_stats   = {}   # chat_id → int
bot_start   = time.time()

user_names = {}; names_lock = threading.Lock()
user_state = {}; state_lock  = threading.Lock()

# OTP registries — plain_number → info dict
_p1_registry = {}; _p1_reg_lock = threading.Lock()
_p2_registry = {}; _p2_reg_lock = threading.Lock()

SVC_ICON = {"whatsapp": "💬", "facebook": "📘", "telegram": "✈️"}
DEFAULT_SVCS = {"whatsapp", "facebook", "telegram"}

_FLAG = {
    "ivory coast":"🇨🇮","cameroon":"🇨🇲","madagascar":"🇲🇬","nigeria":"🇳🇬",
    "ghana":"🇬🇭","kenya":"🇰🇪","ethiopia":"🇪🇹","tanzania":"🇹🇿","uganda":"🇺🇬",
    "senegal":"🇸🇳","mali":"🇲🇱","burkina faso":"🇧🇫","guinea":"🇬🇳","togo":"🇹🇬",
    "benin":"🇧🇯","niger":"🇳🇪","chad":"🇹🇩","angola":"🇦🇴","mozambique":"🇲🇿",
    "zambia":"🇿🇲","zimbabwe":"🇿🇼","botswana":"🇧🇼","namibia":"🇳🇦",
    "south africa":"🇿🇦","rwanda":"🇷🇼","burundi":"🇧🇮","congo":"🇨🇬",
    "dr congo":"🇨🇩","gabon":"🇬🇦","malawi":"🇲🇼","mauritius":"🇲🇺",
    "cape verde":"🇨🇻","sierra leone":"🇸🇱","eritrea":"🇪🇷","somalia":"🇸🇴",
    "mauritania":"🇲🇷","egypt":"🇪🇬","morocco":"🇲🇦","algeria":"🇩🇿",
    "tunisia":"🇹🇳","libya":"🇱🇾","india":"🇮🇳","pakistan":"🇵🇰","bangladesh":"🇧🇩",
    "indonesia":"🇮🇩","philippines":"🇵🇭","vietnam":"🇻🇳","thailand":"🇹🇭",
    "malaysia":"🇲🇾","myanmar":"🇲🇲","cambodia":"🇰🇭","sri lanka":"🇱🇰",
    "nepal":"🇳🇵","ukraine":"🇺🇦","russia":"🇷🇺","brazil":"🇧🇷","argentina":"🇦🇷",
    "colombia":"🇨🇴","mexico":"🇲🇽","peru":"🇵🇪","chile":"🇨🇱","venezuela":"🇻🇪",
    "united states":"🇺🇸","united kingdom":"🇬🇧","france":"🇫🇷","germany":"🇩🇪",
    "spain":"🇪🇸","china":"🇨🇳","japan":"🇯🇵","south korea":"🇰🇷",
    "saudi arabia":"🇸🇦","turkey":"🇹🇷","iran":"🇮🇷","iraq":"🇮🇶","afghanistan":"🇦🇫",
}

# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────
def _flag(c): return _FLAG.get((c or "").strip().lower(), "🌍")

def _svc_icon(s): return SVC_ICON.get((s or "").lower(), "📲")

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
    header = f"{_flag(country)}|`{full_num}`| {icon} {svc} 🌍COUNTRY: {ctry}"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        f"🔑  {otp_code}", copy_text=types.CopyTextButton(text=otp_code)))
    try:
        bot.send_message(chat_id, header, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        print(f"[OTP-NOTIFY] {e}")

# ─────────────────────────────────────────────────────────────
#  GLOBAL P1 POLLER — 1s interval
# ─────────────────────────────────────────────────────────────
def _fetch_p1_otps():
    try:
        resp = p1_get("/success-otp")
        otps = (resp.get("data") or {}).get("otps", [])
        return otps if isinstance(otps, list) else []
    except:
        return []

def _global_p1_poller():
    seen = {str(o.get("otp_id","")) for o in _fetch_p1_otps() if o.get("otp_id")}
    print(f"[P1-POLLER] শুরু। pre-seen={len(seen)}")
    while True:
        time.sleep(1)
        try:
            with _p1_reg_lock:
                if not _p1_registry: continue
                now = time.time()
                for k in [k for k, v in list(_p1_registry.items()) if v["deadline"] < now]:
                    del _p1_registry[k]
            f
