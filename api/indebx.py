import json
import html
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler

# ============================================================
# KRYZO TELEGRAM SUPPORT BOT - VERCEL WEBHOOK
# ============================================================
# PASTE YOUR REAL BOT TOKEN BETWEEN THE QUOTES BELOW.
# Example:
# BOT_TOKEN = "123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
#
# Do NOT paste the token anywhere else.
# ============================================================

BOT_TOKEN = ""

# Telegram numeric admin ID(s)
ADMIN_IDS = {8814358315}

# Username WITHOUT @
SUPPORT_USERNAME = "KryzoHelpBot"

# Keep blank unless you intentionally configure a Telegram
# webhook secret.
WEBHOOK_SECRET = ""

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ============================================================
# TELEGRAM API
# ============================================================

def tg(method, data=None):
    data = data or {}
    encoded = urllib.parse.urlencode(data).encode()

    req = urllib.request.Request(
        f"{API}/{method}",
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode())


def send_message(chat_id, text, reply_markup=None, reply_to_message_id=None):
    data = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML",
    }

    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)

    if reply_to_message_id:
        data["reply_to_message_id"] = str(reply_to_message_id)

    return tg("sendMessage", data)


def edit_message(chat_id, message_id, text, reply_markup=None):
    data = {
        "chat_id": str(chat_id),
        "message_id": str(message_id),
        "text": text,
        "parse_mode": "HTML",
    }

    if reply_markup is not None:
        data["reply_markup"] = json.dumps(reply_markup)

    return tg("editMessageText", data)


def answer_callback(callback_id, text=None, show_alert=False):
    data = {
        "callback_query_id": callback_id
    }

    if text:
        data["text"] = text

    if show_alert:
        data["show_alert"] = "true"

    return tg("answerCallbackQuery", data)


# ============================================================
# HELPERS
# ============================================================

def is_admin(user_id):
    return user_id in ADMIN_IDS


def esc(value):
    return html.escape(str(value or ""))


def force_reply():
    return {
        "force_reply": True,
        "selective": True
    }


def extract_text(message):
    return (
        message.get("text")
        or message.get("caption")
        or "[Attachment without text]"
    )


# ============================================================
# MENUS
# ============================================================

def main_menu():
    return {
        "inline_keyboard": [
            [
                {"text": "📚 Education", "callback_data": "cat:Education"},
                {"text": "📖 Manga", "callback_data": "cat:Manga"},
            ],
            [
                {"text": "💳 Wallet / Payment", "callback_data": "cat:Wallet / Payment"}
            ],
            [
                {"text": "🌐 Website Issue", "callback_data": "cat:Website Issue"}
            ],
            [
                {"text": "🎫 My Tickets", "callback_data": "tickets"}
            ],
            [
                {"text": "👨‍💻 Contact Admin", "callback_data": "contact"}
            ],
        ]
    }


def category_menu():
    return {
        "inline_keyboard": [
            [
                {"text": "📚 Education", "callback_data": "cat:Education"},
                {"text": "📖 Manga", "callback_data": "cat:Manga"},
            ],
            [
                {"text": "💳 Wallet / Payment", "callback_data": "cat:Wallet / Payment"}
            ],
            [
                {"text": "🌐 Website Issue", "callback_data": "cat:Website Issue"}
            ],
            [
                {"text": "🔙 Main Menu", "callback_data": "menu"}
            ],
        ]
    }


def ticket_keyboard(ticket_id, user_id):
    return {
        "inline_keyboard": [
            [
                {
                    "text": "✉️ Send Message",
                    "callback_data": f"msg:{ticket_id}:{user_id}"
                }
            ],
            [
                {
                    "text": "🔒 Close Ticket",
                    "callback_data": f"close:{ticket_id}:{user_id}"
                }
            ],
            [
                {
                    "text": "🔙 Main Menu",
                    "callback_data": "menu"
                }
            ],
        ]
    }


