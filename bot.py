import os
import json
import hmac
import hashlib
import time
import threading
import urllib.request

from urllib.parse import parse_qsl

from flask import Flask, request, jsonify

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo
)

from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)


# ============================================================
# CONFIGURATION
# ============================================================

TOKEN = os.environ["BOT_TOKEN"]
SITE_URL = os.environ["SITE_URL"]
GOOGLE_SCRIPT_URL = os.environ["GOOGLE_SCRIPT_URL"]


# ============================================================
# SERVEUR WEB
# ============================================================

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


@app.route("/", methods=["GET"])
def home():
    return "Bot en ligne"


# ============================================================
# VERIFICATION TELEGRAM MINI APP
# ============================================================

def verify_telegram_data(init_data):
    try:
        if not init_data:
            return None

        data = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        received_hash = data.pop("hash", None)

        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={data[key]}"
            for key in sorted(data)
        )

        secret_key = hmac.new(
            b"WebAppData",
            TOKEN.encode("utf-8"),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash
        ):
            return None

        auth_date = int(
            data.get("auth_date", "0")
        )

        if auth_date <= 0:
            return None

        if time.time() - auth_date > 86400:
            return None

        return data

    except Exception as error:
        print("Erreur vérification Telegram :", str(error))
        return None


# ============================================================
# API DU JEU
# ============================================================

@app.route(
    "/api/game",
    methods=["POST", "OPTIONS"]
)
def game():

    if request.method == "OPTIONS":
        return jsonify({
            "success": True
        })

    try:

        data = request.get_json(force=True)

        if not data:
            return jsonify({
                "success": False,
                "error": "Données manquantes"
            }), 400

        init_data = data.get(
            "initData",
            ""
        )

        telegram_data = verify_telegram_data(
            init_data
        )

        if not telegram_data:
            return jsonify({
                "success": False,
                "error": "Session Telegram invalide"
            }), 401

        user_raw = telegram_data.get(
            "user",
            ""
        )

        if not user_raw:
            return jsonify({
                "success": False,
                "error": "Utilisateur Telegram introuvable"
            }), 400

        try:
            user_data = json.loads(
                user_raw
            )
        except Exception:
            return jsonify({
                "success": False,
                "error": "Données utilisateur Telegram invalides"
            }), 400

        telegram_id = str(
            user_data.get("id", "")
        )

        if not telegram_id:
            return jsonify({
                "success": False,
                "error": "ID Telegram introuvable"
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

        request_data = json.dumps(
            payload
        ).encode("utf-8")

        google_request = urllib.request.Request(
            GOOGLE_SCRIPT_URL,
            data=request_data,
            headers={
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(
            google_request,
            timeout=20
        ) as response:

            response_text = (
                response
                .read()
                .decode("utf-8")
            )

        result = json.loads(
            response_text
        )

        return jsonify(result)

    except Exception as error:

        print(
            "ERREUR API :",
            str(error)
        )

        return jsonify({
            "success": False,
            "error": "Erreur interne du serveur"
        }), 500


# ============================================================
# COMMANDE /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = [
        [
            InlineKeyboardButton(
                "🎮 Ouvrir le jeu",
                web_app=WebAppInfo(
                    url=SITE_URL
                )
            )
        ]
    ]

    await update.message.reply_text(
        "Bienvenue !\n\n"
        "Clique sur le bouton ci-dessous "
        "pour accéder au jeu.",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# SERVEUR FLASK
# ============================================================

def run_server():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


# ============================================================
# BOT TELEGRAM
# ============================================================

def main():

    server_thread = threading.Thread(
        target=run_server,
        daemon=True
    )

    server_thread.start()

    application = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    print(
        "Bot Telegram démarré."
    )

    application.run_polling()


# ============================================================
# LANCEMENT
# ============================================================

if __name__ == "__main__":
    main()
