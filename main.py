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
GAME_URL = os.environ.get("GAME_URL", "")

# =========================================================
# ADMINS AUTORISÉS À REJOUER À L'INFINI
# Variable Render : ADMIN_IDS = "123456789,987654321"
# =========================================================
ADMIN_IDS_STR = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = [x.strip() for x in ADMIN_IDS_STR.split(",") if x.strip()]

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

    # ------- Réclamation -------
    if args and args[0].lower() == "claim":
        context.user_data.clear()
        context.user_data["lang"] = lang
        await update.message.reply_text(t("claim_intro", lang))
        return CLAIM_NOM

    # ------- Jeu -------
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
        "nom_complet": nom,
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
# LANCEMENT BOT TELEGRAM
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


# =========================================================
# VÉRIFICATION TELEGRAM (avec debug)
# =========================================================
def verify_telegram_data(init_data):
    if not init_data:
        print("❌ VERIFY: init_data est vide")
        return False
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = data.pop("hash", None)
        if not received_hash:
            print("❌ VERIFY: pas de hash dans init_data")
            print(f"   init_data reçu: {init_data[:200]}")
            return False

        auth_date = int(data.get("auth_date", 0))
        age = time.time() - auth_date
        print(f"🔍 VERIFY: auth_date age = {age:.0f} secondes")

        if age > 3600:
            print(f"❌ VERIFY: init_data expiré ({age:.0f}s > 3600s)")
            return False

        data_check_string = "\n".join(
            f"{k}={data[k]}" for k in sorted(data)
        )
        secret_key = hmac.new(
            b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
        ).digest()
        calculated = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        print(f"🔍 VERIFY: hash reçu     = {received_hash[:30]}...")
        print(f"🔍 VERIFY: hash calculé  = {calculated[:30]}...")
        print(f"🔍 VERIFY: token utilisé = {BOT_TOKEN[:15]}...")

        result = hmac.compare_digest(calculated, received_hash)
        print(f"🔍 VERIFY: résultat = {result}")
        return result
    except Exception as e:
        print("❌ VERIFY: erreur =", repr(e))
        return False


def get_telegram_user_id(init_data):
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        user = json.loads(data.get("user", "{}"))
        uid = user.get("id")
        return str(uid) if uid else None
    except Exception:
        return None


def get_telegram_lang(init_data):
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        user = json.loads(data.get("user", "{}"))
        code = (user.get("language_code") or "en")[:2]
        return code if code in ("fr", "en", "ar", "pt", "es") else "en"
    except Exception:
        return "en"


# =========================================================
# CORS
# =========================================================
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


# =========================================================
# API : INSCRIPTION DU JOUEUR
# =========================================================
@app.route("/api/register", methods=["POST", "OPTIONS"])
def api_register():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    try:
        body = request.get_json(silent=True) or {}
        init_data = body.get("initData", "")

        print(f"📥 /api/register: initData length = {len(init_data) if init_data else 0}")

        if not init_data:
            return jsonify({"ok": False, "message": "initData manquant"}), 403
        if not verify_telegram_data(init_data):
            return jsonify({"ok": False, "message": "Données Telegram invalides."}), 403

        telegram_id = get_telegram_user_id(init_data)
        lang = get_telegram_lang(init_data)

        nom = str(body.get("nom_complet", "")).strip()
        tel = str(body.get("telephone", "")).strip()
        adresse = str(body.get("adresse", "")).strip()
        email = str(body.get("email", "")).strip()

        if not re.fullmatch(r"[A-Za-zÀ-ÿ' -]{2,80}", nom):
            return jsonify({
                "ok": False,
                "message": t("register_error_nom", lang)
            }), 400

        if not re.fullmatch(r"\+?\d[\d\s-]{7,20}", tel):
            return jsonify({
                "ok": False,
                "message": t("register_error_tel", lang)
            }), 400

        if len(adresse) < 3:
            return jsonify({
                "ok": False,
                "message": t("register_error_adresse", lang)
            }), 400

        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return jsonify({
                "ok": False,
                "message": t("register_error_email", lang)
            }), 400

        response = send_to_google({
            "action": "register",
            "telegram_id": telegram_id,
            "nom_complet": nom,
            "telephone": tel,
            "adresse": adresse,
            "email": email,
            "lang": lang,
            "date": datetime.now(timezone.utc).isoformat()
        })

        if response.get("alreadyRegistered"):
            return jsonify({
                "ok": False,
                "alreadyRegistered": True,
                "message": t("register_already", lang)
            }), 409

        if not response.get("success"):
            return jsonify({
                "ok": False,
                "message": t("error_server", lang)
            }), 502

        return jsonify({
            "ok": True,
            "message": t("register_success", lang)
        }), 200

    except Exception as e:
        print("ERREUR /api/register:", repr(e))
        return jsonify({"ok": False, "message": "Erreur serveur"}), 500