def admin_keyboard(ticket_id, user_id):
    return {
        "inline_keyboard": [
            [
                {
                    "text": "💬 Reply",
                    "callback_data": f"adminreply:{ticket_id}:{user_id}"
                }
            ],
            [
                {
                    "text": "🔒 Close",
                    "callback_data": f"adminclose:{ticket_id}:{user_id}"
                }
            ],
        ]
    }


# ============================================================
# TICKET DATA
# ============================================================

# Database-free Vercel version.
# Ticket information is kept in Telegram messages rather than
# a persistent database.

def category_prompt(category):
    return (
        f"🎫 <b>{esc(category)}</b>\n\n"
        "Please reply to this message with your problem in one message.\n"
        "You can include useful details, order/ticket IDs, or a screenshot."
    )


def notify_admins(user, category, text):
    username = (
        f"@{user.get('username')}"
        if user.get("username")
        else "No username"
    )

    body = (
        "🎫 <b>New KRYZO Support Ticket</b>\n\n"
        f"<b>User:</b> {esc(user.get('first_name', ''))}\n"
        f"<b>Username:</b> {esc(username)}\n"
        f"<b>User ID:</b> <code>{esc(user.get('id'))}</code>\n"
        f"<b>Category:</b> {esc(category)}\n\n"
        f"<b>Message:</b>\n{esc(text)}"
    )

    results = []

    for admin_id in ADMIN_IDS:
        try:
            results.append(
                tg(
                    "sendMessage",
                    {
                        "chat_id": str(admin_id),
                        "text": body,
                        "parse_mode": "HTML",
                    },
                )
            )
        except Exception:
            pass

    return results


# ============================================================
# UPDATE ROUTER
# ============================================================

def handle_update(update):
    if "callback_query" in update:
        return handle_callback(update["callback_query"])

    if "message" in update:
        return handle_message(update["message"])

    return {"ok": True}


# ============================================================
# MESSAGE HANDLER
# ============================================================

def handle_message(message):
    user = message.get("from", {})
    user_id = user.get("id")
    chat_id = message.get("chat", {}).get("id")
    text = extract_text(message)

    # ----------------------------
    # /start
    # ----------------------------

    if message.get("text") == "/start":
        send_message(
            chat_id,
            "👋 <b>Welcome to KRYZO Help Centre</b>\n\n"
            "Choose the category related to your problem:",
            main_menu(),
        )
        return {"ok": True}

    # ----------------------------
    # /help
    # ----------------------------

    if message.get("text") == "/help":
        send_message(
            chat_id,
            "🆘 <b>KRYZO Help Centre</b>\n\n"
            "Choose a category to create a support ticket.",
            category_menu(),
        )
        return {"ok": True}

    # ----------------------------
    # /cancel
    # ----------------------------

    if message.get("text") == "/cancel":
        send_message(
            chat_id,
            "❌ <b>Cancelled.</b>\n\nChoose an option:",
            main_menu(),
        )
        return {"ok": True}

    # ----------------------------
    # /admin
    # ----------------------------

    if message.get("text") == "/admin":
        if is_admin(user_id):
            send_message(
                chat_id,
                "👑 <b>KRYZO Admin Panel</b>\n\n"
                "New support tickets will appear here automatically.\n\n"
                "Use <b>Reply</b> to reply to the user or "
                "<b>Close</b> to close the ticket.",
            )
        return {"ok": True}

    # ========================================================
    # REPLY TO BOT PROMPT
    # ========================================================

    reply = message.get("reply_to_message")

    if reply and reply.get("from", {}).get("is_bot"):
        prompt = reply.get("text", "")

        # ----------------------------------------------------
        # USER CREATED A NEW TICKET
        # ----------------------------------------------------

        if (
            prompt.startswith("🎫 <b>")
            and "Please reply to this message" in prompt
        ):
            category = prompt.split("<b>", 1)[1].split("</b>", 1)[0]

            results = notify_admins(
                user,
                category,
                text,
            )

            # Use admin alert message ID as ticket number.
            ticket_id = None

            if results:
                ticket_id = (
                    results[0]
                    .get("result", {})
                    .get("message_id")
                )

            if not ticket_id:
                ticket_id = message.get("message_id")

            # Confirm ticket to user.
            send_message(
                chat_id,
                f"✅ <b>Ticket #{ticket_id} created.</b>\n\n"
                "Your request has been sent to the KRYZO support team.\n"
                "An admin will reply here when available.",
                ticket_keyboard(
                    ticket_id,
                    user_id,
                ),
            )

            # Add admin buttons.
            for result in results:
                admin_message_id = (
                    result
                    .get("result", {})
                    .get("message_id")
                )

                admin_chat_id = (
                    result
                    .get("result", {})
                    .get("chat", {})
                    .get("id")
                )

                if admin_message_id and admin_chat_id:
                    try:
                        tg(
                            "editMessageReplyMarkup",
                            {
                                "chat_id": str(admin_chat_id),
                                "message_id": str(admin_message_id),
                                "reply_markup": json.dumps(
                                    admin_keyboard(
                                        ticket_id,
                                        user_id,
                                    )
                                ),
                            },
                        )
                    except Exception:
                        pass

            return {"ok": True}

        # ----------------------------------------------------
        # ADMIN REPLY
        # ----------------------------------------------------

        if prompt.startswith("💬 <b>Admin reply"):
            marker = "USER_ID="

            if marker in prompt and is_admin(user_id):
                target = (
                    prompt
                    .split(marker, 1)[1]
                    .split()[0]
                )

                try:
                    target_id = int(target)

                    send_message(
                        target_id,
                        "💬 <b>KRYZO Support</b>\n\n"
                        + esc(text),
                    )

                    send_message(
                        chat_id,
                        "✅ <b>Reply sent.</b>",
                    )

                except Exception:
                    send_message(
                        chat_id,
                        "❌ <b>Could not send the reply.</b>",
                    )

            return {"ok": True}

        # ----------------------------------------------------
        # USER SENDS ANOTHER MESSAGE FROM TICKET BUTTON
        # ----------------------------------------------------

        if prompt.startswith("✉️ <b>Ticket #"):
            # This version forwards the new message to admins.
            # Ticket ID is extracted from the prompt.
            try:
                ticket_id = (
                    prompt
                    .split("Ticket #", 1)[1]
                    .split("</b>", 1)[0]
                )
            except Exception:
                ticket_id = "Unknown"

            username = (
                f"@{user.get('username')}"
                if user.get("username")
                else "No username"
            )

            body = (
                "💬 <b>New message on KRYZO Ticket</b>\n\n"
                f"<b>Ticket:</b> #{esc(ticket_id)}\n"
                f"<b>User:</b> {esc(user.get('first_name', ''))}\n"
                f"<b>Username:</b> {esc(username)}\n"
                f"<b>User ID:</b> <code>{esc(user_id)}</code>\n\n"
                f"<b>Message:</b>\n{esc(text)}"
            )

            for admin_id in ADMIN_IDS:
                try:
                    tg(
                        "sendMessage",
                        {
                            "chat_id": str(admin_id),
                            "text": body,
                            "parse_mode": "HTML",
                        },
                    )
                except Exception:
                    pass

            send_message(
                chat_id,
                "✅ <b>Message sent to KRYZO Support.</b>",
            )

            return {"ok": True}

    # Normal random message.
    if text and not text.startswith("/"):
        send_message(
            chat_id,
            "👋 Please choose an option from the menu.",
            main_menu(),
        )

    return {"ok": True}


# ============================================================
# CALLBACK HANDLER
# ============================================================

