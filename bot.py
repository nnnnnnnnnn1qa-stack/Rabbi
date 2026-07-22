            f"🔴 *{len(found)}টি WhatsApp নাম্বার পাওয়া গেছে*\n"
                f"⏳ _OTP আসলে inbox-এ দেখাবে_")
    kb = _old_number_kb(found, range_id)

    if edit_msg_id:
        try: bot.edit_message_text(header, cid, st_id, reply_markup=kb, parse_mode="Markdown"); 
        except: bot.send_message(cid, header, reply_markup=kb, parse_mode="Markdown")
    else:
        safe_delete(cid, st_id)
        bot.send_message(cid, header, reply_markup=kb, parse_mode="Markdown")

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
    bot.send_message(msg.chat.id,
        "🤖 *OTP Panel Bot v6.0*\n\n"
        "🔴 *P1 Console* — WealthoraPrime লাইভ ট্র্যাফিক\n"
        "🔵 *P2 Console* — FastXOTPs লাইভ ট্র্যাফিক\n"
        "📲 *OLD নাম্বার* — P1 থেকে শুধু WA আছে এমন ৫টি নাম্বার\n"
        "🔍 *নাম্বার চেকার* — WhatsApp আছে কিনা চেক করুন\n"
        "❌ *WP Checker* — WhatsApp লগইন (Phone code)\n"
        "🔌 *WP Disconnect* — সংযোগ বন্ধ\n\n"
        "⚡ OTP আসামাত্র ≤১ সেকেন্ডে পাবেন",
        reply_markup=_main_kb(msg.chat.id))

# ─────────────────────────────────────────────────────────────
#  /stats  /status  (admin)
# ─────────────────────────────────────────────────────────────
@bot.message_handler(commands=["stats"])
def cmd_stats(msg):
    if msg.chat.id != ADMIN_ID: return
    if not otp_stats: bot.send_message(msg.chat.id, "📊 এখনো কোনো OTP নেই।"); return
    text  = "📊 *OTP Statistics*\n━━━━━━━━━━━━━━━━━\n"
    total = 0
    for uid, cnt in sorted(otp_stats.items(), key=lambda x: -x[1]):
        lbl = _get_label(uid)
        lnk = f"[{lbl}](tg://user?id={uid})"
        text += f"👤 {lnk} — *{cnt}* OTP\n"; total += cnt
    text += f"━━━━━━━━━━━━━━━━━\n📋 মোট: *{total}*"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(commands=["status"])
def cmd_status(msg):
    if msg.chat.id != ADMIN_ID: return
    connected  = [c for c,s in wa_statuses.items() if s=="connected"]
    connecting = [c for c,s in wa_statuses.items() if s=="connecting"]
    with _p1_reg_lock: p1w = len(_p1_registry)
    with _p2_reg_lock: p2w = len(_p2_registry)
    text = (f"🖥 *Bot Status v6.0*\n━━━━━━━━━━━━━━━━━\n"
            f"⏱ Uptime: `{uptime_str()}`\n"
            f"👥 WA Connected: `{len(connected)}`\n"
            f"🔄 WA Connecting: `{len(connecting)}`\n"
            f"🔴 P1 watching: `{p1w}` নাম্বার\n"
            f"🔵 P2 watching: `{p2w}` নাম্বার\n"
            f"📨 Total OTPs: `{sum(otp_stats.values())}`\n━━━━━━━━━━━━━━━━━\n")
    if connected:
        text += "*Connected:*\n"
        for cid in connected:
            text += f"  • `{cid}` ({_get_label(cid)}) — {otp_stats.get(cid,0)} OTP\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)

# ─────────────────────────────────────────────────────────────
#  CONSOLE BUTTONS
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🔴 P1 Console")
def btn_p1_console(msg):
    _save_user(msg)
    threading.Thread(target=_send_console, args=(msg.chat.id,"p1"), daemon=True).start()

@bot.message_handler(func=lambda m: m.text == "🔵 P2 Console")
def btn_p2_console(msg):
    _save_user(msg)
    threading.Thread(target=_send_console, args=(msg.chat.id,"p2"), daemon=True).start()

