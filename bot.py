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
GOOGLE_SCRIPT_URL = os.environ["GOOGLE_SCRIPT_URL"]

PORT = int(os.environ.get("PORT", "10000"))

# Adresse de ton jeu
GAME_URL = "https://telegram-number-game-3.onrender.com"

app = Flask(__name__)


# =========================
# BOT TELEGRAM
# =========================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = [
        [
            InlineKeyboardButton(
                "🎮 Jouer",
                web_app=WebAppInfo(url=GAME_URL)
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(
        keyboard
    )

    await update.message.reply_text(
        "🎉 Bienvenue !\n\n"
        "Vous êtes invité à participer à notre jeu.\n\n"
        "Cliquez sur le bouton ci-dessous pour commencer.",
        reply_markup=reply_markup
    )


async def run_telegram_bot():

    telegram_app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    telegram_app.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    print("Bot Telegram démarré.")

    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()

    # Garder le bot actif
    await asyncio.Event().wait()


def start_telegram_thread():

    asyncio.run(
        run_telegram_bot()
    )


# =========================
# CORS
# =========================

@app.after_request
def add_cors_headers(response):

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"

    return response


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

        received_hash = data.pop(
            "hash",
            None
        )

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
# ENVOI GOOGLE SHEETS
# =========================

def send_to_google(data):

    try:

        payload = json.dumps(
            data
        ).encode("utf-8")

        req = urllib.request.Request(
            GOOGLE_SCRIPT_URL,
            data=payload,
            headers={
                "Content-Type":
                    "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(
            req,
            timeout=20
        ) as response:

            result = response.read().decode(
                "utf-8"
            )

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
# PAGE PRINCIPALE
# =========================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "ok": True,
        "message": "Serveur du jeu en ligne."
    })


# =========================
# TEST SERVEUR
# =========================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "ok": True,
        "message": "Serveur opérationnel."
    })


# =========================
# API DU JEU
# =========================

@app.route(
    "/api/game",
    methods=["POST", "OPTIONS"]
)
def game():

    if request.method == "OPTIONS":

        return jsonify({
            "ok": True
        })

    try:

        body = request.get_json(
            silent=True
        )

        if not body:

            return jsonify({
                "ok": False,
                "message":
                    "Aucune donnée reçue."
            }), 400

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

                return jsonify({
                    "ok": False,
                    "message":
                        "Données Telegram invalides."
                }), 403

        # =========================
        # DONNEES JOUEUR
        # =========================

        player_data = {

            "nom":
                body.get(
                    "nom",
                    ""
                ),

            "prenom":
                body.get(
                    "prenom",
                    ""
                ),

            "pays":
                body.get(
                    "pays",
                    ""
                ),

            "ville":
                body.get(
                    "ville",
                    ""
                ),

            "adresse":
                body.get(
                    "adresse",
                    ""
                ),

            "telephone":
                body.get(
                    "telephone",
                    ""
                ),

            "resultat":
                body.get(
                    "resultat",
                    "jeu_en_cours"
                ),

            "date":
                datetime.now(
                    timezone.utc
                ).isoformat()
        }

        # =========================
        # SAUVEGARDE GOOGLE
        # =========================

        save_to_google_background(
            player_data
        )

        # =========================
        # REPONSE AU SITE
        # =========================

        return jsonify({

            "ok": True,

            "message":
                "Jeu autorisé."

        }), 200

    except Exception as error:

        print(
            "ERREUR /api/game :",
            repr(error)
        )

        return jsonify({

            "ok": False,

            "message":
                "Erreur serveur."

        }), 500


# =========================
# DEMARRAGE
# =========================

if __name__ == "__main__":

    print(
        "Serveur Flask démarré."
    )

    # Démarrage du bot Telegram
    telegram_thread = threading.Thread(
        target=start_telegram_thread,
        daemon=True
    )

    telegram_thread.start()

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )
