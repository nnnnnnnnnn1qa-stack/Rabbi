name}](tg://user?id={uid})"
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
        "🖥 *Bot Status  v5*\n━━━━━━━━━━━━━━━━━\n"
        f"⏱ Uptime: `{uptime_str()}`\n"
        f"👥 WA Connected: `{len(connected)}`\n"
        f"🔄 WA Connecting: `{len(connecting)}`\n"
        f"👁 Active watches: `{watching}`\n"
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
        bot.send_message(chat_id, "⏳ কোড তৈরি হচ্ছে, একটু অপেক্ষা করুন...")
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
                "❌ *নম্বর সঠিক নয়।*\n\nদেশের কোড সহ দিন।\nউদাহরণ: `+8801712345678`",
                parse_mode="Markdown",
            )
            return
        bot.send_message(chat_id,
                         f"⏳ `{phone}` এর জন্য pairing code তৈরি হচ্ছে...",
                         parse_mode="Markdown")
        threading.Thread(
            target=connect_with_code, args=(chat_id, phone), daemon=True
        ).start()

    # ── wait_range_p1 ───────────────────────────────────────────
    elif mode == "wait_range_p1":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        threading.Thread(
            target=get_6_numbers, args=(chat_id, "p1", text), daemon=True
        ).start()

    # ── wait_range_p2 ───────────────────────────────────────────
    elif mode == "wait_range_p2":
        with state_lock:
            user_state[chat_id] = {"mode": "idle"}
        threading.Thread(
            target=get_6_numbers, args=(chat_id, "p2", text), daemon=True
        ).start()

    # ── wait_check_numbers ──────────────────────────────────────
    elif mode == "wait_check_numbers":
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
            out = []
            for n, is_on in results.items():
                if is_on is True:   icon = "🔴 WhatsApp আছে"
                elif is_on is False: icon = "🟢 WhatsApp নেই"
                else:               icon = "⬜ চেক হয়নি"
                out.append(f"`{n}` — {icon}")
            safe_delete(chat_id, loading.message_id)
            bot.send_message(
                chat_id,
                "🔍 *নাম্বার চেকার ফলাফল:*\n\n" + "\n".join(out),
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

    if data.startswith("nb|"):
        parts    = data.split("|", 2)
        panel    = parts[1]
        range_id = parts[2]
        bot.answer_callback_query(call.id, "🔄 নতুন নাম্বার আনা হচ্ছে...")
        threading.Thread(
            target=get_6_numbers,
            args=(chat_id, panel, range_id, msg_id),
            daemon=True,
        ).start()
        return

    bot.answer_callback_query(call.id)

# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🤖 OTP Panel Bot v5.0 চালু হচ্ছে... (admin={ADMIN_ID})")

    # Global pollers — daemon thread, একটাই প্রতিটার জন্য
    threading.Thread(target=_global_p2_poller, daemon=True,
                     name="P2-GlobalPoller").start()
    threading.Thread(target=_global_p1_poller, daemon=True,
                     name="P1-GlobalPoller").start()

    bot.infinity_polling(timeout=30, long_polling_timeout=20)