# =========================================================
# API : DÉMARRER UNE PARTIE
# =========================================================
@app.route("/api/start", methods=["POST", "OPTIONS"])
def api_start():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    try:
        body = request.get_json(silent=True) or {}
        init_data = body.get("initData", "")

        if not init_data:
            return jsonify({"ok": False, "message": "initData manquant"}), 403
        if not verify_telegram_data(init_data):
            return jsonify({"ok": False, "message": "Données Telegram invalides."}), 403

        telegram_id = get_telegram_user_id(init_data)
        lang = get_telegram_lang(init_data)

        is_admin = telegram_id in ADMIN_IDS

        if not is_admin:
            check = send_to_google({
                "action": "check",
                "telegram_id": telegram_id
            })

            if not check.get("registered"):
                return jsonify({
                    "ok": False,
                    "notRegistered": True,
                    "message": "Vous devez d'abord vous inscrire."
                }), 403

            if check.get("alreadyPlayed"):
                return jsonify({
                    "ok": False,
                    "message": t("already_played", lang)
                }), 409

        winning = secrets.SystemRandom().sample(range(12), 4)

        GAMES[telegram_id] = {
            "winning": winning,
            "tries_left": 3,
            "played": [],
            "is_admin": is_admin,
            "date": datetime.now(timezone.utc).isoformat()
        }

        return jsonify({
            "ok": True,
            "nb_cases": 12,
            "tries_left": 3,
            "lang": lang,
            "is_admin": is_admin,
            "choose_case": t("choose_case", lang),
            "tries_left_text": t("tries_left", lang, n=3)
        }), 200

    except Exception as e:
        print("ERREUR /api/start:", repr(e))
        return jsonify({"ok": False, "message": "Erreur serveur"}), 500


# =========================================================
# API : JOUER UNE CASE
# =========================================================
@app.route("/api/choose", methods=["POST", "OPTIONS"])
def api_choose():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    try:
        body = request.get_json(silent=True) or {}
        init_data = body.get("initData", "")

        if not verify_telegram_data(init_data):
            return jsonify({"ok": False, "message": "Données Telegram invalides."}), 403

        telegram_id = get_telegram_user_id(init_data)
        lang = get_telegram_lang(init_data)
        partie = GAMES.get(telegram_id)

        if not partie:
            return jsonify({"ok": False, "message": "Aucune partie"}), 400

        if partie["tries_left"] <= 0:
            return jsonify({"ok": False, "message": "Plus d'essais"}), 400

        try:
            case = int(body.get("case"))
            if not (0 <= case <= 11):
                raise ValueError
            if case in partie["played"]:
                return jsonify({"ok": False, "message": "Case déjà jouée"}), 400
        except (TypeError, ValueError):
            return jsonify({"ok": False, "message": "Case invalide"}), 400

        partie["played"].append(case)
        partie["tries_left"] -= 1

        is_admin = partie.get("is_admin", False)

        if case in partie["winning"]:
            if not is_admin:
                send_to_google({
                    "action": "result",
                    "telegram_id": telegram_id,
                    "resultat": "gagne",
                    "case_choisie": case,
                    "tentatives": partie["played"],
                    "lang": lang,
                    "date": datetime.now(timezone.utc).isoformat()
                })
                notify_admin(
                    f"🎉 NOUVEAU GAGNANT\n"
                    f"Telegram ID : {telegram_id}\n"
                    f"Case : {case + 1}\n"
                    f"Langue : {lang}"
                )
            else:
                print(f"[ADMIN TEST] Gagné - ID: {telegram_id}")

            del GAMES[telegram_id]
            return jsonify({
                "ok": True,
                "resultat": "gagne",
                "message": t("case_won", lang, n=case + 1)
            }), 200

        if partie["tries_left"] == 0:
            if not is_admin:
                send_to_google({
                    "action": "result",
                    "telegram_id": telegram_id,
                    "resultat": "perdu",
                    "tentatives": partie["played"],
                    "lang": lang,
                    "date": datetime.now(timezone.utc).isoformat()
                })
            else:
                print(f"[ADMIN TEST] Perdu - ID: {telegram_id}")

            winning_1based = [c + 1 for c in partie["winning"]]
            del GAMES[telegram_id]
            return jsonify({
                "ok": True,
                "resultat": "perdu",
                "winning": winning_1based,
                "message": t("game_lost", lang, cases=winning_1based)
            }), 200

        return jsonify({
            "ok": True,
            "resultat": "en_cours",
            "tries_left": partie["tries_left"],
            "message": t("case_lost", lang, n=case + 1) + " " +
                       t("tries_left", lang, n=partie["tries_left"])
        }), 200

    except Exception as e:
        print("ERREUR /api/choose:", repr(e))
        return jsonify({"ok": False, "message": "Erreur serveur"}), 500


# =========================================================
# PAGE JEU
# =========================================================
@app.route("/", methods=["GET"])
def home():
    return send_file("index.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


# =========================================================
# LANCEMENT
# =========================================================
if __name__ == "__main__":
    print("Flask démarré.")
    print(f"Admins autorisés : {ADMIN_IDS}")
    threading.Thread(target=start_telegram_thread, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
