import asyncio
import json
import logging
import os
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from peach_flower import get_peach_flower_info
from activation import ACTIVATION_TEXT
from days_calculator import format_favorable_days, get_activation_datetimes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан!")

OWNER_USERNAME = "astrosista"

# ⬇️ ЭТО ЕДИНСТВЕННОЕ ПРАВИЛЬНОЕ СОЗДАНИЕ bot и dp
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Хранит последний расчёт {user_id: {year_animal, day_animal, year_branch, day_branch}}
_user_peach: dict[int, dict] = {}

# Хранит задачи напоминаний {user_id: [asyncio.Task, ...]}
_reminder_tasks: dict[int, list] = {}

# ─── Выданные вручную доступы ─────────────────────────────────────
_GRANTED_FILE = Path(__file__).parent / "granted_users.json"
_OWNER_FILE   = Path(__file__).parent / "owner_id.json"


def _load_granted() -> set[int]:
    if _GRANTED_FILE.exists():
        try:
            return set(json.loads(_GRANTED_FILE.read_text()))
        except Exception:
            pass
    return set()


def _save_granted(granted: set[int]) -> None:
    _GRANTED_FILE.write_text(json.dumps(list(granted)))


def _load_owner_id() -> int | None:
    if _OWNER_FILE.exists():
        try:
            return json.loads(_OWNER_FILE.read_text())
        except Exception:
            pass
    return None


def _save_owner_id(uid: int) -> None:
    _OWNER_FILE.write_text(json.dumps(uid))


_granted_users: set[int] = _load_granted()
_owner_id: int | None = _load_owner_id()


def _has_access(user_id: int) -> bool:
    """Пользователь оплатил звёздами или получил доступ от владельца."""
    return user_id in _granted_users


class BirthForm(StatesGroup):
    consent = State()
    birth_date = State()
    birth_time = State()
    birth_city = State()


# ───────────────────────── Клавиатуры ──────────────────────────

def consent_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Согласен(а)", callback_data="consent_agree")
    return builder.as_markup()


def result_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🌸 5 способов активизаций", callback_data="show_activation")
    builder.button(text="🌸 Активизация Цветка Персика", callback_data="show_days")
    builder.button(text="🕐 Калькулятор времени", callback_data="show_time_calc")
    builder.button(text="🏠 Определить сектора в помещении", callback_data="show_sectors")
    builder.button(text="💰 Поблагодарить", callback_data="show_donate")
    builder.button(text="🔄 Новый расчёт", callback_data="new_calculation")
    builder.adjust(1)
    return builder.as_markup()


def donate_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🐾 Помочь животным", callback_data="donate_animals")
    builder.button(text="✨ Поддержать развитие проекта", callback_data="donate_project")
    builder.button(text="◀️ Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


# ───────────────────────── Напоминания ──────────────────────────

async def _send_reminder(user_id: int, date_str: str, time_str: str) -> None:
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "🌸 <b>Напоминание об активизации!</b>\n\n"
                "Через 12 часов у Вас благоприятное время для установки активатора:\n\n"
                f"📅 {date_str}\n"
                f"🕐 {time_str}\n\n"
                "Не забудьте поставить активатор в нужный сектор! "
                "Инструкция — кнопка «🌸 5 способов активизаций»."
            ),
            parse_mode="HTML",
            reply_markup=result_keyboard(),
        )
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания user={user_id}: {e}")


async def _delayed_reminder(delay_seconds: float, user_id: int, date_str: str, time_str: str) -> None:
    await asyncio.sleep(delay_seconds)
    await _send_reminder(user_id, date_str, time_str)


def _schedule_reminders(user_id: int, activation_datetimes: list) -> None:
    """Отменяет старые напоминания и ставит новые за 12 часов до каждой активизации."""
    for task in _reminder_tasks.get(user_id, []):
        task.cancel()

    tasks = []
    now_utc = datetime.now(timezone.utc)

    for utc_dt, date_str, time_str in activation_datetimes:
        reminder_utc = utc_dt - timedelta(hours=12)
        delay = (reminder_utc - now_utc).total_seconds()
        if delay > 0:
            task = asyncio.create_task(
                _delayed_reminder(delay, user_id, date_str, time_str)
            )
            tasks.append(task)

    _reminder_tasks[user_id] = tasks
    logger.info(f"Запланировано {len(tasks)} напоминаний для user={user_id}")


# ───────────────────────── Доставка расчёта ──────────────────────

