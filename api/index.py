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
# Public chapter links:
#   ADMIN: /upload -> chapter name -> send/forward videos
#          -> Generate Link -> link is shown immediately.
#   USER: opens chapter link -> bot sends all videos.
#
# Upload/edit/delete/search are ADMIN ONLY.
#
# IMPORTANT:
# Vercel serverless memory is temporary. CHAPTERS/SESSIONS can be
# lost after a cold start/redeploy. Use persistent storage later
# if you need chapters to survive deployments.
# ============================================================

# Keep the token here if you are using index.py directly.
# Do NOT commit/share this file publicly.
BOT_TOKEN = "8948580898:AAHB0heqE9uOdol1IEOQ1wwH8DYs9N5n7jQ"

ADMIN_IDS = {
    8814358315,
    8140703825,
    8072943024,
    8691769606,
    6886719955,
}

BOT_USERNAME = "KryzoEducationBot"  # without @
PUBLIC_URL = "https://kryzo-education-bot.vercel.app"

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

CHAPTERS = {}
SESSIONS = {}


def tg(method, data=None):
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("BOT_TOKEN is not configured")

    encoded = urllib.parse.urlencode(data or {}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/{method}",
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
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
            [{"text": "➕ Upload Chapter", "callback_data": "admin:create"}],
            [
                {"text": "📚 Chapters", "callback_data": "admin:list"},
                {"text": "🔎 Search", "callback_data": "admin:search"},
            ],
            [
                {"text": "✏️ Edit", "callback_data": "admin:edit"},
                {"text": "🗑 Delete", "callback_data": "admin:delete"},
            ],
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
        "created_by": int(owner_id),
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
        send(
            chat_id,
            f"📚 <b>{esc(chapter['name'])}</b>\n\n"
            "⚠️ No lectures are currently available."
        )
        return

    send(
        chat_id,
        f"📚 <b>{esc(chapter['name'])}</b>\n\n"
        f"🎥 <b>{len(chapter['videos'])}</b> lectures found.\n"
        "Sending them now..."
    )

    sent = 0
    for item in chapter["videos"]:
        try:
            send_video(chat_id, item)
            sent += 1
        except Exception as exc:
            print("send_video error:", repr(exc))

    if sent == len(chapter["videos"]):
        send(chat_id, "✅ <b>All lectures have been sent.</b>")
    else:
        send(
            chat_id,
            f"⚠️ <b>{sent}/{len(chapter['videos'])}</b> lectures were sent."
        )


def chapter_summary(chapter):
    return (
        f"📚 <b>{esc(chapter['name'])}</b>\n"
        f"🎥 Videos: <b>{len(chapter['videos'])}</b>\n"
        f"🆔 Chapter ID: <code>{esc(chapter['id'])}</code>\n"
        f"🌐 <b>Chapter Link:</b>\n"
        f"{esc(make_link(chapter['id']))}"
    )


def chapter_link_menu(chapter_id):
    return {
        "inline_keyboard": [
            [{"text": "🔗 Open Chapter", "url": make_link(chapter_id)}],
            [{"text": "✏️ Edit", "callback_data": f"edit:open:{chapter_id}"}],
            [{"text": "🗑 Delete", "callback_data": f"delete:ask:{chapter_id}"}],
        ]
    }


def admin_chapters(chat_id, query=None):
    chapters = list(CHAPTERS.values())

    if query:
        q = query.strip().lower()
        chapters = [
            c for c in chapters
            if q in c["name"].lower() or q in c["id"].lower()
        ]

    if not chapters:
        if query:
            send(chat_id, f"🔎 No chapters found for <code>{esc(query)}</code>.", admin_menu())
        else:
            send(chat_id, "📚 <b>No chapters created yet.</b>", admin_menu())
        return

    for chapter in chapters:
        send(chat_id, chapter_summary(chapter), chapter_link_menu(chapter["id"]))


def parse_chapter_id(text):
    parts = (text or "").split()
    if len(parts) < 2:
        return None
    return parts[1].strip()


def parse_user_ids(text):
    raw = (text or "").replace(",", " ").replace(";", " ").split()
    ids = []
    for part in raw:
        if part.isdigit() and int(part) > 0:
            ids.append(int(part))
    return list(dict.fromkeys(ids))


def edit_menu(chapter_id):
    return {
        "inline_keyboard": [
            [{"text": "✏️ Rename", "callback_data": f"edit:rename:{chapter_id}"}],
            [{"text": "➕ Add Videos", "callback_data": f"edit:add:{chapter_id}"}],
            [{"text": "🗑 Remove Video", "callback_data": f"edit:remove:{chapter_id}"}],
            [{"text": "🔗 Show Link", "callback_data": f"edit:link:{chapter_id}"}],
            [{"text": "🔙 Admin Panel", "callback_data": "admin:panel"}],
        ]
    }


def delete_confirm_menu(chapter_id):
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Delete", "callback_data": f"delete:yes:{chapter_id}"},
                {"text": "❌ Cancel", "callback_data": "admin:panel"},
            ]
        ]
    }


