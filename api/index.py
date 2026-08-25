import json
import os
import html
import urllib.request
import urllib.parse
import secrets
from http.server import BaseHTTPRequestHandler

# ============================================================
# KRYZO EDUCATION BOT
# Vercel + Telegram
#
# IMPORTANT:
# - Put your bot token below.
# - Put only trusted Telegram numeric IDs in ADMIN_IDS.
# - Videos are NOT downloaded to Vercel.
# - Admin forwards/sends videos to this bot.
# - /done generates ONE chapter link.
#
# NOTE:
# This version uses memory for chapter metadata. For permanent
# storage across Vercel restarts, add a persistent database/KV.
# ============================================================

BOT_TOKEN = "PASTE_YOUR_BOT_TOKEN_HERE"

ADMIN_IDS = {
    8814358315,
    # Add trusted admins here:
    # 123456789,
}

BOT_USERNAME = "KryzoEducationBot"   # without @
PUBLIC_URL = "https://YOUR-PROJECT.vercel.app"

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

CHAPTERS = {}
SESSIONS = {}


def tg(method, data=None):
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("BOT_TOKEN is not configured")

    encoded = urllib.parse.urlencode(data or {}).encode()
    req = urllib.request.Request(
        f"{API}/{method}",
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def send(chat_id, text, markup=None):
    data = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML",
    }

    if markup is not None:
        data["reply_markup"] = json.dumps(markup)

    return tg("sendMessage", data)


def edit(chat_id, message_id, text, markup=None):
    data = {
        "chat_id": str(chat_id),
        "message_id": str(message_id),
        "text": text,
        "parse_mode": "HTML",
    }

    if markup is not None:
        data["reply_markup"] = json.dumps(markup)

    return tg("editMessageText", data)


def callback(callback_id, text=None, alert=False):
    data = {"callback_query_id": callback_id}

    if text:
        data["text"] = text

    if alert:
        data["show_alert"] = "true"

    return tg("answerCallbackQuery", data)


def esc(value):
    return html.escape(str(value or ""))


def is_admin(user_id):
    return user_id in ADMIN_IDS


def admin_menu():
    return {
        "inline_keyboard": [
            [{"text": "➕ Create Chapter", "callback_data": "admin:create"}],
            [{"text": "📚 My Chapters", "callback_data": "admin:list"}],
        ]
    }


def home_menu():
    return {
        "inline_keyboard": [
            [{"text": "📚 Browse Chapters", "callback_data": "browse"}],
        ]
    }


def make_id():
    # Short enough for Telegram callback/deep-link usage.
    return secrets.token_urlsafe(6).replace("-", "").replace("_", "")


def make_link(chapter_id):
    # Website link can be placed directly on the chapter card.
    # The website URL redirects/opens Telegram through /?chapter=...
    # The bot deep link is the actual Telegram delivery link.
    return f"https://t.me/{BOT_USERNAME}?start=chapter_{chapter_id}"


def create_chapter(name):
    chapter_id = make_id()

    while chapter_id in CHAPTERS:
        chapter_id = make_id()

    CHAPTERS[chapter_id] = {
        "id": chapter_id,
        "name": name.strip(),
        "videos": [],
        "owner": None,
    }

    return CHAPTERS[chapter_id]


def video_from_message(message):
    video = message.get("video")
    if video:
        return {
            "type": "video",
            "file_id": video.get("file_id"),
            "caption": message.get("caption") or "",
        }

    document = message.get("document")
    if document:
        mime = document.get("mime_type") or ""
        if mime.startswith("video/"):
            return {
                "type": "document",
                "file_id": document.get("file_id"),
                "caption": message.get("caption") or "",
            }

    return None


def send_video(chat_id, item):
    title = item.get("title") or "Lecture"

    if item["type"] == "video":
        return tg("sendVideo", {
            "chat_id": str(chat_id),
            "video": item["file_id"],
            "caption": f"🎥 <b>{esc(title)}</b>",
            "parse_mode": "HTML",
        })

    return tg("sendDocument", {
        "chat_id": str(chat_id),
        "document": item["file_id"],
        "caption": f"🎥 <b>{esc(title)}</b>",
        "parse_mode": "HTML",
    })