async def _deliver_activation(target: types.Message, user_id: int) -> None:
    """Отправляет расчёт активизации и ставит напоминания."""
    peach = _user_peach.get(user_id)
    if not peach:
        await target.answer(
            "⚠️ Сначала сделайте расчёт Цветка Персика — нажмите /start",
            parse_mode="HTML",
        )
        return

    await target.answer("⏳ Рассчитываю благоприятные дни...")

    try:
        result = format_favorable_days(
            peach["year_animal"],
            peach["day_animal"],
            peach["year_branch"],
            peach["day_branch"],
        )
        await target.answer(result, parse_mode="HTML", reply_markup=result_keyboard())

        # Планируем напоминания за 12 часов до каждой активизации
        activation_times = get_activation_datetimes(
            peach["year_animal"],
            peach["day_animal"],
            peach["year_branch"],
            peach["day_branch"],
        )
        _schedule_reminders(user_id, activation_times)

        if activation_times:
            count = len(activation_times)
            await target.answer(
                f"🔔 Я пришлю Вам напоминание за 12 часов до каждой активизации "
                f"(запланировано: {count}).",
                parse_mode="HTML",
            )

    except Exception as e:
        logger.error(f"Ошибка доставки активизации user={user_id}: {e}", exc_info=True)
        await target.answer(
            f"⚠️ Ошибка расчёта: <code>{str(e)}</code>",
            parse_mode="HTML",
        )


# ───────────────────────── Хэндлеры команд ──────────────────────

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    global _owner_id
    await state.clear()
    # Сохраняем ID владельца при первом /start
    if message.from_user.username == OWNER_USERNAME and _owner_id is None:
        _owner_id = message.from_user.id
        _save_owner_id(_owner_id)
        logger.info(f"Owner ID сохранён: {_owner_id}")
    user_name = message.from_user.first_name or "гость"
    await message.answer(
        f"🌸 Приветствуем Вас, <b>{user_name}</b>!\n\n"
        "С помощью китайской метафизики Вы можете узнать свою символическую звезду "
        "«Цветок Персика» и как её использовать в повседневной жизни. "
        "Дополнительно предлагается услуга <b>«Активизация Цветка Персика»</b>.\n\n"
        "⚠️ <b>Согласие на обработку персональных данных</b>\n\n"
        "Для расчёта необходимо ввести дату и время рождения. "
        "Эти данные используются исключительно для астрологического расчёта "
        "и не передаются третьим лицам.\n\n"
        "Нажимая кнопку «Согласен(а)», Вы подтверждаете своё согласие "
        "на обработку указанных персональных данных в соответствии "
        "с Федеральным законом № 152-ФЗ «О персональных данных».",
        parse_mode="HTML",
        reply_markup=consent_keyboard(),
    )
    await state.set_state(BirthForm.consent)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Справка</b>\n\n"
        "/start — начать расчёт заново\n\n"
        "<b>Формат ввода:</b>\n"
        "• Дата: ДД.ММ.ГГГГ (например: <code>15.03.1990</code>)\n"
        "• Время: ЧЧ:ММ (например: <code>14:30</code>)\n"
        "• Город: название на русском или английском",
        parse_mode="HTML",
    )


# ───────────────────────── FSM: ввод данных ──────────────────────

@dp.callback_query(F.data == "consent_agree")
async def callback_consent_agree(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "✅ Согласие получено.\n\n"
        "Введите <b>дату рождения</b> в формате ДД.ММ.ГГГГ\n"
        "Например: <code>15.03.1990</code>",
        parse_mode="HTML",
    )
    await state.set_state(BirthForm.birth_date)


@dp.message(BirthForm.birth_date)
async def process_birth_date(message: types.Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    try:
        birth_date = datetime.strptime(text, "%d.%m.%Y").date()
        if birth_date.year < 1900 or birth_date > date.today():
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты.\n"
            "Введите дату в формате <b>ДД.ММ.ГГГГ</b>\n"
            "Например: <code>15.03.1990</code>",
            parse_mode="HTML",
        )
        return

    await state.update_data(birth_date=birth_date.isoformat())
    await message.answer(
        f"✅ Дата: <b>{birth_date.strftime('%d.%m.%Y')}</b>\n\n"
        "Теперь введите <b>время рождения</b> в формате ЧЧ:ММ\n"
        "Например: <code>14:30</code>\n\n"
        "Если время неизвестно, введите <code>00:00</code>",
        parse_mode="HTML",
    )
    await state.set_state(BirthForm.birth_time)


@dp.message(BirthForm.birth_time)
async def process_birth_time(message: types.Message, state: FSMContext):
    text = message.text.strip() if message.text else ""
    try:
        birth_time = datetime.strptime(text, "%H:%M").time()
    except ValueError:
        await message.answer(
            "❌ Неверный формат времени.\n"
            "Введите время в формате <b>ЧЧ:ММ</b>\n"
            "Например: <code>14:30</code>",
            parse_mode="HTML",
        )
        return

    await state.update_data(birth_time=birth_time.strftime("%H:%M"))
    await message.answer(
        f"✅ Время: <b>{birth_time.strftime('%H:%M')}</b>\n\n"
        "Введите <b>город рождения</b>\n"
        "Например: <code>Москва</code> или <code>Moscow</code>",
        parse_mode="HTML",
    )
    await state.set_state(BirthForm.birth_city)


