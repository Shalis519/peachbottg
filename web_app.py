from flask import Flask
import threading
import asyncio
import os
import sys

# Добавляем папку bot в путь, чтобы импортировать оттуда файлы
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

# Импортируем объект dp (диспетчер) и функцию main из вашего bot.py
# Подстройте имена, если в bot.py они называются иначе
try:
    from bot import dp, bot, main  # предполагаем, что в bot.py есть main()
except ImportError:
    print("Ошибка импорта из bot.py. Проверьте имена.")
    # Заглушка, чтобы сервер запустился
    async def main():
        print("Бот не запущен из-за ошибки импорта.")
    dp = None
    bot = None

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

def run_bot():
    """Запускает основную функцию бота в отдельном потоке."""
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Ошибка при запуске бота: {e}")

if __name__ == "__main__":
    # Запускаем бота в фоновом потоке
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    # Запускаем веб-сервер для Render
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
