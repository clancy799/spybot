import telebot
from telebot import types

BOT_TOKEN = "YOUR_TOKEN"
bot = telebot.TeleBot(BOT_TOKEN)

# Хранение игр по чатам
games = {}

LOCATIONS = [
    "Аэропорт", "Банк", "Больница", "Казино", "Кинотеатр",
    "Корабль", "Космическая станция", "Пляж", "Поезд", "Полицейский участок",
    "Ресторан", "Школа", "Супермаркет", "Цирк", "Зоопарк"
]

@bot.message_handler(commands=['start'])
def start(message):
    name = message.from_user.first_name
    text = (
        f"Игра Шпион:\n"
        f"👋 Привет, {name}!\n\n"
        f"Чтобы начать игру используй команду /game в групповом чате.\n\n"
        f"Команды\n"
        f"/profile — твоя статистика\n"
        f"/achievements — все достижения\n"
        f"/rating — общий рейтинг\n"
        f"/premium — подписка"
    )
    bot.send_message(message.chat.id, text)
    bot.send_message(message.chat.id, "🕵️ Вступайте в оффициальное сообщество: @")

@bot.message_handler(commands=['game'])
def game(message):
    if message.chat.type == 'private':
        bot.send_message(message.chat.id, "❌ Команду /game используй в групповом чате!")
        return

    chat_id = message.chat.id
    name = message.from_user.first_name

    games[chat_id] = {
        'players': [message.from_user],
        'started': False,
        'host': message.from_user.id
    }

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Войти в игру", callback_data="join"))
    markup.add(types.InlineKeyboardButton("▶️ Начать игру", callback_data="start_game"))

    text = (
        f"🕵️ Открывается набор в игру\n\n"
        f"⚙️ Настройки (используются настройки {name}):\n\n"
        f"Количество шпионов: Авто\n\n"
        f"Список локаций: Места и локации 🌍\n\n"
        f"Подсказки шпиону: Да\n\n"
        f"Удаление сообщений: Нет\n\n"
        f"Анонимное голосование: Нет\n\n"
        f"👥 Игроки: {name}"
    )
    bot.send_message(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "join")
def join_game(call):
    chat_id = call.message.chat.id
    user = call.from_user

    if chat_id not in games:
        bot.answer_callback_query(call.id, "Игра не найдена!")
        return

    players = games[chat_id]['players']
    for p in players:
        if p.id == user.id:
            bot.answer_callback_query(call.id, "Ты уже в игре!")
            return

    players.append(user)
    names = ", ".join([p.first_name for p in players])

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Войти в игру", callback_data="join"))
    markup.add(types.InlineKeyboardButton("▶️ Начать игру", callback_data="start_game"))

    host_name = players[0].first_name
    text = (
        f"🕵️ Открывается набор в игру\n\n"
        f"⚙️ Настройки (используются настройки {host_name}):\n\n"
        f"Количество шпионов: Авто\n\n"
        f"Список локаций: Места и локации 🌍\n\n"
        f"Подсказки шпиону: Да\n\n"
        f"Удаление сообщений: Нет\n\n"
        f"Анонимное голосование: Нет\n\n"
        f"👥 Игроки: {names}"
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id, "Ты вошёл в игру!")

@bot.callback_query_handler(func=lambda call: call.data == "start_game")
def start_game(call):
    import random
    chat_id = call.message.chat.id

    if chat_id not in games:
        bot.answer_callback_query(call.id, "Игра не найдена!")
        return

    if call.from_user.id != games[chat_id]['host']:
        bot.answer_callback_query(call.id, "Только организатор может начать игру!")
        return

    players = games[chat_id]['players']
    if len(players) < 3:
        bot.answer_callback_query(call.id, "Нужно минимум 3 игрока!")
        return

    location = random.choice(LOCATIONS)
    spy = random.choice(players)

    for player in players:
        if player.id == spy.id:
            msg = f"🕵️ Ты — ШПИОН!\n\nУзнай локацию у других игроков, не раскрывая себя!"
        else:
            msg = f"📍 Локация: {location}\n\nНайди шпиона среди игроков!"
        try:
            bot.send_message(player.id, msg)
        except:
            pass

    bot.send_message(chat_id, f"🎮 Игра началась! Роли отправлены в личные сообщения.\n📍 Локация известна всем, кроме шпиона!")
    bot.answer_callback_query(call.id, "Игра началась!")
    del games[chat_id]

@bot.message_handler(commands=['profile'])
def profile(message):
    name = message.from_user.first_name
    bot.send_message(message.chat.id, f"👤 Профиль {name}\n\n🎮 Игр сыграно: 0\n🕵️ Шпионом был: 0 раз\n✅ Побед: 0")

@bot.message_handler(commands=['achievements'])
def achievements(message):
    bot.send_message(message.chat.id, "🏆 Достижения\n\nУ тебя пока нет достижений. Сыграй в игру!")

@bot.message_handler(commands=['rating'])
def rating(message):
    bot.send_message(message.chat.id, "📊 Общий рейтинг\n\nРейтинг пока пуст. Сыграй в игру!")

@bot.message_handler(commands=['premium'])
def premium(message):
    bot.send_message(message.chat.id, "⭐ Премиум подписка\n\nПремиум функции скоро будут доступны!")

bot.polling(none_stop=True)