@dp.message(BirthForm.birth_city)
async def process_birth_city(message: types.Message, state: FSMContext):
    city = message.text.strip() if message.text else ""
    if not city or len(city) < 2:
        await message.answer("❌ Введите корректное название города.")
        return

    data = await state.get_data()
    await state.clear()

    birth_date = date.fromisoformat(data["birth_date"])
    birth_time = datetime.strptime(data["birth_time"], "%H:%M").time()

    await message.answer("⏳ Рассчитываю...")

    try:
        result, year_animal, day_animal, year_branch, day_branch = get_peach_flower_info(
            birth_date, birth_time, city
        )
        _user_peach[message.from_user.id] = {
            "year_animal": year_animal,
            "day_animal": day_animal,
            "year_branch": year_branch,
            "day_branch": day_branch,
        }
        await message.answer(result, parse_mode="HTML", reply_markup=result_keyboard())
    except Exception as e:
        logger.error(f"Ошибка расчёта: {e}", exc_info=True)
        await message.answer(
            f"⚠️ Произошла ошибка при расчёте:\n<code>{str(e)}</code>\n\n"
            "Попробуйте ещё раз с командой /start",
            parse_mode="HTML",
        )


# ───────────────────────── Разделы меню ──────────────────────────

@dp.callback_query(F.data == "show_activation")
async def callback_show_activation(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        ACTIVATION_TEXT, parse_mode="HTML", reply_markup=result_keyboard()
    )


@dp.callback_query(F.data == "show_time_calc")
async def callback_show_time_calc(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "🕐 <b>Калькулятор времени для активизации</b>\n\n"
        "Часы в расчёте благоприятных дней указаны по пекинскому времени — "
        "но каждый двухчасовой период привязан к Вашему городу.\n\n"
        "По ссылке ниже Вы можете рассчитать точные двухчасовки для своего города: "
        "введите дату и местоположение, и получите время начала каждого часа "
        "по Вашему часовому поясу.\n\n"
        "👉 <a href=\"https://tvoibazi.ru/hours\">tvoibazi.ru/hours</a>\n\n"
        "<i>Зная точное время в своём городе, выбирайте нужный час "
        "и устанавливайте активатор.</i>",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=result_keyboard(),
    )


@dp.callback_query(F.data == "show_sectors")
async def callback_show_sectors(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "🏠 <b>Как определить сектора в помещении</b>\n\n"
        "Посмотрите обучающее видео — в нём подробно показано, "
        "как правильно определить стороны света и найти нужный сектор "
        "в Вашем помещении.\n\n"
        "👉 <a href=\"https://rutube.ru/video/3f5c3af512144a0dd2f644b57c4b374e/\">"
        "Смотреть видео на Rutube</a>\n\n"
        "<i>Видео взято из открытого источника.</i>",
        parse_mode="HTML",
        reply_markup=result_keyboard(),
    )


@dp.callback_query(F.data == "back_to_menu")
async def callback_back_to_menu(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Выберите нужный раздел:",
        reply_markup=result_keyboard(),
    )


@dp.callback_query(F.data == "new_calculation")
async def callback_new_calculation(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "Введите <b>дату рождения</b> в формате ДД.ММ.ГГГГ\n"
        "Например: <code>15.03.1990</code>",
        parse_mode="HTML",
    )
    await state.set_state(BirthForm.birth_date)


# ───────────────────────── Активизация (бесплатно) ───────────────

