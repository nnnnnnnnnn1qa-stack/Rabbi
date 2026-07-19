"""
OTP Panel Bot
Panels : P1 (WealthoraPrime) + P2 (FastXOTPs)
WA     : neonize PairPhone code login (per-user, no QR)
Admin  : ADMIN_ID
"""

import os, re, time, threading, logging, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import telebot
from telebot import types
from neonize.client import NewClient
from neonize.events import ConnectedEv, DisconnectedEv

# ══════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════
BOT_TOKEN = (os.environ.get("WA_CHECKER_BOT_TOKEN")
             or os.environ.get("TELEGRAM_BOT_TOKEN", ""))

ADMIN_ID = int(os.environ.get("ADMIN_ID", "8523774444"))

P1_BASE = os.environ.get("WEALTHORA_API_BASE",
          "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api")
P1_KEY  = os.environ.get("WEALTHORA_API_KEY", "MWFG9WNAHZQ")
P1_HDRS = {"mauthapi": P1_KEY}

P2_BASE = os.environ.get("FASTXOTPS_API_BASE", "https://fastxotps.com")
P2_KEY  = os.environ.get("FASTXOTPS_API_KEY", "MURAD_69548E938AF8F1D4E0587220")
P2_HDRS = {"X-API-Key": P2_KEY, "Content-Type": "application/json"}

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN env var is required.")

logging.basicConfig(level=logging.WARNING)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════
#  GLOBAL STATE
# ══════════════════════════════════════════════════════════════════════
wa_clients  = {}   # chat_id -> NewClient
wa_statuses = {}   # chat_id -> "disconnected" | "connecting" | "connected"
otp_stats   = {}   # chat_id -> int

user_state  = {}
state_lock  = threading.Lock()

DEFAULT_SERVICES = {"whatsapp", "facebook", "telegram"}
SVC_ICON = {"whatsapp": "💬", "facebook": "📘", "telegram": "✈️"}

# ══════════════════════════════════════════════════════════════════════
#  HTTP HELPERS
# ══════════════════════════════════════════════════════════════════════
def _get(url, params=None, headers=None, timeout=10):
    try:
        return requests.get(url, params=params, headers=headers, timeout=timeout).json()
    except Exception as e:
        return {"error": str(e)}

def _post(url, data=None, headers=None, timeout=10):
    try:
        return requests.post(url, json=data or {}, headers=headers, timeout=timeout).json()
    except Exception as e:
        return {"error": str(e)}

def p1_get(path, params=None):
    return _get(f"{P1_BASE}{path}", params=params, headers=P1_HDRS)

def p1_post(path, data=None):
    return _post(f"{P1_BASE}{path}", data=data, headers=P1_HDRS)

def p2_post(path, data=None):
    return _post(f"{P2_BASE}/api{path}", data=data or {}, headers=P2_HDRS)

# ══════════════════════════════════════════════════════════════════════
#  UTILITY
# ══════════════════════════════════════════════════════════════════════
def time_ago(ms: float) -> str:
    s = max(0, int(time.time() - ms / 1000))
    if s < 60:   return f"{s}s ago"
    if s < 3600: return f"{s // 60}m ago"
    return f"{s // 3600}h ago"

def extract_otp(msg: str) -> str:
    m = re.search(r'\b(\d{3}[- ]\d{3})\b', msg)
    if m: return m.group(1).replace(" ", "-")
    m = re.search(r'\b(\d{4,7})\b', msg)
    if m: return m.group(1)
    return "???"

def safe_delete(chat_id, msg_id):
    try: bot.delete_message(chat_id, msg_id)
    except: pass

def edit_safe(chat_id, msg_id, text, kb=None):
    try:
        if kb:
            bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb, parse_mode="Markdown")
        else:
            bot.edit_message_text(text, chat_id, msg_id, parse_mode="Markdown")
    except: pass

def _increment_otp(chat_id):
    otp_stats[chat_id] = otp_stats.get(chat_id, 0) + 1

def get_wa_status(chat_id) -> str:
    return wa_statuses.get(chat_id, "disconnected")

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

def _get_flag(country: str) -> str:
    return _FLAG.get(country.strip().lower(), "🌍")

def _svc_label(service="", range_id="") -> str:
    s = (service or "").lower(); r = (range_id or "").lower()
    if "facebook" in s or "fb" in r: return "Facebook"
    if "telegram" in s or "tg" in r: return "Telegram"
    return "WhatsApp"

