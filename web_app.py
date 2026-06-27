import os
import sys
import threading
import asyncio
from flask import Flask

# Ключевая строка: добавляем папку bot в путь поиска
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

# Теперь импорт РАБОТАЕТ
from bot import bot, dp, main

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

def run_bot():
    asyncio.run(main())

if __name__ == "__main__":
    # Запускаем бота в фоновом потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