def send_chapter(chat_id, chapter):
    if not chapter["videos"]:
        send(chat_id, f"📚 <b>{esc(chapter['name'])}</b>\n\nNo lectures available.")
        return

    send(
        chat_id,
        f"📚 <b>{esc(chapter['name'])}</b>\n\n"
        f"🎥 <b>{len(chapter['videos'])}</b> lectures found.\n"
        "Sending them now..."
    )

    for item in chapter["videos"]:
        try:
            send_video(chat_id, item)
        except Exception:
            send(chat_id, "⚠️ One lecture could not be sent.")

    send(chat_id, "✅ <b>All available lectures have been sent.</b>")


def admin_chapters(chat_id):
    if not CHAPTERS:
        send(chat_id, "📚 <b>My Chapters</b>\n\nNo chapters created yet.", admin_menu())
        return

    for c in CHAPTERS.values():
        send(
            chat_id,
            f"📚 <b>{esc(c['name'])}</b>\n\n"
            f"🎥 Videos: <b>{len(c['videos'])}</b>\n"
            f"🆔 <code>{esc(c['id'])}</code>\n\n"
            f"🔗 <b>Student Link:</b>\n{esc(make_link(c['id']))}"
        )


def handle_admin_message(message):
    user_id = message.get("from", {}).get("id")
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text") or ""
    state = SESSIONS.get(user_id)

    if not is_admin(user_id):
        return False

    if text == "/admin":
        send(
            chat_id,
            "👑 <b>KRYZO Education Admin Panel</b>\n\n"
            "Only authorized admins can manage chapters and videos.",
            admin_menu(),
        )
        return True

    if text == "/cancel":
        SESSIONS.pop(user_id, None)
        send(chat_id, "❌ Cancelled.", admin_menu())
        return True

    if state and state.get("step") == "chapter_name":
        if not text or text.startswith("/"):
            send(chat_id, "Send a chapter name.")
            return True

        chapter = create_chapter(text)
        chapter["owner"] = user_id

        SESSIONS[user_id] = {
            "step": "videos",
            "chapter_id": chapter["id"],
        }

        send(
            chat_id,
            f"✅ <b>{esc(chapter['name'])}</b> created.\n\n"
            "Now forward/send all lectures here.\n"
            "You can send them one after another.\n\n"
            "Optional: add a caption to a video to use it as the lecture title.\n\n"
            "When finished, tap <b>Generate Link</b> below.",
            {
                "inline_keyboard": [
                    [{"text": "🔗 Generate Link", "callback_data": "admin:done"}],
                    [{"text": "❌ Cancel", "callback_data": "admin:cancel"}],
                ]
            }
        )
        return True

    if state and state.get("step") == "videos":
        chapter = CHAPTERS.get(state.get("chapter_id"))

        if not chapter:
            SESSIONS.pop(user_id, None)
            send(chat_id, "❌ Chapter session expired.", admin_menu())
            return True

        item = video_from_message(message)

        if item:
            title = item["caption"].strip() or f"Lecture {len(chapter['videos']) + 1}"

            chapter["videos"].append({
                "type": item["type"],
                "file_id": item["file_id"],
                "title": title,
            })

            send(
                chat_id,
                f"✅ <b>Lecture {len(chapter['videos'])} added.</b>\n"
                f"{esc(title)}\n\n"
                "Send another video or tap <b>Generate Link</b>."
            )
            return True

        if text:
            send(
                chat_id,
                "📹 Please send/forward a video, or tap <b>Generate Link</b>."
            )
            return True

    return False


def handle_message(message):
    user_id = message.get("from", {}).get("id")
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text") or ""

    if is_admin(user_id) and handle_admin_message(message):
        return {"ok": True}

    # Telegram deep-link:
    # /start chapter_<chapter_id>
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        payload = parts[1] if len(parts) == 2 else ""

        if payload.startswith("chapter_"):
            chapter_id = payload[len("chapter_"):]
            chapter = CHAPTERS.get(chapter_id)

            if not chapter:
                send(
                    chat_id,
                    "❌ <b>Chapter not found.</b>\n\n"
                    "The chapter may have been removed or the link is invalid.",
                    home_menu(),
                )
                return {"ok": True}

            send(
                chat_id,
                f"📚 <b>{esc(chapter['name'])}</b>\n\n"
                f"🎥 {len(chapter['videos'])} lectures available.\n\n"
                "Tap below to receive them.",
                {
                    "inline_keyboard": [
                        [{"text": "▶️ Get All Lectures", "callback_data": f"get:{chapter_id}"}],
                        [{"text": "🏠 Home", "callback_data": "home"}],
                    ]
                }
            )
            return {"ok": True}

        send(
            chat_id,
            "👋 <b>Welcome to KRYZO Education</b>\n\n"
            "Open a chapter link from the KRYZO website.",
            home_menu(),
        )
        return {"ok": True}

    return {"ok": True}


