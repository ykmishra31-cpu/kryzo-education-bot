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
# Flow:
#   ADMIN: create chapter -> send/forward videos -> choose users
#          -> bot generates one private chapter link.
#   USER: opens that link -> if their Telegram ID is allowed,
#         the bot immediately sends all saved videos.
#
# Videos are never downloaded to Vercel. Telegram file_id values
# are stored in memory and reused with sendVideo/sendDocument.
# ============================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

ADMIN_IDS = {
    8814358315,
    8140703825,
    8072943024,
    8691769606,
    6886719955,
}

BOT_USERNAME = "KryzoEducationBot"  # without @
PUBLIC_URL = "https://YOUR-PROJECT.vercel.app"

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# NOTE: Vercel serverless memory is not permanent. A restart/redeploy
# clears these dictionaries. Add persistent storage later for permanent data.
CHAPTERS = {}
SESSIONS = {}


def tg(method, data=None):
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured")

    encoded = urllib.parse.urlencode(data or {}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/{method}",
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=20) as r:
        payload = json.loads(r.read().decode("utf-8"))

    if not payload.get("ok"):
        raise RuntimeError(payload.get("description", "Telegram API error"))

    return payload


def send(chat_id, text, markup=None):
    data = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if markup is not None:
        data["reply_markup"] = json.dumps(markup, ensure_ascii=False)
    return tg("sendMessage", data)


def edit(chat_id, message_id, text, markup=None):
    data = {
        "chat_id": str(chat_id),
        "message_id": str(message_id),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if markup is not None:
        data["reply_markup"] = json.dumps(markup, ensure_ascii=False)
    return tg("editMessageText", data)


def callback(callback_id, text=None, alert=False):
    data = {"callback_query_id": callback_id}
    if text:
        data["text"] = text
    if alert:
        data["show_alert"] = "true"
    return tg("answerCallbackQuery", data)


def esc(value):
    return html.escape(str(value or ""), quote=False)


def is_admin(user_id):
    try:
        return int(user_id) in ADMIN_IDS
    except Exception:
        return False


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
            [{"text": "🆔 My Telegram ID", "callback_data": "myid"}],
        ]
    }


def make_id():
    return secrets.token_urlsafe(7).replace("-", "").replace("_", "")


def make_link(chapter_id):
    return f"https://t.me/{BOT_USERNAME}?start=chapter_{chapter_id}"


def create_chapter(name, owner_id):
    chapter_id = make_id()
    while chapter_id in CHAPTERS:
        chapter_id = make_id()

    CHAPTERS[chapter_id] = {
        "id": chapter_id,
        "name": name.strip(),
        "videos": [],
        "owner": int(owner_id),
        "allowed_users": set(),
    }
    return CHAPTERS[chapter_id]


def video_from_message(message):
    video = message.get("video")
    if video and video.get("file_id"):
        return {
            "type": "video",
            "file_id": video["file_id"],
            "caption": message.get("caption") or "",
        }

    document = message.get("document")
    if document and document.get("file_id"):
        mime = document.get("mime_type") or ""
        if mime.startswith("video/"):
            return {
                "type": "document",
                "file_id": document["file_id"],
                "caption": message.get("caption") or "",
            }

    return None


