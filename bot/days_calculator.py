"""
Расчёт благоприятных дней и часов для активизации Цветка Персика.

ДНИ   — собственный день Цветка Персика + день его Слияния (六合).
ЧАСЫ  — для собственных дней: Слияние+Союз+Сезон с Благородным (天乙贵人).
         для дней Слияния: только Благородный.
ИСКЛЮЧЕНИЯ:
  — Пустой час (旬空) и Нежелательный час (六害 Вред ветвей).
  — Часы, конфликтующие с годом и днём рождения человека.
  — День Слияния, если его ветвь конфликтует с годом/днём рождения.
  — Дни, конфликтующие с текущим годом или текущим месяцем.
"""

from datetime import date, timedelta, datetime, timezone
from lunar_python import Solar

MONTHS_RU = [
    '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
]
WEEKDAYS_RU = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']

BRANCH_RU_NOM = {
    '子': 'Крыса', '丑': 'Бык', '寅': 'Тигр', '卯': 'Кролик',
    '辰': 'Дракон', '巳': 'Змея', '午': 'Лошадь', '未': 'Коза',
    '申': 'Обезьяна', '酉': 'Петух', '戌': 'Собака', '亥': 'Свинья',
}

PEACH_ANIMAL_TO_BRANCH = {
    'Крыса':  '子',
    'Лошадь': '午',
    'Кролик': '卯',
    'Петух':  '酉',
}

PEACH_ANIMAL_SECTOR = {
    'Крыса':  ('Север-2',  '352.6°–7.5°'),
    'Лошадь': ('Юг-2',     '172.6°–187.5°'),
    'Кролик': ('Восток-2', '82.6°–97.5°'),
    'Петух':  ('Запад-2',  '262.6°–277.5°'),
}

SIX_HARMONY = {
    '子': '丑', '丑': '子', '寅': '亥', '亥': '寅',
    '卯': '戌', '戌': '卯', '辰': '酉', '酉': '辰',
    '巳': '申', '申': '巳', '午': '未', '未': '午',
}

TRIPLE_HARMONY = {
    '子': ['辰', '申'], '丑': ['巳', '酉'], '寅': ['午', '戌'],
    '卯': ['未', '亥'], '辰': ['子', '申'], '巳': ['丑', '酉'],
    '午': ['寅', '戌'], '未': ['卯', '亥'], '申': ['子', '辰'],
    '酉': ['丑', '巳'], '戌': ['寅', '午'], '亥': ['卯', '未'],
}

SEASONAL = {
    '子': ['亥', '丑'], '丑': ['亥', '子'], '亥': ['子', '丑'],
    '寅': ['卯', '辰'], '卯': ['寅', '辰'], '辰': ['寅', '卯'],
    '巳': ['午', '未'], '午': ['巳', '未'], '未': ['巳', '午'],
    '申': ['酉', '戌'], '酉': ['申', '戌'], '戌': ['申', '酉'],
}

# Конфликты ветвей (六冲 Шесть столкновений)
SIX_CLASHES = {
    '子': '午', '午': '子', '丑': '未', '未': '丑',
    '寅': '申', '申': '寅', '卯': '酉', '酉': '卯',
    '辰': '戌', '戌': '辰', '巳': '亥', '亥': '巳',
}

# Вред ветвей (六害 Liù Hài) — нежелательный час
SIX_HARMS = {
    '子': '未', '未': '子',
    '丑': '午', '午': '丑',
    '寅': '巳', '巳': '寅',
    '卯': '辰', '辰': '卯',
    '申': '亥', '亥': '申',
    '酉': '戌', '戌': '酉',
}

# Благородный (天乙贵人): стебель дня → ветви с Благородным
GUIREN = {
    '甲': {'丑', '未'}, '乙': {'子', '申'},
    '丙': {'亥', '酉'}, '丁': {'亥', '酉'},
    '戊': {'丑', '未'}, '己': {'子', '申'},
    '庚': {'寅', '午'}, '辛': {'寅', '午'},
    '壬': {'卯', '巳'}, '癸': {'卯', '巳'},
}

