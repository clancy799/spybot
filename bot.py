import telebot
from telebot import types
import random
import time
import threading
import logging
import sqlite3
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

SUPER_ADMIN_ID = 7949674678  # Осы жерге өз ID-іңді қой
games = {}

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
        voice_protect INTEGER DEFAULT 0,
        correct_answer INTEGER DEFAULT 0,
        rifle INTEGER DEFAULT 0,
        missions_success INTEGER DEFAULT 0,
        total_games INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0,
        is_muted INTEGER DEFAULT 0,
        is_donor INTEGER DEFAULT 0,
        registered_at TEXT DEFAULT (datetime('now'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        level INTEGER DEFAULT 1,
        added_by INTEGER,
        added_at TEXT DEFAULT (datetime('now'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        details TEXT,
        timestamp TEXT DEFAULT (datetime('now'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS disabled_locations (
        location_name TEXT PRIMARY KEY
    )''')
    conn.commit()
    conn.close()

def add_log(user_id, action, details=""):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)", (user_id, action, details))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Log error: {e}")

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

def add_diamonds(user_id, amount):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET diamonds = diamonds + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def add_game(user_id, won):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if won:
        c.execute("UPDATE users SET total_games=total_games+1, missions_success=missions_success+1 WHERE user_id=?", (user_id,))
    else:
        c.execute("UPDATE users SET total_games=total_games+1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def is_admin(user_id):
    if user_id == SUPER_ADMIN_ID:
        return True
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row is not None

def is_super_admin(user_id):
    return user_id == SUPER_ADMIN_ID

def get_enabled_locations():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT location_name FROM disabled_locations")
    disabled = [r[0] for r in c.fetchall()]
    conn.close()
    return [l for l in LOCATION_CHOICES if l not in disabled]

def get_rank(missions):
    if missions < 3: return "🟤 Новичок"
    elif missions < 7: return "🔵 Агент"
    elif missions < 15: return "🟣 Оперативник"
    elif missions < 30: return "🟡 Мастер"
    else: return "🔴 Легенда"

def format_profile(user_id, name):
    row = get_user(user_id, name)
    if not row: return "Профиль табылмады!"
    rank = get_rank(row[8])
    donor = "⭐ Донатор\n" if len(row) > 12 and row[12] else ""
    return (
        f"👤 {row[1]}\n{rank}\n{donor}\n"
        f"💵 Наличные: {row[2]}\n"
        f"💎 Алмазы: {row[3]}\n\n"
        f"🎒 Купленные товары:\n"
        f"📡 Шпионское устройство: {row[4]}\n"
        f"⚖️ Защита голоса: {row[5]}\n"
        f"🎭 Один правильный ответ: {row[6]}\n"
        f"🔫 Винтовка: {row[7]}\n\n"
        f"🎯 Успешные миссии: {row[8]}\n"
        f"🎲 Всего операций: {row[9]}"
    )

def check_achievements(user_id, name):
    row = get_user(user_id, name)
    if not row: return
    missions = row[8]
    rewards = {
        1: ("🕵️ Первый шаг — первая миссия!", 10),
        3: ("🎯 Агент — 3 победы!", 30),
        7: ("👁 Оперативник — 7 побед!", 60),
        15: ("🔥 Мастер — 15 побед!", 100),
        30: ("💀 Легенда — 30 побед!", 150),
    }
    if missions in rewards:
        text, bonus = rewards[missions]
        add_cash(user_id, bonus)
        try:
            bot.send_message(user_id, f"🏆 Достижение разблокировано!\n\n{text}\n\nНаграда: 💵 {bonus}")
        except Exception:
            pass

def send_win_message(chat_id, player, spy_won=False):
    reward_cash = 50 if spy_won else 30
    add_cash(player.id, reward_cash)
    add_game(player.id, True)
    check_achievements(player.id, player.first_name)
    add_log(player.id, "WIN", f"reward={reward_cash}")
    profile = format_profile(player.id, player.first_name)
    try:
        bot.send_message(player.id,
            f"🏆 ПОБЕДА!\n\nВы выиграли и получили награду.\n\n"
            f"Награда: 💵 {reward_cash} | 💎 0\n\n{profile}\n\n📢 Поздравляем с победой!")
    except Exception:
        pass

def send_lose_message(chat_id, player):
    add_game(player.id, False)
    add_log(player.id, "LOSE", "")
    profile = format_profile(player.id, player.first_name)
    try:
        bot.send_message(player.id,
            f"❌ ПОРАЖЕНИЕ!\n\nВы проиграли и не получили награду.\n\n"
            f"Награда: 💵 0 | 💎 0\n\n{profile}\n\n📢 Повезёт в следующий раз!")
    except Exception:
        pass

# ─── ЛОКАЦИЯ БЕЛГІЛЕРІ ────────────────────────────────────────────────────────
LOCATION_HINTS = {
    "Аэропорт": "Это место связано с дальними путешествиями и транспортом",
    "Банк": "Здесь хранятся и обрабатываются деньги",
    "Больница": "Это место связано со здоровьем и медициной",
    "Казино": "Здесь царит азарт и риск",
    "Кинотеатр": "Здесь показывают фильмы в темноте",
    "Корабль": "Это место движется по воде",
    "Космическая станция": "Это место находится за пределами Земли",
    "Пляж": "Здесь есть песок, вода и солнце",
    "Поезд": "Это место движется по рельсам",
    "Полицейский участок": "Здесь работают стражи порядка",
    "Ресторан": "Здесь готовят и подают еду",
    "Школа": "Здесь учатся дети и подростки",
    "Супермаркет": "Здесь продают продукты и товары",
    "Цирк": "Здесь выступают артисты и акробаты",
    "Зоопарк": "Здесь живут разные животные"
}

# RP өлім хабарлары
DEATH_MESSAGES = [
    "{name} был застрелен неизвестным стрелком и покинул игру.",
    "{name} внезапно исчез при невыясненных обстоятельствах.",
    "{name} был нейтрализован и выбыл из игры.",
    "{name} получил сообщение и молча покинул локацию.",
    "{name} был устранён профессиональным образом.",
]

LOCATIONS = {
    "Аэропорт": {"вопросы": [
        {"вопрос": "Что находится прямо перед вами?", "правильные": ["Стойка регистрации с очередью", "Табло с расписанием рейсов", "Ленточный транспортёр с багажом", "Паспортный контроль"]},
        {"вопрос": "Что вы слышите вокруг?", "правильные": ["Объявления о рейсах по громкой связи", "Гул самолётных двигателей вдали", "Скрип колёсиков чемоданов", "Голос диктора на нескольких языках"]},
        {"вопрос": "Что вы держите в руках?", "правильные": ["Посадочный талон", "Паспорт с визой", "Бирку для багажа", "Распечатку маршрута"]},
        {"вопрос": "Что происходит вокруг вас?", "правильные": ["Люди спешат с чемоданами", "Очередь на досмотр", "Кто-то машет рукой на прощание", "Группа туристов с гидом"]}
    ]},
    "Банк": {"вопросы": [
        {"вопрос": "Что вы держите в руках?", "правильные": ["Талон с номером очереди", "Пачку документов для подписи", "Банковскую карту", "Квитанцию о переводе"]},
        {"вопрос": "Что находится перед вами?", "правильные": ["Окошко кассира за стеклом", "Терминал для карт", "Стопку бланков на стойке", "Экран с номером очереди"]},
        {"вопрос": "Что вы слышите?", "правильные": ["Тихие переговоры у стойки", "Звук принтера за стеклом", "Электронный голос вызова номера", "Шелест купюр у кассира"]},
        {"вопрос": "Что происходит рядом с вами?", "правильные": ["Охранник проверяет документы", "Клиент подписывает договор", "Кассир пересчитывает деньги", "Менеджер объясняет условия"]}
    ]},
    "Больница": {"вопросы": [
        {"вопрос": "Что вы слышите вокруг себя?", "правильные": ["Звук капельницы и тихие голоса", "Объявления по громкой связи", "Скрип каталки по коридору", "Писк медицинских приборов"]},
        {"вопрос": "Что находится перед вами?", "правильные": ["Дверь с номером палаты", "Стойка медсестры с документами", "Каталка у стены коридора", "Информационный стенд с расписанием"]},
        {"вопрос": "Что вы чувствуете?", "правильные": ["Запах дезинфицирующего средства", "Прохладный кондиционированный воздух", "Жёсткое кресло в коридоре", "Яркий белый свет ламп"]},
        {"вопрос": "Что происходит рядом?", "правильные": ["Медсестра меняет капельницу", "Врач изучает карточку пациента", "Санитар везёт каталку", "Родственники ждут у палаты"]}
    ]},
    "Казино": {"вопросы": [
        {"вопрос": "Что происходит прямо сейчас?", "правильные": ["Крутится рулетка", "Дилер раздаёт карты", "Кто-то громко выигрывает", "Монеты сыплются из автомата"]},
        {"вопрос": "Что вы слышите?", "правильные": ["Звон фишек на столе", "Музыку и гул голосов", "Звуковые сигналы автоматов", "Возгласы выигравшего игрока"]},
        {"вопрос": "Что вы держите в руках?", "правильные": ["Стопку разноцветных фишек", "Карты, которые только пришли", "Бокал с напитком", "Чек на обмен фишек"]},
        {"вопрос": "Что вы видите вокруг?", "правильные": ["Ряды игровых автоматов", "Стол с зелёным сукном", "Крупье в форменной одежде", "Камеры наблюдения под потолком"]}
    ]},
    "Кинотеатр": {"вопросы": [
        {"вопрос": "Что вы видите перед собой?", "правильные": ["Большой экран с фильмом", "Тёмный зал с силуэтами зрителей", "Мерцающий проектор сзади", "Ряды откидных кресел"]},
        {"вопрос": "Что вы слышите?", "правильные": ["Громкий звук из динамиков", "Шорох попкорна рядом", "Музыку из фильма", "Чей-то тихий смех в зале"]},
        {"вопрос": "Что вы держите в руках?", "правильные": ["Стакан с газировкой", "Коробку попкорна", "Билет с номером места", "Телефон на беззвучном режиме"]},
        {"вопрос": "Что происходит вокруг?", "правильные": ["Гаснет свет перед сеансом", "Кто-то опаздывает и ищет место", "Идут рекламные ролики", "Зрители реагируют на сцену"]}
    ]},
    "Корабль": {"вопросы": [
        {"вопрос": "Что вы чувствуете прямо сейчас?", "правильные": ["Лёгкое покачивание под ногами", "Солёный морской ветер", "Вибрацию двигателей", "Брызги волн на лице"]},
        {"вопрос": "Что вы видите вокруг?", "правильные": ["Горизонт и открытое море", "Другие палубы корабля", "Чаек, летящих за кормой", "Спасательные шлюпки на бортах"]},
        {"вопрос": "Что вы слышите?", "правильные": ["Плеск волн о борт", "Гудок корабля вдали", "Скрип такелажа на ветру", "Команды матросов на палубе"]},
        {"вопрос": "Что происходит рядом?", "правильные": ["Матросы драят палубу", "Пассажиры смотрят на море", "Капитан делает объявление", "Груз закрепляют в трюме"]}
    ]},
    "Космическая станция": {"вопросы": [
        {"вопрос": "Что вы видите в иллюминатор?", "правильные": ["Голубой шар Земли", "Бесконечную черноту с звёздами", "Солнечные панели станции", "Другой стыковочный модуль"]},
        {"вопрос": "Что вы чувствуете?", "правильные": ["Невесомость — всё парит", "Гул системы вентиляции", "Прохладный переработанный воздух", "Вибрацию корпуса станции"]},
        {"вопрос": "Что вы держите в руках?", "правильные": ["Планшет с данными телеметрии", "Контейнер с едой в тюбике", "Ручку на липучке", "Инструмент для ремонта модуля"]},
        {"вопрос": "Что происходит вокруг?", "правильные": ["Коллега проводит эксперимент", "Сигнализирует один из приборов", "Связь с Землёй по рации", "Стыкуется грузовой корабль"]}
    ]},
    "Пляж": {"вопросы": [
        {"вопрос": "Что вы ощущаете под ногами?", "правильные": ["Горячий песок", "Мокрые камни у воды", "Тёплую гальку", "Влажный песок у прибоя"]},
        {"вопрос": "Что вы слышите?", "правильные": ["Шум прибоя", "Крики чаек над головой", "Смех и голоса отдыхающих", "Музыку с соседнего зонтика"]},
        {"вопрос": "Что вы видите вокруг?", "правильные": ["Яркие зонтики вдоль берега", "Волны, набегающие на берег", "Детей, строящих замок из песка", "Лодки у горизонта"]},
        {"вопрос": "Что вы держите в руках?", "правильные": ["Холодный напиток в бутылке", "Крем от загара", "Полотенце с песком", "Ракушку, найденную у воды"]}
    ]},
    "Поезд": {"вопросы": [
        {"вопрос": "Что вы видите за окном?", "правильные": ["Мелькающие деревья и поля", "Тёмный тоннель", "Пролетающую платформу", "Другой состав рядом"]},
        {"вопрос": "Что вы слышите?", "правильные": ["Стук колёс на стыках рельсов", "Объявление следующей станции", "Разговоры соседей по купе", "Свисток локомотива"]},
        {"вопрос": "Что происходит в вагоне?", "правильные": ["Проводник проверяет билеты", "Пассажир несёт чай из буфета", "Кто-то укладывает вещи на полку", "Люди выходят на остановке"]},
        {"вопрос": "Что вы держите в руках?", "правильные": ["Билет с местом и вагоном", "Стакан горячего чая", "Книгу или телефон", "Пакет с едой из дома"]}
    ]},
    "Полицейский участок": {"вопросы": [
        {"вопрос": "Что находится перед вами на столе?", "правильные": ["Протокол для подписи", "Жетон и удостоверение", "Папку с уголовным делом", "Дактилоскопическую карту"]},
        {"вопрос": "Что вы слышите?", "правильные": ["Звук рации на дежурном столе", "Печать документов за стеной", "Чьи-то показания в соседней комнате", "Звяканье ключей у охраны"]},
        {"вопрос": "Что вы видите вокруг?", "правильные": ["Стенд с ориентировками", "Решётчатые окна в коридоре", "Дежурного за стеклянной перегородкой", "Скамейку у стены для ожидающих"]},
        {"вопрос": "Что происходит рядом?", "правильные": ["Следователь задаёт вопросы", "Задержанного проводят мимо", "Офицер заполняет рапорт", "Адвокат просматривает документы"]}
    ]},
    "Ресторан": {"вопросы": [
        {"вопрос": "Что стоит перед вами?", "правильные": ["Тарелку с горячим блюдом", "Меню в кожаной обложке", "Бокал с вином", "Корзинку со свежим хлебом"]},
        {"вопрос": "Что вы слышите?", "правильные": ["Тихую фоновую музыку", "Звон бокалов за соседним столом", "Голоса официантов", "Звук из открытой кухни"]},
        {"вопрос": "Что происходит вокруг?", "правильные": ["Официант принимает заказ", "Сомелье открывает бутылку", "Пара отмечает годовщину", "Повар готовит прямо в зале"]},
        {"вопрос": "Что вы держите в руках?", "правильные": ["Вилку и нож над тарелкой", "Меню с выбором блюд", "Бокал, который только подняли", "Салфетку на коленях"]}
    ]},
    "Школа": {"вопросы": [
        {"вопрос": "Что лежит перед вами?", "правильные": ["Открытый учебник", "Тетрадь с заданием", "Дневник с оценками", "Пенал с карандашами"]},
        {"вопрос": "Что вы слышите?", "правильные": ["Голос учителя у доски", "Звонок между уроками", "Скрип мела по доске", "Шёпот соседа по парте"]},
        {"вопрос": "Что происходит в классе?", "правильные": ["Учитель объясняет тему", "Кто-то отвечает у доски", "Контрольная работа в тишине", "Раздают проверенные тетради"]},
        {"вопрос": "Что вы видите перед собой?", "правильные": ["Доску с записями", "Спину одноклассника за партой", "Таблицы и плакаты на стене", "Журнал на учительском столе"]}
    ]},
    "Супермаркет": {"вопросы": [
        {"вопрос": "Что вы держите в руках?", "правильные": ["Корзину с продуктами", "Список товаров для покупки", "Товар, который изучаете", "Дисконтную карту"]},
        {"вопрос": "Что вы видите вокруг?", "правильные": ["Длинные стеллажи с товарами", "Кассы с очередями", "Акционные ценники на полках", "Холодильники с молочным"]},
        {"вопрос": "Что вы слышите?", "правильные": ["Объявления о скидках по радио", "Пиканье сканера на кассе", "Скрип тележки на колёсиках", "Фоновую музыку в зале"]},
        {"вопрос": "Что происходит рядом?", "правильные": ["Сотрудник выкладывает товар", "Покупатель сравнивает этикетки", "Охранник следит за залом", "Промоутер предлагает пробники"]}
    ]},
    "Цирк": {"вопросы": [
        {"вопрос": "Что происходит на арене?", "правильные": ["Акробат летит под куполом", "Клоун делает фокус", "Дрессировщик работает с животными", "Жонглёр подбрасывает шары"]},
        {"вопрос": "Что вы слышите?", "правильные": ["Барабанную дробь перед трюком", "Смех зрителей в зале", "Бравурную цирковую музыку", "Ведущего в блестящем фраке"]},
        {"вопрос": "Что вы видите вокруг?", "правильные": ["Купол с трапецией наверху", "Ряды зрителей вокруг арены", "Прожекторы, бьющие в центр", "Сетку безопасности под акробатами"]},
        {"вопрос": "Что вы держите в руках?", "правильные": ["Программку с именами артистов", "Сахарную вату на палочке", "Билет с номером ряда", "Воздушный шарик от клоуна"]}
    ]},
    "Зоопарк": {"вопросы": [
        {"вопрос": "Что вы видите прямо перед собой?", "правильные": ["Животное за стеклом вольера", "Табличку с названием вида", "Кормушку внутри клетки", "Ров с водой перед загоном"]},
        {"вопрос": "Что вы слышите?", "правильные": ["Крики и рёв животных", "Голос экскурсовода рядом", "Смех детей у вольера", "Шелест листвы в вольере с птицами"]},
        {"вопрос": "Что происходит рядом?", "правильные": ["Смотритель кормит животных", "Туристы фотографируют вольер", "Ребёнок тянется к ограждению", "Животное прячется в укрытие"]},
        {"вопрос": "Что вы держите в руках?", "правильные": ["Карту зоопарка", "Пакет с едой для животных", "Фотоаппарат или телефон", "Билет на входе"]}
    ]}
}

LOCATION_CHOICES = list(LOCATIONS.keys())

def get_max_rounds(player_count):
    if player_count <= 4: return 2
    elif player_count <= 7: return 3
    elif player_count <= 10: return 4
    else: return 5

def get_max_game_time(player_count):
    if player_count <= 4: return 15 * 60
    elif player_count <= 7: return 17 * 60
    else: return 20 * 60

def get_game(chat_id):
    return games.get(chat_id)

def elapsed_str(start_time):
    e = int(time.time() - start_time)
    return f"{e // 60} мин {e % 60} сек"

def active_players(game):
    return [p for p in game['players'] if p.id not in game['eliminated']]

def end_game(chat_id, text, spy_won=False):
    game = get_game(chat_id)
    try:
        bot.send_message(chat_id, text)
    except Exception:
        pass
    if game:
        spy_id = game.get('spy')
        players = game.get('players', [])
        location = game.get('location', '?')
        for player in players:
            if player.id == spy_id:
                if spy_won:
                    send_win_message(chat_id, player, spy_won=True)
                else:
                    send_lose_message(chat_id, player)
            else:
                if not spy_won:
                    send_win_message(chat_id, player, spy_won=False)
                else:
                    send_lose_message(chat_id, player)
        add_log(0, "GAME_END", f"chat={chat_id} location={location} spy_won={spy_won}")
    games.pop(chat_id, None)

# ─── КОМАНДАЛАР ──────────────────────────────────────────────────────────────
@bot.message_handler(commands=['start'])
def cmd_start(message):
    get_user(message.from_user.id, message.from_user.first_name)
    name = message.from_user.first_name
    bot.send_message(message.chat.id,
        f"🕵️ Игра Шпион\n👋 Привет, {name}!\n\n"
        f"Чтобы начать игру используй /game в групповом чате.\n\n"
        f"Команды:\n/profile — статистика\n/achievements — достижения\n"
        f"/rating — рейтинг\n/shop — магазин\n/rules — правила\n"
        f"/endgame — завершить игру (только хост)")

@bot.message_handler(commands=['rules'])
def cmd_rules(message):
    bot.send_message(message.chat.id,
        "📖 Правила игры Шпион:\n\n"
        "1. Один игрок — шпион, остальные знают локацию\n"
        "2. Каждому приходит вопрос в личку — 60 секунд на ответ\n"
        "3. Вопросы задаются по очереди\n"
        "4. После всех ответов — голосование: кто шпион?\n"
        "5. Шпион пытается угадать локацию\n"
        "6. Шпион угадал — шпион победил!\n"
        "7. Игроки нашли шпиона — игроки победили!\n\n🕵️ Удачи!")

@bot.message_handler(commands=['profile'])
def cmd_profile(message):
    get_user(message.from_user.id, message.from_user.first_name)
    profile = format_profile(message.from_user.id, message.from_user.first_name)
    bot.send_message(message.chat.id, f"👤 Профиль\n\n{profile}")

@bot.message_handler(commands=['achievements'])
def cmd_achievements(message):
    row = get_user(message.from_user.id, message.from_user.first_name)
    missions = row[8] if row else 0
    achievements = [
        (1, "🕵️ Первый шаг", "Первая миссия", 10),
        (3, "🎯 Агент", "3 победы", 30),
        (7, "👁 Оперативник", "7 побед", 60),
        (15, "🔥 Мастер", "15 побед", 100),
        (30, "💀 Легенда", "30 побед", 150),
    ]
    text = "🏆 Достижения\n\n"
    for req, name, desc, bonus in achievements:
        if missions >= req:
            text += f"✅ {name} — {desc} (💵 {bonus})\n"
        else:
            text += f"🔒 {name} — {desc} (💵 {bonus}) — нужно {req} побед\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['rating'])
def cmd_rating(message):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, missions_success, total_games FROM users WHERE total_games > 0 ORDER BY missions_success DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "📊 Рейтинг пуст. Сыграй в игру!")
        return
    text = "📊 Топ игроков:\n\n"
    for i, (name, wins, total) in enumerate(rows, 1):
        text += f"{i}. {name} — 🎯 {wins} побед / 🎲 {total} игр\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['endgame'])
def cmd_endgame(message):
    chat_id = message.chat.id
    game = get_game(chat_id)
    if not game:
        bot.send_message(chat_id, "❌ Активная игра не найдена!")
        return
    if message.from_user.id != game['host'] and not is_admin(message.from_user.id):
        bot.send_message(chat_id, "❌ Только организатор может завершить игру!")
        return
    end_game(chat_id, "🛑 Игра завершена!")

# ─── МАГАЗИН ─────────────────────────────────────────────────────────────────
@bot.message_handler(commands=['shop'])
def cmd_shop(message):
    get_user(message.from_user.id, message.from_user.first_name)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💵 Купить за наличные", callback_data="shop_cash"))
    markup.add(types.InlineKeyboardButton("💎 Купить за алмазы", callback_data="shop_diamonds"))
    markup.add(types.InlineKeyboardButton("⭐ Купить алмазы", callback_data="shop_buy_diamonds"))
    bot.send_message(message.chat.id, "🛒 Магазин\n\nВыбери категорию:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "shop_cash")
def cb_shop_cash(call):
    row = get_user(call.from_user.id, call.from_user.first_name)
    cash = row[2] if row else 0
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⚖️ Защита голоса — 💵 100", callback_data="buy_voice_protect"))
    markup.add(types.InlineKeyboardButton("🎭 Один правильный ответ — 💵 150", callback_data="buy_correct_answer"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="shop_back"))
    bot.edit_message_text(
        f"💵 Магазин за наличные\n\nБаланс: 💵 {cash}\n\n"
        f"⚖️ Защита голоса — если все проголосуют против вас, 1 раз останетесь в игре (авто)\n"
        f"🎭 Один правильный ответ — при вопросе правильный ответ будет выделен\n\nВыберите товар:",
        call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "shop_diamonds")
def cb_shop_diamonds(call):
    row = get_user(call.from_user.id, call.from_user.first_name)
    diamonds = row[3] if row else 0
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔫 Винтовка — 💎 1", callback_data="buy_rifle"))
    markup.add(types.InlineKeyboardButton("📡 Шпионское устройство — 💎 1", callback_data="buy_spy_device"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="shop_back"))
    bot.edit_message_text(
        f"💎 Магазин за алмазы\n\nБаланс: 💎 {diamonds}\n\n"
        f"🔫 Винтовка — только для шпиона, устраняет одного игрока\n"
        f"📡 Шпионское устройство — только для шпиона, даёт подсказку о локации\n\nВыберите товар:",
        call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "shop_buy_diamonds")
def cb_shop_buy_diamonds(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    packages = [
        ("💎 1 — ⭐ 15", "buy_diamonds_1"),
        ("💎 5 — ⭐ 75", "buy_diamonds_5"),
        ("💎 10 — ⭐ 150", "buy_diamonds_10"),
        ("💎 30 — ⭐ 450", "buy_diamonds_30"),
        ("💎 50 — ⭐ 750", "buy_diamonds_50"),
        ("💎 100 — ⭐ 1500", "buy_diamonds_100"),
    ]
    for text, data in packages:
        markup.add(types.InlineKeyboardButton(text, callback_data=data))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="shop_back"))
    bot.edit_message_text("⭐ Купить алмазы\n\nВыберите пакет:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "shop_back")
def cb_shop_back(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💵 Купить за наличные", callback_data="shop_cash"))
    markup.add(types.InlineKeyboardButton("💎 Купить за алмазы", callback_data="shop_diamonds"))
    markup.add(types.InlineKeyboardButton("⭐ Купить алмазы", callback_data="shop_buy_diamonds"))
    bot.edit_message_text("🛒 Магазин\n\nВыбери категорию:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "buy_voice_protect")
def cb_buy_voice_protect(call):
    row = get_user(call.from_user.id, call.from_user.first_name)
    if row[2] < 100:
        bot.answer_callback_query(call.id, "❌ Недостаточно наличных!")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET cash=cash-100, voice_protect=voice_protect+1 WHERE user_id=?", (call.from_user.id,))
    conn.commit()
    conn.close()
    add_log(call.from_user.id, "BUY", "voice_protect")
    bot.answer_callback_query(call.id, "✅ Куплено!")
    bot.send_message(call.from_user.id, "✅ Куплено: ⚖️ Защита голоса\n\nЕсли все проголосуют против вас — автоматически останетесь в игре!")

@bot.callback_query_handler(func=lambda call: call.data == "buy_correct_answer")
def cb_buy_correct_answer(call):
    row = get_user(call.from_user.id, call.from_user.first_name)
    if row[2] < 150:
        bot.answer_callback_query(call.id, "❌ Недостаточно наличных!")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET cash=cash-150, correct_answer=correct_answer+1 WHERE user_id=?", (call.from_user.id,))
    conn.commit()
    conn.close()
    add_log(call.from_user.id, "BUY", "correct_answer")
    bot.answer_callback_query(call.id, "✅ Куплено!")
    bot.send_message(call.from_user.id, "✅ Куплено: 🎭 Один правильный ответ\n\nПри следующем вопросе правильный ответ будет выделен!")

@bot.callback_query_handler(func=lambda call: call.data == "buy_rifle")
def cb_buy_rifle(call):
    row = get_user(call.from_user.id, call.from_user.first_name)
    if row[3] < 1:
        bot.answer_callback_query(call.id, "❌ Недостаточно алмазов!")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET diamonds=diamonds-1, rifle=rifle+1 WHERE user_id=?", (call.from_user.id,))
    conn.commit()
    conn.close()
    add_log(call.from_user.id, "BUY", "rifle")
    bot.answer_callback_query(call.id, "✅ Куплено!")
    bot.send_message(call.from_user.id, "✅ Куплено: 🔫 Винтовка\n\nТолько для шпиона! Можете устранить одного игрока во время игры.")

@bot.callback_query_handler(func=lambda call: call.data == "buy_spy_device")
def cb_buy_spy_device(call):
    row = get_user(call.from_user.id, call.from_user.first_name)
    if row[3] < 1:
        bot.answer_callback_query(call.id, "❌ Недостаточно алмазов!")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET diamonds=diamonds-1, spy_device=spy_device+1 WHERE user_id=?", (call.from_user.id,))
    conn.commit()
    conn.close()
    add_log(call.from_user.id, "BUY", "spy_device")
    bot.answer_callback_query(call.id, "✅ Куплено!")
    bot.send_message(call.from_user.id, "✅ Куплено: 📡 Шпионское устройство\n\nТолько для шпиона! Даёт подсказку о локации.")

# ─── АДМИН ПАНЕЛЬ ────────────────────────────────────────────────────────────
@bot.message_handler(commands=['admin'])
def cmd_admin(message):
    if not is_admin(message.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(total_games) FROM users")
    total_games = c.fetchone()[0] or 0
    conn.close()
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎮 Ойынды басқару", callback_data="adm_game"))
    markup.add(types.InlineKeyboardButton("🕵️ Рөлдерді басқару", callback_data="adm_roles"))
    markup.add(types.InlineKeyboardButton("📍 Локациялар", callback_data="adm_locs"))
    markup.add(types.InlineKeyboardButton("👥 Ойыншылар", callback_data="adm_players"))
    markup.add(types.InlineKeyboardButton("💰 Экономика", callback_data="adm_economy"))
    markup.add(types.InlineKeyboardButton("📢 Хабарлама жіберу", callback_data="adm_broadcast_menu"))
    markup.add(types.InlineKeyboardButton("📊 Бақылау (Logs)", callback_data="adm_logs"))
    if is_super_admin(message.from_user.id):
        markup.add(types.InlineKeyboardButton("👑 Super Admin", callback_data="adm_super"))
    bot.send_message(message.chat.id,
        f"⚙️ Админ панель\n\n"
        f"👥 Ойыншылар: {total_users}\n"
        f"🎲 Жалпы ойындар: {total_games}\n"
        f"🎮 Белсенді ойындар: {len(games)}\n\n"
        f"Бөлім таңда:", reply_markup=markup)

def admin_main_markup(user_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎮 Ойынды басқару", callback_data="adm_game"))
    markup.add(types.InlineKeyboardButton("🕵️ Рөлдерді басқару", callback_data="adm_roles"))
    markup.add(types.InlineKeyboardButton("📍 Локациялар", callback_data="adm_locs"))
    markup.add(types.InlineKeyboardButton("👥 Ойыншылар", callback_data="adm_players"))
    markup.add(types.InlineKeyboardButton("💰 Экономика", callback_data="adm_economy"))
    markup.add(types.InlineKeyboardButton("📢 Хабарлама жіберу", callback_data="adm_broadcast_menu"))
    markup.add(types.InlineKeyboardButton("📊 Бақылау (Logs)", callback_data="adm_logs"))
    if is_super_admin(user_id):
        markup.add(types.InlineKeyboardButton("👑 Super Admin", callback_data="adm_super"))
    return markup

@bot.callback_query_handler(func=lambda call: call.data == "adm_back")
def cb_adm_back(call):
    if not is_admin(call.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(total_games) FROM users")
    total_games = c.fetchone()[0] or 0
    conn.close()
    try:
        bot.edit_message_text(
            f"⚙️ Админ панель\n\n👥 Ойыншылар: {total_users}\n🎲 Жалпы ойындар: {total_games}\n🎮 Белсенді: {len(games)}\n\nБөлім таңда:",
            call.message.chat.id, call.message.message_id,
            reply_markup=admin_main_markup(call.from_user.id))
    except Exception:
        pass

# 🎮 ОЙЫНДЫ БАСҚАРУ
@bot.callback_query_handler(func=lambda call: call.data == "adm_game")
def cb_adm_game(call):
    if not is_admin(call.from_user.id): return
    if not games:
        bot.answer_callback_query(call.id, "Белсенді ойын жоқ!", show_alert=True)
        return
    text = "🎮 Белсенді ойындар:\n\n"
    markup = types.InlineKeyboardMarkup()
    for chat_id, game in games.items():
        status = "▶️" if game.get('started') else "⏳"
        players_count = len(game['players'])
        text += f"{status} Chat: {chat_id} | {players_count} ойыншы\n"
        markup.add(types.InlineKeyboardButton(f"🛑 {chat_id} тоқтату", callback_data=f"adm_stop_{chat_id}"))
        markup.add(types.InlineKeyboardButton(f"⏭ {chat_id} келесі раунд", callback_data=f"adm_next_{chat_id}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="adm_back"))
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_stop_"))
def cb_adm_stop(call):
    if not is_admin(call.from_user.id): return
    chat_id = int(call.data.replace("adm_stop_", ""))
    end_game(chat_id, "🛑 Игра остановлена администратором!")
    add_log(call.from_user.id, "ADMIN_STOP", f"chat={chat_id}")
    bot.answer_callback_query(call.id, f"✅ {chat_id} ойыны тоқтатылды!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_next_"))
def cb_adm_next(call):
    if not is_admin(call.from_user.id): return
    chat_id = int(call.data.replace("adm_next_", ""))
    game = get_game(chat_id)
    if game and game.get('started'):
        next_round(chat_id)
        add_log(call.from_user.id, "ADMIN_NEXT_ROUND", f"chat={chat_id}")
        bot.answer_callback_query(call.id, "✅ Келесі раунд басталды!")
    else:
        bot.answer_callback_query(call.id, "❌ Ойын табылмады!")

# 🕵️ РӨЛДЕРДІ БАСҚАРУ
@bot.callback_query_handler(func=lambda call: call.data == "adm_roles")
def cb_adm_roles(call):
    if not is_admin(call.from_user.id): return
    if not games:
        bot.answer_callback_query(call.id, "Белсенді ойын жоқ!", show_alert=True)
        return
    text = "🕵️ Белсенді ойындар рөлдері:\n\n"
    for chat_id, game in games.items():
        if game.get('started'):
            spy_name = next((p.first_name for p in game['players'] if p.id == game['spy']), "?")
            players_list = ", ".join(p.first_name for p in game['players'])
            text += f"Chat {chat_id}:\n🕵️ Шпион: {spy_name}\n📍 Локация: {game['location']}\n👥 {players_list}\n\n"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔀 Шпионды өзгерту: /setspy [chat_id] [user_id]", callback_data="adm_setspy_info"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="adm_back"))
    try:
        bot.edit_message_text(text if text != "🕵️ Белсенді ойындар рөлдері:\n\n" else "Белсенді ойын жоқ",
            call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data == "adm_setspy_info")
def cb_adm_setspy_info(call):
    bot.answer_callback_query(call.id, "🕵️ Шпионды өзгерту:\n/setspy [chat_id] [user_id]\n\nМысалы: /setspy -100123456 987654321", show_alert=True)

# 📍 ЛОКАЦИЯЛАР
@bot.callback_query_handler(func=lambda call: call.data == "adm_locs")
def cb_adm_locs(call):
    if not is_admin(call.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT location_name FROM disabled_locations")
    disabled = [r[0] for r in c.fetchall()]
    conn.close()
    markup = types.InlineKeyboardMarkup()
    for loc in LOCATION_CHOICES:
        status = "❌" if loc in disabled else "✅"
        markup.add(types.InlineKeyboardButton(f"{status} {loc}", callback_data=f"adm_loc_{loc}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="adm_back"))
    try:
        bot.edit_message_text("📍 Локациялар\n\n✅ қосылған | ❌ өшірілген:",
            call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_loc_"))
def cb_adm_loc_toggle(call):
    if not is_admin(call.from_user.id): return
    loc = call.data.replace("adm_loc_", "")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT location_name FROM disabled_locations WHERE location_name=?", (loc,))
    exists = c.fetchone()
    if exists:
        c.execute("DELETE FROM disabled_locations WHERE location_name=?", (loc,))
        msg = f"✅ {loc} қосылды!"
    else:
        c.execute("INSERT INTO disabled_locations (location_name) VALUES (?)", (loc,))
        msg = f"❌ {loc} өшірілді!"
    conn.commit()
    conn.close()
    add_log(call.from_user.id, "ADMIN_TOGGLE_LOC", loc)
    bot.answer_callback_query(call.id, msg)
    cb_adm_locs(call)

# 👥 ОЙЫНШЫЛАР
@bot.callback_query_handler(func=lambda call: call.data == "adm_players")
def cb_adm_players(call):
    if not is_admin(call.from_user.id): return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚫 /ban [id]", callback_data="adm_info_ban"))
    markup.add(types.InlineKeyboardButton("✅ /unban [id]", callback_data="adm_info_unban"))
    markup.add(types.InlineKeyboardButton("🔇 /mute [id]", callback_data="adm_info_mute"))
    markup.add(types.InlineKeyboardButton("🗑 /resetuser [id]", callback_data="adm_info_reset"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="adm_back"))
    try:
        bot.edit_message_text("👥 Ойыншылар басқару:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_info_"))
def cb_adm_info(call):
    info = {
        "adm_info_ban": "🚫 Бан:\n/ban [user_id]",
        "adm_info_unban": "✅ Бан алу:\n/unban [user_id]",
        "adm_info_mute": "🔇 Мут:\n/mute [user_id]",
        "adm_info_reset": "🗑 Тазалау:\n/resetuser [user_id]",
    }
    bot.answer_callback_query(call.id, info.get(call.data, ""), show_alert=True)

# 💰 ЭКОНОМИКА
@bot.callback_query_handler(func=lambda call: call.data == "adm_economy")
def cb_adm_economy(call):
    if not is_admin(call.from_user.id): return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💵 /addcash [id] [сумма]", callback_data="adm_eco_cash"))
    markup.add(types.InlineKeyboardButton("💎 /adddiamonds [id] [сумма]", callback_data="adm_eco_dia"))
    markup.add(types.InlineKeyboardButton("⭐ /setdonor [id]", callback_data="adm_eco_donor"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="adm_back"))
    try:
        bot.edit_message_text("💰 Экономика басқару:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_eco_"))
def cb_adm_eco_info(call):
    info = {
        "adm_eco_cash": "💵 Ақша қосу:\n/addcash [user_id] [сумма]",
        "adm_eco_dia": "💎 Алмаз қосу:\n/adddiamonds [user_id] [сумма]",
        "adm_eco_donor": "⭐ Донатор:\n/setdonor [user_id]",
    }
    bot.answer_callback_query(call.id, info.get(call.data, ""), show_alert=True)

# 📢 BROADCAST МЕНЮ
@bot.callback_query_handler(func=lambda call: call.data == "adm_broadcast_menu")
def cb_adm_broadcast_menu(call):
    if not is_admin(call.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    conn.close()
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="adm_back"))
    try:
        bot.edit_message_text(
            f"📢 Хабарлама жіберу\n\n👥 Жалпы ойыншылар: {total}\n\n"
            f"Команда:\n/broadcast [текст]\n\nМысалы:\n/broadcast Привет всем! Новое обновление!",
            call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        pass

# 📊 LOGS
@bot.callback_query_handler(func=lambda call: call.data == "adm_logs")
def cb_adm_logs(call):
    if not is_admin(call.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, action, details, timestamp FROM logs ORDER BY id DESC LIMIT 15")
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.answer_callback_query(call.id, "Журнал бос!", show_alert=True)
        return
    text = "📊 Соңғы 15 әрекет:\n\n"
    for uid, action, details, ts in rows:
        text += f"[{ts[:16]}] {uid} → {action}"
        if details:
            text += f" ({details})"
        text += "\n"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="adm_back"))
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        bot.send_message(call.message.chat.id, text)

# 👑 SUPER ADMIN
@bot.callback_query_handler(func=lambda call: call.data == "adm_super")
def cb_adm_super(call):
    if not is_super_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Рұқсат жоқ!")
        return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👤 /addadmin [id]", callback_data="adm_s_info_add"))
    markup.add(types.InlineKeyboardButton("🗑 /removeadmin [id]", callback_data="adm_s_info_remove"))
    markup.add(types.InlineKeyboardButton("💾 DB резервтік көшіру", callback_data="adm_s_backup"))
    markup.add(types.InlineKeyboardButton("⚠️ Барлық статистиканы тазалау", callback_data="adm_s_resetall"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="adm_back"))
    try:
        bot.edit_message_text("👑 Super Admin панель:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data in ["adm_s_info_add", "adm_s_info_remove"])
def cb_adm_s_info(call):
    info = {
        "adm_s_info_add": "👤 Админ қосу:\n/addadmin [user_id]",
        "adm_s_info_remove": "🗑 Админ алу:\n/removeadmin [user_id]",
    }
    bot.answer_callback_query(call.id, info.get(call.data, ""), show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "adm_s_backup")
def cb_adm_s_backup(call):
    if not is_super_admin(call.from_user.id): return
    try:
        with open(DB_PATH, 'rb') as f:
            bot.send_document(call.from_user.id, f, caption="💾 Database резервтік көшірмесі")
        bot.answer_callback_query(call.id, "✅ Жіберілді!")
        add_log(call.from_user.id, "SUPER_BACKUP", "")
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Қате: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "adm_s_resetall")
def cb_adm_s_resetall(call):
    if not is_super_admin(call.from_user.id): return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⚠️ Иә, тазала!", callback_data="adm_s_resetall_confirm"))
    markup.add(types.InlineKeyboardButton("❌ Жоқ", callback_data="adm_super"))
    try:
        bot.edit_message_text("⚠️ Барлық статистика тазаланады!\n\nРастайсың ба?",
            call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data == "adm_s_resetall_confirm")
def cb_adm_s_resetall_confirm(call):
    if not is_super_admin(call.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET cash=0, diamonds=0, missions_success=0, total_games=0, spy_device=0, voice_protect=0, correct_answer=0, rifle=0")
    conn.commit()
    conn.close()
    add_log(call.from_user.id, "SUPER_RESET_ALL", "")
    bot.answer_callback_query(call.id, "✅ Барлық статистика тазаланды!")

# ─── АДМИН КОМАНДАЛАР ────────────────────────────────────────────────────────
@bot.message_handler(commands=['addcash'])
def cmd_addcash(message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 3:
        bot.send_message(message.chat.id, "❌ Формат: /addcash [user_id] [сумма]")
        return
    try:
        user_id, amount = int(parts[1]), int(parts[2])
        add_cash(user_id, amount)
        add_log(message.from_user.id, "ADMIN_ADDCASH", f"target={user_id} amount={amount}")
        bot.send_message(message.chat.id, f"✅ {user_id} аккаунтына 💵 {amount} қосылды!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Қате: {e}")

@bot.message_handler(commands=['adddiamonds'])
def cmd_adddiamonds(message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 3:
        bot.send_message(message.chat.id, "❌ Формат: /adddiamonds [user_id] [сумма]")
        return
    try:
        user_id, amount = int(parts[1]), int(parts[2])
        add_diamonds(user_id, amount)
        add_log(message.from_user.id, "ADMIN_ADDDIAMONDS", f"target={user_id} amount={amount}")
        bot.send_message(message.chat.id, f"✅ {user_id} аккаунтына 💎 {amount} қосылды!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Қате: {e}")

@bot.message_handler(commands=['ban'])
def cmd_ban(message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "❌ Формат: /ban [user_id]")
        return
    user_id = int(parts[1])
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    add_log(message.from_user.id, "ADMIN_BAN", f"target={user_id}")
    bot.send_message(message.chat.id, f"🚫 {user_id} банға жіберілді!")

@bot.message_handler(commands=['unban'])
def cmd_unban(message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "❌ Формат: /unban [user_id]")
        return
    user_id = int(parts[1])
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    add_log(message.from_user.id, "ADMIN_UNBAN", f"target={user_id}")
    bot.send_message(message.chat.id, f"✅ {user_id} банан алынды!")

@bot.message_handler(commands=['mute'])
def cmd_mute(message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "❌ Формат: /mute [user_id]")
        return
    user_id = int(parts[1])
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_muted=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    add_log(message.from_user.id, "ADMIN_MUTE", f"target={user_id}")
    bot.send_message(message.chat.id, f"🔇 {user_id} мутқа алынды!")

@bot.message_handler(commands=['setdonor'])
def cmd_setdonor(message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "❌ Формат: /setdonor [user_id]")
        return
    user_id = int(parts[1])
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_donor=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    add_log(message.from_user.id, "ADMIN_SETDONOR", f"target={user_id}")
    bot.send_message(message.chat.id, f"⭐ {user_id} донатор мәртебесі берілді!")

@bot.message_handler(commands=['resetuser'])
def cmd_resetuser(message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "❌ Формат: /resetuser [user_id]")
        return
    user_id = int(parts[1])
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET cash=0, diamonds=0, spy_device=0, voice_protect=0, correct_answer=0, rifle=0, missions_success=0, total_games=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    add_log(message.from_user.id, "ADMIN_RESETUSER", f"target={user_id}")
    bot.send_message(message.chat.id, f"✅ {user_id} деректері тазаланды!")

@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(message):
    if not is_admin(message.from_user.id): return
    text = message.text.replace('/broadcast', '').strip()
    if not text:
        bot.send_message(message.chat.id, "❌ Формат: /broadcast [текст]")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    sent = 0
    for (uid,) in users:
        try:
            bot.send_message(uid, f"📢 Хабарлама:\n\n{text}")
            sent += 1
        except Exception:
            pass
    add_log(message.from_user.id, "ADMIN_BROADCAST", f"sent={sent}")
    bot.send_message(message.chat.id, f"✅ {sent} ойыншыға жіберілді!")

@bot.message_handler(commands=['setspy'])
def cmd_setspy(message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 3:
        bot.send_message(message.chat.id, "❌ Формат: /setspy [chat_id] [user_id]")
        return
    try:
        chat_id = int(parts[1])
        user_id = int(parts[2])
        game = get_game(chat_id)
        if not game:
            bot.send_message(message.chat.id, "❌ Ойын табылмады!")
            return
        player = next((p for p in game['players'] if p.id == user_id), None)
        if not player:
            bot.send_message(message.chat.id, "❌ Ойыншы табылмады!")
            return
        game['spy'] = user_id
        add_log(message.from_user.id, "ADMIN_SETSPY", f"chat={chat_id} spy={user_id}")
        bot.send_message(message.chat.id, f"✅ {player.first_name} шпион болды!")
        try:
            bot.send_message(user_id, "🕵️ Администратор сізді шпион етіп тағайындады!")
        except Exception:
            pass
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Қате: {e}")

@bot.message_handler(commands=['stats'])
def cmd_stats(message):
    if not is_admin(message.from_user.id): return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT SUM(total_games) FROM users")
    total_games = c.fetchone()[0] or 0
    c.execute("SELECT SUM(cash) FROM users")
    total_cash = c.fetchone()[0] or 0
    c.execute("SELECT SUM(diamonds) FROM users")
    total_diamonds = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")
    banned = c.fetchone()[0]
    conn.close()
    bot.send_message(message.chat.id,
        f"📊 Статистика:\n\n"
        f"👥 Ойыншылар: {total_users}\n"
        f"🎲 Жалпы ойындар: {total_games}\n"
        f"💵 Жалпы ақша: {total_cash}\n"
        f"💎 Жалпы алмаз: {total_diamonds}\n"
        f"🚫 Банда: {banned}\n"
        f"🎮 Белсенді ойындар: {len(games)}")

@bot.message_handler(commands=['addadmin'])
def cmd_addadmin(message):
    if not is_super_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "❌ Формат: /addadmin [user_id]")
        return
    user_id = int(parts[1])
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO admins (user_id, name, added_by) VALUES (?, ?, ?)",
              (user_id, "Admin", message.from_user.id))
    conn.commit()
    conn.close()
    add_log(message.from_user.id, "SUPER_ADDADMIN", f"target={user_id}")
    bot.send_message(message.chat.id, f"✅ {user_id} админге қосылды!")

@bot.message_handler(commands=['removeadmin'])
def cmd_removeadmin(message):
    if not is_super_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "❌ Формат: /removeadmin [user_id]")
        return
    user_id = int(parts[1])
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    add_log(message.from_user.id, "SUPER_REMOVEADMIN", f"target={user_id}")
    bot.send_message(message.chat.id, f"✅ {user_id} админнен алынды!")

# ─── ОЙЫН ────────────────────────────────────────────────────────────────────
@bot.message_handler(commands=['game'])
def cmd_game(message):
    if message.chat.type == 'private':
        bot.send_message(message.chat.id, "❌ Команду /game используй в групповом чате!")
        return
    chat_id = message.chat.id
    if chat_id in games:
        bot.send_message(chat_id, "❌ Игра уже идёт!")
        return
    user = message.from_user
    get_user(user.id, user.first_name)
    # Бан тексеру жоқ — кез келген адам ойнай алады
    games[chat_id] = {
        'players': [user], 'started': False, 'host': user.id,
        'start_time': None, 'eliminated': [], 'round': 0,
        'answers': [], 'answered': [], 'player_answers': {},
        'correct_answer': {}, 'spy_guessed': None, 'votes': {},
        'voted': [], 'vote_detail': {}, 'location': None, 'spy': None,
        'timer_msg_id': None, 'current_player_index': 0,
        'lobby_msg_id': None, 'last_activity': time.time(), 'max_rounds': 3,
        'rifle_used': False
    }
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Войти в игру", callback_data="join"))
    markup.add(types.InlineKeyboardButton("▶️ Начать игру", callback_data="start_game"))
    sent = bot.send_message(chat_id,
        f"🕵️ Открывается набор в игру\n\n👥 Игроки: {user.first_name}\n\n⏱ Игра начнётся автоматически через 3 минуты!",
        reply_markup=markup)
    games[chat_id]['lobby_msg_id'] = sent.message_id
    try:
        bot.pin_chat_message(chat_id, sent.message_id)
    except Exception:
        pass

    def auto_start():
        time.sleep(180)
        g = get_game(chat_id)
        if not g or g.get('started'): return
        if len(g['players']) < 3:
            bot.send_message(chat_id, "⏱ Время вышло! Недостаточно игроков. Игра отменена.")
            games.pop(chat_id, None)
            return
        bot.send_message(chat_id, "⏱ 3 минуты прошло — игра начинается!")
        start_the_game(chat_id)

    threading.Thread(target=auto_start, daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data == "join")
def cb_join(call):
    chat_id = call.message.chat.id
    user = call.from_user
    get_user(user.id, user.first_name)
    game = get_game(chat_id)
    if not game or game.get('started'):
        bot.answer_callback_query(call.id, "Игра не найдена или уже началась!")
        return
    if any(p.id == user.id for p in game['players']):
        bot.answer_callback_query(call.id, "Ты уже в игре!")
        return
    game['players'].append(user)
    names = ", ".join(p.first_name for p in game['players'])
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Войти в игру", callback_data="join"))
    markup.add(types.InlineKeyboardButton("▶️ Начать игру", callback_data="start_game"))
    try:
        bot.edit_message_text(
            f"🕵️ Открывается набор в игру\n\n👥 Игроки: {names}\n\n⏱ Игра начнётся автоматически через 3 минуты!",
            chat_id, call.message.message_id, reply_markup=markup)
    except Exception:
        pass
    bot.answer_callback_query(call.id, "Ты вошёл в игру!")
    try:
        bot.send_message(user.id, "✅ Ты в игре! Жди начала.")
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data == "start_game")
def cb_start_game(call):
    chat_id = call.message.chat.id
    game = get_game(chat_id)
    if not game or call.from_user.id != game['host']:
        bot.answer_callback_query(call.id, "Только организатор может начать!")
        return
    if len(game['players']) < 3:
        bot.answer_callback_query(call.id, "Нужно минимум 3 игрока!")
        return
    bot.answer_callback_query(call.id, "Игра началась!")
    start_the_game(chat_id)

def start_the_game(chat_id):
    game = get_game(chat_id)
    if not game or game.get('started'): return
    enabled_locs = get_enabled_locations()
    if not enabled_locs:
        bot.send_message(chat_id, "❌ Барлық локациялар өшірілген!")
        return
    location = random.choice(enabled_locs)
    all_players = game['players'][:]
    spy = random.choice(all_players)
    max_rounds = get_max_rounds(len(game['players']))
    max_time = get_max_game_time(len(game['players']))
    game.update({
        'location': location, 'spy': spy.id, 'start_time': time.time(),
        'round': 1, 'answers': [], 'answered': [], 'player_answers': {},
        'correct_answer': {}, 'spy_guessed': None, 'started': True,
        'votes': {}, 'voted': [], 'vote_detail': {},
        'current_player_index': 0, 'max_rounds': max_rounds,
        'last_activity': time.time(), 'eliminated': [], 'rifle_used': False
    })
    lobby_msg_id = game.get('lobby_msg_id')
    if lobby_msg_id:
        try:
            bot.unpin_chat_message(chat_id, lobby_msg_id)
            bot.edit_message_reply_markup(chat_id, lobby_msg_id, reply_markup=None)
        except Exception:
            pass
    names = ", ".join(p.first_name for p in game['players'])
    bot.send_message(chat_id,
        f"🎮 Игра началась! Раунд 1 из {max_rounds}\n\n👥 Игроки: {names}\n\n⏱ У каждого 60 секунд на ответ!")
    add_log(0, "GAME_START", f"chat={chat_id} location={location} spy={spy.id} players={len(game['players'])}")

    def game_time_limit():
        time.sleep(max_time)
        g = get_game(chat_id)
        if not g: return
        spy_name = next((p.first_name for p in g['players'] if p.id == g['spy']), "?")
        end_game(chat_id, f"⏱ Время игры вышло!\n\nШпионом был: {spy_name}\nЛокация: {g['location']}\n\n❌ Шпион победил!", spy_won=True)

    def afk_check():
        while True:
            time.sleep(60)
            g = get_game(chat_id)
            if not g: break
            if time.time() - g.get('last_activity', time.time()) >= 15 * 60:
                end_game(chat_id, "⏱ Игра завершена из-за неактивности!")
                break

    threading.Thread(target=game_time_limit, daemon=True).start()
    threading.Thread(target=afk_check, daemon=True).start()
    prepare_questions(chat_id)
    send_next_player_question(chat_id)

def prepare_questions(chat_id):
    game = get_game(chat_id)
    if not game: return
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
        correct = random.choice(chosen_q['правильные'])
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
        game['player_questions'][player.id] = chosen_q['вопрос']

def send_next_player_question(chat_id):
    game = get_game(chat_id)
    if not game: return
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
    correct = game['correct_answer'][player.id]
    game['last_activity'] = time.time()

    bot.send_message(chat_id, f"❓ Раунд {round_num} — Вопрос для {player.first_name}!")

    row = get_user(player.id, player.first_name)
    has_correct_answer = row[6] > 0 if row else False
    has_rifle = row[7] > 0 if row else False
    has_device = row[4] > 0 if row else False

    markup = types.InlineKeyboardMarkup()

    if player.id == game['spy']:
        for i, ans in enumerate(ans_list):
            markup.add(types.InlineKeyboardButton(ans, callback_data=f"ans_{chat_id}_{player.id}_{i}"))
        # Барлық шпионға заттар шығады — сатып алмаса хабарлама шығады
        markup.add(types.InlineKeyboardButton(
            f"🔫 Винтовка {'✅' if has_rifle else '❌'}", 
            callback_data=f"use_rifle_{chat_id}"))
        markup.add(types.InlineKeyboardButton(
            f"📡 Устройство {'✅' if has_device else '❌'}", 
            callback_data=f"use_device_{chat_id}"))
        dm_text = f"🕵️ Ты — ШПИОН!\n\n⚠️ Ты не знаешь локацию!\n\n❓ Вопрос: {question}\n\nВыбери ответ:\n\n🎒 Купленные товары внизу"
    else:
        for i, ans in enumerate(ans_list):
            btn = f"✅ {ans}" if has_correct_answer and ans == correct else ans
            markup.add(types.InlineKeyboardButton(btn, callback_data=f"ans_{chat_id}_{player.id}_{i}"))
        dm_text = f"📍 Локация: {location}\n\n🔍 Среди вас есть шпион!\n\n❓ Вопрос: {question}\n\nВыбери ответ:"
        if has_correct_answer:
            dm_text += "\n\n🎭 Правильный ответ выделен ✅"
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE users SET correct_answer=correct_answer-1 WHERE user_id=?", (player.id,))
            conn.commit()
            conn.close()

    try:
        bot.send_message(player.id, dm_text, reply_markup=markup)
    except Exception as e:
        logger.warning(f"DM error: {e}")

    start_player_timer(chat_id, player.id, player.first_name)

# ─── ЗАТТАРДЫ ҚОЛДАНУ ────────────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("use_rifle_"))
def cb_use_rifle(call):
    chat_id = int(call.data.split("_")[2])
    game = get_game(chat_id)
    if not game or call.from_user.id != game['spy']:
        bot.answer_callback_query(call.id, "❌ Только шпион может использовать!")
        return
    row = get_user(call.from_user.id, call.from_user.first_name)
    if not row or row[7] < 1:
        bot.answer_callback_query(call.id, "❌ У вас нет винтовки. Купите в /shop", show_alert=True)
        return
    if game.get('rifle_used'):
        bot.answer_callback_query(call.id, "❌ Винтовка уже использована в этом раунде!", show_alert=True)
        return
    players = active_players(game)
    targets = [p for p in players if p.id != call.from_user.id]
    if not targets:
        bot.answer_callback_query(call.id, "❌ Нет целей!")
        return
    markup = types.InlineKeyboardMarkup()
    for p in targets:
        markup.add(types.InlineKeyboardButton(p.first_name, callback_data=f"rifle_shoot_{chat_id}_{p.id}"))
    bot.answer_callback_query(call.id)
    bot.send_message(call.from_user.id, "🔫 Выбери цель:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("rifle_shoot_"))
def cb_rifle_shoot(call):
    parts = call.data.split("_")
    chat_id = int(parts[2])
    target_id = int(parts[3])
    game = get_game(chat_id)
    if not game or call.from_user.id != game['spy']:
        bot.answer_callback_query(call.id, "Ошибка!")
        return
    if game.get('rifle_used'):
        bot.answer_callback_query(call.id, "❌ Уже использована!")
        return
    target = next((p for p in game['players'] if p.id == target_id), None)
    if not target or target_id in game['eliminated']:
        bot.answer_callback_query(call.id, "❌ Игрок уже выбыл!")
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET rifle=rifle-1 WHERE user_id=?", (call.from_user.id,))
    conn.commit()
    conn.close()
    game['eliminated'].append(target_id)
    game['rifle_used'] = True
    add_log(call.from_user.id, "USE_RIFLE", f"target={target_id} chat={chat_id}")
    bot.answer_callback_query(call.id, "✅ Выстрел произведён!")
    # RP хабар — нақты ник көрсетеді
    death_msg = random.choice(DEATH_MESSAGES).format(name=target.first_name)
    bot.send_message(chat_id, f"🔫 {death_msg}")
    try:
        bot.send_message(target_id, "💀 Вы были устранены шпионом и выбыли из игры.\n\nНаблюдайте за происходящим!")
    except Exception:
        pass
    # 1 ойыншы қалса тексер
    ap = active_players(game)
    if len(ap) <= 1:
        t_str = elapsed_str(game['start_time'])
        spy_name = next((p.first_name for p in game['players'] if p.id == game['spy']), "?")
        end_game(chat_id,
            f"🕵️ Шпион устранил всех игроков!\n\nШпионом был: {spy_name}\nЛокация: {game['location']}\n\n❌ Шпион победил!\n\n⏱ {t_str}",
            spy_won=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("use_device_"))
def cb_use_device(call):
    chat_id = int(call.data.split("_")[2])
    game = get_game(chat_id)
    if not game or call.from_user.id != game['spy']:
        bot.answer_callback_query(call.id, "❌ Только шпион может использовать!")
        return
    row = get_user(call.from_user.id, call.from_user.first_name)
    if not row or row[4] < 1:
        bot.answer_callback_query(call.id, "❌ У вас нет устройства. Купите в /shop", show_alert=True)
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET spy_device=spy_device-1 WHERE user_id=?", (call.from_user.id,))
    conn.commit()
    conn.close()
    hint = LOCATION_HINTS.get(game['location'], "Место остаётся загадкой...")
    add_log(call.from_user.id, "USE_DEVICE", f"chat={chat_id}")
    bot.answer_callback_query(call.id)
    bot.send_message(call.from_user.id, f"📡 Шпионское устройство активировано!\n\n🔍 Подсказка: {hint}")

def start_player_timer(chat_id, player_id, player_name):
    def timer():
        try:
            timer_msg = bot.send_message(chat_id, f"⏱ {player_name} — 60 сек на ответ!")
            game = get_game(chat_id)
            if not game: return
            game['timer_msg_id'] = timer_msg.message_id
        except Exception:
            return
        for remaining in range(50, 0, -10):
            time.sleep(10)
            game = get_game(chat_id)
            if not game or player_id in game['answered']:
                try:
                    bot.delete_message(chat_id, timer_msg.message_id)
                except Exception:
                    pass
                return
            try:
                bot.edit_message_text(f"⏱ {player_name} — {remaining} сек на ответ!", chat_id, timer_msg.message_id)
            except Exception:
                pass
        time.sleep(10)
        game = get_game(chat_id)
        if not game: return
        try:
            bot.delete_message(chat_id, timer_msg.message_id)
        except Exception:
            pass
        if player_id in game['answered']: return
        location = game['location']
        all_answers = []
        for q in LOCATIONS[location]['вопросы']:
            all_answers.extend(q['правильные'])
        rand_answer = random.choice(all_answers)
        game['answers'].append({'player': player_name, 'a': rand_answer, 'afk': True})
        game['answered'].append(player_id)
        bot.send_message(chat_id, f"💬 {player_name} отвечает:\n➡️ {rand_answer}")
        game['current_player_index'] = game.get('current_player_index', 0) + 1
        send_next_player_question(chat_id)

    threading.Thread(target=timer, daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data.startswith("ans_"))
def cb_answer(call):
    parts = call.data.split("_")
    if len(parts) != 4: return
    chat_id = int(parts[1])
    player_id = int(parts[2])
    answer_index = int(parts[3])
    if call.from_user.id != player_id:
        bot.answer_callback_query(call.id, "Это не твой вопрос!")
        return
    game = get_game(chat_id)
    if not game or player_id in game['answered']:
        bot.answer_callback_query(call.id, "Уже ответил!")
        return
    ans_list = game['player_answers'].get(player_id)
    if not ans_list or answer_index >= len(ans_list): return
    answer_text = ans_list[answer_index]
    player = call.from_user
    game['answers'].append({'player': player.first_name, 'a': answer_text, 'afk': False})
    game['answered'].append(player_id)
    game['last_activity'] = time.time()
    bot.answer_callback_query(call.id, "Ответ принят!")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    bot.send_message(chat_id, f"💬 {player.first_name} отвечает:\n➡️ {answer_text}")
    game['current_player_index'] = game.get('current_player_index', 0) + 1
    send_next_player_question(chat_id)

def start_voting(chat_id):
    game = get_game(chat_id)
    if not game: return
    players = active_players(game)
    # 1 ойыншы қалса — шпион жеңеді
    if len(players) <= 1:
        t_str = elapsed_str(game['start_time'])
        spy_name = next((p.first_name for p in game['players'] if p.id == game['spy']), "?")
        end_game(chat_id,
            f"🕵️ Остался один игрок!\n\nШпионом был: {spy_name}\nЛокация: {game['location']}\n\n❌ Шпион победил!\n\n⏱ {t_str}",
            spy_won=True)
        return
    markup_vote = types.InlineKeyboardMarkup()
    for p in players:
        markup_vote.add(types.InlineKeyboardButton(p.first_name, callback_data=f"vote_{chat_id}_{p.id}"))
    bot.send_message(chat_id, "🗳 Голосование!\n\n👇 Кто шпион?\n⚠️ На себя голосовать нельзя!\n⏱ 60 секунд!", reply_markup=markup_vote)

    def vote_timer():
        time.sleep(60)
        g = get_game(chat_id)
        if not g: return
        ap = active_players(g)
        if len(g['voted']) < len(ap):
            bot.send_message(chat_id, "⏱ Время голосования вышло!")
            finish_voting(chat_id)

    threading.Thread(target=vote_timer, daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data.startswith("vote_"))
def cb_vote(call):
    parts = call.data.split("_")
    chat_id = int(parts[1])
    voted_for_id = int(parts[2])
    voter_id = call.from_user.id
    game = get_game(chat_id)
    if not game or voter_id == voted_for_id or voter_id in game['voted']:
        bot.answer_callback_query(call.id, "Ошибка!")
        return
    ap = active_players(game)
    if voter_id not in [p.id for p in ap]:
        bot.answer_callback_query(call.id, "Ты выбыл!")
        return
    game['voted'].append(voter_id)
    game['votes'][voted_for_id] = game['votes'].get(voted_for_id, 0) + 1
    game['vote_detail'][voter_id] = voted_for_id
    game['last_activity'] = time.time()
    voted_name = next((p.first_name for p in game['players'] if p.id == voted_for_id), "?")
    bot.answer_callback_query(call.id, f"Проголосовал за {voted_name}!")
    bot.send_message(chat_id, f"🗳 {call.from_user.first_name} проголосовал!")
    if len(game['voted']) >= len(ap):
        finish_voting(chat_id)

def finish_voting(chat_id):
    game = get_game(chat_id)
    if not game: return
    votes = game['votes']
    spy_id = game['spy']
    players = game['players']
    t_str = elapsed_str(game['start_time'])
    spy_name = next((p.first_name for p in players if p.id == spy_id), "?")
    vote_log = []
    for vid, tid in game.get('vote_detail', {}).items():
        vname = next((p.first_name for p in players if p.id == vid), "?")
        tname = next((p.first_name for p in players if p.id == tid), "?")
        vote_log.append(f"  {vname} → {tname}")
    vote_log_text = "\n".join(vote_log) if vote_log else "  —"
    if not votes:
        bot.send_message(chat_id, "Никто не проголосовал!")
        next_round(chat_id)
        return
    max_votes = max(votes.values())
    top_ids = [uid for uid, v in votes.items() if v == max_votes]
    results = "\n".join(
        f"  {next((p.first_name for p in players if p.id == uid), '?')}: {v} голос(а)"
        for uid, v in sorted(votes.items(), key=lambda x: -x[1])
    )
    # Ничья — повтор жоқ
    if len(top_ids) > 1:
        tied_names = ", ".join(next((p.first_name for p in players if p.id == uid), "?") for uid in top_ids)
        bot.send_message(chat_id,
            f"📊 Результаты:\n{vote_log_text}\n\n🔢 Итог:\n{results}\n\n"
            f"⚖️ Ничья! Шпион остался в тени...")
        next_round(chat_id)
        return
    max_votes_id = top_ids[0]
    max_votes_name = next((p.first_name for p in players if p.id == max_votes_id), "?")
    bot.send_message(chat_id, f"📊 Результаты:\n{vote_log_text}\n\n🔢 Итог:\n{results}\n\n❌ Выбывает: {max_votes_name}")
    # ⚖️ Защита голоса — автоматты
    row = get_user(max_votes_id, max_votes_name)
    if row and row[5] > 0:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET voice_protect=voice_protect-1 WHERE user_id=?", (max_votes_id,))
        conn.commit()
        conn.close()
        bot.send_message(chat_id, f"⚖️ {max_votes_name} использовал защиту голоса и остался в игре!")
        add_log(max_votes_id, "USE_VOICE_PROTECT", f"chat={chat_id}")
        next_round(chat_id)
        return
    if max_votes_id == spy_id:
        end_game(chat_id,
            f"🎉 Шпион найден!\n\nШпионом был: {spy_name}\nЛокация: {game['location']}\n\n✅ Игроки победили!\n\n⏱ {t_str}",
            spy_won=False)
        return
    game['eliminated'].append(max_votes_id)
    bot.send_message(chat_id, f"❌ {max_votes_name} выбыл! Но это был не шпион...\n\nПродолжаем!")
    try:
        elim = next(p for p in players if p.id == max_votes_id)
        bot.send_message(elim.id, "❌ Тебя выбрали шпионом, но ты им не был...\nТы выбыл.")
    except Exception:
        pass
    # 1 ойыншы қалса тексер
    ap = active_players(game)
    if len(ap) <= 1:
        end_game(chat_id,
            f"🕵️ Игра окончена!\n\nШпионом был: {spy_name}\nЛокация: {game['location']}\n\n❌ Шпион победил!\n\n⏱ {t_str}",
            spy_won=True)
        return
    send_spy_guess(chat_id)

def send_spy_guess(chat_id):
    game = get_game(chat_id)
    if not game: return
    spy_id = game['spy']
    location = game['location']
    players = game['players']
    t_str = elapsed_str(game['start_time'])
    spy_name = next((p.first_name for p in players if p.id == spy_id), "?")
    if spy_id in game['eliminated']:
        end_game(chat_id,
            f"🎉 Шпион найден!\n\nШпионом был: {spy_name}\nЛокация: {location}\n\n✅ Игроки победили!\n\n⏱ {t_str}",
            spy_won=False)
        return
    enabled_locs = get_enabled_locations()
    other_locs = [l for l in enabled_locs if l != location]
    fake_locs = random.sample(other_locs, min(5, len(other_locs)))
    fake_locs.append(location)
    random.shuffle(fake_locs)
    markup = types.InlineKeyboardMarkup()
    for loc in fake_locs:
        markup.add(types.InlineKeyboardButton(loc, callback_data=f"spyg_{chat_id}_{loc}"))
    try:
        bot.send_message(spy_id, f"🗺 Попробуй угадать локацию!\n⏱ У тебя 60 секунд:", reply_markup=markup)
    except Exception:
        pass
    bot.send_message(chat_id, "🕵️ Шпион пытается угадать локацию... (60 сек)")

    def spy_timer():
        time.sleep(60)
        g = get_game(chat_id)
        if not g or g.get('spy_guessed') is not None: return
        g['spy_guessed'] = 'timeout'
        bot.send_message(chat_id, "⏱ Шпион не успел угадать!")
        check_game_end(chat_id)

    threading.Thread(target=spy_timer, daemon=True).start()

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
    except Exception:
        pass
    t_str = elapsed_str(game['start_time'])
    spy_name = next((p.first_name for p in game['players'] if p.id == game['spy']), "?")
    if guessed == game['location']:
        end_game(chat_id,
            f"🕵️ ШПИОН УГАДАЛ ЛОКАЦИЮ!\n\nЛокация была: {game['location']}\n\n🏆 Шпион ({spy_name}) победил!\n\n⏱ {t_str}",
            spy_won=True)
    else:
        bot.send_message(chat_id, "❌ Шпион не угадал локацию!\n\nИгра продолжается!")
        try:
            bot.send_message(call.from_user.id, "❌ Неверно! Продолжай!")
        except Exception:
            pass
        check_game_end(chat_id)

def check_game_end(chat_id):
    game = get_game(chat_id)
    if not game: return
    players = game['players']
    ap = active_players(game)
    t_str = elapsed_str(game['start_time'])
    spy_name = next((p.first_name for p in players if p.id == game['spy']), "?")
    max_rounds = game.get('max_rounds', 3)
    if len(ap) <= 1 or game['round'] >= max_rounds:
        end_game(chat_id,
            f"🕵️ Игра окончена!\n\nШпионом был: {spy_name}\nЛокация: {game['location']}\n\n❌ Шпион победил!\n\n⏱ {t_str}",
            spy_won=True)
        return
    next_round(chat_id)

def next_round(chat_id):
    game = get_game(chat_id)
    if not game: return
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
    game['rifle_used'] = False  # Раунд сайын винтовка қайтадан қолданылады
    max_rounds = game.get('max_rounds', 3)
    bot.send_message(chat_id, f"🔄 Начинается Раунд {game['round']} из {max_rounds}!\n\n⏱ У каждого 60 секунд на ответ!")
    prepare_questions(chat_id)
    send_next_player_question(chat_id)

# ─── ІСКЕ ҚОСУ ───────────────────────────────────────────────────────────────
init_db()
try:
    bot.remove_webhook()
    logger.info("✅ Бот запущен!")
except Exception as e:
    logger.warning(f"Webhook error: {e}")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
# v5
