# KRYZO Education Bot

## 1. Configure the bot

Open `api/index.py` and set:

```python
BOT_TOKEN = "YOUR_BOT_TOKEN"

ADMIN_IDS = {
    8814358315,
}

BOT_USERNAME = "KryzoEducationBot"
PUBLIC_URL = "https://YOUR-PROJECT.vercel.app"
```

Only Telegram numeric IDs in `ADMIN_IDS` can create chapters and add videos.

## 2. Deploy on Vercel

Keep this structure:

```text
api/
  index.py
```

There is intentionally **no vercel.json** in this fixed version.
Vercel automatically detects Python files inside `/api`.

## 3. Set the Telegram webhook

After deployment, set:

```text
https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=https://YOUR-PROJECT.vercel.app/api
```

If an old webhook is already set, first call:

```text
https://api.telegram.org/botYOUR_BOT_TOKEN/deleteWebhook
```

Then set the new webhook again.

## 4. Admin workflow

Open the bot as an admin and send:

`/admin`

Then:

1. Create Chapter
2. Enter chapter name
3. Send/forward videos to the bot
4. Generate Link

The bot gives one chapter link.

Put that link on the matching chapter on your website.

## 5. Student workflow

Student opens the chapter link from your website.

Telegram opens the bot and shows:

**Get All Lectures**

Tapping it sends the videos stored for that chapter.

## Important

The bot does not download videos to Vercel. When an admin sends/forwards a Telegram video, the bot stores its Telegram `file_id`.

This version uses in-memory storage only. Vercel can restart serverless instances, so chapter/video data is not guaranteed to survive a restart or redeploy. Persistent storage is required for permanent production storage.