def send_video(chat_id, item):
    title = item.get("title") or "Lecture"
    caption = f"🎥 <b>{esc(title)}</b>"

    if item["type"] == "video":
        return tg("sendVideo", {
            "chat_id": str(chat_id),
            "video": item["file_id"],
            "caption": caption,
            "parse_mode": "HTML",
        })

    return tg("sendDocument", {
        "chat_id": str(chat_id),
        "document": item["file_id"],
        "caption": caption,
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
        "Sending them now...",
    )

    sent = 0
    for item in chapter["videos"]:
        try:
            send_video(chat_id, item)
            sent += 1
        except Exception:
            pass

    if sent == len(chapter["videos"]):
        send(chat_id, "✅ <b>All lectures have been sent.</b>")
    else:
        send(chat_id, f"⚠️ <b>{sent}/{len(chapter['videos'])}</b> lectures were sent.")


def parse_user_ids(text):
    """Accept comma/space/newline separated numeric Telegram user IDs."""
    raw = (text or "").replace(",", " ").replace(";", " ").split()
    ids = []
    invalid = []
    for part in raw:
        if part.isdigit():
            value = int(part)
            if value > 0:
                ids.append(value)
            else:
                invalid.append(part)
        else:
            invalid.append(part)

    # Keep order but remove duplicates.
    ids = list(dict.fromkeys(ids))
    return ids, invalid


def admin_chapters(chat_id):
    if not CHAPTERS:
        send(chat_id, "📚 <b>My Chapters</b>\n\nNo chapters created yet.", admin_menu())
        return

    for c in CHAPTERS.values():
        allowed = sorted(c.get("allowed_users", set()))
        allowed_text = ", ".join(str(x) for x in allowed) if allowed else "None yet"
        send(
            chat_id,
            f"📚 <b>{esc(c['name'])}</b>\n\n"
            f"🎥 Videos: <b>{len(c['videos'])}</b>\n"
            f"👥 Allowed users: <b>{len(allowed)}</b>\n"
            f"🆔 <code>{esc(c['id'])}</code>\n"
            f"👤 IDs: <code>{esc(allowed_text)}</code>\n\n"
            f"🔗 <b>Private Student Link:</b>\n{esc(make_link(c['id']))}",
        )


def finish_access_setup(user_id, chat_id, text):
    state = SESSIONS.get(user_id)
    if not state or state.get("step") != "access_users":
        return False

    chapter = CHAPTERS.get(state.get("chapter_id"))
    if not chapter:
        SESSIONS.pop(user_id, None)
        send(chat_id, "❌ Chapter session expired.", admin_menu())
        return True

    if text.strip().lower() in {"cancel", "/cancel"}:
        SESSIONS.pop(user_id, None)
        send(chat_id, "❌ Cancelled.", admin_menu())
        return True

    ids, invalid = parse_user_ids(text)
    if not ids:
        send(
            chat_id,
            "❌ No valid Telegram IDs found.\n\n"
            "Send numeric Telegram user IDs separated by commas.\n"
            "Example: <code>8140703825, 6886719955</code>",
        )
        return True

    # The admin automatically has access for testing/management.
    chapter["allowed_users"] = set(ids)
    chapter["allowed_users"].add(int(user_id))

    SESSIONS[user_id] = {"step": "idle"}

    warning = ""
    if invalid:
        warning = f"\n⚠️ Ignored invalid values: <code>{esc(', '.join(invalid))}</code>\n"

    send(
        chat_id,
        f"🎉 <b>Chapter Ready!</b>\n\n"
        f"📚 <b>{esc(chapter['name'])}</b>\n"
        f"🎥 Videos: <b>{len(chapter['videos'])}</b>\n"
        f"👥 Allowed users: <b>{len(chapter['allowed_users'])}</b>\n"
        f"{warning}\n"
        f"🔗 <b>Private Student Link:</b>\n"
        f"<code>{esc(make_link(chapter['id']))}</code>\n\n"
        "Only the Telegram IDs you approved can receive these lectures.\n"
        "If the link is forwarded to someone else, they will be denied.",
        admin_menu(),
    )
    return True


def handle_admin_message(message):
    user_id = message.get("from", {}).get("id")
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text") or ""

    if not is_admin(user_id):
        return False

    if text == "/admin":
        SESSIONS[user_id] = {"step": "idle"}
        send(
            chat_id,
            "👑 <b>KRYZO Education Admin Panel</b>\n\n"
            "Only authorized admins can create chapters, upload videos and decide who gets access.",
            admin_menu(),
        )
        return True

    if text == "/upload":
        SESSIONS[user_id] = {"step": "chapter_name"}
        send(
            chat_id,
            "➕ <b>Upload Chapter</b>\n\n"
            "Send the chapter name.\n\n"
            "Example: <code>Ray Optics</code>",
            admin_menu(),
        )
        return True

    if text == "/cancel":
        SESSIONS.pop(user_id, None)
        send(chat_id, "❌ Cancelled.", admin_menu())
        return True

    # Optional quick command for adding/replacing access later:
    # /allow CHAPTER_ID 123456789 987654321
    if text.startswith("/allow "):
        parts = text.split()
        if len(parts) < 3:
            send(chat_id, "Usage: <code>/allow CHAPTER_ID USER_ID [USER_ID...]</code>")
            return True
        chapter = CHAPTERS.get(parts[1])
        if not chapter:
            send(chat_id, "❌ Chapter not found.")
            return True
        ids, invalid = parse_user_ids(" ".join(parts[2:]))
        if not ids:
            send(chat_id, "❌ No valid Telegram IDs supplied.")
            return True
        chapter["allowed_users"].update(ids)
        send(
            chat_id,
            f"✅ Added <b>{len(ids)}</b> user(s) to <b>{esc(chapter['name'])}</b>.\n"
            f"👥 Total allowed: <b>{len(chapter['allowed_users'])}</b>",
            admin_menu(),
        )
        return True

    if text.startswith("/deny "):
        parts = text.split()
        if len(parts) < 3:
            send(chat_id, "Usage: <code>/deny CHAPTER_ID USER_ID [USER_ID...]</code>")
            return True
        chapter = CHAPTERS.get(parts[1])
        if not chapter:
            send(chat_id, "❌ Chapter not found.")
            return True
        ids, _ = parse_user_ids(" ".join(parts[2:]))
        removed = 0
        for uid in ids:
            if uid in chapter["allowed_users"]:
                chapter["allowed_users"].remove(uid)
                removed += 1
        send(chat_id, f"✅ Removed <b>{removed}</b> user(s) from <b>{esc(chapter['name'])}</b>.", admin_menu())
        return True

    state = SESSIONS.get(user_id)

    if state and state.get("step") == "chapter_name":
        if not text or text.startswith("/"):
            send(chat_id, "Send a chapter name.")
            return True

        chapter = create_chapter(text, user_id)
        SESSIONS[user_id] = {
            "step": "videos",
            "chapter_id": chapter["id"],
        }

        send(
            chat_id,
            f"✅ <b>{esc(chapter['name'])}</b> created.\n\n"
            "Now forward/send all lectures here.\n"
            "You can send them one after another.\n\n"
            "Optional: put the lecture name in the video caption.\n\n"
            "When finished, tap <b>Generate Link</b>.",
            {
                "inline_keyboard": [
                    [{"text": "🔗 Generate Link", "callback_data": "admin:done"}],
                    [{"text": "❌ Cancel", "callback_data": "admin:cancel"}],
                ]
            },
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
                "Send another video or tap <b>Generate Link</b>.",
            )
            return True

        if text:
            send(chat_id, "📹 Please send/forward a video, or tap <b>Generate Link</b>.")
            return True

    if state and state.get("step") == "access_users":
        return finish_access_setup(user_id, chat_id, text)

    return False


def handle_message(message):
    user_id = message.get("from", {}).get("id")
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text") or ""

    if is_admin(user_id) and handle_admin_message(message):
        return {"ok": True}

    if text == "/id":
        send(
            chat_id,
            f"🆔 <b>Your Telegram ID</b>\n\n<code>{esc(user_id)}</code>\n\n"
            "Send this ID to the KRYZO admin if you need access to a chapter.",
            home_menu(),
        )
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
                    "The chapter may have expired or the link is invalid.",
                    home_menu(),
                )
                return {"ok": True}

            if int(user_id) not in chapter.get("allowed_users", set()):
                send(
                    chat_id,
                    "🔒 <b>Access denied.</b>\n\n"
                    "This chapter is private and your Telegram ID has not been approved by the admin.\n\n"
                    f"🆔 Your ID: <code>{esc(user_id)}</code>\n\n"
                    "Send this ID to the admin if you should receive this chapter.",
                    home_menu(),
                )
                return {"ok": True}

            # Authorized users receive the stored videos immediately.
            send_chapter(chat_id, chapter)
            return {"ok": True}

        send(
            chat_id,
            "👋 <b>Welcome to KRYZO Education</b>\n\n"
            "You can only access chapters through a private chapter link approved by the admin.\n\n"
            "If you need access, send <code>/id</code> to get your Telegram ID.",
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
        if data == "myid":
            send(chat_id, f"🆔 <b>Your Telegram ID</b>\n\n<code>{esc(user_id)}</code>")
            callback(callback_id)
            return {"ok": True}

        if data == "home":
            edit(chat_id, message_id, "👋 <b>KRYZO Education</b>\n\nPrivate chapter links are required to receive lectures.", home_menu())
            callback(callback_id)
            return {"ok": True}

        if data == "admin:create" and is_admin(user_id):
            SESSIONS[user_id] = {"step": "chapter_name"}
            send(chat_id, "➕ <b>Create Chapter</b>\n\nSend the chapter name.\n\nExample: <code>Ray Optics</code>")
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

            SESSIONS[user_id] = {
                "step": "access_users",
                "chapter_id": chapter["id"],
            }

            send(
                chat_id,
                f"👥 <b>Who should receive this chapter?</b>\n\n"
                f"📚 <b>{esc(chapter['name'])}</b>\n"
                f"🎥 Videos: <b>{len(chapter['videos'])}</b>\n\n"
                "Send the Telegram user IDs separated by commas.\n"
                "Example:\n<code>8140703825, 6886719955, 8072943024</code>\n\n"
                "Only these IDs will be allowed to receive the videos.\n"
                "You will automatically be included as admin.",
                {
                    "inline_keyboard": [
                        [{"text": "❌ Cancel", "callback_data": "admin:cancel"}],
                    ]
                },
            )
            callback(callback_id)
            return {"ok": True}

        # Admin can also use the button to return to the panel after access setup.
        if data == "admin:panel" and is_admin(user_id):
            SESSIONS[user_id] = {"step": "idle"}
            edit(chat_id, message_id, "👑 <b>KRYZO Education Admin Panel</b>", admin_menu())
            callback(callback_id)
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
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.send_json(200, {
            "ok": True,
            "service": "KRYZO Education Telegram Bot",
            "admin_only_uploads": True,
            "private_chapter_access": True,
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
            self.send_json(500, {"ok": False, "error": str(e)})

    def log_message(self, format, *args):
        return


handler = Handler
