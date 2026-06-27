import os
import asyncio
import threading
from flask import Flask

# Импортируем бота из папки bot
from bot import bot, dp, main

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

def run_flask():
    """Запускает Flask-сервер в отдельном потоке."""
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    # Запускаем Flask в фоновом потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем бота в основном потоке (ГЛАВНОЕ ИЗМЕНЕНИЕ)
    print("Запуск бота...")
    asyncio.run(main())  # Теперь бот работает в главном потоке