# ─────────────────────────────────────────────────────────────
#  📲 OLD নাম্বার — সরাসরি range চাও (P1 only)
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "📲 OLD নাম্বার")
def btn_old(msg):
    _save_user(msg)
    cid = msg.chat.id
    if get_wa_status(cid) != "connected":
        bot.send_message(cid,
            "❌ *OLD নাম্বার পেতে WhatsApp সংযুক্ত থাকতে হবে।*\n\n"
            "প্রথমে *❌ WP Checker* দিয়ে লগইন করুন।",
            reply_markup=_main_kb(cid), parse_mode="Markdown")
        return
    with state_lock: user_state[cid] = {"mode": "wait_range_old"}
    bot.send_message(cid,
        "📲 *OLD নাম্বার* — রেঞ্জ লিখুন\n"
        "_(যেমন: `22501XXX`)_\n\n"
        "_P1 থেকে ৩০টা করে WA চেক করে ৫টা পুরনো নাম্বার দেবে_",
        parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────
#  WP CHECKER
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text in ("✅ WP Checker","❌ WP Checker"))
def btn_wa(msg):
    _save_user(msg)
    cid = msg.chat.id
    st  = get_wa_status(cid)
    if st == "connected":
        bot.send_message(cid, "✅ *WhatsApp ইতিমধ্যে সংযুক্ত!*", reply_markup=_main_kb(cid))
        return
    if st == "connecting":
        bot.send_message(cid, "⏳ *কোড তৈরি হচ্ছে...* একটু অপেক্ষা করুন।", parse_mode="Markdown")
        return
    with state_lock: user_state[cid] = {"mode": "wait_phone"}
    bot.send_message(cid,
        "📱 *WhatsApp নম্বর দিন* (দেশের কোড সহ)\n\nযেমন: `+8801712345678`",
        parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────
#  WP DISCONNECT
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🔌 WP Disconnect")
def btn_disconnect(msg):
    _save_user(msg)
    threading.Thread(target=disconnect_wa, args=(msg.chat.id,), daemon=True).start()

# ─────────────────────────────────────────────────────────────
#  নাম্বার চেকার
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🔍 নাম্বার চেকার")
def btn_checker(msg):
    _save_user(msg)
    cid = msg.chat.id
    if get_wa_status(cid) != "connected":
        bot.send_message(cid, "❌ *WhatsApp সংযুক্ত নেই।*\n\nপ্রথমে *❌ WP Checker* চাপুন।",
                         reply_markup=_main_kb(cid))
        return
    with state_lock: user_state[cid] = {"mode": "wait_check"}
    bot.send_message(cid,
        "🔍 *নাম্বার চেকার*\n\n📞 নাম্বার পাঠান (প্রতি লাইনে একটি, সর্বোচ্চ ২০টি):",
        parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────
#  FREE TEXT HANDLER
# ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(msg):
    _save_user(msg)
    cid  = msg.chat.id
    text = msg.text.strip()
    if text.startswith("/") or text in _ALL_BTN: return
    with state_lock: mode = user_state.get(cid, {}).get("mode","idle")

    if mode == "wait_phone":
        with state_lock: user_state[cid] = {"mode":"idle"}
        phone = text.replace(" ","").replace("-","")
        if not phone.startswith("+"): phone = "+" + phone
        if not re.match(r"^\+\d{7,15}$", phone):
            bot.send_message(cid,
                "❌ *নম্বর সঠিক নয়।*\n\nদেশের কোড সহ দিন।\nযেমন: `+8801712345678`",
                parse_mode="Markdown"); return
        bot.send_message(cid, f"⏳ `{phone}` এর pairing code তৈরি হচ্ছে...", parse_mode="Markdown")
        threading.Thread(target=connect_with_code, args=(cid,phone), daemon=True).start()

    elif mode == "wait_range_old":
        with state_lock: user_state[cid] = {"mode":"idle"}
        threading.Thread(target=get_old_numbers, args=(cid,text), daemon=True).start()

    elif mode == "wait_check":
        with state_lock: user_state[cid] = {"mode":"idle"}
        lines = [l.strip() for l in text.splitlines() if l.strip()][:20]
        if not lines: bot.send_message(cid, "❌ কোনো নাম্বার পাওয়া যায়নি।"); return
        loading = bot.send_message(cid, f"⏳ {len(lines)}টি নাম্বার চেক হচ্ছে...", parse_mode="Markdown")
        def _do():
            res = _wa_check(cid, lines)
            wa, no_wa, unk = [], [], []
            for n, v in res.items():
                if v is True:  wa.append(f"🔴 `{n}` — WA আছে")
                elif v is False: no_wa.append(f"🟢 `{n}` — WA নেই")
                else: unk.append(f"⬜ `{n}` — চেক হয়নি")
            safe_delete(cid, loading.message_id)
            bot.send_message(cid, "🔍 *ফলাফল:*\n\n" + "\n".join(wa+no_wa+unk), parse_mode="Markdown")
        threading.Thread(target=_do, daemon=True).start()

# ─────────────────────────────────────────────────────────────
#  CALLBACK HANDLER
# ─────────────────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    _save_user(call.from_user)
    data = call.data; cid = call.message.chat.id; mid = call.message.message_id

    if data == "cb":
        safe_delete(cid, mid); bot.answer_callback_query(call.id); return

    if data.startswith("cr|"):
        panel = data.split("|")[1]
        bot.answer_callback_query(call.id, "🔄 Refreshing...")
        threading.Thread(target=_send_console, args=(cid,panel,mid), daemon=True).start(); return

    if data.startswith("old|"):
        range_id = data.split("|",1)[1]
        bot.answer_callback_query(call.id, "🔴 OLD নাম্বার খোঁজা হচ্ছে...")
        threading.Thread(target=get_old_numbers, args=(cid,range_id,mid), daemon=True).start(); return

    bot.answer_callback_query(call.id)

# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🤖 OTP Panel Bot v6.0 চালু হচ্ছে... (admin={ADMIN_ID})")
    threading.Thread(target=_global_p1_poller, daemon=True, name="P1-Poller").start()
    threading.Thread(target=_global_p2_poller, daemon=True, name="P2-Poller").start()
    bot.infinity_polling(timeout=30, long_polling_timeout=20)