def handle_callback(call):
    callback_id = call.get("id")
    data = call.get("data", "")

    message = call.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")

    user = call.get("from", {})
    user_id = user.get("id")

    try:

        # ----------------------------------------------------
        # MAIN MENU
        # ----------------------------------------------------

        if data == "menu":
            edit_message(
                chat_id,
                message_id,
                "👋 <b>KRYZO Help Centre</b>\n\n"
                "Choose an option:",
                main_menu(),
            )

            answer_callback(callback_id)
            return {"ok": True}

        # ----------------------------------------------------
        # HELP
        # ----------------------------------------------------

        if data == "help":
            edit_message(
                chat_id,
                message_id,
                "🆘 <b>Select your issue category:</b>",
                category_menu(),
            )

            answer_callback(callback_id)
            return {"ok": True}

        # ----------------------------------------------------
        # CATEGORY
        # ----------------------------------------------------

        if data.startswith("cat:"):
            category = data.split(":", 1)[1]

            send_message(
                chat_id,
                category_prompt(category),
                force_reply(),
            )

            answer_callback(callback_id)
            return {"ok": True}

        # ----------------------------------------------------
        # CONTACT ADMIN
        # ----------------------------------------------------

        if data == "contact":

            # Direct support username.
            if SUPPORT_USERNAME:
                text = (
                    "👨‍💻 <b>KRYZO Support</b>\n\n"
                    "Need help? You can create a ticket below "
                    "or contact the support account directly.\n\n"
                    f"📩 <b>Support:</b> @{esc(SUPPORT_USERNAME)}"
                )
            else:
                text = (
                    "👨‍💻 <b>KRYZO Support</b>\n\n"
                    "Please create a support ticket below."
                )

            edit_message(
                chat_id,
                message_id,
                text,
                {
                    "inline_keyboard": [
                        [
                            {
                                "text": "🎫 Create Ticket",
                                "callback_data": "help",
                            }
                        ],
                        [
                            {
                                "text": "🔙 Main Menu",
                                "callback_data": "menu",
                            }
                        ],
                    ],
                },
            )

            answer_callback(callback_id)
            return {"ok": True}

        # ----------------------------------------------------
        # MY TICKETS
        # ----------------------------------------------------

        if data == "tickets":

            edit_message(
                chat_id,
                message_id,
                "🎫 <b>My Tickets</b>\n\n"
                "Your ticket confirmations and support replies "
                "remain in this Telegram chat.\n\n"
                "For a new request, choose <b>Create Ticket</b>.",
                {
                    "inline_keyboard": [
                        [
                            {
                                "text": "🎫 Create Ticket",
                                "callback_data": "help",
                            }
                        ],
                        [
                            {
                                "text": "🔙 Main Menu",
                                "callback_data": "menu",
                            }
                        ],
                    ],
                },
            )

            answer_callback(callback_id)
            return {"ok": True}

        # ----------------------------------------------------
        # USER SEND MESSAGE
        # ----------------------------------------------------

        if data.startswith("msg:"):
            parts = data.split(":")

            if len(parts) == 3:
                ticket_id = parts[1]
                owner_id = int(parts[2])

                if user_id != owner_id:
                    answer_callback(
                        callback_id,
                        "Not your ticket.",
                        True,
                    )
                    return {"ok": True}

                send_message(
                    chat_id,
                    f"✉️ <b>Ticket #{esc(ticket_id)}</b>\n\n"
                    "Reply to this message with your new message.",
                    force_reply(),
                )

                answer_callback(callback_id)
                return {"ok": True}

        # ----------------------------------------------------
        # USER CLOSE TICKET
        # ----------------------------------------------------

        if data.startswith("close:"):
            parts = data.split(":")

            if len(parts) == 3:
                ticket_id = parts[1]
                owner_id = int(parts[2])

                if user_id != owner_id:
                    answer_callback(
                        callback_id,
                        "Not your ticket.",
                        True,
                    )
                    return {"ok": True}

                edit_message(
                    chat_id,
                    message_id,
                    f"🔒 <b>Ticket #{esc(ticket_id)} closed.</b>",
                    main_menu(),
                )

                # Notify admins.
                for admin_id in ADMIN_IDS:
                    try:
                        send_message(
                            admin_id,
                            f"🔒 <b>User closed Ticket #{esc(ticket_id)}.</b>\n\n"
                            f"User ID: <code>{esc(user_id)}</code>",
                        )
                    except Exception:
                        pass

                answer_callback(callback_id)
                return {"ok": True}

        # ----------------------------------------------------
        # ADMIN REPLY
        # ----------------------------------------------------

        if data.startswith("adminreply:"):

            parts = data.split(":")

            if len(parts) == 3 and is_admin(user_id):

                ticket_id = parts[1]
                target_id = int(parts[2])

                prompt = (
                    f"💬 <b>Admin reply for Ticket #{esc(ticket_id)}</b>\n"
                    f"USER_ID={target_id}\n\n"
                    "Reply to this message with the text you want to send."
                )

                send_message(
                    chat_id,
                    prompt,
                    force_reply(),
                )

                answer_callback(callback_id)
                return {"ok": True}

            answer_callback(
                callback_id,
                "Admin only.",
                True,
            )
            return {"ok": True}

        # ----------------------------------------------------
        # ADMIN CLOSE
        # ----------------------------------------------------

        if data.startswith("adminclose:"):

            parts = data.split(":")

            if len(parts) == 3 and is_admin(user_id):

                ticket_id = parts[1]
                target_id = int(parts[2])

                send_message(
                    int(target_id),
                    f"🔒 <b>Ticket #{esc(ticket_id)} has been closed by KRYZO Support.</b>",
                    main_menu(),
                )

                edit_message(
                    chat_id,
                    message_id,
                    f"🔒 <b>Ticket #{esc(ticket_id)} closed.</b>",
                )

                answer_callback(callback_id)
                return {"ok": True}

            answer_callback(
                callback_id,
                "Admin only.",
                True,
            )
            return {"ok": True}

        answer_callback(callback_id)

    except Exception:
        try:
            answer_callback(
                callback_id,
                "Something went wrong.",
                True,
            )
        except Exception:
            pass

    return {"ok": True}


