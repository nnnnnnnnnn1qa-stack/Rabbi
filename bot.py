"""
OTP Panel Bot — Final
Panels : P1 (WealthoraPrime) + P2 (FastXOTPs)
WA     : neonize QR-based login + bulk checker
"""

import io, os, re, time, threading, logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import segno
import telebot
from telebot import types
from neonize.client import NewClient
from neonize.events import ConnectedEv, DisconnectedEv

# ══════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════
BOT_TOKEN = (os.environ.get("WA_CHECKER_BOT_TOKEN")
             or os.environ.get("TELEGRAM_BOT_TOKEN", ""))

# P1 — WealthoraPrime (GET + header auth)
P1_BASE = os.environ.get("WEALTHORA_API_BASE",
          "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api")
P1_KEY  = os.environ.get("WEALTHORA_API_KEY", "MWFG9WNAHZQ")
P1_HDRS = {"mauthapi": P1_KEY}

# P2 — FastXOTPs (POST + X-API-Key header)
P2_BASE = os.environ.get("FASTXOTPS_API_BASE", "https://fastxotps.com")
P2_KEY  = os.environ.get("FASTXOTPS_API_KEY",  "MURAD_69548E938AF8F1D4E0587220")
P2_HDRS = {"X-API-Key": P2_KEY, "Content-Type": "application/json"}

SESSION_NAME = "wa_py_session"

if not BOT_TOKEN:
    raise SystemExit("❌  WA_CHECKER_BOT_TOKEN env var is required.")

logging.basicConfig(level=logging.WARNING)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════
#  GLOBAL STATE
# ══════════════════════════════════════════════════════════════════════
wa_client      = None
wa_status      = "disconnected"   # "disconnected" | "connecting" | "connected"
pending_chatid = None

user_state = {}   # chat_id → {"mode": str}
state_lock = threading.Lock()

DEFAULT_SERVICES = {"whatsapp", "facebook", "telegram"}
SVC_ICON         = {"whatsapp": "💬", "facebook": "📘", "telegram": "✈️"}

# ══════════════════════════════════════════════════════════════════════
#  LOW-LEVEL HTTP HELPERS
# ══════════════════════════════════════════════════════════════════════
def _get(url, params=None, headers=None, timeout=10):
    try:
        return requests.get(url, params=params, headers=headers,
                            timeout=timeout).json()
    except Exception as e:
        return {"error": str(e)}

def _post(url, data=None, headers=None, timeout=10):
    try:
        return requests.post(url, json=data or {}, headers=headers,
                             timeout=timeout).json()
    except Exception as e:
        return {"error": str(e)}

def p1_get(path, params=None):
    return _get(f"{P1_BASE}{path}", params=params, headers=P1_HDRS)

def p1_post(path, data=None):
    return _post(f"{P1_BASE}{path}", data=data, headers=P1_HDRS)

def p2(path, data=None):
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
    """Extract OTP code from a message string."""
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
            bot.edit_message_text(text, chat_id, msg_id,
                                  reply_markup=kb, parse_mode="Markdown")
        else:
            bot.edit_message_text(text, chat_id, msg_id, parse_mode="Markdown")
    except Exception as e:
        print(f"[edit_safe] {e}")

