import os
import json
import hmac
import hashlib
import threading
import asyncio
import urllib.request
from datetime import datetime, timezone
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes


# =========================
# CONFIGURATION
# =========================

BOT_TOKEN = os.environ["BOT_TOKEN"]
SITE_URL = os.environ["SITE_URL"]
GOOGLE_SCRIPT_URL = os.environ["GOOGLE_SCRIPT_URL"]

PORT = int(os.environ.get("PORT", "10000"))

app = Flask(__name__)


# =========================
# VERIFICATION TELEGRAM
# =========================

def verify_telegram_data(init_data):
    if not init_data:
        return True

    try:
        data = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        received_hash = data.pop("hash", None)

        if not received_hash:
            return False

        data_check_string = "\n".join(
            f"{key}={data[key]}"
            for key in sorted(data)
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode("utf-8"),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(
            calculated_hash,
            received_hash
        )

    except Exception as error:
        print(
            "Erreur vérification Telegram :",
            repr(error)
        )
        return False


# =========================
# GOOGLE APPS SCRIPT
# =========================

def send_to_google(data):
    try:
        payload = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(
            GOOGLE_SCRIPT_URL,
            data=payload,
            headers={
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(
            req,
            timeout=20
        ) as response:

            result = response.read().decode("utf-8")

        print(
            "Réponse Google Apps Script :",
            result
        )

        return True

    except Exception as error:

        print(
            "Erreur Google Apps Script :",
            repr(error)
        )

        return False


def save_to_google_background(data):

    thread = threading.Thread(
        target=send_to_google,
        args=(data,),
        daemon=True
    )

    thread.start()


# =========================
# ROUTE PRINCIPALE
# =========================

@app.route("/", methods=["GET"])
def home():

    return "Bot en ligne", 200


# =========================
# API DU JEU
# =========================

@app.route(
    "/api/game",
    methods=["POST", "OPTIONS"]
)
def game():

    # Gestion CORS
    if request.method == "OPTIONS":

        response = jsonify({
            "ok": True
        })

        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"

        return response

    try:

        body = request.get_json(
            silent=True
        )

        if not body:

            response = jsonify({
                "ok": False,
                "message": "Aucune donnée reçue."
            })

            response.status_code = 400
            response.headers["Access-Control-Allow-Origin"] = "*"

            return response

        print(
            "Données reçues :",
            body
        )

        # =========================
        # VERIFICATION TELEGRAM
        # =========================

        init_data = body.get(
            "initData",
            ""
        )

        if init_data:

            if not verify_telegram_data(
                init_data
            ):

                response = jsonify({
                    "ok": False,
                    "message": "Données Telegram invalides."
                })

                response.status_code = 403
                response.headers["Access-Control-Allow-Origin"] = "*"

                return response

        # =========================
        # DONNEES JOUEUR
        # =========================

        player_data = {

            "nom": body.get(
                "nom",
                ""
            ),

            "prenom": body.get(
                "prenom",
                ""
            ),

            "pays": body.get(
                "pays",
                ""
            ),

            "ville": body.get(
                "ville",
                ""
            ),

            "adresse": body.get(
                "adresse",
                ""
            ),

            "telephone": body.get(
                "telephone",
                ""
            ),

            "resultat": body.get(
                "resultat",
                "jeu_en_cours"
            ),

            "date": datetime.now(
                timezone.utc
            ).isoformat()
        }

        # =========================
        # ENREGISTREMENT EN ARRIERE-PLAN
        # =========================

        save_to_google_background(
            player_data
        )

        # =========================
        # REPONSE IMMEDIATE
        # =========================

        response = jsonify({
            "ok": True,
            "message": "Jeu autorisé."
        })

        response.headers[
            "Access-Control-Allow-Origin"
        ] = "*"

        return response

    except Exception as error:

        print(
            "ERREUR /api/game :",
            repr(error)
        )

        response = jsonify({
            "ok": False,
            "message": "Erreur serveur."
        })

        response.status_code = 500
        response.headers[
            "Access-Control-Allow-Origin"
        ] = "*"

        return response


# =========================
# BOUTON TELEGRAM
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = [[

        InlineKeyboardButton(
            "🎮 Jouer",
            web_app=WebAppInfo(
                url=SITE_URL
            )
        )

    ]]

    reply_markup = InlineKeyboardMarkup(
        keyboard
    )

    await update.message.reply_text(

        "Bienvenue !\n\n"
        "Clique sur le bouton ci-dessous pour commencer.",

        reply_markup=reply_markup
    )


# =========================
# BOT TELEGRAM
# =========================

async def run_bot():

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
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

    await application.initialize()

    await application.start()

    await application.updater.start_polling()

    while True:

        await asyncio.sleep(
            3600
        )


def start_telegram_bot():

    try:

        asyncio.run(
            run_bot()
        )

    except Exception as error:

        print(
            "Bot Telegram arrêté :",
            repr(error)
        )


# =========================
# DEMARRAGE
# =========================

if __name__ == "__main__":

    telegram_thread = threading.Thread(
        target=start_telegram_bot,
        daemon=True
    )

    telegram_thread.start()

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )
