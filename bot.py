import os
import json
import hmac
import hashlib
import threading
import asyncio
import urllib.request

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
    ContextTypes
)


# =========================
# CONFIGURATION
# =========================

BOT_TOKEN = os.environ["BOT_TOKEN"]

GOOGLE_SCRIPT_URL = os.environ[
    "GOOGLE_SCRIPT_URL"
]

PORT = int(
    os.environ.get(
        "PORT",
        "10000"
    )
)

GAME_URL = (
    "https://telegram-number-game-3.onrender.com"
)

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
                web_app=WebAppInfo(
                    url=GAME_URL
                )
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(
        keyboard
    )

    await update.message.reply_text(
        "🎉 Bienvenue !\n\n"
        "Vous êtes invité à participer "
        "à notre jeu.\n\n"
        "Cliquez sur le bouton ci-dessous "
        "pour commencer.",
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

    print(
        "Bot Telegram démarré."
    )

    await telegram_app.initialize()

    await telegram_app.start()

    await telegram_app.updater.start_polling()

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

    response.headers[
        "Access-Control-Allow-Origin"
    ] = "*"

    response.headers[
        "Access-Control-Allow-Headers"
    ] = "Content-Type"

    response.headers[
        "Access-Control-Allow-Methods"
    ] = "GET, POST, OPTIONS"

    return response


# =========================
# VERIFICATION TELEGRAM
# =========================

def verify_telegram_data(
    init_data
):

    if not init_data:
        return False

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
            BOT_TOKEN.encode(
                "utf-8"
            ),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(
                "utf-8"
            ),
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
# RECUPERER TELEGRAM ID
# =========================

def get_telegram_user_id(
    init_data
):

    try:

        data = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        user_data = data.get(
            "user",
            ""
        )

        if not user_data:
            return None

        user = json.loads(
            user_data
        )

        telegram_id = user.get(
            "id"
        )

        if telegram_id is None:
            return None

        return str(
            telegram_id
        )

    except Exception as error:

        print(
            "Erreur récupération Telegram ID :",
            repr(error)
        )

        return None


# =========================
# ENVOI GOOGLE SHEETS
# =========================

def send_to_google(
    data
):

    try:

        payload = json.dumps(
            data
        ).encode(
            "utf-8"
        )

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

        try:

            return json.loads(
                result
            )

        except Exception:

            return {
                "success": False,
                "message":
                    "Réponse Google invalide."
            }

    except Exception as error:

        print(
            "Erreur Google Apps Script :",
            repr(error)
        )

        return {
            "success": False,
            "message":
                "Impossible de contacter Google Sheets."
        }


# =========================
# PAGE PRINCIPALE
# =========================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return send_file(
        "index.html"
    )


# =========================
# TEST SERVEUR
# =========================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "ok": True,

        "message":
            "Serveur opérationnel."

    })


# =========================
# API DU JEU
# =========================

@app.route(
    "/api/game",
    methods=[
        "POST",
        "OPTIONS"
    ]
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
        # TELEGRAM
        # =========================

        init_data = body.get(
            "initData",
            ""
        )

        if not init_data:

            return jsonify({

                "ok": False,

                "message":
                    "Veuillez ouvrir le jeu depuis Telegram."

            }), 403


        if not verify_telegram_data(
            init_data
        ):

            return jsonify({

                "ok": False,

                "message":
                    "Données Telegram invalides."

            }), 403


        telegram_id = get_telegram_user_id(
            init_data
        )


        if not telegram_id:

            return jsonify({

                "ok": False,

                "message":
                    "Identifiant Telegram introuvable."

            }), 403


        # =========================
        # DONNEES JOUEUR
        # =========================

        nom = body.get(
            "nom",
            ""
        )

        prenom = body.get(
            "prenom",
            ""
        )

        nom_prenom = (
            str(nom).strip()
            + " "
            + str(prenom).strip()
        ).strip()


        player_data = {

            "telegram_id":
                telegram_id,

            "nom_prenom":
                nom_prenom,

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
        # DEBUT DE PARTIE
        # =========================

        if (
            player_data["resultat"]
            == "jeu_en_cours"
        ):

            google_data = {

                "action":
