import telebot
from telebot import types
import random
import time
import threading
import logging
import sqlite3
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import os
BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

games = {}
_lock = threading.Lock()

# ─── DATABASE ────────────────────────────────────────────────────────────────
DB_PATH = "spy_game.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        cash INTEGER DEFAULT 0,
        diamonds INTEGER DEFAULT 0,
        spy_device INTEGER DEFAULT 0,
        special_pass INTEGER DEFAULT 0,
        voice_protect INTEGER DEFAULT 0,
        correct_answer INTEGER DEFAULT 0,
        secret_data INTEGER DEFAULT 0,
        rifle INTEGER DEFAULT 0,
        missions_success INTEGER DEFAULT 0,
        total_games INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()

def get_user(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, name) VALUES (?, ?)", (user_id, name))
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
    conn.close()
    return row

def add_cash(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET cash = cash + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def add_game(user_id, won: bool):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if won:
        c.execute("UPDATE users SET total_games = total_games + 1, missions_success = missions_success + 1 WHERE user_id=?", (user_id,))
    else:
        c.execute("UPDATE users SET total_games = total_games + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def format_profile(user_id, name):
    row = get_user(user_id, name)
    if not row:
        return "Профиль табылмады!"
    return (
        f"👤 {row[1]}\n\n"
        f"💵 Наличные: {row[2]}\n"
        f"💎 Алмазы: {row[3]}\n"
        f"📡 Шпионское устройство: {row[4]}\n"
        f"🎫 Специальный пропуск: {row[5]}\n"
        f"⚖️ Защита голоса: {row[6]}\n"
        f"🎭 Один правильный ответ: {row[7]}\n\n"
        f"🔒 Требуется Премиум или 💎\n\n"
        f"📁 Секретные данные: {row[8]}\n"
        f"🔫 Винтовка: {row[9]}\n\n"
        f"🎯 Успешные миссии: {row[10]}\n"
        f"🎲 Всего операций: {row[11]}"
    )

def send_win_message(chat_id, player, reward_cash=30, reward_diamonds=0):
    """Жеңіс хабары жіберу"""
    add_cash(player.id, reward_cash)
    add_game(player.id, won=True)
    profile = format_profile(player.id, player.first_name)
    text = (
        f"🏆 ПОБЕДА!\n\n"
        f"Вы выиграли и получили награду.\n\n"
        f"Награда: 💵 {reward_cash} | 💎 {reward_diamonds}\n\n"
        f"{profile}\n\n"
        f"📢 Поздравляем с победой!"
    )
    try:
        bot.send_message(player.id, text)
    except Exception as e:
        logger.warning(f"Win DM error: {e}")

def send_lose_message(chat_id, player):
    """Жеңіліс хабары жіберу"""
    add_game(player.id, won=False)
    profile = format_profile(player.id, player.first_name)
    text = (
        f"❌ ПОРАЖЕНИЕ!\n\n"
        f"Вы проиграли и не получили награду.\n\n"
        f"Награда: 💵 0 | 💎 0\n\n"
        f"{profile}\n\n"
        f"📢 Повезёт в следующий раз!"
    )
    try:
        bot.send_message(player.id, text)
    except Exception as e:
        logger.warning(f"Lose DM error: {e}")

# ─── ЛОКАЦИЯЛАР ──────────────────────────────────────────────────────────────
LOCATIONS = {
    "Аэропорт": {
        "вопросы": [
            {"вопрос": "Что находится прямо перед вами?", "правильные": ["Стойка регистрации с очередью", "Табло с расписанием рейсов", "Ленточный транспортёр с багажом", "Паспортный контроль"]},
            {"вопрос": "Что вы слышите вокруг?", "правильные": ["Объявления о рейсах по громкой связи", "Гул самолётных двигателей вдали", "Скрип колёсиков чемоданов", "Голос диктора на нескольких языках"]},
            {"вопрос": "Что вы держите в руках?", "правильные": ["Посадочный талон", "Паспорт с визой", "Бирку для багажа", "Распечатку маршрута"]},
            {"вопрос": "Что происходит вокруг вас?", "правильные": ["Люди спешат с чемоданами", "Очередь на досмотр", "Кто-то машет рукой на прощание", "Группа туристов с гидом"]}
        ]
    },
    "Банк": {
        "вопросы": [
            {"вопрос": "Что вы держите в руках?", "правильные": ["Талон с номером очереди", "Пачку документов для подписи", "Банковскую карту", "Квитанцию о переводе"]},
            {"вопрос": "Что находится перед вами?", "правильные": ["Окошко кассира за стеклом", "Терминал для карт", "Стопку бланков на стойке", "Экран с номером очереди"]},
            {"вопрос": "Что вы слышите?", "правильные": ["Тихие переговоры у стойки", "Звук принтера за стеклом", "Электронный голос вызова номера", "Шелест купюр у кассира"]},
            {"вопрос": "Что происходит рядом с вами?", "правильные": ["Охранник проверяет документы", "Клиент подписывает договор", "Кассир пересчитывает деньги", "Менеджер объясняет условия"]}
        ]
    },
    "Больница": {
        "вопросы": [
            {"вопрос": "Что вы слышите вокруг себя?", "правильные": ["Звук капельницы и тихие голоса", "Объявления по громкой связи", "Скрип каталки по коридору", "Писк медицинских приборов"]},
            {"вопрос": "Что находится перед вами?", "правильные": ["Дверь с номером палаты", "Стойка медсестры с документами", "Каталка у стены коридора", "Информационный стенд с расписанием"]},
            {"вопрос": "Что вы чувствуете?", "правильные": ["Запах дезинфицирующего средства", "Прохладный кондиционированный воздух", "Жёсткое кресло в коридоре", "Яркий белый свет ламп"]},
            {"вопрос": "Что происходит рядом?", "правильные": ["Медсестра меняет капельницу", "Врач изучает карточку пациента", "Санитар везёт каталку", "Родственники ждут у палаты"]}
        ]
    },
    "Казино": {
        "вопросы": [
            {"вопрос": "Что происходит прямо сейчас?", "правильные": ["Крутится рулетка", "Дилер раздаёт карты", "Кто-то громко выигрывает", "Монеты сыплются из автомата"]},
            {"вопрос": "Что вы слышите?", "правильные": ["Звон фишек на столе", "Музыку и гул голосов", "Звуковые сигналы автоматов", "Возгласы выигравшего игрока"]},
            {"вопрос": "Что вы держите в руках?", "правильные": ["Стопку разноцветных фишек", "Карты, которые только пришли", "Бокал с напитком", "Чек на обмен фишек"]},
            {"вопрос": "Что вы видите вокруг?", "правильные": ["Ряды игровых автоматов", "Стол с зелёным сукном", "Крупье в форменной одежде", "Камеры наблюдения под потолком"]}
        ]
    },
    "Кинотеатр": {
        "вопросы": [
            {"вопрос": "Что вы видите перед собой?", "правильные": ["Большой экран с фильмом", "Тёмный зал с силуэтами зрителей", "Мерцающий проектор сзади", "Ряды откидных кресел"]},
            {"вопрос": "Что вы слышите?", "правильные": ["Громкий звук из динамиков", "Шорох попкорна рядом", "Музыку из фильма", "Чей-то тихий смех в зале"]},
            {"вопрос": "Что вы держите в руках?", "правильные": ["Стакан с газировкой", "Коробку попкорна", "Билет с номером места", "Телефон на беззвучном режиме"]},
            {"вопрос": "Что происходит вокруг?", "правильные": ["Гаснет свет перед сеансом", "Кто-то опаздывает и ищет место", "Идут рекламные ролики", "Зрители реагируют на сцену"]}
        ]
    },
    "Корабль": {
        "вопросы": [
            {"вопрос": "Что вы чувствуете прямо сейчас?", "правильные": ["Лёгкое покачивание под ногами", "Солёный морской ветер", "Вибрацию двигателей", "Брызги волн на лице"]},
            {"вопрос": "Что вы видите вокруг?", "правильные": ["Горизонт и открытое море", "Другие палубы корабля", "Чаек, летящих за кормой", "Спасательные шлюпки на бортах"]},
            {"вопрос": "Что вы слышите?", "правильные": ["Плеск волн о борт", "Гудок корабля вдали", "Скрип такелажа на ветру", "Команды матросов на палубе"]},
            {"вопрос": "Что происходит рядом?", "правильные": ["Матросы драят палубу", "Пассажиры смотрят на море", "Капитан делает объявление", "Груз закрепляют в трюме"]}
        ]
    },
    "Космическая станция": {
        "вопросы": [
            {"вопрос": "Что вы видите в иллюминатор?", "правильные": ["Голубой шар Земли", "Бесконечную черноту с звёздами", "Солнечные панели станции", "Другой стыковочный модуль"]},
            {"вопрос": "Что вы чувствуете?", "правильные": ["Невесомость — всё парит", "Гул системы вентиляции", "Прохладный переработанный воздух", "Вибрацию корпуса станции"]},
            {"вопрос": "Что вы держите в руках?", "правильные": ["Планшет с данными телеметрии", "Контейнер с едой в тюбике", "Ручку на липучке", "Инструмент для ремонта модуля"]},
            {"вопрос": "Что происходит вокруг?", "правильные": ["Коллега проводит эксперимент", "Сигнализирует один из приборов", "Связь с Землёй по рации", "Стыкуется грузовой корабль"]}
        ]
    },
    "Пляж": {
        "вопросы": [
            {"вопрос": "Что вы ощущаете под ногами?", "правильные": ["Горячий песок", "Мокрые камни у воды", "Тёплую гальку", "Влажный песок у прибоя"]},
            {"вопрос": "Что вы слышите?", "правильные": ["Шум прибоя", "Крики чаек над головой", "Смех и голоса отдыхающих", "Музыку с соседнего зонтика"]},
            {"вопрос": "Что вы видите вокруг?", "правильные": ["Яркие зонтики вдоль берега", "Волны, набегающие на берег", "Детей, строящих замок из песка", "Лодки у горизонта"]},
            {"вопрос": "Что вы держите в руках?", "правильные": ["Холодный напиток в бутылке", "Крем от загара", "Полотенце с песком", "Ракушку, найденную у воды"]}
        ]
    },
    "Поезд": {
        "вопросы": [
            {"вопрос": "Что вы видите за окном?", "правильные": ["Мелькающие деревья и поля", "Тёмный тоннель", "Пролетающую платформу", "Другой состав рядом"]},
            {"вопрос": "Что вы слышите?", "правильные": ["Стук колёс на стыках рельсов", "Объявление следующей станции", "Разговоры соседей по купе", "Свисток локомотива"]},
            {"вопрос": "Что происходит в вагоне?", "правильные": ["Проводник проверяет билеты", "Пассажир несёт чай из буфета", "Кто-то укладывает вещи на полку", "Люди выходят на остановке"]},
            {"вопрос": "Что вы держите в руках?", "правильные": ["Билет с местом и вагоном", "Стакан горячего чая", "Книгу или телефон", "Пакет с едой из дома"]}
        ]
    },
    "Полицейский участок": {
        "вопросы": [
            {"вопрос": "Что находится перед вами на столе?", "правильные": ["Протокол для подписи", "Жетон и удостоверение", "Папку с уголовным делом", "Дактилоскопическую карту"]},
            {"вопрос": "Что вы слышите?", "правильные": ["Звук рации на дежурном столе", "Печать документов за стеной", "Чьи-то показания в соседней комнате", "Звяканье ключей у охраны"]},
            {"вопрос": "Что вы видите вокруг?", "правильные": ["Стенд с ориентировками", "Решётчатые окна в коридоре", "Дежурного за стеклянной перегородкой", "Скамейку у стены для ожидающих"]},
            {"вопрос": "Что происходит рядом?", "правильные": ["Следователь задаёт вопросы", "Задержанного проводят мимо", "Офицер заполняет рапорт", "Адвокат просматривает документы"]}
        ]
    },
    "Ресторан": {
        "вопросы": [
            {"вопрос": "Что стоит перед вами?", "правильные": ["Тарелку с горячим блюдом", "Меню в кожаной обложке", "Бокал с вином", "Корзинку со свежим хлебом"]},
            {"вопрос": "Что вы слышите?", "правильные": ["Тихую фоновую музыку", "Звон бокалов за соседним столом", "Голоса официантов", "Звук из открытой кухни"]},
            {"вопрос": "Что происходит вокруг?", "правильные": ["Официант принимает заказ", "Сомелье открывает бутылку", "Пара отмечает годовщину", "Повар готовит прямо в зале"]},
            {"вопрос": "Что вы держите в руках?", "правильные": ["Вилку и нож над тарелкой", "Меню с выбором блюд", "Бокал, который только подняли", "Салфетку на коленях"]}
        ]
    },
    "Школа": {
        "вопросы": [
            {"вопрос": "Что лежит перед вами?", "правильные": ["Открытый учебник", "Тетрадь с заданием", "Дневник с оценками", "Пенал с карандашами"]},
            {"вопрос": "Что вы слышите?", "правильные": ["Голос учителя у доски", "Звонок между уроками", "Скрип мела по доске", "Шёпот соседа по парте"]},
            {"вопрос": "Что происходит в классе?", "правильные": ["Учитель объясняет тему", "Кто-то отвечает у доски", "Контрольная работа в тишине", "Раздают проверенные тетради"]},
            {"вопрос": "Что вы видите перед собой?", "правильные": ["Доску с записями", "Спину одноклассника за партой", "Таблицы и плакаты на стене", "Журнал на учительском столе"]}
        ]
    },
    "Супермаркет": {
        "вопросы": [
            {"вопрос": "Что вы держите в руках?", "правильные": ["Корзину с продуктами", "Список покупок", "Товар, который изучаете", "Дисконтную карту"]},
            {"вопрос": "Что вы видите вокруг?", "правильные": ["Длинные стеллажи с товарами", "Кассы с очередями", "Акционные ценники на полках", "Холодильники с молочным"]},
            {"вопрос": "Что вы слышите?", "правильные": ["Объявления о скидках по радио", "Пиканье сканера на кассе", "Скрип тележки на колёсиках", "Фоновую музыку в зале"]},
            {"вопрос": "Что происходит рядом?", "правильные": ["Сотрудник выкладывает товар", "Покупатель сравнивает этикетки", "Охранник следит за залом", "Промоутер предлагает пробники"]}
        ]
    },
    "Цирк": {
        "вопросы": [
            {"вопрос": "Что происходит на арене?", "правильные": ["Акробат летит под куполом", "Клоун делает фокус", "Дрессировщик работает с животными", "Жонглёр подбрасывает шары"]},
            {"вопрос": "Что вы слышите?", "правильные": ["Барабанную дробь перед трюком", "Смех зрителей в зале", "Бравурную цирковую музыку", "Ведущего в блестящем фраке"]},
            {"вопрос": "Что вы видите вокруг?", "правильные": ["Купол с трапецией наверху", "Ряды зрителей вокруг арены", "Прожекторы, бьющие в центр", "Сетку безопасности под акробатами"]},
            {"вопрос": "Что вы держите в руках?", "правильные": ["Программку с именами артистов", "Сахарную вату на палочке", "Билет с номером ряда", "Воздушный шарик от клоуна"]}
        ]
    },
    "Зоопарк": {
        "вопросы": [
            {"вопрос": "Что вы видите прямо перед собой?", "правильные": ["Животное за стеклом вольера", "Табличку с названием вида", "Кормушку внутри клетки", "Ров с водой перед загоном"]},
            {"вопрос": "Что вы слышите?", "правильные": ["Крики и рёв животных", "Голос экскурсовода рядом", "Смех детей у вольера", "Шелест листвы в вольере с птицами"]},
            {"вопрос": "Что происходит рядом?", "правильные": ["Смотритель кормит животных", "Туристы фотографируют вольер", "Ребёнок тянется к ограждению", "Животное прячется в укрытие"]},
            {"вопрос": "Что вы держите в руках?", "правильные": ["Карту зоопарка", "Пакет с едой для животных", "Фотоаппарат или телефон", "Билет на входе"]}
        ]
    }
}

LOCATION_CHOICES = list(LOCATIONS.keys())

FAKE_ANSWERS = [
    "Что-то невзрачное и обычное", "Ничего особенного", "Стандартный предмет этого места",
    "То, что всегда здесь бывает", "Обычную вещь без особых примет", "Что-то, что сложно описать точно",
    "Предмет, типичный для этой обстановки", "Нечто привычное для этого места", "Обычный атрибут этой локации",
    "Что-то стандартное и незаметное", "Вещь без особых характеристик", "Предмет, который здесь всегда есть"
]

# ─── ВСПОМОГАТЕЛЬНЫЕ ─────────────────────────────────────────────────────────
def get_game(chat_id):
    return games.get(chat_id)

def elapsed_str(start_time):
    e = int(time.time() - start_time)
    return f"{e // 60} мин {e % 60} сек"

def active_players(game):
    return [p for p in game['players'] if p.id not in game['eliminated']]

def end_game(chat_id, text, spy_won=False):
    """Ойынды аяқтау — жеңіс/жеңіліс хабары жіберу"""
    game = get_game(chat_id)
    bot.send_message(chat_id, text)

    if game:
        spy_id = game.get('spy')
        players = game.get('players', [])

        for player in players:
            if player.id == spy_id:
                # Шпион жеңді ме?
                if spy_won:
                    send_win_message(chat_id, player, reward_cash=50, reward_diamonds=0)
                else:
                    send_lose_message(chat_id, player)
            else:
                # Қалған ойыншылар
                if not spy_won:
                    send_win_message(chat_id, player, reward_cash=30, reward_diamonds=0)
                else:
                    send_lose_message(chat_id, player)

    games.pop(chat_id, None)

# ─── КОМАНДАЛАР ──────────────────────────────────────────────────────────────
@bot.message_handler(commands=['start'])
def cmd_start(message):
    get_user(message.from_user.id, message.from_user.first_name)
    name = message.from_user.first_name
    text = (f"🕵️ Игра Шпион\n👋 Привет, {name}!\n\n"
            f"Чтобы начать игру используй /game в групповом чате.\n\n"
            f"Команды:\n/profile — твоя статистика\n/achievements — достижения\n"
            f"/rating — рейтинг\n/premium — подписка\n/rules — правила игры\n"
            f"/endgame — завершить игру (только хост)")
    bot.send_message(message.chat.id, text)
    bot.send_message(message.chat.id, "📢 Новостной канал: https://t.me/SpyGameNews")
    bot.send_message(message.chat.id, "🎮 Игровая группа: https://t.me/SpyArenaChat")

@bot.message_handler(commands=['rules'])
def cmd_rules(message):
    bot.send_message(message.chat.id,
        "📖 Правила игры Шпион:\n\n"
        "1. Один игрок — шпион, остальные знают локацию\n"
        "2. Каждому приходит вопрос в личку — 60 секунд на ответ\n"
        "3. Вопросы задаются по очереди каждому игроку\n"
        "4. После ответа группа видит: 💬 [имя] отвечает: ➡️ ...\n"
        "5. После всех ответов — голосование: кто шпион?\n"
        "6. После голосования шпион пытается угадать локацию\n"
        "7. Шпион угадал — шпион победил!\n"
        "8. Игроки нашли шпиона — игроки победили!\n\n"
        "🕵️ Удачи!")

@bot.message_handler(commands=['profile'])
def cmd_profile(message):
    get_user(message.from_user.id, message.from_user.first_name)
    profile = format_profile(message.from_user.id, message.from_user.first_name)
    bot.send_message(message.chat.id, f"👤 Профиль\n\n{profile}")

@bot.message_handler(commands=['achievements'])
def cmd_achievements(message):
    bot.send_message(message.chat.id, "🏆 Достижения\n\nУ тебя пока нет достижений. Сыграй в игру!")

@bot.message_handler(commands=['rating'])
def cmd_rating(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, missions_success, total_games FROM users ORDER BY missions_success DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "📊 Рейтинг пуст. Сыграй в игру!")
        return
    text = "📊 Топ игроков:\n\n"
    for i, (name, wins, total) in enumerate(rows, 1):
        text += f"{i}. {name} — 🎯 {wins} побед / 🎲 {total} игр\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['premium'])
def cmd_premium(message):
    bot.send_message(message.chat.id, "⭐ Премиум подписка\n\nПремиум функции скоро будут доступны!")

@bot.message_handler(commands=['endgame'])
def cmd_endgame(message):
    chat_id = message.chat.id
    game = get_game(chat_id)
    if not game:
        bot.send_message(chat_id, "❌ Активная игра не найдена!")
        return
    if message.from_user.id != game['host']:
        bot.send_message(chat_id, "❌ Только организатор может завершить игру!")
        return
    end_game(chat_id, "🛑 Игра завершена организатором!")

# ─── ОЙЫН: ЖИНАУ ─────────────────────────────────────────────────────────────
@bot.message_handler(commands=['game'])
def cmd_game(message):
    if message.chat.type == 'private':
        bot.send_message(message.chat.id, "❌ Команду /game используй в групповом чате!")
        return
    chat_id = message.chat.id
    if chat_id in games:
        bot.send_message(chat_id, "❌ Игра уже идёт! Дождитесь её окончания.")
        return
    get_user(message.from_user.id, message.from_user.first_name)
    name = message.from_user.first_name
    games[chat_id] = {
        'players': [message.from_user], 'started': False, 'host': message.from_user.id,
        'start_time': None, 'eliminated': [], 'round': 0, 'answers': [], 'answered': [],
        'player_answers': {}, 'correct_answer': {}, 'spy_guessed': None, 'votes': {},
        'voted': [], 'vote_detail': {}, 'location': None, 'spy': None, 'timer_msg_id': None,
        'afk_count': {}, 'current_player_index': 0, 'lobby_msg_id': None
    }
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Войти в игру", callback_data="join"))
    markup.add(types.InlineKeyboardButton("▶️ Начать игру", callback_data="start_game"))
    sent = bot.send_message(
        chat_id,
        f"🕵️ Открывается набор в игру\n\n👥 Игроки: {name}\n\n⏱ Игра начнётся автоматически через 3 минуты!",
        reply_markup=markup
    )
    games[chat_id]['lobby_msg_id'] = sent.message_id

    # Закрепляем только лобби хабарын
    try:
        bot.pin_chat_message(chat_id, sent.message_id)
    except Exception as e:
        logger.warning(f"Pin error: {e}")

    # 3 минут таймер — автоматты басталу
    def auto_start_timer():
        time.sleep(180)
        g = get_game(chat_id)
        if not g or g.get('started'):
            return
        if len(g['players']) < 3:
            bot.send_message(chat_id, "⏱ Время вышло! Недостаточно игроков (минимум 3). Игра отменена.")
            games.pop(chat_id, None)
            return
        bot.send_message(chat_id, "⏱ 3 минуты прошло — игра начинается автоматически!")
        start_the_game(chat_id)

    threading.Thread(target=auto_start_timer, daemon=True).start()

# ─── CALLBACK: ВОЙТИ В ИГРУ ──────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "join")
def cb_join(call):
    chat_id = call.message.chat.id
    user = call.from_user
    get_user(user.id, user.first_name)
    game = get_game(chat_id)
    if not game or game.get('started'):
        bot.answer_callback_query(call.id, "Игра не найдена или уже началась!")
        return
    players = game['players']
    if any(p.id == user.id for p in players):
        bot.answer_callback_query(call.id, "Ты уже в игре!")
        return
    players.append(user)
    names = ", ".join(p.first_name for p in players)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Войти в игру", callback_data="join"))
    markup.add(types.InlineKeyboardButton("▶️ Начать игру", callback_data="start_game"))
    try:
        bot.edit_message_text(
            f"🕵️ Открывается набор в игру\n\n👥 Игроки: {names}\n\n⏱ Игра начнётся автоматически через 3 минуты!",
            chat_id, call.message.message_id, reply_markup=markup
        )
    except Exception as e:
        logger.warning(f"Edit error: {e}")
    bot.answer_callback_query(call.id, "Ты вошёл в игру!")
    try:
        bot.send_message(user.id, "✅ Ты в игре! Жди начала.")
    except Exception as e:
        logger.warning(f"DM error for {user.first_name}: {e}")
        markup2 = types.InlineKeyboardMarkup()
        markup2.add(types.InlineKeyboardButton("🚀 Запустить бота", url="https://t.me/GameShpion_bot?start=join"))
        bot.send_message(chat_id, f"⚠️ {user.first_name}, сначала напиши боту в личку!", reply_markup=markup2)

# ─── CALLBACK: НАЧАТЬ ИГРУ ───────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "start_game")
def cb_start_game(call):
    chat_id = call.message.chat.id
    game = get_game(chat_id)
    if not game or call.from_user.id != game['host']:
        bot.answer_callback_query(call.id, "Только организатор может начать игру!")
        return
    if len(game['players']) < 3:
        bot.answer_callback_query(call.id, "Нужно минимум 3 игрока!")
        return
    bot.answer_callback_query(call.id, "Игра началась!")
    start_the_game(chat_id)

def start_the_game(chat_id):
    """Ойынды іске қосу"""
    game = get_game(chat_id)
    if not game or game.get('started'):
        return
    location = random.choice(LOCATION_CHOICES)
    spy = random.choice(game['players'])
    game.update({
        'location': location, 'spy': spy.id, 'start_time': time.time(), 'round': 1,
        'answers': [], 'answered': [], 'player_answers': {}, 'correct_answer': {},
        'spy_guessed': None, 'started': True, 'afk_count': {p.id: 0 for p in game['players']},
        'votes': {}, 'voted': [], 'vote_detail': {}, 'current_player_index': 0
    })

    # Лобби хабарынан кнопкаларды жою
    lobby_msg_id = game.get('lobby_msg_id')
    if lobby_msg_id:
        try:
            bot.edit_message_reply_markup(chat_id, lobby_msg_id, reply_markup=None)
        except Exception as e:
            logger.warning(f"Edit lobby markup error: {e}")

    names = ", ".join(p.first_name for p in game['players'])
    # 🎮 Игра началась! хабарын закрепке қоймаймыз
    bot.send_message(
        chat_id,
        f"🎮 Игра началась! Раунд 1\n\n👥 Игроки: {names}\n\n"
        f"Вопросы задаются по очереди каждому игроку!\n⏱ У каждого 60 секунд на ответ!"
    )
    prepare_questions(chat_id)
    send_next_player_question(chat_id)

# ─── СҰРАҚТАРДЫ ДАЙЫНДАУ ─────────────────────────────────────────────────────
def prepare_questions(chat_id):
    game = get_game(chat_id)
    if not game:
        return
    location = game['location']
    players = active_players(game)
    all_questions = LOCATIONS[location]['вопросы']
    game['player_answers'] = {}
    game['correct_answer'] = {}
    game['player_questions'] = {}
    used_questions = []
    for player in players:
        available = [q for q in all_questions if q not in used_questions]
        if not available:
            used_questions = []
            available = all_questions[:]
        chosen_q = random.choice(available)
        used_questions.append(chosen_q)
        question = chosen_q['вопрос']
        correct_answers = chosen_q['правильные']
        correct = random.choice(correct_answers)
        other_correct = []
        for loc_name, loc_data in LOCATIONS.items():
            if loc_name != location:
                for q in loc_data['вопросы']:
                    other_correct.extend(q['правильные'])
        fakes = random.sample(other_correct, 3)
        ans_list = fakes + [correct]
        random.shuffle(ans_list)
        game['player_answers'][player.id] = ans_list
        game['correct_answer'][player.id] = correct
        game['player_questions'][player.id] = question

# ─── КЕЛЕСІ ОЙЫНШЫҒА СҰРАҚ ЖІБЕРУ ───────────────────────────────────────────
def send_next_player_question(chat_id):
    game = get_game(chat_id)
    if not game:
        return
    players = active_players(game)
    idx = game.get('current_player_index', 0)
    if idx >= len(players):
        start_voting(chat_id)
        return
    player = players[idx]
    round_num = game['round']
    location = game['location']
    question = game['player_questions'][player.id]
    ans_list = game['player_answers'][player.id]
    bot.send_message(chat_id, f"❓ Раунд {round_num} — Вопрос для {player.first_name}!\n⏱ 60 секунд на ответ!")
    markup = types.InlineKeyboardMarkup()
    for i, ans in enumerate(ans_list):
        markup.add(types.InlineKeyboardButton(ans, callback_data=f"ans_{chat_id}_{player.id}_{i}"))
    if player.id == game['spy']:
        dm_text = (f"🕵️ Ты — ШПИОН!\n\n⚠️ Ты не знаешь локацию!\n"
                   f"Слушай ответы других...\n\n❓ Вопрос: {question}\n\nВыбери ответ:")
    else:
        dm_text = (f"📍 Локация: {location}\n\n🔍 Среди вас есть шпион!\n"
                   f"Отвечай правдиво...\n\n❓ Вопрос: {question}\n\nВыбери ответ:")
    try:
        bot.send_message(player.id, dm_text, reply_markup=markup)
    except Exception as e:
        logger.warning(f"DM error for {player.first_name}: {e}")
        markup2 = types.InlineKeyboardMarkup()
        markup2.add(types.InlineKeyboardButton("🚀 Запустить бота", url="https://t.me/GameShpion_bot?start=start"))
        bot.send_message(chat_id, f"⚠️ {player.first_name}, напиши боту в личку чтобы получить вопрос!", reply_markup=markup2)
    start_player_timer(chat_id, player.id, player.first_name)

# ─── ӘР ОЙЫНШЫҒА ТАЙМЕР (60 секунд) ──────────────────────────────────────────
def start_player_timer(chat_id, player_id, player_name):
    def timer():
        try:
            timer_msg = bot.send_message(chat_id, f"⏱ {player_name} — 60 сек на ответ!")
            game = get_game(chat_id)
            if not game:
                return
            game['timer_msg_id'] = timer_msg.message_id
        except Exception as e:
            logger.error(f"Timer send error: {e}")
            return
        for remaining in range(50, 0, -10):
            time.sleep(10)
            game = get_game(chat_id)
            if not game:
                return
            if player_id in game['answered']:
                try:
                    bot.delete_message(chat_id, timer_msg.message_id)
                except Exception:
                    pass
                return
            try:
                bot.edit_message_text(f"⏱ {player_name} — {remaining} сек на ответ!", chat_id, timer_msg.message_id)
            except Exception as e:
                logger.warning(f"Timer edit error: {e}")
        time.sleep(10)
        game = get_game(chat_id)
        if not game:
            return
        try:
            bot.delete_message(chat_id, timer_msg.message_id)
        except Exception:
            pass
        if player_id in game['answered']:
            return
        players = active_players(game)
        player_obj = next((p for p in players if p.id == player_id), None)
        if not player_obj:
            return
        rand_answer = random.choice(FAKE_ANSWERS)
        game['answers'].append({'player': player_name, 'a': rand_answer, 'afk': True})
        game['answered'].append(player_id)
        game['afk_count'][player_id] = game['afk_count'].get(player_id, 0) + 1
        bot.send_message(chat_id, f"💬 {player_name} отвечает:\n➡️ {rand_answer}\n\n⚠️ (Ответ выбран автоматически — время вышло)")
        game['current_player_index'] = game.get('current_player_index', 0) + 1
        send_next_player_question(chat_id)
    threading.Thread(target=timer, daemon=True).start()

# ─── CALLBACK: ОЙЫНШЫ ЖАУАБЫ ─────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("ans_"))
def cb_answer(call):
    parts = call.data.split("_")
    if len(parts) != 4:
        bot.answer_callback_query(call.id, "Ошибка данных!")
        return
    chat_id = int(parts[1])
    player_id = int(parts[2])
    answer_index = int(parts[3])
    if call.from_user.id != player_id:
        bot.answer_callback_query(call.id, "Это не твой вопрос!")
        return
    game = get_game(chat_id)
    if not game or player_id in game['answered']:
        bot.answer_callback_query(call.id, "Игра не найдена или ты уже ответил!")
        return
    ans_list = game['player_answers'].get(player_id)
    if not ans_list or answer_index >= len(ans_list):
        bot.answer_callback_query(call.id, "Ошибка! Попробуй снова.")
        return
    answer_text = ans_list[answer_index]
    player = call.from_user
    game['answers'].append({'player': player.first_name, 'a': answer_text, 'afk': False})
    game['answered'].append(player_id)
    game['afk_count'][player_id] = 0
    bot.answer_callback_query(call.id, "Ответ принят!")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception as e:
        logger.warning(f"Edit markup error: {e}")
    bot.send_message(chat_id, f"💬 {player.first_name} отвечает:\n➡️ {answer_text}")
    game['current_player_index'] = game.get('current_player_index', 0) + 1
    send_next_player_question(chat_id)

# ─── ДАУЫС БЕРУ БАСТАЛУЫ ─────────────────────────────────────────────────────
def start_voting(chat_id):
    game = get_game(chat_id)
    if not game:
        return
    players = active_players(game)
    markup_vote = types.InlineKeyboardMarkup()
    for player_v in players:
        markup_vote.add(types.InlineKeyboardButton(player_v.first_name, callback_data=f"vote_{chat_id}_{player_v.id}"))
    bot.send_message(chat_id, "🗳 Голосование!\n\n👇 Кто шпион?\n⚠️ На себя голосовать нельзя!\n⏱ 60 секунд!", reply_markup=markup_vote)
    def vote_timer():
        time.sleep(60)
        g = get_game(chat_id)
        if not g:
            return
        ap = active_players(g)
        if len(g['voted']) < len(ap):
            bot.send_message(chat_id, "⏱ Время голосования вышло!")
            finish_voting(chat_id)
    threading.Thread(target=vote_timer, daemon=True).start()

# ─── CALLBACK: ДАУЫС БЕРУ ────────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("vote_"))
def cb_vote(call):
    parts = call.data.split("_")
    chat_id = int(parts[1])
    voted_for_id = int(parts[2])
    voter_id = call.from_user.id
    game = get_game(chat_id)
    if not game or voter_id == voted_for_id or voter_id in game['voted']:
        bot.answer_callback_query(call.id, "Ошибка голосования!")
        return
    ap = active_players(game)
    if voter_id not in [p.id for p in ap]:
        bot.answer_callback_query(call.id, "Ты выбыл из игры!")
        return
    game['voted'].append(voter_id)
    game['votes'][voted_for_id] = game['votes'].get(voted_for_id, 0) + 1
    game['vote_detail'][voter_id] = voted_for_id
    voted_name = next((p.first_name for p in game['players'] if p.id == voted_for_id), "?")
    bot.answer_callback_query(call.id, f"Ты проголосовал за {voted_name}!")
    bot.send_message(chat_id, f"🗳 {call.from_user.first_name} проголосовал!")
    if len(game['voted']) >= len(ap):
        finish_voting(chat_id)

def finish_voting(chat_id):
    game = get_game(chat_id)
    if not game:
        return
    votes = game['votes']
    spy_id = game['spy']
    players = game['players']
    t_str = elapsed_str(game['start_time'])
    spy_name = next((p.first_name for p in players if p.id == spy_id), "Неизвестен")
    vote_log = []
    for vid, tid in game.get('vote_detail', {}).items():
        vname = next((p.first_name for p in players if p.id == vid), "?")
        tname = next((p.first_name for p in players if p.id == tid), "?")
        vote_log.append(f"  {vname} → {tname}")
    vote_log_text = "\n".join(vote_log) if vote_log else "  —"
    if not votes:
        bot.send_message(chat_id, "Никто не проголосовал! Переходим к следующему раунду...")
        next_round(chat_id)
        return
    max_votes = max(votes.values())
    top_ids = [uid for uid, v in votes.items() if v == max_votes]
    results = "\n".join(
        f"  {next((p.first_name for p in players if p.id == uid), '?')}: {v} голос(а)"
        for uid, v in sorted(votes.items(), key=lambda x: -x[1])
    )
    if len(top_ids) > 1:
        tied_names = ", ".join(next((p.first_name for p in players if p.id == uid), "?") for uid in top_ids)
        bot.send_message(chat_id,
            f"📊 Результаты голосования:\n{vote_log_text}\n\n🔢 Итог:\n{results}\n\n"
            f"⚖️ Ничья между: {tied_names}!\n🔁 Повторное голосование!")
        game['votes'] = {}
        game['voted'] = []
        game['vote_detail'] = {}
        tied_players = [p for p in players if p.id in top_ids and p.id not in game['eliminated']]
        markup = types.InlineKeyboardMarkup()
        for player in tied_players:
            markup.add(types.InlineKeyboardButton(player.first_name, callback_data=f"vote_{chat_id}_{player.id}"))
        bot.send_message(chat_id, "🗳 Повторное голосование!\n\n👇 Кто шпион?\n⏱ 60 секунд!", reply_markup=markup)
        def revote_timer():
            time.sleep(60)
            g = get_game(chat_id)
            if not g:
                return
            ap = active_players(g)
            if len(g['voted']) < len(ap):
                bot.send_message(chat_id, "⏱ Время повторного голосования вышло!")
                finish_voting(chat_id)
        threading.Thread(target=revote_timer, daemon=True).start()
        return
    max_votes_id = top_ids[0]
    max_votes_name = next((p.first_name for p in players if p.id == max_votes_id), "?")
    bot.send_message(chat_id,
        f"📊 Результаты голосования:\n{vote_log_text}\n\n🔢 Итог:\n{results}\n\n❌ Выбывается: {max_votes_name}")
    if max_votes_id == spy_id:
        end_game(chat_id,
            f"🎉 Шпион найден!\n\nШпионом был: {spy_name}\nЛокация: {game['location']}\n\n"
            f"✅ Игроки победили!\n\n⏱ Игра длилась: {t_str}",
            spy_won=False)
        return
    game['eliminated'].append(max_votes_id)
    bot.send_message(chat_id, f"❌ {max_votes_name} выбыл! Но это был не шпион...\n\nПродолжаем!")
    try:
        elim = next(p for p in players if p.id == max_votes_id)
        bot.send_message(elim.id, "❌ Тебя выбрали шпионом, но ты им не был...\nТы выбыл из игры. Наблюдай за происходящим!")
    except Exception as e:
        logger.warning(f"DM elim error: {e}")
    send_spy_guess(chat_id)

def send_spy_guess(chat_id):
    game = get_game(chat_id)
    if not game:
        return
    spy_id = game['spy']
    location = game['location']
    players = game['players']
    t_str = elapsed_str(game['start_time'])
    spy_name = next((p.first_name for p in players if p.id == spy_id), "Неизвестен")
    if spy_id in game['eliminated']:
        end_game(chat_id,
            f"🎉 Шпион найден и выбыл!\n\nШпионом был: {spy_name}\nЛокация: {location}\n\n"
            f"✅ Игроки победили!\n\n⏱ Игра длилась: {t_str}",
            spy_won=False)
        return
    fake_locs = random.sample([l for l in LOCATION_CHOICES if l != location], 5)
    fake_locs.append(location)
    random.shuffle(fake_locs)
    markup = types.InlineKeyboardMarkup()
    for loc in fake_locs:
        markup.add(types.InlineKeyboardButton(loc, callback_data=f"spyg_{chat_id}_{loc}"))
    try:
        bot.send_message(spy_id,
            f"🗺 Раунд {game['round']} завершён!\n\nПопробуй угадать локацию!\n⏱ У тебя 60 секунд:",
            reply_markup=markup)
    except Exception as e:
        logger.warning(f"DM spy guess error: {e}")
    bot.send_message(chat_id, "🕵️ Шпион пытается угадать локацию... (60 сек)")
    def spy_timer():
        time.sleep(60)
        g = get_game(chat_id)
        if not g:
            return
        if g.get('spy_guessed') is None:
            g['spy_guessed'] = 'timeout'
            bot.send_message(chat_id, "⏱ Шпион не успел угадать локацию!")
            check_game_end(chat_id)
    threading.Thread(target=spy_timer, daemon=True).start()

# ─── CALLBACK: ШПИОН БОЛЖАУЫ ─────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("spyg_"))
def cb_spy_guess(call):
    parts = call.data.split("_", 2)
    chat_id = int(parts[1])
    guessed = parts[2]
    game = get_game(chat_id)
    if not game or call.from_user.id != game['spy'] or game.get('spy_guessed') is not None:
        bot.answer_callback_query(call.id, "Ошибка!")
        return
    game['spy_guessed'] = guessed
    bot.answer_callback_query(call.id, "Ответ принят!")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception as e:
        logger.warning(f"Edit markup error: {e}")
    t_str = elapsed_str(game['start_time'])
    spy_name = next((p.first_name for p in game['players'] if p.id == game['spy']), "Неизвестен")
    if guessed == game['location']:
        end_game(chat_id,
            f"🕵️ ШПИОН УГАДАЛ ЛОКАЦИЮ!\n\nЛокация была: {game['location']}\n\n"
            f"🏆 Шпион ({spy_name}) победил!\n\n⏱ Игра длилась: {t_str}",
            spy_won=True)
    else:
        bot.send_message(chat_id, f"❌ Шпион не угадал локацию!\n\nИгра продолжается!")
        try:
            bot.send_message(call.from_user.id, "❌ Неверно! Продолжай, у тебя ещё есть шанс!")
        except Exception as e:
            logger.warning(f"DM spy error: {e}")
        check_game_end(chat_id)

def check_game_end(chat_id):
    game = get_game(chat_id)
    if not game:
        return
    players = game['players']
    ap = active_players(game)
    t_str = elapsed_str(game['start_time'])
    spy_name = next((p.first_name for p in players if p.id == game['spy']), "Неизвестен")
    if len(ap) < 2 or game['round'] >= 3:
        end_game(chat_id,
            f"🕵️ Игра окончена!\n\nШпионом был: {spy_name}\nЛокация: {game['location']}\n\n"
            f"❌ Шпион победил!\n\n⏱ Игра длилась: {t_str}",
            spy_won=True)
        return
    next_round(chat_id)

def next_round(chat_id):
    game = get_game(chat_id)
    if not game:
        return
    game['round'] += 1
    game['answers'] = []
    game['answered'] = []
    game['player_answers'] = {}
    game['correct_answer'] = {}
    game['player_questions'] = {}
    game['spy_guessed'] = None
    game['votes'] = {}
    game['voted'] = []
    game['vote_detail'] = {}
    game['timer_msg_id'] = None
    game['current_player_index'] = 0
    bot.send_message(chat_id, f"🔄 Начинается Раунд {game['round']}!\n\n⏱ У каждого 60 секунд на ответ!")
    prepare_questions(chat_id)
    send_next_player_question(chat_id)

# ─── ІСКЕ ҚОСУ ───────────────────────────────────────────────────────────────
init_db()
try:
    bot.remove_webhook()
    logger.info("✅ Webhook удалён, запускаем polling...")
except Exception as e:
    logger.warning(f"Webhook delete error: {e}")
logger.info("Бот запущен!")
bot.infinity_polling(timeout=60, long_polling_timeout=60)