# Пустой час (旬空 Xūnkōng)
STEM_IDX = {'甲': 0, '乙': 1, '丙': 2, '丁': 3, '戊': 4,
            '己': 5, '庚': 6, '辛': 7, '壬': 8, '癸': 9}
BRANCH_IDX = {'子': 0, '丑': 1, '寅': 2, '卯': 3, '辰': 4, '巳': 5,
              '午': 6, '未': 7, '申': 8, '酉': 9, '戌': 10, '亥': 11}

XUN_EMPTY = {
    0: {'戌', '亥'},
    1: {'申', '酉'},
    2: {'午', '未'},
    3: {'辰', '巳'},
    4: {'寅', '卯'},
    5: {'子', '丑'},
}

BRANCH_TIME_ORDER = ['丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥', '子']

HOUR_DISPLAY = {
    '子': '23:00–01:00', '丑': '01:00–03:00', '寅': '03:00–05:00',
    '卯': '05:00–07:00', '辰': '07:00–09:00', '巳': '09:00–11:00',
    '午': '11:00–13:00', '未': '13:00–15:00', '申': '15:00–17:00',
    '酉': '17:00–19:00', '戌': '19:00–21:00', '亥': '21:00–23:00',
}

HOUR_ANIMAL = {
    '子': 'Крыса', '丑': 'Бык', '寅': 'Тигр', '卯': 'Кролик',
    '辰': 'Дракон', '巳': 'Змея', '午': 'Лошадь', '未': 'Коза',
    '申': 'Обезьяна', '酉': 'Петух', '戌': 'Собака', '亥': 'Свинья',
}

# Час начала двухчасового периода по пекинскому времени (UTC+8)
HOUR_START_BEIJING = {
    '子': 23, '丑': 1,  '寅': 3,  '卯': 5,
    '辰': 7,  '巳': 9,  '午': 11, '未': 13,
    '申': 15, '酉': 17, '戌': 19, '亥': 21,
}

BEIJING_TZ = timezone(timedelta(hours=8))


# ──────────────────────── Вспомогательные функции ────────────────────────

def _bazi(d: date):
    return Solar.fromYmd(d.year, d.month, d.day).getLunar().getEightChar()


