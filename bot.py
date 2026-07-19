"""
OTP Panel Bot  v4.1  — FIXED
=========================================================
P1  : WealthoraPrime
P2  : FastXOTPs
WA  : neonize – PairPhone code (no QR), per-user session
Admin : ADMIN_ID → /stats  /status
=========================================================
✅  pair_phone সঠিকভাবে call করা হচ্ছে
✅  Username সহ OTP stats
✅  P2 OTP watcher সব method দিয়ে try করে
✅  P1 OTP watcher unchanged (working)
✅  50-60 user support
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
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────
#  HTTP SESSION  (connection pool – 50-60 concurrent users)
# ─────────────────────────────────────────────────────────────
def _make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.3,
                  status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(
        pool_connections=30,
        pool_maxsize=60,
        max_retries=retry,
    )
    s.mount("http://",  adapter)
    s.mount("https://", adapter)
    return s

_session = _make_session()

def _get(url, params=None, headers=None, timeout=10):
    try:
        return _session.get(url, params=params, headers=headers,
                            timeout=timeout).json()
    except Exception as e:
        return {"error": str(e)}

def _post(url, data=None, headers=None, timeout=10):
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

# ── username cache: chat_id → "@username" or "First Last" ───
user_names  = {}   # chat_id → str
names_lock  = threading.Lock()

# per-user active number batches:  chat_id → set of plain numbers being watched
active_watches: dict = {}
watch_lock = threading.Lock()

user_state = {}
state_lock = threading.Lock()

DEFAULT_SERVICES = {"whatsapp", "facebook", "telegram"}
SVC_ICON = {"whatsapp": "💬", "facebook": "📘", "telegram": "✈️"}

# ─────────────────────────────────────────────────────────────
#  USERNAME HELPER
# ─────────────────────────────────────────────────────────────
def _save_user(msg_or_user):
    """msg অথবা User object থেকে username/name cache করে।"""
    try:
        u = getattr(msg_or_user, "from_user", msg_or_user) or msg_or_user
        if u is None:
            return
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

# ─────────────────────────────────────────────────────────────
#  UTILITY
# ─────────────────────────────────────────────────────────────
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
#  PAIR PHONE  — neonize সব version support
# ─────────────────────────────────────────────────────────────
def _do_pair_phone(client: NewClient, phone: str) -> str:
    """
    neonize বিভিন্ন version-এ method name আলাদা।
    সব সম্ভাব্য নাম try করে code return করে।
    """
    # method name candidates (neonize version অনুযায়ী)
    candidates = [
        "pair_phone",       # v1.x snake_case
        "PairPhone",        # CamelCase variant
        "pairPhone",        # camelCase variant
        "request_pairing_code",  # older alias
    ]
    for name in candidates:
        method = getattr(client, name, None)
        if callable(method):
            try:
                result = method(phone)
                if result:
                    return str(result)
            except Exception as e:
                print(f"[PAIR] {name} failed: {e}")
                continue

    # শেষ চেষ্টা: সব attribute দেখি
    attrs = [a for a in dir(client)
             if "pair" in a.lower() or "phone" in a.lower() or "code" in a.lower()]
    raise AttributeError(
        f"pair_phone method পাওয়া যায়নি। Available: {attrs}"
    )


def connect_with_code(chat_id: int, phone: str):
    """
    PairPhone:
      1) connect() → background thread (WebSocket)
      2) 8s wait → socket ready
      3) pair_phone() → 8-digit code  (QR সম্পূর্ণ বাদ)
    """
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

    def _do():
        try:
            # WebSocket thread শুরু
            t = threading.Thread(target=client.connect, daemon=True)
            t.start()

            # socket establish হওয়ার জন্য অপেক্ষা
            # (3s প্রায়ই কম হয়, 8s দিলে reliable)
            time.sleep(8)

            code = _do_pair_phone(client, phone)
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
                f"❌ সংযোগ ব্যর্থ:\n`{e}`\n\nআবার *❌ WA Checker* চাপুন।",
                reply_markup=_main_kb(chat_id),
                parse_mode="Markdown",
            )

    threading.Thread(target=_do, daemon=True).start()

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
#  KEYBOARDS
# ─────────────────────────────────────────────────────────────
def _main_kb(chat_id=None):
    st = get_wa_status(chat_id) if chat_id else "disconnected"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(types.KeyboardButton("🔴 P1 Console"),
           types.KeyboardButton("🔵 P2 Console"))
    kb.row(types.KeyboardButton("📞 P1 নাম্বার"),
           types.KeyboardButton("📞 P2 নাম্বার"))
    kb.add(types.KeyboardButton("🔍 নাম্বার চেকার"))
    if st == "connected":
        kb.row(types.KeyboardButton("✅ WA Checker"),
               types.KeyboardButton("🔌 WA ডিসকানেক্ট"))
    else:
        kb.add(types.KeyboardButton("❌ WA Checker"))
    return kb

def _console_kb(panel: str):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "🔄 Refresh", callback_data=f"cr|{panel}"))
    return kb

def _number_kb(numbers, wa_res, panel, range_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for n in numbers:
        v    = wa_res.get(n["full"])
        icon = "🔴" if v is True else ("🟢" if v is False else "⬜")
        kb.add(types.InlineKeyboardButton(
            f"{icon}  {n['full']}",
            copy_text=types.CopyTextButton(text=n["full"])))
    kb.row(
        types.InlineKeyboardButton(
            "🔄 নাম্বার চেঞ্জ", callback_data=f"nb|{panel}|{range_id}"),
        types.InlineKeyboardButton(
            "❌ বন্ধ", callback_data="cb"),
    )
    return kb

def _card_header(range_id, panel, count, failed=0, service=""):
    label    = "P1" if panel == "p1" else "P2"
    svc_name = service or _resolve_service(range_id=range_id)
    icon     = _svc_icon(svc_name)
    h = f"{icon} *{svc_name.upper()}* [{label}]  —  {count}টি নাম্বার"
    if failed: h += f"  _(⚠️ {failed} মিস)_"
    h += "\n⏳ _OTP আসলে আপনার inbox-এ দেখাবে_"
    return h

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
#  OTP NOTIFICATION  → সঠিক user-এর inbox-এ যাবে
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
#  FETCH NUMBERS  (super-fast: 10 workers + shared session)
# ─────────────────────────────────────────────────────────────
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

    # p2 — আরো বেশি field parse করা হচ্ছে
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

    print(f"[P2-FETCH] full={full} rid={rid} otp_now={otp_now} "
          f"otp_msg={otp_msg[:40] if otp_msg else ''}")

    if full:
        return dict(full=full, plain=plain, country=country,
                    service=service, rid=rid,
                    otp_now=otp_now, otp_msg=otp_msg)
    return None

def get_6_numbers(chat_id, panel, range_id, edit_msg_id=None):
    label   = "P1" if panel == "p1" else "P2"
    loading = f"⏳ `{range_id}` [{label}] থেকে নাম্বার আনা হচ্ছে..."

    if edit_msg_id:
        edit_safe(chat_id, edit_msg_id, loading)
        st_id = edit_msg_id
    else:
        st    = bot.send_message(chat_id, loading, parse_mode="Markdown")
        st_id = st.message_id

    results, failed = [], 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(_fetch_one, panel, range_id) for _ in range(6)]
        for f in as_completed(futs):
            info = f.result()
            if info: results.append(info)
            else:    failed += 1

    if not results:
        err = (f"❌ `{range_id}` [{label}] থেকে নাম্বার পাওয়া যায়নি।\n"
               "_রেঞ্জ খালি বা API error।_")
        if edit_msg_id: edit_safe(chat_id, st_id, err)
        else:
            safe_delete(chat_id, st_id)
            bot.send_message(chat_id, err, parse_mode="Markdown")
        return

    batch_svc  = results[0].get("service","") if results else ""
    wa_res     = _wa_bulk(chat_id, results)
    header     = _card_header(range_id, panel, len(results),
                               failed, service=batch_svc)
    kb         = _number_kb(results, wa_res, panel, range_id)

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

    num_meta = {
        n["plain"].lstrip("+"): dict(
            full=n["full"],
            country=n.get("country",""),
            service=n.get("service",""),
            range_id=range_id,
        )
        for n in results
    }

    plains = set(num_meta.keys())
    with watch_lock:
        existing = active_watches.get(chat_id, set())
        active_watches[chat_id] = existing | plains

    def _cleanup():
        time.sleep(605)
        with watch_lock:
            cur = active_watches.get(chat_id, set())
            active_watches[chat_id] = cur - plains
    threading.Thread(target=_cleanup, daemon=True).start()

    # P1 OTP watcher (সব panel-এর জন্য চলে)
    threading.Thread(
        target=_p1_otp_watcher,
        args=(chat_id, plains, 600, num_meta),
        daemon=True).start()

    # P2 extra watcher
    if panel == "p2":
        for n in results:
            if n.get("otp_now") and n.get("otp_msg"):
                _notify_otp(chat_id,
                            full_num=n["full"],
                            otp_code=extract_otp(n["otp_msg"]),
                            country=n.get("country",""),
                            service=n.get("service",""),
                            range_id=range_id)
        pending = [n for n in results
                   if n.get("rid") and
                   not (n.get("otp_now") and n.get("otp_msg"))]

        # rid ছাড়া numbers-ও watch করা দরকার (P1 fallback)
        no_rid = [n for n in results
                  if not n.get("rid") and
                  not (n.get("otp_now") and n.get("otp_msg"))]

        print(f"[P2] pending={len(pending)} no_rid={len(no_rid)}")

        if pending or no_rid:
            threading.Thread(
                target=_p2_otp_watcher,
                args=(chat_id, pending, range_id, 600, num_meta),
                daemon=True).start()

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
#  P1 OTP WATCHER
# ─────────────────────────────────────────────────────────────
def _p1_otps():
    try:
        resp = p1_get("/success-otp")
        otps = (resp.get("data") or {}).get("otps", [])
        return otps if isinstance(otps, list) else []
    except: return []

def _num_matches(api_num: str, watch: set) -> bool:
    a = api_num.strip().lstrip("+")
    for w in watch:
        wc = w.strip().lstrip("+")
        if a == wc: return True
        sl = min(len(a), len(wc), 9)
        if sl >= 7 and a[-sl:] == wc[-sl:]: return True
    return False

def _p1_otp_watcher(chat_id, watch: set, duration: int, num_meta=None):
    seen = {str(o.get("otp_id","")) for o in _p1_otps() if o.get("otp_id")}
    deadline = time.time() + duration
    while time.time() < deadline:
        time.sleep(2)
        for o in _p1_otps():
            oid = str(o.get("otp_id") or "")
            if not oid or oid in seen: continue
            api_num = str(o.get("number","")).strip()
            if not _num_matches(api_num, watch): continue
            seen.add(oid)
            api_sid = str(o.get("sid") or o.get("service") or "")
            meta = {}
            if num_meta:
                for pw, m in num_meta.items():
                    if _num_matches(api_num, {pw}):
                        meta = m; break
            _notify_otp(
                chat_id,
                full_num=meta.get("full") or f"+{api_num}",
                otp_code=extract_otp(str(o.get("message",""))),
                country=meta.get("country",""),
                service=meta.get("service") or api_sid,
                range_id=meta.get("range_id",""),
            )

# ─────────────────────────────────────────────────────────────
#  P2 OTP WATCHER  — 3 method + P1 fallback (FIXED)
# ─────────────────────────────────────────────────────────────
def _p2_otp_watcher(chat_id, numbers, range_id,
                    duration=600, num_meta=None):
    """
    Method 1 → POST /api/getotp   {rid}
    Method 2 → GET  /api/getnum/{rid}
    Method 3 → POST /api/checkotp {rid}  (extra endpoint try)
    Method 4 → P1 success-otp fallback
    """
    pending = {n["rid"]: n for n in numbers if n.get("rid")}
    # rid নেই এমন numbers-এর জন্য plain number দিয়ে P1 fallback watch
    plains_no_rid = {n["plain"].lstrip("+"): n
                     for n in numbers if not n.get("rid")}
    seen_p1: set = set()
    deadline = time.time() + duration
    print(f"[P2-OTP] start chat={chat_id} rid_pending={len(pending)} "
          f"no_rid={len(plains_no_rid)}")

    while time.time() < deadline and (pending or plains_no_rid):
        time.sleep(3)

        # ── Method 1: POST /api/getotp ──────────────────────────
        for rid in list(pending.keys()):
            try:
                r = _session.post(
                    f"{P2_BASE}/api/getotp",
                    json={"rid": rid}, headers=P2_HDRS, timeout=10)
                if r.status_code != 200:
                    continue
                resp = r.json()
                d    = resp.get("data", resp) or {}
                if not isinstance(d, dict): d = {}
                msg  = (d.get("otp_message") or d.get("otp") or d.get("message")
                        or resp.get("otp_message") or resp.get("otp")
                        or resp.get("message") or "")
                if not msg:
                    continue
                code = extract_otp(str(msg))
                if code == "???":
                    continue
                n = pending.pop(rid, None)
                if n:
                    print(f"[P2-M1] ✅ {n['full']} otp={code}")
                    _notify_otp(chat_id, full_num=n["full"], otp_code=code,
                                country=n.get("country",""),
                                service=n.get("service",""),
                                range_id=range_id)
            except Exception as e:
                print(f"[P2-M1] rid={rid} err={e}")

        if not pending and not plains_no_rid:
            break

        # ── Method 2: GET /api/getnum/{rid} ────────────────────
        for rid in list(pending.keys()):
            try:
                r = _session.get(
                    f"{P2_BASE}/api/getnum/{rid}",
                    headers={"X-API-Key": P2_KEY}, timeout=10)
                if r.status_code != 200:
                    continue
                resp = r.json()
                d    = resp.get("data", resp) or {}
                if not isinstance(d, dict): d = {}
                msg      = (d.get("otp_message") or d.get("otp") or d.get("message")
                            or resp.get("otp_message") or resp.get("otp")
                            or resp.get("message") or "")
                otp_now  = bool(d.get("otp_now") or resp.get("otp_now"))
                if not (msg or otp_now):
                    continue
                code = extract_otp(str(msg)) if msg else "???"
                if code == "???":
                    continue
                n = pending.pop(rid, None)
                if n:
                    print(f"[P2-M2] ✅ {n['full']} otp={code}")
                    _notify_otp(chat_id, full_num=n["full"], otp_code=code,
                                country=n.get("country",""),
                                service=n.get("service",""),
                                range_id=range_id)
            except Exception as e:
                print(f"[P2-M2] rid={rid} err={e}")

        if not pending and not plains_no_rid:
            break

        # ── Method 3: POST /api/checkotp (extra endpoint) ──────
        for rid in list(pending.keys()):
            try:
                r = _session.post(
                    f"{P2_BASE}/api/checkotp",
                    json={"rid": rid}, headers=P2_HDRS, timeout=10)
                if r.status_code != 200:
                    continue
                resp = r.json()
                d    = resp.get("data", resp) or {}
                if not isinstance(d, dict): d = {}
                msg  = (d.get("otp_message") or d.get("otp") or d.get("message")
                        or resp.get("otp_message") or resp.get("otp")
                        or resp.get("message") or "")
                if not msg:
                    continue
                code = extract_otp(str(msg))
                if code == "???":
                    continue
                n = pending.pop(rid, None)
                if n:
                    print(f"[P2-M3] ✅ {n['full']} otp={code}")
                    _notify_otp(chat_id, full_num=n["full"], otp_code=code,
                                country=n.get("country",""),
                                service=n.get("service",""),
                                range_id=range_id)
            except Exception as e:
                print(f"[P2-M3] rid={rid} err={e}")

        # ── Method 4: P1 success-otp fallback ──────────────────
        all_plains = (
            {n["plain"].lstrip("+") for n in pending.values()}
            | set(plains_no_rid.keys())
        )
        if all_plains:
            try:
                for o in _p1_otps():
                    oid = str(o.get("otp_id") or "")
                    if not oid or oid in seen_p1:
                        continue
                    api_num = str(o.get("number","")).strip()
                    if not _num_matches(api_num, all_plains):
                        continue
                    seen_p1.add(oid)
                    code    = extract_otp(str(o.get("message","")))
                    api_sid = str(o.get("sid") or o.get("service") or "")

                    # rid pending থেকে match করো
                    for rid, n in list(pending.items()):
                        if _num_matches(api_num, {n["plain"].lstrip("+")}):
                            pending.pop(rid)
                            print(f"[P2-M4-rid] ✅ {n['full']} otp={code}")
                            _notify_otp(chat_id, full_num=n["full"],
                                        otp_code=code,
                                        country=n.get("country",""),
                                        service=n.get("service") or api_sid,
                                        range_id=range_id)
                            break
                    # no-rid থেকে match করো
                    for pw, n in list(plains_no_rid.items()):
                        if _num_matches(api_num, {pw}):
                            plains_no_rid.pop(pw, None)
                            print(f"[P2-M4-norid] ✅ {n['full']} otp={code}")
                            _notify_otp(chat_id, full_num=n["full"],
                                        otp_code=code,
                                        country=n.get("country",""),
                                        service=n.get("service") or api_sid,
                                        range_id=range_id)
                            break
            except Exception as e:
                print(f"[P2-M4] {e}")

    print(f"[P2-OTP] done chat={chat_id} "
          f"left_rid={len(pending)} left_norid={len(plains_no_rid)}")

# ─────────────────────────────────────────────────────────────
#  BUTTON LABELS
# ─────────────────────────────────────────────────────────────
_ALL_BTN = {
    "🔴 P1 Console","🔵 P2 Console",
    "📞 P1 নাম্বার","📞 P2 নাম্বার",
    "🔍 নাম্বার চেকার",
    "✅ WA Checker","❌ WA Checker",
    "🔌 WA ডিসকানেক্ট",
}

# ─────────────────────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    _save_user(msg)
    bot.send_message(
        msg.chat.id,
        "🤖 *OTP Panel Bot*\n\n"
        "🔴 P1 / 🔵 P2 Console — লাইভ ট্র্যাফিক\n"
        "📞 P1 / 📞 P2 নাম্বার — রেঞ্জ → ৬টি নাম্বার\n"
        "🔍 নাম্বার চেকার — WhatsApp check\n"
        "❌ WA Checker — Phone code দিয়ে লগইন (QR নেই)\n"
        "🔌 WA ডিসকানেক্ট — সংযোগ বন্ধ",
        reply_markup=_main_kb(msg.chat.id),
    )

# ─────────────────────────────────────────────────────────────
#  /stats  (admin only) — username সহ
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
        label  = _get_label(uid)
        # username telegram link
        with names_lock:
            uname = user_names.get(uid, "")
        if uname.startswith("@"):
            link = f"[{uname}](tg://user?id={uid})"
        else:
            link = f"[{uname or uid}](tg://user?id={uid})"
        text  += f"👤 {link} — *{cnt}* OTP\n"
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
    connected    = [cid for cid, st in wa_statuses.items() if st == "connected"]
    connecting   = [cid for cid, st in wa_statuses.items() if st == "connecting"]
    disconnected = [cid for cid, st in wa_statuses.items() if st == "disconnected"]
    with watch_lock:
        watching = sum(len(v) for v in active_watches.values())
    total_otp = sum(otp_stats.values()) if otp_stats else 0

    text = (
        "🖥 *Bot Status*\n━━━━━━━━━━━━━━━━━\n"
        f"⏱ Uptime: `{uptime_str()}`\n"
        f"👥 WA Connected: `{len(connected)}`\n"
        f"🔄 WA Connecting: `{len(connecting)}`\n"
        f"❌ WA Disconnected: `{len(disconnected)}`\n"
        f"👁 Active number watches: `{watching}`\n"
        f"📨 Total OTPs delivered: `{total_otp}`\n"
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
#  NUMBER BUTTONS
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "📞 P1 নাম্বার")
def btn_p1_num(msg):
    _save_user(msg)
    with state_lock:
        user_state[msg.chat.id] = {"mode": "wait_range_p1"}
    bot.send_message(msg.chat.id,
                     "📝 *P1* রেঞ্জ লিখুন  (যেমন: `22501XXX`)",
                     parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📞 P2 নাম্বার")
def btn_p2_num(msg):
    _save_user(msg)
    with state_lock:
        user_state[msg.chat.id] = {"mode": "wait_range_p2"}
    bot.send_message(msg.chat.id,
                     "📝 *P2* রেঞ্জ লিখুন  (যেমন: `26134XXX`)",
                     parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────
#  ❌ / ✅ WA CHECKER BUTTON
# ─────────────────────────────────────────────────────────────
@bot.message_handler(
    func=lambda m: m.text in ("✅ WA Checker", "❌ WA Checker"))
def btn_wa(msg):
    _save_user(msg)
    chat_id = msg.chat.id
    status  = get_wa_status(chat_id)

    if status == "connected":
        bot.send_message(chat_id, "✅ *WhatsApp ইতিমধ্যে সংযুক্ত!*",
                         reply_markup=_main_kb(chat_id))
        return

    if status == "connecting":
        bot.send_message(chat_id,
                         "⏳ কোড তৈরি হচ্ছে, একটু অপেক্ষা করুন...")
        return

    with state_lock:
        user_state[chat_id] = {"mode": "wait_phone"}
    bot.send_message(
        chat_id,
        "📱 *WhatsApp নম্বর* দিন (দেশের কোড সহ)\n\n"
        "উদাহরণ: `+8801712345678`",
        parse_mode="Markdown",
    )

# ─────────────────────────────────────────────────────────────
#  🔌 DISCONNECT BUTTON
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🔌 WA ডিসকানেক্ট")
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
        bot.send_message(chat_id,
                         "❌ *WhatsApp সংযুক্ত নেই।*\n\n"
                         "প্রথমে *❌ WA Checker* চাপুন।",
                         reply_markup=_main_kb(chat_id))
        return
    with state_lock:
        user_state[chat_id] = {"mode": "wait_check_numbers"}
    bot.send_message(chat_id,
                     "🔍 *নাম্বার চেকার*\n\n"
                     "📞 নাম্বার পাঠান (প্রতি লাইনে একটি, সর্বোচ্চ ২০টি):",
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
        with state_lock: user_state[chat_id] = {"mode": "idle"}
        phone = text.replace(" ","").replace("-","")
        if not phone.startswith("+"): phone = "+" + phone
        if len(phone) < 8:
            bot.send_message(chat_id,
                             "❌ অবৈধ নম্বর।\nউদাহরণ: `+8801712345678`",
                             parse_mode="Markdown")
            return
        bot.send_message(chat_id, "⏳ কোড তৈরি হচ্ছে... (৮-১০ সেকেন্ড)")
        threading.Thread(target=connect_with_code,
                         args=(chat_id, phone), daemon=True).start()
        return

    if mode == "wait_range_p1":
        with state_lock: user_state[chat_id] = {"mode": "idle"}
        threading.Thread(target=get_6_numbers,
                         args=(chat_id,"p1",text), daemon=True).start()
        return

    if mode == "wait_range_p2":
        with state_lock: user_state[chat_id] = {"mode": "idle"}
        threading.Thread(target=get_6_numbers,
                         args=(chat_id,"p2",text), daemon=True).start()
        return

    if mode == "wait_check_numbers":
        with state_lock: user_state[chat_id] = {"mode": "idle"}
        _handle_wa_check(chat_id, text)
        return

    # auto-detect pasted numbers
    lines   = [l.strip() for l in text.split("\n") if l.strip()]
    numbers = [l for l in lines
               if l and l[0] in "+0123456789"
               and len(l.replace("+","").replace(" ","").replace("-","")) >= 7]
    if not numbers: return
    if get_wa_status(chat_id) != "connected":
        bot.send_message(chat_id,
                         "❌ WhatsApp সংযুক্ত নেই।\n*❌ WA Checker* চাপুন।",
                         reply_markup=_main_kb(chat_id))
        return
    _handle_wa_check(chat_id, text)


def _handle_wa_check(chat_id, text: str):
    lines   = [l.strip() for l in text.split("\n") if l.strip()]
    numbers = [l for l in lines
               if l and l[0] in "+0123456789"
               and len(l.replace("+","").replace(" ","").replace("-","")) >= 7]
    if not numbers:
        bot.send_message(chat_id, "⚠️ কোনো valid নাম্বার পাওয়া যায়নি।")
        return
    if len(numbers) > 20:
        bot.send_message(chat_id, "⚠️ সর্বোচ্চ ২০টি নাম্বার দিন।")
        return
    loading = bot.send_message(chat_id,
                                f"⏳ {len(numbers)}টি নাম্বার চেক হচ্ছে…")
    def _do():
        results = _wa_check(chat_id, numbers)
        has_wa  = sum(1 for v in results.values() if v is True)
        no_wa   = sum(1 for v in results.values() if v is False)
        out     = "📊 *WhatsApp Check Report*\n━━━━━━━━━━━━━━━━━\n"
        for num, exists in results.items():
            if   exists is True:  out += f"🔴  `{num}` — *WA আছে*\n"
            elif exists is False: out += f"🟢  `{num}` — WA নেই\n"
            else:                 out += f"⬜  `{num}` — চেক হয়নি\n"
        out += (f"━━━━━━━━━━━━━━━━━\n"
                f"📋 মোট: {len(numbers)}  🔴: {has_wa}  🟢: {no_wa}")
        try:
            bot.edit_message_text(out, chat_id, loading.message_id,
                                  parse_mode="Markdown")
        except: pass
    threading.Thread(target=_do, daemon=True).start()

# ─────────────────────────────────────────────────────────────
#  INLINE CALLBACKS
# ─────────────────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    _save_user(call.from_user)
    chat_id = call.message.chat.id
    msg_id  = call.message.message_id
    data    = call.data
    bot.answer_callback_query(call.id)

    if data.startswith("cr|"):
        panel = data.split("|",1)[1]
        threading.Thread(target=_send_console,
                         args=(chat_id, panel, msg_id), daemon=True).start()
    elif data.startswith("nb|"):
        _, panel, range_id = data.split("|",2)
        threading.Thread(target=get_6_numbers,
                         args=(chat_id, panel, range_id, msg_id),
                         daemon=True).start()
    elif data == "cb":
        try: bot.delete_message(chat_id, msg_id)
        except: pass

# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("✅ OTP Panel Bot v4.1 চালু  (P1+P2 | PairPhone fixed | Username stats | 60-user ready)")
    while True:
        try:
            bot.infinity_polling(
                skip_pending=True, timeout=30, long_polling_timeout=20)
        except Exception as e:
            wait = 15 if "409" in str(e) else 5
            print(f"[POLL] {e} — {wait}s retry...")
            time.sleep(wait)