@dp.callback_query(F.data == "show_days")
async def callback_show_days(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    if not _user_peach.get(user_id):
        await callback.message.answer(
            "⚠️ Сначала сделайте расчёт Цветка Персика — нажмите /start",
            parse_mode="HTML",
        )
        return

    await _deliver_activation(callback.message, user_id)


# ───────────────────────── Донейшен ──────────────────────────────

_QR_ANIMALS  = Path(__file__).parent / "qr_animals.png"
_QR_PROJECT  = Path(__file__).parent / "qr_project.png"


@dp.callback_query(F.data == "show_donate")
async def callback_show_donate(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "💰 <b>Поблагодарить</b>\n\n"
        "Выберите, куда направить Вашу поддержку:",
        parse_mode="HTML",
        reply_markup=donate_keyboard(),
    )


@dp.callback_query(F.data == "donate_animals")
async def callback_donate_animals(callback: types.CallbackQuery):
    await callback.answer()
    link_builder = InlineKeyboardBuilder()
    link_builder.button(
        text="💳 Перейти к переводу",
        url="https://qr.nspk.ru/BS1A003UB187KMB7863RBSJ0VAL538IN",
    )
    await callback.message.answer(
        "🐾 <b>Помочь животным</b>\n\n"
        "«Земля Прайда» строит второй приют для диких животных. "
        "Вы можете оказать помощь в покупке новой земли.\n\n"
        "Спасибо за участие в добром деле! 🙏",
        parse_mode="HTML",
        reply_markup=link_builder.as_markup(),
    )


@dp.callback_query(F.data == "donate_project")
async def callback_donate_project(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "✨ <b>Поддержать развитие проекта</b>\n\n"
        "Если Вам откликается мой проект, то можно поддержать его развитие — "
        "это поможет создавать новые расчёты и функции. 🌸",
        parse_mode="HTML",
    )
    await callback.message.answer_photo(
        photo=FSInputFile(_QR_PROJECT),
        caption="Отсканируйте QR-код для перевода",
    )


# ───────────────────────── Команды владельца ─────────────────────

@dp.message(Command("myid"))
async def cmd_myid(message: types.Message):
    """Любой пользователь может узнать свой Telegram ID."""
    await message.answer(
        f"🆔 Ваш Telegram ID: <code>{message.from_user.id}</code>\n\n"
        "Отправьте этот номер @astrosista, чтобы получить доступ к расчёту.",
        parse_mode="HTML",
    )


@dp.message(Command("grant"))
async def cmd_grant(message: types.Message):
    """Выдать доступ пользователю. Только для @astrosista."""
    global _owner_id
    if message.from_user.username != OWNER_USERNAME:
        return
    if _owner_id is None:
        _owner_id = message.from_user.id
        _save_owner_id(_owner_id)

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        await message.answer(
            "Использование: <code>/grant 123456789</code>",
            parse_mode="HTML",
        )
        return

    uid = int(parts[1])
    _granted_users.add(uid)
    _save_granted(_granted_users)

    # Уведомить пользователя
    notify_builder = InlineKeyboardBuilder()
    notify_builder.button(text="🌸 Получить расчёт", callback_data="show_days")
    try:
        await bot.send_message(
            chat_id=uid,
            text=(
                "🌸 <b>Ваш доступ к расчёту открыт!</b>\n\n"
                "Нажмите кнопку ниже, чтобы получить персональный список "
                "благоприятных дней и часов для активизации Цветка Персика."
            ),
            parse_mode="HTML",
            reply_markup=notify_builder.as_markup(),
        )
        await message.answer(
            f"✅ Доступ выдан и уведомление отправлено пользователю <code>{uid}</code>.",
            parse_mode="HTML",
        )
    except Exception:
        await message.answer(
            f"✅ Доступ выдан пользователю <code>{uid}</code>.\n"
            "⚠️ Уведомить не удалось — пользователь ещё не запускал бота.",
            parse_mode="HTML",
        )


@dp.message(Command("revoke"))
async def cmd_revoke(message: types.Message):
    """Отозвать доступ. Только для @astrosista."""
    if message.from_user.username != OWNER_USERNAME:
        return

    parts = message.text.split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        await message.answer(
            "Использование: <code>/revoke 123456789</code>",
            parse_mode="HTML",
        )
        return

    uid = int(parts[1])
    _granted_users.discard(uid)
    _save_granted(_granted_users)
    await message.answer(f"🚫 Доступ пользователя <code>{uid}</code> отозван.", parse_mode="HTML")


@dp.message(Command("granted"))
async def cmd_granted(message: types.Message):
    """Список всех пользователей с доступом. Только для @astrosista."""
    if message.from_user.username != OWNER_USERNAME:
        return

    if not _granted_users:
        await message.answer("Список пуст — доступ не выдан никому.")
        return

    ids = "\n".join(f"• <code>{uid}</code>" for uid in sorted(_granted_users))
    await message.answer(f"👥 Пользователи с доступом:\n{ids}", parse_mode="HTML")


# ───────────────────────── ЗАПУСК (ЕДИНСТВЕННЫЙ ПРАВИЛЬНЫЙ) ────

# ЯВНЫЙ ЭКСПОРТ ДЛЯ WEB_APP.PY
__all__ = ['bot', 'dp', 'main']

# Убеждаемся, что объекты существуют в глобальной области
# (они уже созданы в начале файла, но на всякий случай)
if 'bot' not in globals():
    bot = Bot(token=BOT_TOKEN)
if 'dp' not in globals():
    dp = Dispatcher(storage=MemoryStorage())

async def main():
    """Главная функция запуска бота."""
    logger.info("Бот запущен...")
    await dp.start_polling(bot)


# ⬇️ ЭТО ДЛЯ ЛОКАЛЬНОГО ЗАПУСКА (НЕ ТРОГАТЬ!)
if __name__ == "__main__":
    asyncio.run(main())
