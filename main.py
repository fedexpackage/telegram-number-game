
import os
import json
import hmac
import hashlib
import threading
import asyncio
import secrets
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from urllib.parse import parse_qsl
from flask import Flask, request, jsonify, send_file
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)

from i18n import t, get_user_lang, DEFAULT_LANG

# =========================================================
# CONFIGURATION
# =========================================================
BOT_TOKEN = os.environ["BOT_TOKEN"]
GOOGLE_SCRIPT_URL = os.environ["GOOGLE_SCRIPT_URL"]
ADMIN_CHAT_ID = os.environ["ADMIN_CHAT_ID"]
PORT = int(os.environ.get("PORT", "10000"))
GAME_URL = os.environ.get("GAME_URL", "https://telegram-number-game-3.onrender.com")

app = Flask(__name__)

# =========================================================
# ÉTATS CONVERSATION
# =========================================================
CLAIM_NOM = 1
CLAIM_TELEPHONE = 2
CLAIM_EMAIL = 3

# =========================================================
# PARTIES EN COURS
# =========================================================
GAMES = {}

# =========================================================
# NOTIFICATION ADMIN
# =========================================================
def notify_admin(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": ADMIN_CHAT_ID,
            "text": message
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            print("Admin notifié:", r.read().decode())
    except Exception as e:
        print("Erreur notification admin:", repr(e))


# =========================================================
# GOOGLE APPS SCRIPT
# =========================================================
def send_to_google(data):
    try:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            GOOGLE_SCRIPT_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            result = r.read().decode("utf-8")
            print("Google:", result)
            return json.loads(result)
    except Exception as e:
        print("Erreur Google:", repr(e))
        return {"success": False}


# =========================================================
# /START
# =========================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return ConversationHandler.END

    lang = get_user_lang(update)
    context.user_data["lang"] = lang

    args = context.args or []

    if args and args[0].lower() == "claim":
        context.user_data.clear()
        context.user_data["lang"] = lang
        await update.message.reply_text(t("claim_intro", lang))
        return CLAIM_NOM

    keyboard = [[
        InlineKeyboardButton(
            t("play_button", lang),
            web_app=WebAppInfo(url=f"{GAME_URL}?lang={lang}")
        )
    ]]
    await update.message.reply_text(
        t("welcome", lang),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


# =========================================================
# RÉCLAMATION — NOM COMPLET
# =========================================================
async def claim_nom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", DEFAULT_LANG)
    nom = update.message.text.strip()

    if not re.fullmatch(r"[A-Za-zÀ-ÿ' -]{2,80}", nom):
        await update.message.reply_text(t("invalid_nom", lang))
        return CLAIM_NOM

    context.user_data["claim_nom"] = nom
    await update.message.reply_text(t("ask_tel", lang))
    return CLAIM_TELEPHONE


# =========================================================
# RÉCLAMATION — TÉLÉPHONE
# =========================================================
async def claim_telephone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", DEFAULT_LANG)
    tel = update.message.text.strip()

    if not re.fullmatch(r"\+?\d[\d\s-]{7,20}", tel):
        await update.message.reply_text(t("invalid_tel", lang))
        return CLAIM_TELEPHONE

    context.user_data["claim_tel"] = tel
    await update.message.reply_text(t("ask_email", lang))
    return CLAIM_EMAIL


# =========================================================
# RÉCLAMATION — EMAIL
# =========================================================
async def claim_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", DEFAULT_LANG)
    email = update.message.text.strip()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        await update.message.reply_text(t("invalid_email", lang))
        return CLAIM_EMAIL

    nom = context.user_data.get("claim_nom", "")
    tel = context.user_data.get("claim_tel", "")
    telegram_id = str(update.effective_user.id)

    response = send_to_google({
        "action": "claim",
        "telegram_id": telegram_id,
        "nom": nom,
        "telephone": tel,
        "email": email
    })

    if response.get("alreadyClaimed"):
        await update.message.reply_text(t("already_claimed", lang))
        context.user_data.clear()
        return ConversationHandler.END

    if not response.get("eligible"):
        await update.message.reply_text(t("not_eligible", lang))
        context.user_data.clear()
        return ConversationHandler.END

    message_admin = (
        "🏆 NOUVELLE RÉCLAMATION DE GAIN\n\n"
        f"Nom : {nom}\n"
        f"Téléphone : {tel}\n"
        f"Email : {email}\n\n"
        f"Telegram ID : {telegram_id}\n\n"
        f"Résultat Google Sheets : {response.get('resultat', '')}"
    )
    notify_admin(message_admin)

    await update.message.reply_text(t("claim_success", lang))
    context.user_data.clear()
    return ConversationHandler.END


# =========================================================
# ANNULATION
# =========================================================
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("lang", DEFAULT_LANG)
    context.user_data.clear()
    if update.message:
        await update.message.reply_text(t("cancelled", lang))
    return ConversationHandler.END


# =========================================================
# LANCEMENT BOT
# =========================================================
async def run_telegram_bot():
    telegram_app = Application.builder().token(BOT_TOKEN).build()

    claim_conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            CLAIM_NOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, claim_nom)],
            CLAIM_TELEPHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, claim_telephone)],
            CLAIM_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, claim_email)],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        conversation_timeout=600
    )

    telegram_app.add_handler(claim_conversation)
    print("Bot Telegram démarré.")
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    await asyncio.Event().wait()


def start_telegram_thread():
    asyncio.run(run_telegram_bot())
