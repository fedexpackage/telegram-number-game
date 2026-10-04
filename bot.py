import os
import threading
import json
import hmac
import hashlib
import time
import urllib.request
from urllib.parse import parse_qsl
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ["BOT_TOKEN"]
SITE_URL = os.environ["SITE_URL"]
GOOGLE_SCRIPT_URL = os.environ["GOOGLE_SCRIPT_URL"]

app = Flask(__name__)
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response

@app.route("/")
def home():
    return "Bot en ligne"


def verify_telegram_data(init_data):
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        )

        received_hash = data.pop("hash", None)

        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={data[key]}"
            for key in sorted(data)
        )

        secret_key = hmac.new(
    TOKEN.encode(),
    b"WebAppData",
    hashlib.sha256
).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        if time.time() - int(data.get("auth_date", 0)) > 86400:
            return None

        return data

    except Exception:
        return None


@app.route("/api/game", methods=["POST"])
def game():
    try:
        data = request.get_json(force=True)

        init_data = data.get("initData", "")
        telegram_data = verify_telegram_data(init_data)

        if not telegram_data:
            return jsonify({
                "success": False,
                "error": "Session Telegram invalide"
            }), 401

        user_data = json.loads(
            telegram_data.get("user", "{}")
        )

        telegram_id = str(user_data.get("id", ""))

        if not telegram_id:
            return jsonify({
                "success": False,
                "error": "Utilisateur Telegram introuvable"
            }), 400

        payload = {
            "telegram_id": telegram_id,
            "action": data.get("action", ""),
            "nom": data.get("nom", ""),
            "pays": data.get("pays", ""),
            "ville": data.get("ville", ""),
            "adresse": data.get("adresse", ""),
            "telephone": data.get("telephone", ""),
            "numero": data.get("numero", "")
        }

        req = urllib.request.Request(
            GOOGLE_SCRIPT_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        return jsonify(result)

    except Exception as error:
        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [
        [
            InlineKeyboardButton(
                "🎮 Ouvrir le jeu",
                web_app=WebAppInfo(url=SITE_URL)
            )
        ]
    ]

    await update.message.reply_text(
        "Bienvenue !\n\nClique sur le bouton ci-dessous pour accéder au jeu.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


def main():
    threading.Thread(
        target=run_server,
        daemon=True
    ).start()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.run_polling()


if __name__ == "__main__":
    main()