def handle_admin_command(message):
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
            "Only authorized admins can upload, edit, delete and search chapters.\n"
            "Chapter links are public: anyone with a chapter link can receive its videos.",
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

    if text == "/chapters" or text == "/list":
        admin_chapters(chat_id)
        return True

    if text.startswith("/search"):
        query = text[len("/search"):].strip()
        if not query:
            SESSIONS[user_id] = {"step": "search"}
            send(chat_id, "🔎 Send the chapter name or Chapter ID to search.")
        else:
            admin_chapters(chat_id, query)
        return True

    if text.startswith("/edit"):
        chapter_id = parse_chapter_id(text)
        if not chapter_id:
            send(chat_id, "Usage: <code>/edit CHAPTER_ID</code>\n\nUse /chapters to see IDs.")
            return True

        chapter = CHAPTERS.get(chapter_id)
        if not chapter:
            send(chat_id, "❌ Chapter not found.", admin_menu())
            return True

        send(chat_id, chapter_summary(chapter), edit_menu(chapter_id))
        return True

    if text.startswith("/delete"):
        chapter_id = parse_chapter_id(text)
        if not chapter_id:
            send(chat_id, "Usage: <code>/delete CHAPTER_ID</code>\n\nUse /chapters to see IDs.")
            return True

        chapter = CHAPTERS.get(chapter_id)
        if not chapter:
            send(chat_id, "❌ Chapter not found.", admin_menu())
            return True

        send(
            chat_id,
            f"⚠️ <b>Delete this chapter?</b>\n\n{chapter_summary(chapter)}\n\n"
            "This removes the chapter and its generated link.",
            delete_confirm_menu(chapter_id),
        )
        return True

    if text == "/cancel":
        SESSIONS.pop(user_id, None)
        send(chat_id, "❌ Cancelled.", admin_menu())
        return True

    state = SESSIONS.get(user_id)

    if state and state.get("step") == "search":
        if not text:
            send(chat_id, "Send a search term.")
            return True
        SESSIONS[user_id] = {"step": "idle"}
        admin_chapters(chat_id, text)
        return True

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

    if state and state.get("step") == "edit_rename":
        chapter = CHAPTERS.get(state.get("chapter_id"))
        if not chapter:
            SESSIONS.pop(user_id, None)
            send(chat_id, "❌ Chapter not found.", admin_menu())
            return True
        if not text or text.startswith("/"):
            send(chat_id, "Send the new chapter name.")
            return True
        chapter["name"] = text.strip()
        SESSIONS[user_id] = {"step": "idle"}
        send(chat_id, f"✅ Chapter renamed to <b>{esc(chapter['name'])}</b>.", edit_menu(chapter["id"]))
        return True

    if state and state.get("step") == "edit_add":
        chapter = CHAPTERS.get(state.get("chapter_id"))
        if not chapter:
            SESSIONS.pop(user_id, None)
            send(chat_id, "❌ Chapter not found.", admin_menu())
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
                f"✅ Added <b>{esc(title)}</b>.\n"
                f"Total videos: <b>{len(chapter['videos'])}</b>\n\n"
                "Send another video or tap Done.",
                {
                    "inline_keyboard": [
                        [{"text": "✅ Done", "callback_data": f"edit:adddone:{chapter['id']}"}],
                        [{"text": "❌ Cancel", "callback_data": f"edit:cancel:{chapter['id']}"}],
                    ]
                },
            )
            return True

        send(chat_id, "📹 Send/forward a video.")
        return True

    if state and state.get("step") == "edit_remove":
        chapter = CHAPTERS.get(state.get("chapter_id"))
        if not chapter:
            SESSIONS.pop(user_id, None)
            send(chat_id, "❌ Chapter not found.", admin_menu())
            return True

        if text.isdigit():
            index = int(text) - 1
            if 0 <= index < len(chapter["videos"]):
                removed = chapter["videos"].pop(index)
                SESSIONS[user_id] = {"step": "idle"}
                send(
                    chat_id,
                    f"🗑 Removed <b>{esc(removed.get('title', 'Lecture'))}</b>.\n\n"
                    f"Remaining videos: <b>{len(chapter['videos'])}</b>",
                    edit_menu(chapter["id"]),
                )
            else:
                send(chat_id, "❌ Invalid video number.")
            return True

        send(chat_id, "Send the video number, e.g. <code>3</code>.")
        return True

    return False


