import os
import json
import hmac
import hashlib
import threading
import asyncio
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


BOT_TOKEN = os.environ["BOT_TOKEN"]
GOOGLE_SCRIPT_URL = os.environ["GOOGLE_SCRIPT_URL"]
ADMIN_CHAT_ID = os.environ["ADMIN_CHAT_ID"]

PORT = int(os.environ.get("PORT", "10000"))

GAME_URL = "https://telegram-number-game-3.onrender.com"

app = Flask(__name__)


# =========================================================
# ÉTAPES DE RÉCLAMATION
# =========================================================

CLAIM_NOM = 1
CLAIM_PRENOM = 2
CLAIM_TELEPHONE = 3


# =========================================================
# NOTIFICATION ADMIN
# =========================================================

def notify_admin(message):
    try:
        url = (
            "https://api.telegram.org/bot"
            + BOT_TOKEN
            + "/sendMessage"
        )

        data = urllib.parse.urlencode({
            "chat_id": ADMIN_CHAT_ID,
            "text": message
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            method="POST"
        )

        with urllib.request.urlopen(
            req,
            timeout=20
        ) as response:

            result = response.read().decode("utf-8")

        print(
            "Notification admin :",
            result
        )

    except Exception as error:
        print(
            "Erreur notification admin :",
            repr(error)
        )


# =========================================================
# GOOGLE APPS SCRIPT
# =========================================================

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


# =========================================================
# /START
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return ConversationHandler.END

    args = context.args

    # -----------------------------------------------------
    # RÉCLAMATION
    # -----------------------------------------------------

    if args and args[0].lower() == "claim":

        context.user_data.clear()

        await update.message.reply_text(
            "🏆 Félicitations !\n\n"
            "Pour réclamer votre gain, "
            "nous devons vérifier votre participation.\n\n"
            "Veuillez indiquer votre NOM."
        )

        return CLAIM_NOM

    # -----------------------------------------------------
    # JEU
    # -----------------------------------------------------

    keyboard = [[
        InlineKeyboardButton(
            "🎮 Jouer",
            web_app=WebAppInfo(
                url=GAME_URL
            )
        )
    ]]

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

    return ConversationHandler.END


# =========================================================
# NOM
# =========================================================

async def claim_nom(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return CLAIM_NOM

    nom = update.message.text.strip()

    if not nom:

        await update.message.reply_text(
            "Veuillez saisir votre nom."
        )

        return CLAIM_NOM

    context.user_data["claim_nom"] = nom

    await update.message.reply_text(
        "Merci.\n\n"
        "Veuillez maintenant indiquer votre PRÉNOM."
    )

    return CLAIM_PRENOM


# =========================================================
# PRÉNOM
# =========================================================

async def claim_prenom(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return CLAIM_PRENOM

    prenom = update.message.text.strip()

    if not prenom:

        await update.message.reply_text(
            "Veuillez saisir votre prénom."
        )

        return CLAIM_PRENOM

    context.user_data["claim_prenom"] = prenom

    await update.message.reply_text(
        "Très bien.\n\n"
        "Veuillez maintenant indiquer votre "
        "NUMÉRO DE TÉLÉPHONE."
    )

    return CLAIM_TELEPHONE


# =========================================================
# TÉLÉPHONE + VALIDATION
# =========================================================

async def claim_telephone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return CLAIM_TELEPHONE

    telephone = update.message.text.strip()

    if not telephone:

        await update.message.reply_text(
            "Veuillez saisir votre numéro de téléphone."
        )

        return CLAIM_TELEPHONE

    nom = context.user_data.get(
        "claim_nom",
        ""
    )

    prenom = context.user_data.get(
        "claim_prenom",
        ""
    )

    telegram_id = str(
        update.effective_user.id
    )

    # -----------------------------------------------------
    # VÉRIFICATION DANS GOOGLE SHEETS
    # -----------------------------------------------------

    response = send_to_google({

        "action": "claim",

        "telegram_id":
            telegram_id,

        "nom":
            nom,

        "prenom":
            prenom,

        "telephone":
            telephone

    })


    # -----------------------------------------------------
    # RÉCLAMATION DÉJÀ FAITE
    # -----------------------------------------------------

    if response.get("alreadyClaimed"):

        await update.message.reply_text(
            "⚠️ Cette réclamation a déjà été "
            "enregistrée.\n\n"
            "Veuillez contacter l'administration "
            "si nécessaire."
        )

        context.user_data.clear()

        return ConversationHandler.END


    # -----------------------------------------------------
    # PAS DE GAIN
    # -----------------------------------------------------

    if not response.get("eligible"):

        await update.message.reply_text(
            "❌ Votre participation ne correspond "
            "pas à un gain validé.\n\n"
            "La réclamation ne peut pas être enregistrée."
        )

        context.user_data.clear()

        return ConversationHandler.END


    # -----------------------------------------------------
    # RÉCLAMATION VALIDÉE
    # -----------------------------------------------------

    message_admin = (

        "🏆 NOUVELLE RÉCLAMATION DE GAIN\n\n"

        "Nom fourni : "
        + nom
        + "\n"

        "Prénom fourni : "
        + prenom
        + "\n"

        "Téléphone fourni : "
        + telephone
        + "\n\n"

        "Telegram ID : "
        + telegram_id
        + "\n\n"

        "Nom enregistré : "
        + str(
            response.get(
                "nom_prenom",
                ""
            )
        )
        + "\n"

        "Pays : "
        + str(
            response.get(
                "pays",
                ""
            )
        )
        + "\n"

        "Ville : "
        + str(
            response.get(
                "ville",
                ""
            )
        )
        + "\n"

        "Téléphone enregistré : "
        + str(
            response.get(
                "telephone",
                ""
            )
        )
        + "\n\n"

        "Résultat : "
        + str(
            response.get(
                "resultat",
                ""
            )
        )

    )

    notify_admin(
        message_admin
    )


    await update.message.reply_text(
        "✅ Votre demande de réclamation "
        "a été enregistrée.\n\n"
        "Vos informations ont été transmises "
        "à l'administration pour vérification "
        "avant l'attribution du gain.\n\n"
        "Merci de patienter."
    )

    context.user_data.clear()

    return ConversationHandler.END


# =========================================================
# ANNULATION
# =========================================================

async def cancel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data.clear()

    if update.message:

        await update.message.reply_text(
            "❌ Réclamation annulée."
        )

    return ConversationHandler.END


# =========================================================
# DÉMARRAGE DU BOT TELEGRAM
# =========================================================

async def run_telegram_bot():

    telegram_app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    claim_conversation = ConversationHandler(

        entry_points=[
            CommandHandler(
                "start",
                start_command
            )
        ],

        states={

            CLAIM_NOM: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    claim_nom
                )
            ],

            CLAIM_PRENOM: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    claim_prenom
                )
            ],

            CLAIM_TELEPHONE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    claim_telephone
                )
            ]

        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_command
            )
        ]

    )

    telegram_app.add_handler(
        claim_conversation
    )

    print(
        "Bot Telegram démarré."
    )

    await telegram_app.initialize()

    await telegram_app.start()

    await telegram_app.updater.start_polling()

    await asyncio.Event().wait()