def _get_xunkong(day_stem: str, day_branch: str) -> set:
    """Пустые ветви часа (旬空) для данного дня."""
    s = STEM_IDX[day_stem]
    b = BRANCH_IDX[day_branch]
    n = next(x for x in range(s, 60, 10) if x % 12 == b)
    return XUN_EMPTY[n // 10]


def _clashes_with(branch: str, *other_branches: str) -> bool:
    """True если branch конфликтует хотя бы с одной из other_branches."""
    clash = SIX_CLASHES.get(branch)
    return clash in other_branches


def _candidate_hours(pb_branch: str, birth_year_branch: str, birth_day_branch: str) -> set:
    """
    Слияние + Союз + Сезон для собственных дней Цветка Персика,
    минус часы, конфликтующие с годом и днём рождения.
    """
    hours: set = set()
    hours.add(SIX_HARMONY[pb_branch])
    hours.update(TRIPLE_HARMONY[pb_branch])
    hours.update(SEASONAL[pb_branch])
    # Удаляем часы, чья ветвь конфликтует с годом или днём рождения
    hours = {h for h in hours
             if not _clashes_with(h, birth_year_branch, birth_day_branch)}
    return hours


def _date_str(d: date) -> str:
    return f"{d.day} {MONTHS_RU[d.month]} ({WEEKDAYS_RU[d.weekday()]})"


def _good_hours_for_day(
    day_stem: str,
    day_zhi: str,
    candidate_hours: set | None,
    birth_year_branch: str,
    birth_day_branch: str,
) -> list:
    """
    Отфильтровать часы для одного дня.
    candidate_hours=None означает «только Благородный» (для дней Слияния).
    """
    xunkong   = _get_xunkong(day_stem, day_zhi)
    harm_hour = SIX_HARMS.get(day_zhi)
    guiren    = GUIREN.get(day_stem, set())

    return [
        b for b in BRANCH_TIME_ORDER
        if (b in guiren
            and b not in xunkong
            and b != harm_hour
            and not _clashes_with(b, birth_year_branch, birth_day_branch)
            and (candidate_hours is None or b in candidate_hours))
    ]


# ──────────────────────── Основные функции ───────────────────────────────

def _valid_day_branches(pb_branch: str, birth_year_branch: str, birth_day_branch: str) -> set:
    """
    Все ветви дней, допустимых для активизации данного Цветка Персика:
    собственный день + Слияние + Союз + Сезон.
    Исключаем ветви, конфликтующие с годом/днём рождения.
    """
    all_branches = (
        {pb_branch}
        | {SIX_HARMONY[pb_branch]}
        | set(TRIPLE_HARMONY[pb_branch])
        | set(SEASONAL[pb_branch])
    )
    return {b for b in all_branches
            if not _clashes_with(b, birth_year_branch, birth_day_branch)}


def _build_day_hour_pairs(
    animal: str,
    birth_year_branch: str,
    birth_day_branch: str,
    days_ahead: int = 30,
) -> list:
    """
    Возвращает список (date_str, time_str) для благоприятных дней активизации.

    Допустимые дни: собственный день Цветка Персика + Слияние + Союз + Сезон
    (по таблице из методики), кроме ветвей, конфликтующих с годом/днём рождения.

    Допустимые часы: только часы с Благородным (天乙贵人), без пустых/вредных
    и конфликтующих с годом/днём рождения.

    Любой день исключается, если его ветвь конфликтует с текущим годом/месяцем.
    """
    pb_branch   = PEACH_ANIMAL_TO_BRANCH[animal]
    valid_days  = _valid_day_branches(pb_branch, birth_year_branch, birth_day_branch)
    today       = date.today()

    pairs: list = []
    for i in range(1, days_ahead + 1):
        d       = today + timedelta(days=i)
        bazi_d  = _bazi(d)
        day_zhi = bazi_d.getDayZhi()

        if day_zhi not in valid_days:
            continue

        # Исключить день, если его ветвь конфликтует с текущим годом/месяцем
        cur_year_zhi  = bazi_d.getYearZhi()
        cur_month_zhi = bazi_d.getMonthZhi()
        if _clashes_with(day_zhi, cur_year_zhi, cur_month_zhi):
            continue

        day_stem = bazi_d.getDayGan()
        # Часы — только Благородный, без пустых/вредных/конфликтных
        good = _good_hours_for_day(
            day_stem, day_zhi, None, birth_year_branch, birth_day_branch
        )

        if not good:
            continue

        d_str = _date_str(d)
        for h in good:
            pairs.append((d_str, f"{HOUR_DISPLAY[h]} ({HOUR_ANIMAL[h]})"))

    return pairs


def get_activation_datetimes(
    year_animal: str,
    day_animal: str,
    birth_year_branch: str,
    birth_day_branch: str,
) -> list:
    """
    Список (utc_datetime_начала_окна, date_str, time_str) для напоминаний.
    """
    animals = [year_animal]
    if day_animal != year_animal:
        animals.append(day_animal)

    result: list = []
    today = date.today()

    for animal in animals:
        pb_branch  = PEACH_ANIMAL_TO_BRANCH[animal]
        valid_days = _valid_day_branches(pb_branch, birth_year_branch, birth_day_branch)

        for i in range(1, 31):
            d       = today + timedelta(days=i)
            bazi_d  = _bazi(d)
            day_zhi = bazi_d.getDayZhi()

            if day_zhi not in valid_days:
                continue

            cur_year_zhi  = bazi_d.getYearZhi()
            cur_month_zhi = bazi_d.getMonthZhi()
            if _clashes_with(day_zhi, cur_year_zhi, cur_month_zhi):
                continue

            day_stem = bazi_d.getDayGan()
            good     = _good_hours_for_day(
                day_stem, day_zhi, None, birth_year_branch, birth_day_branch
            )

            for h in good:
                start_hour = HOUR_START_BEIJING[h]
                beijing_dt = datetime(
                    d.year, d.month, d.day, start_hour, 0, 0, tzinfo=BEIJING_TZ
                )
                utc_dt   = beijing_dt.astimezone(timezone.utc)
                date_str = _date_str(d)
                time_str = f"{HOUR_DISPLAY[h]} ({HOUR_ANIMAL[h]})"
                result.append((utc_dt, date_str, time_str))

    result.sort(key=lambda x: x[0])
    return result


def format_favorable_days(
    year_animal: str,
    day_animal: str,
    birth_year_branch: str,
    birth_day_branch: str,
) -> str:
    lines = ["📅 <b>Активизация Цветка Персика</b>", ""]

    if year_animal == day_animal:
        animal   = year_animal
        sector, degrees = PEACH_ANIMAL_SECTOR[animal]
        pb_branch       = PEACH_ANIMAL_TO_BRANCH[animal]
        harmony_branch  = SIX_HARMONY[pb_branch]
        harmony_animal  = BRANCH_RU_NOM[harmony_branch]

        lines.append(
            f"<b>Цветок Персика — {animal} ({pb_branch})</b>\n"
            f"Сектор {sector} ({degrees})\n"
            f"Активизатор: смотрите раздел «🌸 5 способов активизаций»"
        )
        lines.append("")
        lines.append(
            "✨ <b>В Вашем случае Цветок Персика по году и дню совпадает.</b> "
            "Данные активизации имеют двойной эффект — делают Вас заметным "
            "в социальных и личных историях одновременно."
        )
        lines.append("")

        pairs = _build_day_hour_pairs(animal, birth_year_branch, birth_day_branch)
        _append_pairs(lines, pairs, harmony_animal)
        lines.append("")

    else:
        for label, animal in [("года", year_animal), ("дня", day_animal)]:
            sector, degrees = PEACH_ANIMAL_SECTOR[animal]
            pb_branch       = PEACH_ANIMAL_TO_BRANCH[animal]
            harmony_branch  = SIX_HARMONY[pb_branch]
            harmony_animal  = BRANCH_RU_NOM[harmony_branch]

            lines.append(
                f"<b>Цветок Персика {label} — {animal} ({pb_branch})</b>\n"
                f"Сектор {sector} ({degrees})\n"
                f"Активизатор: смотрите раздел «🌸 5 способов активизаций»"
            )
            lines.append("")

            pairs = _build_day_hour_pairs(animal, birth_year_branch, birth_day_branch)
            _append_pairs(lines, pairs, harmony_animal)

            if label == "года" and pairs:
                lines.append("")
                lines.append(
                    "<i>Данные активизации сделают Вас заметным в социуме, "
                    "особенно если у Вас деятельность на виду и требует "
                    "внимания к Вашей персоне.</i>"
                )
            if label == "дня" and pairs:
                lines.append("")
                lines.append(
                    "<i>Данные активизации позволят привлечь знакомства "
                    "с противоположным полом, спровоцируют подарки, комплименты.</i>"
                )

            lines.append("")

    lines.append(
        "⏳ <b>Расчёт составлен на 30 дней.</b> По истечении этого срока "
        "Вы можете воспользоваться расчётом повторно.\n"
    )
    lines.append(
        "<i>Точное время для Вашего города — кнопка «🕐 Калькулятор времени».</i>"
    )
    return "\n".join(lines)


def _append_pairs(lines: list, pairs: list, harmony_animal: str) -> None:
    """Добавить строки дней в lines, пояснив какой день — день Слияния."""
    if not pairs:
        lines.append("В ближайшие 30 дней подходящих дней нет.")
        return
    for d_str, time_str in pairs:
        lines.append(f"• {d_str} — {time_str}")