def handle_callback(call):
    callback_id = call.get("id")
    data = call.get("data") or ""
    message = call.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    user_id = call.get("from", {}).get("id")

    try:
        if data == "home":
            edit(
                chat_id,
                message_id,
                "👋 <b>KRYZO Education</b>\n\nChoose an option.",
                home_menu(),
            )
            callback(callback_id)
            return {"ok": True}

        if data == "browse":
            if not CHAPTERS:
                edit(
                    chat_id,
                    message_id,
                    "📚 No chapters are available yet.",
                    home_menu(),
                )
                callback(callback_id)
                return {"ok": True}

            buttons = []
            for c in CHAPTERS.values():
                buttons.append([{
                    "text": f"📚 {c['name']}",
                    "callback_data": f"get:{c['id']}",
                }])

            buttons.append([{
                "text": "🏠 Home",
                "callback_data": "home",
            }])

            edit(
                chat_id,
                message_id,
                "📚 <b>Select a chapter:</b>",
                {"inline_keyboard": buttons},
            )
            callback(callback_id)
            return {"ok": True}

        if data == "admin:create" and is_admin(user_id):
            SESSIONS[user_id] = {"step": "chapter_name"}
            send(
                chat_id,
                "➕ <b>Create Chapter</b>\n\n"
                "Send the chapter name.\n\n"
                "Example: <code>Ray Optics</code>"
            )
            callback(callback_id)
            return {"ok": True}

        if data == "admin:list" and is_admin(user_id):
            admin_chapters(chat_id)
            callback(callback_id)
            return {"ok": True}

        if data == "admin:cancel" and is_admin(user_id):
            SESSIONS.pop(user_id, None)
            send(chat_id, "❌ Chapter creation cancelled.", admin_menu())
            callback(callback_id)
            return {"ok": True}

        if data == "admin:done" and is_admin(user_id):
            state = SESSIONS.get(user_id)

            if not state or state.get("step") != "videos":
                callback(callback_id, "No active chapter.", True)
                return {"ok": True}

            chapter = CHAPTERS.get(state.get("chapter_id"))

            if not chapter:
                SESSIONS.pop(user_id, None)
                callback(callback_id, "Chapter not found.", True)
                return {"ok": True}

            if not chapter["videos"]:
                callback(callback_id, "Add at least one video first.", True)
                return {"ok": True}

            SESSIONS[user_id] = {"step": "idle"}

            send(
                chat_id,
                f"🎉 <b>Chapter Ready!</b>\n\n"
                f"📚 <b>{esc(chapter['name'])}</b>\n"
                f"🎥 Videos: <b>{len(chapter['videos'])}</b>\n\n"
                f"🔗 <b>Website link:</b>\n"
                f"{esc(make_link(chapter['id']))}\n\n"
                "Copy this link and put it on the matching chapter on your website."
            )

            callback(callback_id, "Link generated!")
            return {"ok": True}

        if data.startswith("get:"):
            chapter_id = data.split(":", 1)[1]
            chapter = CHAPTERS.get(chapter_id)

            if not chapter:
                callback(callback_id, "Chapter not found.", True)
                return {"ok": True}

            callback(callback_id)
            send_chapter(chat_id, chapter)
            return {"ok": True}

        callback(callback_id)

    except Exception:
        try:
            callback(callback_id, "Something went wrong.", True)
        except Exception:
            pass

    return {"ok": True}


def handle_update(update):
    if "callback_query" in update:
        return handle_callback(update["callback_query"])

    if "message" in update:
        return handle_message(update["message"])

    return {"ok": True}


class Handler(BaseHTTPRequestHandler):

    def send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.send_json(200, {
            "ok": True,
            "service": "KRYZO Education Telegram Bot",
            "admin_only_uploads": True,
            "chapters": len(CHAPTERS),
        })

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            update = json.loads(raw.decode("utf-8"))
            result = handle_update(update)
            self.send_json(200, result)
        except Exception as e:
            self.send_json(500, {
                "ok": False,
                "error": str(e),
            })

    def log_message(self, format, *args):
        return


# Vercel Python runtime looks for a top-level WSGI-style handler export.
handler = Handler
