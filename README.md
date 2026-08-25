# KRYZO Education Bot

## 1. Configure

Open `api/index.py` and set:

```python
BOT_TOKEN = "YOUR_BOT_TOKEN"

ADMIN_IDS = {
    8814358315,
}

BOT_USERNAME = "KryzoEducationBot"
```

Do not send your token to anyone.

## 2. Deploy

Upload `api/index.py` and `vercel.json` to your Vercel project and deploy.

## 3. Webhook

After deployment, replace `YOUR_BOT_TOKEN` and `YOUR_VERCEL_URL`:

Delete:
`https://api.telegram.org/botYOUR_BOT_TOKEN/deleteWebhook`

Set:
`https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=YOUR_VERCEL_URL/`

No webhook secret is required.

## 4. Admin workflow

Admin sends:

`/admin`

Then:

Create Chapter
-> enter chapter name
-> forward/send videos
-> tap Generate Link

The bot returns one Telegram link.

Put that link on the matching chapter on the website.

## 5. Students

Student clicks the chapter link.
Telegram opens the bot.
Student taps `Get All Lectures`.
The bot sends all stored Telegram videos.

## Important storage limitation

This version intentionally uses no database and does not download videos.
It stores Telegram `file_id`s in memory.

Vercel serverless instances may restart, so data is not permanent.
For a production system where links must keep working after redeploys/restarts,
persistent storage is required.

Only IDs in ADMIN_IDS can add chapters/videos.