def handle_message(message):
    user_id = message.get("from", {}).get("id")
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text") or ""

    if chat_id is None or user_id is None:
        return {"ok": True}

    try:
        if is_admin(user_id) and handle_admin_command(message):
            return {"ok": True}

        if text == "/id":
            send(
                chat_id,
                f"🆔 <b>Your Telegram ID</b>\n\n<code>{esc(user_id)}</code>",
                home_menu(),
            )
            return {"ok": True}

        # Normal users do not get chapter discovery/search.
        # Chapters are accessible only through their generated Telegram links.
        if text.startswith("/search"):
            send(
                chat_id,
                "🔒 <b>Chapter search is admin-only.</b>\n\n"
                "Use the chapter link provided by an admin to access a chapter.",
                home_menu(),
            )
            return {"ok": True}

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
                        "The link may be invalid or the chapter is no longer available.",
                        home_menu(),
                    )
                    return {"ok": True}

                # PUBLIC CHAPTER ACCESS:
                # Anyone who has the chapter link can receive the videos.
                send_chapter(chat_id, chapter)
                return {"ok": True}

            send(
                chat_id,
                "👋 <b>Welcome to KRYZO Education</b>\n\n"
                "Open a chapter link to receive its lectures.\n\n"
                "Only admins can upload, edit, delete or search chapters.",
                home_menu(),
            )
            return {"ok": True}

        return {"ok": True}

    except Exception as exc:
        print("KRYZO message error:", repr(exc))
        try:
            send(chat_id, "❌ <b>Something went wrong.</b> Please try again.")
        except Exception:
            pass
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

        if data == "admin:panel" and is_admin(user_id):
            SESSIONS[user_id] = {"step": "idle"}
            edit(chat_id, message_id, "👑 <b>KRYZO Education Admin Panel</b>", admin_menu())
            callback(callback_id)
            return {"ok": True}

        if data == "admin:create" and is_admin(user_id):
            SESSIONS[user_id] = {"step": "chapter_name"}
            send(
                chat_id,
                "➕ <b>Upload Chapter</b>\n\n"
                "Send the chapter name.\n\n"
                "Example: <code>Ray Optics</code>",
            )
            callback(callback_id)
            return {"ok": True}

        if data == "admin:list" and is_admin(user_id):
            admin_chapters(chat_id)
            callback(callback_id)
            return {"ok": True}

        if data == "admin:search" and is_admin(user_id):
            SESSIONS[user_id] = {"step": "search"}
            send(chat_id, "🔎 Send chapter name or Chapter ID to search.")
            callback(callback_id)
            return {"ok": True}

        if data == "admin:edit" and is_admin(user_id):
            send(
                chat_id,
                "✏️ <b>Edit Chapter</b>\n\n"
                "Send:\n<code>/edit CHAPTER_ID</code>\n\n"
                "Use /chapters to find the ID.",
                admin_menu(),
            )
            callback(callback_id)
            return {"ok": True}

        if data == "admin:delete" and is_admin(user_id):
            send(
                chat_id,
                "🗑 <b>Delete Chapter</b>\n\n"
                "Send:\n<code>/delete CHAPTER_ID</code>\n\n"
                "Use /chapters to find the ID.",
                admin_menu(),
            )
            callback(callback_id)
            return {"ok": True}

        if data == "admin:cancel" and is_admin(user_id):
            SESSIONS.pop(user_id, None)
            send(chat_id, "❌ Cancelled.", admin_menu())
            callback(callback_id)
            return {"ok": True}

        if data == "admin:done" and is_admin(user_id):
            state = SESSIONS.get(user_id)
            if not state or state.get("step") != "videos":
                callback(callback_id, "No active upload.", True)
                return {"ok": True}

            chapter = CHAPTERS.get(state.get("chapter_id"))
            if not chapter:
                SESSIONS.pop(user_id, None)
                callback(callback_id, "Chapter not found.", True)
                return {"ok": True}

            if not chapter["videos"]:
                callback(callback_id, "Add at least one video first.", True)
                return {"ok": True}

            # Public link is generated immediately. No user IDs are requested.
            SESSIONS[user_id] = {"step": "idle"}

            send(
                chat_id,
                "🎉 <b>Chapter Ready!</b>\n\n"
                f"{chapter_summary(chapter)}\n\n"
                "🌐 <b>PUBLIC ACCESS</b>\n"
                "Anyone who has this link can open it and receive the lectures.",
                chapter_link_menu(chapter["id"]),
            )
            callback(callback_id, "Link generated.")
            return {"ok": True}

        if data.startswith("edit:") and is_admin(user_id):
            parts = data.split(":")
            if len(parts) < 3:
                callback(callback_id, "Invalid edit action.", True)
                return {"ok": True}

            action = parts[1]
            chapter_id = parts[2]
            chapter = CHAPTERS.get(chapter_id)

            if not chapter:
                callback(callback_id, "Chapter not found.", True)
                return {"ok": True}

            if action == "open":
                send(chat_id, chapter_summary(chapter), edit_menu(chapter_id))
                callback(callback_id)
                return {"ok": True}

            if action == "rename":
                SESSIONS[user_id] = {"step": "edit_rename", "chapter_id": chapter_id}
                send(chat_id, f"✏️ Send the new name for <b>{esc(chapter['name'])}</b>.")
                callback(callback_id)
                return {"ok": True}

            if action == "add":
                SESSIONS[user_id] = {"step": "edit_add", "chapter_id": chapter_id}
                send(
                    chat_id,
                    f"➕ <b>Add videos</b>\n\n"
                    f"Chapter: <b>{esc(chapter['name'])}</b>\n"
                    f"Current videos: <b>{len(chapter['videos'])}</b>\n\n"
                    "Send/forward videos one by one.",
                    {
                        "inline_keyboard": [
                            [{"text": "❌ Cancel", "callback_data": f"edit:cancel:{chapter_id}"}]
                        ]
                    },
                )
                callback(callback_id)
                return {"ok": True}

            if action == "adddone":
                SESSIONS[user_id] = {"step": "idle"}
                send(chat_id, f"✅ Finished adding videos.\n\n{chapter_summary(chapter)}", edit_menu(chapter_id))
                callback(callback_id)
                return {"ok": True}

            if action == "remove":
                SESSIONS[user_id] = {"step": "edit_remove", "chapter_id": chapter_id}
                if not chapter["videos"]:
                    send(chat_id, "⚠️ This chapter has no videos.", edit_menu(chapter_id))
                else:
                    lines = []
                    for i, item in enumerate(chapter["videos"], 1):
                        lines.append(f"{i}. {esc(item.get('title') or f'Lecture {i}')}")
                    send(
                        chat_id,
                        "🗑 <b>Remove Video</b>\n\n"
                        + "\n".join(lines)
                        + "\n\nSend the video number to remove.",
                    )
                callback(callback_id)
                return {"ok": True}

            if action == "link":
                send(
                    chat_id,
                    f"🔗 <b>Public Chapter Link</b>\n\n{esc(make_link(chapter_id))}",
                    {"inline_keyboard": [[{"text": "🔗 Open Chapter", "url": make_link(chapter_id)}]]},
                )
                callback(callback_id)
                return {"ok": True}

            if action == "cancel":
                SESSIONS[user_id] = {"step": "idle"}
                send(chat_id, "❌ Edit cancelled.", edit_menu(chapter_id))
                callback(callback_id)
                return {"ok": True}

        if data.startswith("delete:ask:") and is_admin(user_id):
            chapter_id = data.split(":", 2)[2]
            chapter = CHAPTERS.get(chapter_id)
            if not chapter:
                callback(callback_id, "Chapter not found.", True)
                return {"ok": True}
            send(
                chat_id,
                f"⚠️ <b>Delete this chapter?</b>\n\n{chapter_summary(chapter)}\n\n"
                "This removes the chapter and its generated link.",
                delete_confirm_menu(chapter_id),
            )
            callback(callback_id)
            return {"ok": True}

        if data.startswith("delete:yes:") and is_admin(user_id):
            chapter_id = data.split(":", 2)[2]
            chapter = CHAPTERS.pop(chapter_id, None)

            if not chapter:
                callback(callback_id, "Chapter not found.", True)
                return {"ok": True}

            SESSIONS[user_id] = {"step": "idle"}
            edit(
                chat_id,
                message_id,
                f"🗑 <b>Chapter deleted.</b>\n\n"
                f"📚 {esc(chapter['name'])}\n"
                f"🎥 Videos removed: <b>{len(chapter['videos'])}</b>",
                admin_menu(),
            )
            callback(callback_id, "Deleted.")
            return {"ok": True}

        if data == "admin:panel" and not is_admin(user_id):
            callback(callback_id, "Not allowed.", True)
            return {"ok": True}

        callback(callback_id)
        return {"ok": True}

    except Exception as exc:
        print("KRYZO callback error:", repr(exc))
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
        self.send_json(
            200,
            {
                "ok": True,
                "service": "KRYZO Education Telegram Bot",
                "admin_only_uploads": True,
                "public_chapter_links": True,
                "chapters": len(CHAPTERS),
            },
        )

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                self.send_json(400, {"ok": False, "error": "empty request"})
                return

            raw = self.rfile.read(length)
            update = json.loads(raw.decode("utf-8"))
            result = handle_update(update)
            self.send_json(200, result)
        except Exception as exc:
            print("KRYZO webhook error:", repr(exc))
            self.send_json(500, {"ok": False, "error": str(exc)})

    def log_message(self, format, *args):
        return


handler = Handler
