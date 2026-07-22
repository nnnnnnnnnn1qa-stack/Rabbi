"""
OTP Panel Bot  v6.0  — ULTRA FAST
=========================================================
P1  : WealthoraPrime    → success-otp     (1s global poll)
P2  : FastXOTPs        → success-otp-info (1s global poll)
WA  : neonize – PairPhone code (no QR), per-user session
Admin : ADMIN_ID → /stats  /status
=========================================================
✅  Global P2 poller  — 1 টা thread, সব user-এর জন্য, 1s interval
✅  Global P1 poller  — 1 টা thread, সব user-এর জন্য, 1s interval
✅  70–80 concurrent user support
✅  OTP panel-এ আসার ≤1s এ user পায়
✅  OLD নম্বর — P1 থেকে 30টা check করে 5টা WA-active দেয়
✅  WA Checker unchanged (working)
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

# ─────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────
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
    raise SystemExit("❌  TELEGRAM_BOT_TOKEN env var is required.")

logging.basicConfig(level=logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown",
                      num_threads=80)

# ─────────────────────────────────────────────────────────────
#  HTTP SESSIONS
# ─────────────────────────────────────────────────────────────
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

_session  = _make_session(pool_conn=50, pool_max=100)
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

# ─────────────────────────────────────────────────────────────
#  GLOBAL STATE
# ─────────────────────────────────────────────────────────────
wa_clients  = {}   # chat_id → NewClient
wa_statuses = {}   # chat_id → "disconnected"|"connecting"|"connected"
otp_stats   = {}   # chat_id → int
bot_start   = time.time()

user_names  = {}
names_lock  = threading.Lock()

user_state  = {}
state_lock  = threading.Lock()

DEFAULT_SERVICES = {"whatsapp", "facebook", "telegram"}
SVC_ICON = {"whatsapp": "💬", "facebook": "📘", "telegram": "✈️"}

# ─────────────────────────────────────────────────────────────
#  GLOBAL OTP WATCH REGISTRIES
# ─────────────────────────────────────────────────────────────
_p1_registry: dict = {}
_p2_registry: dict = {}
_p1_reg_lock = threading.Lock()
_p2_reg_lock = threading.Lock()

def _register_numbers(panel: str, results: list, range_id: str,
                      chat_id: int, duration: int = 600):
    """নম্বরগুলো global poller registry-তে add করে।"""
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

# ─────── shorthand alias ────────────────────────────────────
def _register(panel: str, results: list, range_id: str,
               chat_id: int, dur: int = 600):
    _register_numbers(panel, results, range_id, chat_id, duration=dur)

# ─────────────────────────────────────────────────────────────
#  USERNAME / UTILITY HELPERS
# ─────────────────────────────────────────────────────────────
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

# ─── flags ────────────────────────────────────────────────────
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
def _flag(c: str) -> str:
    return _FLAG.get((c or "").strip().lower(), "🌍")

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
    return SVC_ICON.get(svc.lower(), "📲")

def _num_matches(api_num: str, watch: set) -> bool:
    a = api_num.strip().lstrip("+")
    for w in watch:
        wc = w.strip().lstrip("+")
        if a == wc: return True
        sl = min(len(a), len(wc), 9)
        if sl >= 7 and a[-sl:] == wc[-sl:]: return True
    return False

# ─────────────────────────────────────────────────────────────
#  OTP NOTIFICATION
# ─────────────────────────────────────────────────────────────
def _notify_otp(chat_id, full_num, otp_code,
                country="", service="", range_id=""):
    _inc_otp(chat_id)
    svc_name = _resolve_service(service=service, range_id=range_id)
    icon     = _svc_icon(svc_name)
    ctry     = (country or "Unknown").title()
    header   = (f"{_flag(country)}|`{full_num}`| "
                f"{icon} {svc_name} 🌍COUNTRY: {ctry}")
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        f"🔑  {otp_code}",
        copy_text=types.CopyTextButton(text=otp_code)))
    try:
        bot.send_message(chat_id, header,
                         reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        print(f"[OTP-NOTIFY] {e}")

# ─────────────────────────────────────────────────────────────
#  GLOBAL P2 POLLER
# ─────────────────────────────────────────────────────────────
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
    seen: set = {str(o.get("otp_id","")) for o in _fetch_p2_otps()
                 if o.get("otp_id")}
    print(f"[P2-POLLER] শুরু। pre-seen={len(seen)}")

    while True:
        time.sleep(1)
        try:
            with _p2_reg_lock:
                if not _p2_registry:
                    continue
                now = time.time()
                for k in [k for k, v in _p2_registry.items()
                           if v["deadline"] < now]:
                    del _p2_registry[k]

            for o in _fetch_p2_otps():
                oid = str(o.get("otp_id") or "")
                if not oid or oid in seen:
                    continue
                seen.add(oid)
                # seen set বড় হলে পুরনো entries সরাও
                if len(seen) > 5000:
                    seen.clear()

                api_num = str(o.get("number", "")).strip().lstrip("+")
                otp_val = str(o.get("otp") or "")
                msg_txt = str(o.get("message") or "")
                code    = otp_val or extract_otp(msg_txt)
                if not code or code == "???":
                    continue

                with _p2_reg_lock:
                    for plain, info in list(_p2_registry.items()):
                        if _num_matches(api_num, {plain}):
                            print(f"[P2-POLLER] ✅ {info['full']} otp={code}")
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
#  GLOBAL P1 POLLER
# ─────────────────────────────────────────────────────────────
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
    print(f"[P1-POLLER] শুরু। pre-seen={len(seen)}")

    while True:
        time.sleep(1)
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
                if len(seen) > 5000:
                    seen.clear()

                api_num = str(o.get("number","")).strip()
                api_sid = str(o.get("sid") or o.get("service") or "")
                code    = extract_otp(str(o.get("message","")))
                if not code or code == "???":
                    continue

                with _p1_reg_lock:
                    for plain, info in list(_p1_registry.items()):
                        if _num_matches(api_num, {plain}):
                            print(f"[P1-POLLER] ✅ {info['full']} otp={code}")
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

# ─────────────────────────────────────────────────────────────
#  PER-USER WHATSAPP CLIENT
# ─────────────────────────────────────────────────────────────
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
        print(f"[WA] ✅ connected: {chat_id}")
        try:
            bot.send_message(
                chat_id,
                "✅ *WhatsApp সংযুক্ত হয়েছে!*\n\nএখন নম্বর চেক করা যাবে।",
                reply_markup=_main_kb(chat_id),
            )
        except: pass

    @c.event(DisconnectedEv)
    def _on_disc(client, event):
        wa_statuses[chat_id] = "disconnected"
        print(f"[WA] ⚠️ disconnected: {chat_id}")
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

# ─────────────────────────────────────────────────────────────
#  PAIR PHONE
# ─────────────────────────────────────────────────────────────
def connect_with_code(chat_id: int, phone: str):
    if get_wa_status(chat_id) == "connected":
        bot.send_message(chat_id, "✅ *WhatsApp ইতিমধ্যে সংযুক্ত!*",
                         reply_markup=_main_kb(chat_id))
        return
    if get_wa_status(chat_id) == "connecting":
        bot.send_message(chat_id, "⏳ কোড তৈরি হচ্ছে, একটু অপেক্ষা করুন...")
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
                f"🔑 *WhatsApp Pairing Code:*\n\n`{code}`\n\n"
                "WhatsApp এ যান:\n"
                "⚙️ *Settings → Linked Devices → Link with Phone Number*\n\n"
                "এই ৮-digit কোড দিন।\n"
                "⏳ দেওয়ার পর স্বয়ংক্রিয়ভাবে সংযুক্ত হবে।",
                parse_mode="Markdown",
            )
        except Exception as e:
            wa_statuses[chat_id] = "disconnected"
            wa_clients.pop(chat_id, None)
            bot.send_message(
                chat_id,
                f"❌ সংযোগ ব্যর্থ:\n`{e}`\n\nআবার *❌ WP Checker* চাপুন।",
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
    bot.send_message(chat_id, "✅ WhatsApp সংযোগ বিচ্ছিন্ন হয়েছে।",
                     reply_markup=_main_kb(chat_id))

# ─────────────────────────────────────────────────────────────
#  WA BULK CHECK
# ─────────────────────────────────────────────────────────────
def _wa_bulk(chat_id, numbers):
    """numbers = list of dicts with 'full' and 'plain' keys"""
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

# ─────────────────────────────────────────────────────────────
#  KEYBOARDS
# ─────────────────────────────────────────────────────────────
def _main_kb(chat_id=None):
    st = get_wa_status(chat_id) if chat_id else "disconnected"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(types.KeyboardButton("🔴 P1 Console"),
           types.KeyboardButton("🔵 P2 Console"))
    kb.add(types.KeyboardButton("📲 OLD নাম্বার"))
    kb.add(types.KeyboardButton("🔍 নাম্বার চেকার"))
    if st == "connected":
        kb.row(types.KeyboardButton("✅ WP Checker"),
               types.KeyboardButton("🔌 WP Disconnect"))
    else:
        kb.add(types.KeyboardButton("❌ WP Checker"))
    return kb

def _console_kb(panel: str):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "🔄 Refresh", callback_data=f"cr|{panel}"))
    return kb

def _old_number_kb(numbers: list, range_id: str):
    """OLD নাম্বার কার্ডের keyboard — copy button + refresh + close"""
    kb = types.InlineKeyboardMarkup(row_width=1)
    for n in numbers:
        kb.add(types.InlineKeyboardButton(
            f"🔴  {n['full']}",
            copy_text=types.CopyTextButton(text=n["full"])))
    kb.row(
        types.InlineKeyboardButton(
            "🔄 নতুন খুঁজুন", callback_data=f"old|{range_id}"),
        types.InlineKeyboardButton("❌ বন্ধ", callback_data="cb"),
    )
    return kb

# ─────────────────────────────────────────────────────────────
#  CONSOLE
# ─────────────────────────────────────────────────────────────
def _fmt_p1(hits):
    groups = {}
    for h in hits:
        sid = str(h.get("sid", "")).lower()
        if sid in DEFAULT_SERVICES:
            groups.setdefault(sid, []).append(h)
    if not groups: return "⚠️ কোনো লাইভ ডেটা নেই।"
    lines = []
    for sid in ("whatsapp", "facebook", "telegram"):
        if sid not in groups: continue
        lines.append(f"\n━━━━━━━━━━━━━━━━━\n"
                     f"{SVC_ICON.get(sid,'📲')} *{sid.capitalize()}*")
        for h in groups[sid][:10]:
            lines.append(f"`{h.get('range','')}` — "
                         f"_{time_ago(h.get('time', time.time()*1000))}_")
    lines.append(f"\n━━━━━━━━━━━━━━━━━\n🔄 _{time.strftime('%H:%M:%S')}_")
    return "\n".join(lines)

def _fmt_p2(services):
    order = {"whatsapp":0,"facebook":1,"telegram":2}
    filt  = sorted(
        [s for s in services if str(s.get("sid","")).lower() in DEFAULT_SERVICES],
        key=lambda s: order.get(str(s.get("sid","")).lower(), 9))
    if not filt: return "⚠️ কোনো লাইভ ডেটা নেই।"
    lines = []
    for svc in filt:
        sid = str(svc.get("sid","")).lower()
        ago = time_ago(svc.get("last_at", time.time()*1000))
        lines.append(f"\n━━━━━━━━━━━━━━━━━\n"
                     f"{SVC_ICON.get(sid,'📲')} *{sid.capitalize()}* — _{ago}_")
        for r in svc.get("ranges",[])[:8]:
            lines.append(f"  `{r}`")
    lines.append(f"\n━━━━━━━━━━━━━━━━━\n🔄 _{time.strftime('%H:%M:%S')}_")
    return "\n".join(lines)

def _send_console(chat_id, panel, edit_id=None):
    if panel == "p1":
        resp = p1_get("/console")
        hits = resp.get("data", {}).get("hits", [])
        text = "🔴 *P1 — WealthoraPrime*\n" + _fmt_p1(hits)
    else:
        resp = p2_post("/liveaccess")
        svcs = resp.get("services", [])
        text = "🔵 *P2 — FastXOTPs*\n" + _fmt_p2(svcs)
    kb = _console_kb(panel)
    if edit_id:
        try:
            bot.edit_message_text(text, chat_id, edit_id,
                                  reply_markup=kb, parse_mode="Markdown")
            return
        except: pass
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────
#  FETCH ONE NUMBER  (P1 only for OLD নাম্বার)
# ─────────────────────────────────────────────────────────────
def _fetch_one_p1(range_id: str):
    resp    = p1_post("/getnum", {"range": range_id})
    code    = resp.get("meta", {}).get("code")
    data    = resp.get("data", {}) or {}
    full    = str(data.get("full_number", ""))
    plain   = str(data.get("no_plus_number") or full.lstrip("+"))
    country = str(data.get("country") or "")
    service = str(data.get("service") or data.get("sid") or "")
    if full and code == 200:
        return dict(full=full, plain=plain, country=country, service=service)
    return None

# ─────────────────────────────────────────────────────────────
#  OLD নাম্বার — P1 থেকে 30টা fetch করে WA-active 5টা দেয়
# ─────────────────────────────────────────────────────────────
def get_old_numbers(chat_id: int, range_id: str, edit_msg_id=None):
    cid = chat_id
    loading = f"⏳ `{range_id}` [P1] থেকে OLD নাম্বার খোঁজা হচ্ছে...\n_WA চেক করা হচ্ছে, একটু অপেক্ষা করুন_"

    if edit_msg_id:
        edit_safe(cid, edit_msg_id, loading)
        st_id = edit_msg_id
    else:
        st    = bot.send_message(cid, loading, parse_mode="Markdown")
        st_id = st.message_id

    # ── ৩০টা নম্বর parallel fetch ─────────────────────────────
    fetched = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(_fetch_one_p1, range_id) for _ in range(30)]
        for f in as_completed(futs):
            info = f.result()
            if info:
                fetched.append(info)

    if not fetched:
        err = (f"❌ `{range_id}` [P1] থেকে কোনো নাম্বার পাওয়া যায়নি।\n"
               "_রেঞ্জ খালি বা API error।_")
        if edit_msg_id:
            edit_safe(cid, st_id, err)
        else:
            safe_delete(cid, st_id)
            bot.send_message(cid, err, parse_mode="Markdown")
        return

    # ── WA bulk check ─────────────────────────────────────────
    wa_res = _wa_bulk(cid, fetched)

    # WA আছে এমন নম্বর filter করে প্রথম ৫টা নাও
    found = [n for n in fetched if wa_res.get(n["full"]) is True][:5]

    if not found:
        msg = (f"⚠️ `{range_id}` থেকে {len(fetched)}টি নাম্বার check করা হয়েছে\n"
               "_কোনো WhatsApp নাম্বার পাওয়া যায়নি।_\n\n"
               "🔄 আবার চেষ্টা করুন।")
        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton(
                "🔄 আবার চেষ্টা", callback_data=f"old|{range_id}"),
            types.InlineKeyboardButton("❌ বন্ধ", callback_data="cb"),
        )
        if edit_msg_id:
            try:
                bot.edit_message_text(msg, cid, st_id,
                                      reply_markup=kb, parse_mode="Markdown")
            except:
                bot.send_message(cid, msg, reply_markup=kb, parse_mode="Markdown")
        else:
            safe_delete(cid, st_id)
            bot.send_message(cid, msg, reply_markup=kb, parse_mode="Markdown")
        return

    header = (f"🔴 *{len(found)}টি WhatsApp নাম্বার পাওয়া গেছে*\n"
              f"⏳ _OTP আসলে inbox-এ দেখাবে_")
    kb = _old_number_kb(found, range_id)

    if edit_msg_id:
        try:
            bot.edit_message_text(header, cid, st_id,
                                  reply_markup=kb, parse_mode="Markdown")
        except:
            bot.send_message(cid, header, reply_markup=kb, parse_mode="Markdown")
    else:
        safe_delete(cid, st_id)
        bot.send_message(cid, header, reply_markup=kb, parse_mode="Markdown")

    # Global P1 registry-তে register করো OTP পেতে
    _register("p1", found, range_id, cid, dur=600)

# ─────────────────────────────────────────────────────────────
#  BUTTON LABELS
# ─────────────────────────────────────────────────────────────
_ALL_BTN = {
    "🔴 P1 Console","🔵 P2 Console",
    "📲 OLD নাম্বার",
    "🔍 নাম্বার চেকার",
    "✅ WP Checker","❌ WP Checker",
    "🔌 WP Disconnect",
}

# ─────────────────────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    _save_user(msg)
    bot.send_message(
        msg.chat.id,
        "🤖 *OTP Panel Bot v6.0*\n\n"
        "🔴 *P1 Console* — WealthoraPrime লাইভ ট্র্যাফিক\n"
        "🔵 *P2 Console* — FastXOTPs লাইভ ট্র্যাফিক\n"
        "📲 *OLD নাম্বার* — P1 থেকে শুধু WA আছে এমন ৫টি নাম্বার\n"
        "🔍 *নাম্বার চেকার* — WhatsApp আছে কিনা চেক করুন\n"
        "❌ *WP Checker* — WhatsApp লগইন (Phone code)\n"
        "🔌 *WP Disconnect* — সংযোগ বন্ধ\n\n"
        "⚡ OTP আসামাত্র ≤১ সেকেন্ডে পাবেন",
        reply_markup=_main_kb(msg.chat.id),
    )

# ─────────────────────────────────────────────────────────────
#  /stats  (admin only)
# ─────────────────────────────────────────────────────────────
@bot.message_handler(commands=["stats"])
def cmd_stats(msg):
    if msg.chat.id != ADMIN_ID: return
    if not otp_stats:
        bot.send_message(msg.chat.id, "📊 এখনো কোনো OTP রিসিভ হয়নি।")
        return
    text  = "📊 *OTP Statistics*\n━━━━━━━━━━━━━━━━━\n"
    total = 0
    for uid, cnt in sorted(otp_stats.items(), key=lambda x: -x[1]):
        lbl  = _get_label(uid)
        link = f"[{lbl}](tg://user?id={uid})"
        text += f"👤 {link} — *{cnt}* OTP\n"
        total += cnt
    text += f"━━━━━━━━━━━━━━━━━\n📋 মোট: *{total}* OTP"
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
    total_otp  = sum(otp_stats.values()) if otp_stats else 0
    text = (
        "🖥 *Bot Status v6.0*\n━━━━━━━━━━━━━━━━━\n"
        f"⏱ Uptime: `{uptime_str()}`\n"
        f"👥 WA Connected: `{len(connected)}`\n"
        f"🔄 WA Connecting: `{len(connecting)}`\n"
        f"🔵 P2 watching: `{p2_active}` নম্বর\n"
        f"🔴 P1 watching: `{p1_active}` নম্বর\n"
        f"📨 Total OTPs: `{total_otp}`\n"
        f"━━━━━━━━━━━━━━━━━\n"
    )
    if connected:
        text += "*Connected users:*\n"
        for cid in connected:
            cnt   = otp_stats.get(cid, 0)
            label = _get_label(cid)
            text += f"  • `{cid}` ({label}) — {cnt} OTP\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown",
                     disable_web_page_preview=True)

# ─────────────────────────────────────────────────────────────
#  CONSOLE BUTTONS
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🔴 P1 Console")
def btn_p1_console(msg):
    _save_user(msg)
    threading.Thread(target=_send_console,
                     args=(msg.chat.id,"p1"), daemon=True).start()

@bot.message_handler(func=lambda m: m.text == "🔵 P2 Console")
def btn_p2_console(msg):
    _save_user(msg)
    threading.Thread(target=_send_console,
                     args=(msg.chat.id,"p2"), daemon=True).start()

# ─────────────────────────────────────────────────────────────
#  📲 OLD নাম্বার BUTTON
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "📲 OLD নাম্বার")
def btn_old(msg):
    _save_user(msg)
    cid = msg.chat.id
    if get_wa_status(cid) != "connected":
        bot.send_message(
            cid,
            "❌ *OLD নাম্বার পেতে WhatsApp সংযুক্ত থাকতে হবে।*\n\n"
            "প্রথমে *❌ WP Checker* দিয়ে লগইন করুন।",
            reply_markup=_main_kb(cid),
            parse_mode="Markdown",
        )
        return
    with state_lock:
        user_state[cid] = {"mode": "wait_range_old"}
    bot.send_message(
        cid,
        "📲 *OLD নাম্বার* — রেঞ্জ লিখুন\n"
        "_(যেমন: `22501XXX`)_\n\n"
        "_P1 থেকে ৩০টা করে WA চেক করে ৫টা পুরনো নাম্বার দেবে_",
        parse_mode="Markdown",
    )

# ─────────────────────────────────────────────────────────────
#  ❌ / ✅ WP CHECKER BUTTON
# ─────────────────────────────────────────────────────────────
@bot.message_handler(
    func=lambda m: m.text in ("✅ WP Checker", "❌ WP Checker"))
def btn_wa(msg):
    _save_user(msg)
    chat_id = msg.chat.id
    status  = get_wa_status(chat_id)
    if status == "connected":
        bot.send_message(chat_id, "✅ *WhatsApp ইতিমধ্যে সংযুক্ত!*",
                         reply_markup=_main_kb(chat_id))
        return
    if status == "connecting":
        bot.send_message(chat_id, "⏳ *কোড তৈরি হচ্ছে...* একটু অপেক্ষা করুন।",
                         parse_mode="Markdown")
        return
    with state_lock:
        user_state[chat_id] = {"mode": "wait_phone"}
    bot.send_message(
        chat_id,
        "📱 *WhatsApp নম্বর দিন* (দেশের কোড সহ)\n\nযেমন: `+8801712345678`",
        parse_mode="Markdown",
    )

# ─────────────────────────────────────────────────────────────
#  🔌 DISCONNECT BUTTON
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🔌 WP Disconnect")
def btn_disconnect(msg):
    _save_user(msg)
    threading.Thread(target=disconnect_wa,
                     args=(msg.chat.id,), daemon=True).start()

# ─────────────────────────────────────────────────────────────
#  🔍 NUMBER CHECKER
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🔍 নাম্বার চেকার")
def btn_checker(msg):
    _save_user(msg)
    chat_id = msg.chat.id
    if get_wa_status(chat_id) != "connected":
        bot.send_message(
            chat_id,
            "❌ *WhatsApp সংযুক্ত নেই।*\n\nপ্রথমে *❌ WP Checker* চাপুন।",
            reply_markup=_main_kb(chat_id),
        )
        return
    with state_lock:
        user_state[chat_id] = {"mode": "wait_check"}
    bot.send_message(
        chat_id,
        "🔍 *নাম্বার চেকার*\n\n📞 নাম্বার পাঠান (প্রতি লাইনে একটি, সর্বোচ্চ ২০টি):",
        parse_mode="Markdown",
    )

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

    # ── wait_phone ──────────────────────────────────────────────
    if mode == "wait_phone":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        phone = text.replace(" ", "").replace("-", "")
        if not phone.startswith("+"):
            phone = "+" + phone
        if not re.match(r"^\+\d{7,15}$", phone):
            bot.send_message(
                chat_id,
                "❌ *নম্বর সঠিক নয়।*\n\nদেশের কোড সহ দিন।\nযেমন: `+8801712345678`",
                parse_mode="Markdown",
            )
            return
        bot.send_message(chat_id,
                         f"⏳ `{phone}` এর pairing code তৈরি হচ্ছে...",
                         parse_mode="Markdown")
        threading.Thread(
            target=connect_with_code, args=(chat_id, phone), daemon=True
        ).start()

    # ── wait_range_old ──────────────────────────────────────────
    elif mode == "wait_range_old":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        threading.Thread(
            target=get_old_numbers, args=(chat_id, text), daemon=True
        ).start()

    # ── wait_check ──────────────────────────────────────────────
    elif mode == "wait_check":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        lines = [l.strip() for l in text.splitlines() if l.strip()][:20]
        if not lines:
            bot.send_message(chat_id, "❌ কোনো নাম্বার পাওয়া যায়নি।")
            return
        loading = bot.send_message(
            chat_id, f"⏳ {len(lines)}টি নাম্বার চেক হচ্ছে...", parse_mode="Markdown"
        )
        def _do_check():
            results = _wa_check(chat_id, lines)
            wa, no_wa, unk = [], [], []
            for n, is_on in results.items():
                if is_on is True:    wa.append(f"🔴 `{n}` — WA আছে")
                elif is_on is False: no_wa.append(f"🟢 `{n}` — WA নেই")
                else:                unk.append(f"⬜ `{n}` — চেক হয়নি")
            safe_delete(chat_id, loading.message_id)
            bot.send_message(
                chat_id,
                "🔍 *নাম্বার চেকার ফলাফল:*\n\n" + "\n".join(wa + no_wa + unk),
                parse_mode="Markdown",
            )
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
        bot.answer_callback_query(call.id, "🔄 Refreshing...")
        threading.Thread(
            target=_send_console, args=(chat_id, panel, msg_id), daemon=True
        ).start()
        return

    if data.startswith("old|"):
        range_id = data.split("|", 1)[1]
        bot.answer_callback_query(call.id, "🔴 OLD নাম্বার খোঁজা হচ্ছে...")
        threading.Thread(
            target=get_old_numbers,
            args=(chat_id, range_id, msg_id),
            daemon=True,
        ).start()
        return

    bot.answer_callback_query(call.id)

# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🤖 OTP Panel Bot v6.0 চালু হচ্ছে... (admin={ADMIN_ID})")

    threading.Thread(target=_global_p2_poller, daemon=True,
                     name="P2-GlobalPoller").start()
    threading.Thread(target=_global_p1_poller, daemon=True,
                     name="P1-GlobalPoller").start()

    bot.infinity_polling(timeout=30, long_polling_timeout=20)