# ══════════════════════════════════════════════════════════════════════
#  PER-USER WHATSAPP CLIENT
# ══════════════════════════════════════════════════════════════════════
def _session_path(chat_id: int) -> str:
    return f"wa_session_{chat_id}"

def _clear_session(chat_id: int):
    base = _session_path(chat_id)
    for ext in ["", ".db", ".db-shm", ".db-wal"]:
        fp = base + ext
        if os.path.exists(fp):
            try: os.remove(fp)
            except: pass

def _build_wa_client(chat_id: int) -> NewClient:
    c = NewClient(_session_path(chat_id))

    @c.event(ConnectedEv)
    def on_connected(client, event):
        wa_statuses[chat_id] = "connected"
        print(f"✅ WA connected: {chat_id}")
        try:
            bot.send_message(chat_id,
                "✅ *WhatsApp সংযুক্ত হয়েছে!*\n\nএখন নম্বর চেক করা যাবে।",
                reply_markup=main_kb(chat_id))
        except: pass

    @c.event(DisconnectedEv)
    def on_disconnected(client, event):
        wa_statuses[chat_id] = "disconnected"
        print(f"⚠️ WA disconnected: {chat_id} — reconnecting in 5s...")
        time.sleep(5)
        if os.path.exists(_session_path(chat_id) + ".db"):
            threading.Thread(target=_reconnect_silent, args=(chat_id,), daemon=True).start()

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

def connect_with_code(chat_id: int, phone: str):
    """PairPhone: নম্বর দিয়ে 8-digit code পেয়ে WhatsApp-এ দেওয়া।"""
    if get_wa_status(chat_id) == "connected":
        bot.send_message(chat_id, "✅ *WhatsApp ইতিমধ্যে সংযুক্ত!*",
                         reply_markup=main_kb(chat_id))
        return
    if get_wa_status(chat_id) == "connecting":
        bot.send_message(chat_id, "⏳ সংযোগ চলছে...")
        return

    _clear_session(chat_id)
    wa_statuses[chat_id] = "connecting"
    client = _build_wa_client(chat_id)
    wa_clients[chat_id] = client

    def _do_pair():
        try:
            code = client.pair_phone(phone)
            bot.send_message(chat_id,
                f"🔑 *WhatsApp Pairing Code:*\n\n`{code}`\n\n"
                "WhatsApp এ যান:\n"
                "*Settings → Linked Devices → Link with Phone Number*\n\n"
                "এই কোডটি সেখানে দিন।\n"
                "⏳ কোড দেওয়ার পর স্বয়ংক্রিয়ভাবে সংযুক্ত হবে।",
                parse_mode="Markdown")
        except Exception as e:
            wa_statuses[chat_id] = "disconnected"
            bot.send_message(chat_id,
                f"❌ সংযোগ ব্যর্থ:\n`{e}`\n\nআবার *❌ WA Checker* চাপুন।",
                reply_markup=main_kb(chat_id), parse_mode="Markdown")

    threading.Thread(target=_do_pair, daemon=True).start()

def disconnect_wa(chat_id: int):
    client = wa_clients.pop(chat_id, None)
    if client:
        try: client.disconnect()
        except: pass
    wa_statuses[chat_id] = "disconnected"
    _clear_session(chat_id)
    bot.send_message(chat_id, "✅ WhatsApp সংযোগ বিচ্ছিন্ন করা হয়েছে।",
                     reply_markup=main_kb(chat_id))

# ══════════════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════════════
def main_kb(chat_id=None):
    status = get_wa_status(chat_id) if chat_id else "disconnected"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(types.KeyboardButton("🔴 P1 Console"), types.KeyboardButton("🔵 P2 Console"))
    kb.row(types.KeyboardButton("📞 P1 নাম্বার"), types.KeyboardButton("📞 P2 নাম্বার"))
    kb.add(types.KeyboardButton("🔍 নাম্বার চেকার"))
    if status == "connected":
        kb.row(types.KeyboardButton("✅ WA Checker"),
               types.KeyboardButton("🔌 WA ডিসকানেক্ট"))
    else:
        kb.add(types.KeyboardButton("❌ WA Checker"))
    return kb

def console_kb(panel: str):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔄 Refresh", callback_data=f"console_refresh|{panel}"))
    return kb

def _build_number_kb(numbers: list, wa_results: dict, panel: str, range_id: str):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for n in numbers:
        wa_val = wa_results.get(n["ful