# =========================================================
# THREAD TELEGRAM
# =========================================================

def start_telegram_thread():

    asyncio.run(
        run_telegram_bot()
    )


# =========================================================
# CORS
# =========================================================

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


# =========================================================
# VÉRIFICATION TELEGRAM WEB APP
# =========================================================

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


# =========================================================
# ID TELEGRAM
# =========================================================

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

        user_id = user.get(
            "id"
        )

        if user_id is None:
            return None

        return str(user_id)

    except Exception as error:

        print(
            "Erreur récupération Telegram ID :",
            repr(error)
        )

        return None


# =========================================================
# API DU JEU
# =========================================================

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


        # -------------------------------------------------
        # DÉBUT PARTICIPATION
        # -------------------------------------------------

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
                        "🚫 Vous avez déjà participé "
                        "à ce jeu. Une seule "
                        "participation est autorisée."

                }), 409


            if not response.get(
                "success"
            ):

                return jsonify({

                    "ok": False,

                    "message":
                        response.get(
                            "message",
                            "Impossible d'autoriser "
                            "la participation."
                        )

                }), 502


            return jsonify({

                "ok": True,

                "message":
                    "Jeu autorisé."

            }), 200


        # -------------------------------------------------
        # RÉSULTAT FINAL
        # -------------------------------------------------

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
                    "Impossible d'enregistrer "
                    "le résultat."

            }), 502


        # -------------------------------------------------
        # NOTIFICATION GAGNANT
        # -------------------------------------------------

        if resultat == "gagne":

            notify_admin(

                "🎉 NOUVEAU GAGNANT\n\n"

                "Nom : "
                + nom
                + "\n"

                "Prénom : "
                + prenom
                + "\n"

                "Téléphone : "
                + str(
                    body.get(
                        "telephone",
                        ""
                    )
                )
                + "\n\n"

                "Telegram ID : "
                + telegram_id
                + "\n\n"

                "Résultat : GAGNÉ"

            )


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


# =========================================================
# PAGE DU JEU
# =========================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return send_file(
        "index.html"
    )


# =========================================================
# HEALTH CHECK
# =========================================================

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


# =========================================================
# LANCEMENT
# =========================================================

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
