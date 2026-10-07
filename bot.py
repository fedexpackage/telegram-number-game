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

GOOGLE_SCRIPT_URL = os.environ["GOOGLE_SCRIPT_URL"]

PORT = int(
    os.environ.get("PORT", "10000")
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

def verify_telegram_data(init_data):

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
# TELEGRAM ID
# =========================

def get_telegram_user_id(init_data):

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

        user_id = user.get("id")

        if user_id is None:
            return None

        return str(user_id)

    except Exception as error:

        print(
            "Erreur récupération Telegram ID :",
            repr(error)
        )

        return None


# =========================
# GOOGLE SHEETS
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

        return json.loads(result)

    except Exception as error:

        print(
            "Erreur Google Apps Script :",
            repr(error)
        )

        return {
            "success": False,
            "message":
                "Erreur de communication avec Google Sheets."
        }


# =========================
# PAGE PRINCIPALE
# =========================

@app.route("/", methods=["GET"])
def home():

    return send_file("index.html")


# =========================
# HEALTH
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
        # DONNEES
        # =========================

        nom = str(
            body.get("nom", "")
        ).strip()

        prenom = str(
            body.get("prenom", "")
        ).strip()

        nom_prenom = (
            nom + " " + prenom
        ).strip()


        resultat = body.get(
            "resultat",
            "jeu_en_cours"
        )


        player_data = {

            "telegram_id":
                telegram_id,

            "nom_prenom":
                nom_prenom,

            "pays":
                body.get("pays", ""),

            "ville":
                body.get("ville", ""),

            "adresse":
                body.get("adresse", ""),

            "telephone":
                body.get("telephone", ""),

            "tentative1":
                body.get("tentative1", ""),

            "tentative2":
                body.get("tentative2", ""),

            "tentative3":
                body.get("tentative3", ""),

            "resultat":
                resultat,

            "date":
                datetime.now(
                    timezone.utc
                ).isoformat()
        }


        # =========================
        # NOUVELLE PARTICIPATION
        # =========================

        if resultat == "jeu_en_cours":

            response = send_to_google({

                "action":
                    "start",

                **player_data

            })


            if response.get(
                "alreadyPlayed"
            ):

                return jsonify({

                    "ok": False,

                    "message":
                        "🚫 Vous avez déjà participé à ce jeu. Une seule participation est autorisée."

                }), 409


            if not response.get(
                "success"
            ):

                return jsonify({

                    "ok": False,

                    "message":
                        response.get(
                            "message",
                            "Impossible d'autoriser la participation."
                        )

                }), 502


            return jsonify({

                "ok": True,

                "message":
                    "Jeu autorisé."

            }), 200


        # =========================
        # RESULTAT FINAL
        # =========================

        response = send_to_google({

            "action":
                "result",

            **player_data

        })


        if not response.get(
            "success"
        ):

            return jsonify({

                "ok": False,

                "message":
                    "Impossible d'enregistrer le résultat."

            }), 502


        return jsonify({

            "ok": True,

            "message":
                "Résultat enregistré."

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