# ══════════════════════════════════════════════════════════════════════
#  COUNTRY FLAG LOOKUP
# ══════════════════════════════════════════════════════════════════════
_FLAG: dict[str, str] = {
    "ivory coast":"🇨🇮","côte d'ivoire":"🇨🇮","cameroon":"🇨🇲",
    "madagascar":"🇲🇬","comoros":"🇰🇲","nigeria":"🇳🇬","ghana":"🇬🇭",
    "kenya":"🇰🇪","ethiopia":"🇪🇹","tanzania":"🇹🇿","uganda":"🇺🇬",
    "senegal":"🇸🇳","mali":"🇲🇱","burkina faso":"🇧🇫","guinea":"🇬🇳",
    "guinea-bissau":"🇬🇼","togo":"🇹🇬","benin":"🇧🇯","niger":"🇳🇪",
    "chad":"🇹🇩","angola":"🇦🇴","mozambique":"🇲🇿","zambia":"🇿🇲",
    "zimbabwe":"🇿🇼","botswana":"🇧🇼","namibia":"🇳🇦",
    "south africa":"🇿🇦","rwanda":"🇷🇼","burundi":"🇧🇮",
    "congo":"🇨🇬","democratic republic of the congo":"🇨🇩","dr congo":"🇨🇩",
    "gabon":"🇬🇦","equatorial guinea":"🇬🇶","malawi":"🇲🇼",
    "lesotho":"🇱🇸","eswatini":"🇸🇿","swaziland":"🇸🇿",
    "mauritius":"🇲🇺","seychelles":"🇸🇨","reunion":"🇷🇪",
    "cape verde":"🇨🇻","sierra leone":"🇸🇱","liberia":"🇱🇷",
    "eritrea":"🇪🇷","djibouti":"🇩🇯","somalia":"🇸🇴",
    "mauritania":"🇲🇷","central african republic":"🇨🇫","sudan":"🇸🇩",
    "south sudan":"🇸🇸","egypt":"🇪🇬","morocco":"🇲🇦","algeria":"🇩🇿",
    "tunisia":"🇹🇳","libya":"🇱🇾","india":"🇮🇳","pakistan":"🇵🇰",
    "bangladesh":"🇧🇩","indonesia":"🇮🇩","philippines":"🇵🇭",
    "vietnam":"🇻🇳","thailand":"🇹🇭","malaysia":"🇲🇾","myanmar":"🇲🇲",
    "cambodia":"🇰🇭","sri lanka":"🇱🇰","nepal":"🇳🇵",
    "ukraine":"🇺🇦","russia":"🇷🇺","brazil":"🇧🇷","argentina":"🇦🇷",
    "colombia":"🇨🇴","mexico":"🇲🇽","peru":"🇵🇪","chile":"🇨🇱",
    "venezuela":"🇻🇪","ecuador":"🇪🇨","bolivia":"🇧🇴","paraguay":"🇵🇾",
    "uruguay":"🇺🇾","united states":"🇺🇸","united kingdom":"🇬🇧",
    "france":"🇫🇷","germany":"🇩🇪","spain":"🇪🇸","china":"🇨🇳",
    "japan":"🇯🇵","south korea":"🇰🇷","saudi arabia":"🇸🇦",
    "turkey":"🇹🇷","iran":"🇮🇷","iraq":"🇮🇶","afghanistan":"🇦🇫",
}

def _get_flag(country: str) -> str:
    return _FLAG.get(country.strip().lower(), "🌍")

def _svc_label(service: str = "", range_id: str = "") -> str:
    s = (service or "").lower()
    r = (range_id or "").lower()
    if "facebook" in s or "fb" in r: return "Facebook"
    if "telegram" in s or "tg" in r: return "Telegram"
    return "WhatsApp"

# ══════════════════════════════════════════════════════════════════════
#  OTP NOTIFICATION  (header text + OTP as tappable CopyTextButton)
# ══════════════════════════════════════════════════════════════════════
def _send_otp_notification(chat_id, full_num: str, otp_code: str,
                            country: str = "", service: str = "",
                            range_id: str = ""):
    flag = _get_flag(country)
    svc  = _svc_label(service, range_id)
    ctry = country or "Unknown"
    # One-line header
    header = f"{flag}|`{full_num}`| {svc} 🌍COUNTRY: {ctry}"
    # OTP as CopyTextButton — tap to copy instantly
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        f"🔑  {otp_code}",
        copy_text=types.CopyTextButton(text=otp_code),
    ))
    try:
        bot.send_message(chat_id, header, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        print(f"[OTP-NOTIFY] send error: {e}")

# ══════════════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════════════
def main_kb():
    wa_lbl = "✅ WA Checker" if wa_status == "connected" else "❌ WA Checker"
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(types.KeyboardButton("🔴 P1 Console"), types.KeyboardButton("🔵 P2 Console"))
    kb.row(types.KeyboardButton("📞 P1 নাম্বার"), types.KeyboardButton("📞 P2 নাম্বার"))
    kb.add(types.KeyboardButton("🔍 নাম্বার চেকার"))
    kb.add(types.KeyboardButton(wa_lbl))
    return kb

def console_kb(panel: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "🔄 Refresh", callback_data=f"console_refresh|{panel}"))
    return kb

def _build_number_kb(numbers: list, wa_results: dict,
                     panel: str, range_id: str) -> types.InlineKeyboardMarkup:
    """Each number = CopyTextButton row; bottom row = change / close."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    for n in numbers:
        wa_val = wa_results.get(n["full"])
        icon   = "🔴" if wa_val is True else ("🟢" if wa_val is False else "⬜")
        kb.add(types.InlineKeyboardButton(
            f"{icon}  {n['full']}",
            copy_text=types.CopyTextButton(text=n["full"]),
        ))
    kb.row(
        types.InlineKeyboardButton(
            "🔄 নাম্বার চেঞ্জ", callback_data=f"newbatch|{panel}|{range_id}"),
        types.InlineKeyboardButton(
            "❌ বন্ধ করুন",     callback_data="closebatch"),
    )
    return kb

def _number_card_header(range_id: str, panel: str,
                         count: int, failed: int = 0) -> str:
    label = "P1" if panel == "p1" else "P2"
    svc   = "💬 *WHATSAPP*" if "wa" in range_id.lower() else f"📡 *{range_id}*"
    hdr   = f"{svc} [{label}]  —  {count}টি নাম্বার"
    if failed: hdr += f"  _(⚠️ {failed} মিস)_"
    hdr  += "\n⏳ _OTP আসলে নিচে দেখাবে_"
    return hdr

# ══════════════════════════════════════════════════════════════════════
#  CONSOLE
# ══════════════════════════════════════════════════════════════════════
def _fmt_p1_console(hits: list) -> str:
    groups: dict[str, list] = {}
    for h in hits:
        sid = str(h.get("sid", "")).strip().lower()
        if sid in DEFAULT_SERVICES:
            groups.setdefault(sid, []).append(h)
    if not groups:
        return "⚠️ কোনো লাইভ ডেটা নেই।"
    lines = []
    for sid in ["whatsapp", "facebook", "telegram"]:
        if sid not in groups: continue
        icon = SVC_ICON.get(sid, "📲")
        lines.append(f"\n━━━━━━━━━━━━━━━━━\n{icon} *{sid.capitalize()}*")
        for h in groups[sid][:10]:
            lines.append(
                f"`{h.get('range','')}` — _{time_ago(h.get('time', time.time()*1000))}_")
    lines.append(f"\n━━━━━━━━━━━━━━━━━\n🔄 _{time.strftime('%H:%M:%S')}_")
    return "\n".join(lines)

def _fmt_p2_console(services: list) -> str:
    filtered = sorted(
        [s for s in services if str(s.get("sid","")).lower() in DEFAULT_SERVICES],
        key=lambda s: {"whatsapp":0,"facebook":1,"telegram":2}.get(
            str(s.get("sid","")).lower(), 9))
    if not filtered:
        return "⚠️ কোনো লাইভ ডেটা নেই।"
    lines = []
    for svc in filtered:
        sid  = str(svc.get("sid","")).lower()
        icon = SVC_ICON.get(sid, "📲")
        ago  = time_ago(svc.get("last_at", time.time()*1000))
        lines.append(f"\n━━━━━━━━━━━━━━━━━\n{icon} *{sid.capitalize()}* — _{ago}_")
        for r in svc.get("ranges", [])[:8]:
            lines.append(f"  `{r}`")
    lines.append(f"\n━━━━━━━━━━━━━━━━━\n🔄 _{time.strftime('%H:%M:%S')}_")
    return "\n".join(lines)

def _send_console(chat_id, panel: str, edit_id=None):
    if panel == "p1":
        resp = p1_get("/console")
        hits = resp.get("data", {}).get("hits", [])
        text = "🔴 *P1 — WealthoraPrime*\n" + _fmt_p1_console(hits)
    else:
        resp     = p2("/liveaccess")
        services = resp.get("services", [])
        text     = "🔵 *P2 — FastXOTPs*\n" + _fmt_p2_console(services)
    kb = console_kb(panel)
    if edit_id:
        try:
            bot.edit_message_text(text, chat_id, edit_id,
                                  reply_markup=kb, parse_mode="Markdown")
            return
        except: pass
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════
#  FETCH ONE NUMBER
# ══════════════════════════════════════════════════════════════════════
def _fetch_number(panel: str, range_id: str) -> dict | None:
    """
    Returns {full, plain, country, rid, otp_now, otp_msg} or None.
    P1: GET-based; P2: POST-based, returns rid + otp_now flag.
    """
    if panel == "p1":
        resp    = p1_post("/getnum", {"range": range_id})
        code    = resp.get("meta", {}).get("code")
        data    = resp.get("data", {}) or {}
        full    = str(data.get("full_number", ""))
        plain   = str(data.get("no_plus_number") or full.lstrip("+"))
        country = str(data.get("country") or "")
        if full and code == 200:
            return {"full": full, "plain": plain, "country": country,
                    "rid": None, "otp_now": False, "otp_msg": ""}
        return None
    else:
        resp    = p2("/getnum", {"range": range_id})
        data    = resp.get("data", resp) or {}
        if not isinstance(data, dict): data = {}
        full    = (data.get("full_number") or data.get("number") or
                   resp.get("full_number") or "")
        plain   = str(data.get("no_plus_number") or str(full).lstrip("+"))
        country = str(data.get("country") or resp.get("country") or "")
        rid     = str(resp.get("rid") or data.get("rid") or "")
        otp_now = bool(data.get("otp_now") or resp.get("otp_now"))
        otp_msg = str(data.get("otp_message") or data.get("message") or
                      resp.get("otp_message") or "")
        if not full:
            full  = str(resp.get("full_number") or resp.get("number") or "")
            plain = str(resp.get("no_plus_number") or full.lstrip("+"))
        if full:
            return {"full": full, "plain": plain, "country": country,
                    "rid": rid, "otp_now": otp_now, "otp_msg": otp_msg}
        return None

# ══════════════════════════════════════════════════════════════════════
#  GET 6 NUMBERS  (parallel fetch)
# ══════════════════════════════════════════════════════════════════════
def get_6_numbers(chat_id, panel: str, range_id: str, edit_msg_id=None):
    label        = "P1" if panel == "p1" else "P2"
    loading_text = f"⏳ `{range_id}` [{label}] থেকে নাম্বার আনা হচ্ছে..."

    if edit_msg_id:
        edit_safe(chat_id, edit_msg_id, loading_text)
        st_id = edit_msg_id
    else:
        st    = bot.send_message(chat_id, loading_text, parse_mode="Markdown")
        st_id = st.message_id

    # ── Parallel fetch (handles 50-60 concurrent users efficiently) ──
    results: list[dict] = []
    failed  = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(_fetch_number, panel, range_id) for _ in range(6)]
        for f in as_completed(futs):
            info = f.result()
            if info: results.append(info)
            else:    failed += 1

    if not results:
        err = (f"❌ `{range_id}` [{label}] থেকে নাম্বার পাওয়া যায়নি।\n"
               f"_রেঞ্জ খালি বা API error।_")
        if edit_msg_id:
            edit_safe(chat_id, st_id, err)
        else:
            safe_delete(chat_id, st_id)
            bot.send_message(chat_id, err, parse_mode="Markdown")
        return

    wa_results = _wa_check_bulk(results)
    header     = _number_card_header(range_id, panel, len(results), failed)
    kb         = _build_number_kb(results, wa_results, panel, range_id)

    if edit_msg_id:
        try:
            bot.edit_message_text(header, chat_id, st_id,
                                  reply_markup=kb, parse_mode="Markdown")
        except:
            bot.send_message(chat_id, header, reply_markup=kb, parse_mode="Markdown")
    else:
        safe_delete(chat_id, st_id)
        bot.send_message(chat_id, header, reply_markup=kb, parse_mode="Markdown")

    # ── Build num_meta for OTP watcher notifications ──────────────────
    num_meta = {
        n["plain"]: {"full": n["full"], "country": n.get("country",""),
                     "range_id": range_id}
        for n in results
    }
    # P1 watcher — polls P1 success-otp every 2 s for both panels
    threading.Thread(
        target=_otp_watcher,
        args=(chat_id, set(num_meta.keys()), panel, 600, num_meta),
        daemon=True).start()

    # P2 watcher — polls /api/getnum/{rid} every 2 s
    if panel == "p2":
        p2_nums = [n for n in results if n.get("rid")]
        if p2_nums:
            threading.Thread(
                target=_p2_otp_watcher,
                args=(chat_id, p2_nums),
                daemon=True).start()

# ══════════════════════════════════════════════════════════════════════
#  OTP HELPERS
# ══════════════════════════════════════════════════════════════════════
def _fetch_p1_otps() -> list:
    try:
        resp = p1_get("/success-otp")
        otps = (resp.get("data") or {}).get("otps", [])
        return otps if isinstance(otps, list) else []
    except:
        return []

def _num_matches(api_num: str, watch: set) -> bool:
    """True if api_num matches any plain number in watch (exact or 7-9 digit suffix)."""
    a = api_num.strip().lstrip("+")
    for w in watch:
        wc = w.strip().lstrip("+")
        if a == wc: return True
        sl = min(len(a), len(wc), 9)
        if sl >= 7 and a[-sl:] == wc[-sl:]: return True
    return False

# ══════════════════════════════════════════════════════════════════════
#  P1 OTP WATCHER
# ══════════════════════════════════════════════════════════════════════
def _otp_watcher(chat_id, watch_numbers: set, panel: str,
                  duration: int = 600, num_meta: dict = None):
    """
    Per-call local `seen` set — no cross-contamination between sessions.
    Step 1 : snapshot all current OTP IDs → skip them (already existed).
    Step 2 : poll P1 success-otp every 2 s; any new matching OTP → notify.
    Works for both P1 numbers and P2 numbers (in case P2 shares P1 infra).
    """
    seen: set[str] = set()
    for o in _fetch_p1_otps():
        oid = str(o.get("otp_id") or "")
        if oid: seen.add(oid)

    print(f"[P1-OTP] started | chat={chat_id} | watching={len(watch_numbers)} "
          f"| pre-seen={len(seen)} | panel={panel}")

    deadline = time.time() + duration
    while time.time() < deadline:
        time.sleep(2)
        otps = _fetch_p1_otps()
        print(f"[P1-OTP] poll → {len(otps)} OTPs | watching={len(watch_numbers)}")
        for o in otps:
            oid = str(o.get("otp_id") or "")
            if not oid or oid in seen:
                continue
            api_num = str(o.get("number", "")).strip()
            if not _num_matches(api_num, watch_numbers):
                continue
            seen.add(oid)
            otp_code = extract_otp(str(o.get("message", "")))
            print(f"[P1-OTP] ✅ MATCH  num={api_num}  otp={otp_code}")
            # Lookup rich metadata
            meta     = {}
            if num_meta:
                for pw, m in num_meta.items():
                    if _num_matches(api_num, {pw}):
                        meta = m; break
            _send_otp_notification(
                chat_id,
                full_num  = meta.get("full") or f"+{api_num}",
                otp_code  = otp_code,
                country   = meta.get("country", ""),
                range_id  = meta.get("range_id", ""),
            )

    print(f"[P1-OTP] expired | chat={chat_id}")

# ══════════════════════════════════════════════════════════════════════
#  P2 OTP WATCHER  (rid-based)
# ══════════════════════════════════════════════════════════════════════
def _p2_otp_watcher(chat_id, numbers: list, duration: int = 600):
    """
    For each P2 number, poll GET /api/getnum/{rid} every 2 s.
    • HTTP 500 → OTP not yet arrived, keep polling.
    • HTTP 200 + otp_now / message → OTP arrived, notify and remove.
    Also handles otp_now=True at allocation time (immediate delivery).
    """
    pending: dict[str, dict] = {}
    for n in numbers:
        rid = n.get("rid", "")
        if not rid: continue
        if n.get("otp_now") and n.get("otp_msg"):
            otp_code = extract_otp(n["otp_msg"])
            print(f"[P2-OTP] ✅ immediate  num={n['full']}  otp={otp_code}")
            _send_otp_notification(
                chat_id,
                full_num = n["full"],
                otp_code = otp_code,
                country  = n.get("country", ""),
            )
        else:
            pending[rid] = n

    if not pending:
        print(f"[P2-OTP] no pending numbers | chat={chat_id}")
        return

    print(f"[P2-OTP] started | chat={chat_id} | pending={len(pending)}")
    deadline = time.time() + duration

    while time.time() < deadline and pending:
        time.sleep(2)
        for rid in list(pending.keys()):
            try:
                r = requests.get(
                    f"{P2_BASE}/api/getnum/{rid}",
                    headers={"X-API-Key": P2_KEY},
                    timeout=8,
                )
                print(f"[P2-OTP] poll rid={rid[-6:]} → {r.status_code}")
                if r.status_code == 200:
                    resp    = r.json()
                    d       = resp.get("data", resp) or {}
                    if not isinstance(d, dict): d = {}
                    otp_now = bool(d.get("otp_now") or resp.get("otp_now"))
                    msg     = (d.get("otp_message") or d.get("message") or
                               resp.get("otp_message") or resp.get("otp_text") or "")
                    if otp_now or msg:
                        n        = pending.pop(rid)
                        otp_code = extract_otp(str(msg))
                        print(f"[P2-OTP] ✅ MATCH  num={n['full']}  otp={otp_code}")
                        _send_otp_notification(
                            chat_id,
                            full_num = n["full"],
                            otp_code = otp_code,
                            country  = n.get("country", ""),
                        )
                # HTTP 500 → still pending, keep polling
            except Exception as e:
                print(f"[P2-OTP] request error rid={rid[-6:]}: {e}")

    status = "all resolved" if not pending else f"{len(pending)} unresolved"
    print(f"[P2-OTP] done ({status}) | chat={chat_id}")

# ══════════════════════════════════════════════════════════════════════
#  WHATSAPP HELPERS
# ══════════════════════════════════════════════════════════════════════
def _wa_check_bulk(numbers: list) -> dict:
    result = {n["full"]: None for n in numbers}
    if not wa_client or wa_status != "connected": return result
    try:
        cleaned   = [n["plain"].lstrip("+") for n in numbers]
        jids      = [f"+{c}@s.whatsapp.net" for c in cleaned]
        responses = wa_client.is_on_whatsapp(*jids)
        for i, n in enumerate(numbers):
            matched      = next((r for r in responses if cleaned[i] in r.Query), None)
            result[n["full"]] = (bool(matched.IsIn) if matched else
                                  (bool(responses[i].IsIn) if i < len(responses) else None))
    except Exception as e:
        print(f"[WA-BULK] {e}")
    return result

def check_numbers_wa(numbers: list[str]) -> dict:
    result  = {n: None for n in numbers}
    if not wa_client or wa_status != "connected": return result
    cleaned = [n.replace("+","").replace(" ","").replace("-","") for n in numbers]
    jids    = [f"+{c}@s.whatsapp.net" for c in cleaned]
    try:
        responses = wa_client.is_on_whatsapp(*jids)
        for i, n in enumerate(numbers):
            matched   = next((r for r in responses if cleaned[i] in r.Query), None)
            result[n] = (bool(matched.IsIn) if matched else
                          (bool(responses[i].IsIn) if i < len(responses) else None))
    except Exception as e:
        print(f"[WA-CHECK] {e}")
    return result

# ══════════════════════════════════════════════════════════════════════
#  QR / WA CLIENT
# ══════════════════════════════════════════════════════════════════════
def _send_qr(chat_id: int, qr_data):
    try:
        buf = io.BytesIO()
        segno.make_qr(qr_data).save(buf, kind="png", scale=8, border=2)
        buf.seek(0); buf.name = "qr.png"
        bot.send_photo(chat_id, buf,
            caption=(
                "📱 *WhatsApp QR Code*\n\n"
                "Settings → Linked Devices → Link a Device\n"
                "→ এই QR স্ক্যান করুন"
            ), parse_mode="Markdown")
    except Exception as e:
        print(f"[QR] {e}")
        try: bot.send_message(chat_id, f"❌ QR পাঠাতে সমস্যা: `{e}`")
        except: pass

def _build_client(qr_chat_id=None):
    c = NewClient(SESSION_NAME)

    @c.event.qr
    def on_qr(client, qr_bytes):
        if qr_chat_id is not None:
            _send_qr(qr_chat_id, qr_bytes)

    @c.event(ConnectedEv)
    def on_connected(client, event):
        global wa_status
        wa_status = "connected"
        print("✅ WhatsApp connected.")
        if pending_chatid:
            try:
                bot.send_message(pending_chatid,
                    "✅ *WhatsApp সফলভাবে সংযুক্ত!*\n\nএখন নম্বর চেক করা যাবে।",
                    reply_markup=main_kb())
            except: pass

    @c.event(DisconnectedEv)
    def on_disconnected(client, event):
        global wa_status
        wa_status = "disconnected"
        print("⚠️  WhatsApp disconnected — reconnecting in 5s…")
        time.sleep(5)
        threading.Thread(target=_reconnect_silent, daemon=True).start()

    return c

def _run_client(client):
    try:
        client.connect()
    except Exception as e:
        global wa_status
        wa_status = "disconnected"
        print(f"[WA] connect error: {e}")

def _reconnect_silent():
    global wa_client, wa_status
    if wa_status != "disconnected": return
    wa_status = "connecting"
    wa_client = _build_client(qr_chat_id=None)
    _run_client(wa_client)

def connect_with_qr(chat_id: int):
    global wa_client, wa_status, pending_chatid
    if wa_status == "connected":
        bot.send_message(chat_id, "✅ *WhatsApp ইতিমধ্যে সংযুক্ত!*",
                         reply_markup=main_kb())
        return
    if wa_status == "connecting":
        bot.send_message(chat_id, "⏳ সংযোগ চলছে, একটু অপেক্ষা করুন…")
        return
    db = f"{SESSION_NAME}.db"
    if os.path.exists(db):
        try: os.remove(db)
        except: pass
    wa_status      = "connecting"
    pending_chatid = chat_id
    bot.send_message(chat_id, "⏳ QR code তৈরি হচ্ছে…")
    wa_client = _build_client(qr_chat_id=chat_id)
    threading.Thread(target=_run_client, args=(wa_client,), daemon=True).start()

# ══════════════════════════════════════════════════════════════════════
#  BUTTON LABELS
# ══════════════════════════════════════════════════════════════════════
WA_BTNS = ["✅ WA Checker", "❌ WA Checker"]
ALL_BTN = [
    "🔴 P1 Console", "🔵 P2 Console",
    "📞 P1 নাম্বার",  "📞 P2 নাম্বার",
    "🔍 নাম্বার চেকার",
] + WA_BTNS

# ══════════════════════════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════════════════════════
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    bot.send_message(msg.chat.id,
        "🤖 *OTP Panel Bot*\n\n"
        "🔴 P1 / 🔵 P2 Console — লাইভ ট্র্যাফিক\n"
        "📞 P1 / 📞 P2 নাম্বার — রেঞ্জ লিখুন, ৬টি নাম্বার পান\n"
        "🔍 নাম্বার চেকার — WhatsApp check\n"
        "✅/❌ WA Checker — WhatsApp QR login",
        reply_markup=main_kb())

# ══════════════════════════════════════════════════════════════════════
#  CONSOLE BUTTONS
# ══════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "🔴 P1 Console")
def btn_p1_console(msg):
    threading.Thread(target=_send_console,
                     args=(msg.chat.id, "p1"), daemon=True).start()

@bot.message_handler(func=lambda m: m.text == "🔵 P2 Console")
def btn_p2_console(msg):
    threading.Thread(target=_send_console,
                     args=(msg.chat.id, "p2"), daemon=True).start()

# ══════════════════════════════════════════════════════════════════════
#  NUMBER BUTTONS
# ══════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "📞 P1 নাম্বার")
def btn_p1_num(msg):
    with state_lock: user_state[msg.chat.id] = {"mode": "wait_range_p1"}
    bot.send_message(msg.chat.id,
        "📝 *P1* রেঞ্জ লিখুন  (যেমন: `22501XXX`)",
        parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📞 P2 নাম্বার")
def btn_p2_num(msg):
    with state_lock: user_state[msg.chat.id] = {"mode": "wait_range_p2"}
    bot.send_message(msg.chat.id,
        "📝 *P2* রেঞ্জ লিখুন  (যেমন: `26134XXX`)",
        parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════
#  CHECKER BUTTON
# ══════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "🔍 নাম্বার চেকার")
def btn_checker(msg):
    with state_lock: user_state[msg.chat.id] = {"mode": "wait_check_numbers"}
    note = "" if wa_status == "connected" else "\n⚠️ _WA সংযুক্ত নেই — চেক হবে না_"
    bot.send_message(msg.chat.id,
        f"🔍 *নাম্বার চেকার*{note}\n\n"
        f"📞 নাম্বার পাঠান (প্রতি লাইনে একটি, সর্বোচ্চ ২০টি):",
        parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════
#  WA BUTTON
# ══════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text in WA_BTNS)
def btn_wa(msg):
    threading.Thread(target=connect_with_qr,
                     args=(msg.chat.id,), daemon=True).start()

# ══════════════════════════════════════════════════════════════════════
#  FREE TEXT HANDLER
# ══════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(msg):
    chat_id = msg.chat.id
    text    = msg.text.strip()
    if text.startswith("/") or text in ALL_BTN: return

    with state_lock:
        mode = user_state.get(chat_id, {}).get("mode", "idle")

    if mode == "wait_range_p1":
        with state_lock: user_state[chat_id] = {"mode": "idle"}
        threading.Thread(target=get_6_numbers,
                         args=(chat_id, "p1", text), daemon=True).start()
        return

    if mode == "wait_range_p2":
        with state_lock: user_state[chat_id] = {"mode": "idle"}
        threading.Thread(target=get_6_numbers,
                         args=(chat_id, "p2", text), daemon=True).start()
        return

    if mode == "wait_check_numbers":
        with state_lock: user_state[chat_id] = {"mode": "idle"}
        _do_wa_check(chat_id, text)
        return

    # Auto-detect pasted number list
    lines   = [l.strip() for l in text.split("\n") if l.strip()]
    numbers = [l for l in lines
               if l and l[0] in "+0123456789"
               and len(l.replace("+","").replace(" ","").replace("-","")) >= 7]
    if not numbers: return
    if wa_status != "connected":
        bot.send_message(chat_id,
            "❌ WhatsApp সংযুক্ত নেই।\n*❌ WA Checker* বাটন চাপুন।",
            reply_markup=main_kb())
        return
    _do_wa_check(chat_id, text)

def _do_wa_check(chat_id, text: str):
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

    loading = bot.send_message(chat_id, f"⏳ {len(numbers)}টি নাম্বার চেক হচ্ছে…")

    def do_check():
        results = check_numbers_wa(numbers)
        has_wa  = sum(1 for v in results.values() if v is True)
        no_wa   = sum(1 for v in results.values() if v is False)
        out     = "📊 *WhatsApp Check Report*\n━━━━━━━━━━━━━━━━━\n"
        for num, exists in results.items():
            if   exists is True:  out += f"🔴  `{num}` — *WA আছে*\n"
            elif exists is False: out += f"🟢  `{num}` — WA নেই\n"
            else:                 out += f"⬜  `{num}` — চেক হয়নি\n"
        out += f"━━━━━━━━━━━━━━━━━\n📋 মোট: {len(numbers)}  🔴: {has_wa}  🟢: {no_wa}"
        try:
            bot.edit_message_text(out, chat_id, loading.message_id,
                                  parse_mode="Markdown")
        except Exception as e:
            try:
                bot.edit_message_text(f"❌ চেক করতে সমস্যা: `{e}`",
                                      chat_id, loading.message_id)
            except: pass

    threading.Thread(target=do_check, daemon=True).start()

# ══════════════════════════════════════════════════════════════════════
#  INLINE CALLBACKS
# ══════════════════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    chat_id = call.message.chat.id
    msg_id  = call.message.message_id
    data    = call.data
    bot.answer_callback_query(call.id)

    if data.startswith("console_refresh|"):
        panel = data.split("|", 1)[1]
        threading.Thread(target=_send_console,
                         args=(chat_id, panel, msg_id), daemon=True).start()

    elif data.startswith("rget|"):
        _, panel, range_id = data.split("|", 2)
        threading.Thread(target=get_6_numbers,
                         args=(chat_id, panel, range_id), daemon=True).start()

    elif data.startswith("newbatch|"):
        _, panel, range_id = data.split("|", 2)
        threading.Thread(target=get_6_numbers,
                         args=(chat_id, panel, range_id, msg_id), daemon=True).start()

    elif data.startswith("chnum|"):
        _, panel, range_id = data.split("|", 2)
        threading.Thread(target=get_6_numbers,
                         args=(chat_id, panel, range_id, msg_id), daemon=True).start()

    elif data == "closebatch":
        try: bot.delete_message(chat_id, msg_id)
        except: pass

# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if os.path.exists(f"{SESSION_NAME}.db"):
        print("🔄 পুরানো WA session পাওয়া গেছে — silent reconnect…")
        threading.Thread(target=_reconnect_silent, daemon=True).start()

    print("✅  OTP Panel Bot চালু হয়েছে (P1 + P2 + WA).")

    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30,
                                 long_polling_timeout=20)
        except Exception as e:
            wait = 15 if "409" in str(e) else 5
            print(f"[POLL] error: {e} — {wait}s পরে retry…")
            time.sleep(wait)