# ============================================================
# VERCEL HTTP HANDLER
# ============================================================

class handler(BaseHTTPRequestHandler):

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode()

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json",
        )
        self.send_header(
            "Content-Length",
            str(len(body)),
        )
        self.end_headers()

        self.wfile.write(body)

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    def do_GET(self):

        if not BOT_TOKEN:
            self._send_json(
                500,
                {
                    "ok": False,
                    "error": "BOT_TOKEN is empty. Add your Telegram bot token in BOT_TOKEN.",
                },
            )
            return

        self._send_json(
            200,
            {
                "ok": True,
                "service": "KRYZO Telegram webhook",
            },
        )

    # --------------------------------------------------------
    # POST - TELEGRAM WEBHOOK
    # --------------------------------------------------------

    def do_POST(self):

        if not BOT_TOKEN:
            self._send_json(
                500,
                {
                    "ok": False,
                    "error": "BOT_TOKEN is empty. Add your Telegram bot token in BOT_TOKEN.",
                },
            )
            return

        # Optional Telegram webhook secret.
        if WEBHOOK_SECRET:
            supplied = self.headers.get(
                "X-Telegram-Bot-Api-Secret-Token",
                "",
            )

            if supplied != WEBHOOK_SECRET:
                self._send_json(
                    403,
                    {
                        "ok": False,
                        "error": "forbidden",
                    },
                )
                return

        try:
            length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )

            raw = self.rfile.read(length)

            update = json.loads(
                raw.decode("utf-8")
            )

            result = handle_update(update)

            self._send_json(
                200,
                result,
            )

        except Exception as e:
            self._send_json(
                500,
                {
                    "ok": False,
                    "error": str(e),
                },
            )

    # --------------------------------------------------------
    # Disable default server logging.
    # --------------------------------------------------------

    def log_message(self, format, *args):
        return
