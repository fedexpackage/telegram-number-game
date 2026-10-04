import os
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ["BOT_TOKEN"]
SITE_URL = os.environ["SITE_URL"]

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot en ligne"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎮 Ouvrir le jeu", url=SITE_URL)]
    ]

    await update.message.reply_text(
        "Bienvenue !\n\nClique sur le bouton ci-dessous pour accéder au jeu.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def main():
    threading.Thread(target=run_server, daemon=True).start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    application.run_polling()

if __name__ == "__main__":
    main()
