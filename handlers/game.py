import random
import time
import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from database.models import User
from database.requests import get_user, add_cash, add_game, add_log, get_enabled_locations, is_admin
from utils.helpers import format_profile, get_max_rounds, get_max_game_time, elapsed_str, ACHIEVEMENTS
from data.locations import LOCATIONS, LOCATION_HINTS, DEATH_MESSAGES
from config import SUPER_ADMIN_ID

router = Router()

games: dict = {}


def get_game(chat_id: int):
    return games.get(chat_id)


def active_players(game: dict):
    return [p for p in game["players"] if p.id not in game["eliminated"]]


async def check_achievements(bot, session: AsyncSession, user_id: int, name: str):
    user = await get_user(session, user_id, name)
    rewards = {
        1: ("🕵️ Первый шаг — первая миссия!", 50),
        3: ("🎯 Агент — 3 победы!", 100),
        7: ("👁 Оперативник — 7 побед!", 200),
        15: ("🔥 Мастер — 15 побед!", 350),
        30: ("💀 Легенда — 30 побед!", 500),
    }
    if user.missions_success in rewards:
        text, bonus = rewards[user.missions_success]
        await add_cash(session, user_id, bonus)
        try:
            await bot.send_message(user_id, f"🏆 Достижение разблокировано!\n\n{text}\n\nНаграда: 💵 {bonus}")
        except Exception:
            pass


async def send_win_message(bot, session: AsyncSession, player, spy_won: bool = False):
    reward_cash = 50 if spy_won else 30
    await add_cash(session, player.id, reward_cash)
    await add_game(session, player.id, True)
    await check_achievements(bot, session, player.id, player.first_name)
    await add_log(session, player.id, "WIN", f"reward={reward_cash}")
    user = await get_user(session, player.id, player.first_name)
    try:
        await bot.send_message(player.id,
            f"🏆 ПОБЕДА!\n\nВы выиграли и получили награду.\n\n"
            f"Награда: 💵 {reward_cash}\n\n{format_profile(user)}\n\n📢 Поздравляем с победой!")
    except Exception:
        pass


async def send_lose_message(bot, session: AsyncSession, player):
    await add_game(session, player.id, False)
    await add_log(session, player.id, "LOSE", "")
    user = await get_user(session, player.id, player.first_name)
    try:
        await bot.send_message(player.id,
            f"❌ ПОРАЖЕНИЕ!\n\nВы проиграли и не получили награду.\n\n"
            f"Награда: 💵 0\n\n{format_profile(user)}\n\n📢 Повезёт в следующий раз!")
    except Exception:
        pass


async def end_game(bot, session: AsyncSession, chat_id: int, text: str, spy_won: bool = False, forced: bool = False):
    game = get_game(chat_id)
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        pass
    if game and not forced:
        spy_id = game.get("spy")
        players = game.get("players", [])
        location = game.get("location", "?")
        for player in players:
            if player.id == spy_id:
                if spy_won:
                    await send_win_message(bot, session, player, spy_won=True)
                else:
                    await send_lose_message(bot, session, player)
            else:
                if not spy_won:
                    await send_win_message(bot, session, player, spy_won=False)
                else:
                    await send_lose_message(bot, session, player)
        await add_log(session, 0, "GAME_END", f"chat={chat_id} location={location} spy_won={spy_won}")
    games.pop(chat_id, None)


async def check_min_players(bot, session: AsyncSession, chat_id: int) -> bool:
    game = get_game(chat_id)
    if not game:
        return False
    ap = active_players(game)
    if len(ap) <= 2:
        t_str = elapsed_str(game["start_time"])
        spy_name = next((p.first_name for p in game["players"] if p.id == game["spy"]), "?")
        await end_game(bot, session, chat_id,
            f"🕵️ Осталось мало игроков!\n\nШпионом был: {spy_name}\nЛокация: {game['location']}\n\n❌ Шпион победил!\n\n⏱ {t_str}",
            spy_won=True)
        return True
    return False


# ─── /game ────────────────────────────────────────────────────────────────────
@router.message(Command("game"))
async def cmd_game(message: Message, session: AsyncSession):
    if message.chat.type == "private":
        await message.answer("❌ Команду /game используй в групповом чате!")
        return
    chat_id = message.chat.id
    user = message.from_user
    if chat_id in games:
        await message.answer("❌ Игра уже идёт!")
        return
    await get_user(session, user.id, user.first_name)
    games[chat_id] = {
        "players": [user], "started": False, "host": user.id,
        "start_time": None, "eliminated": [], "round": 0,
        "answers": [], "answered": [], "player_answers": {},
        "correct_answer": {}, "spy_guessed": None, "votes": {},
        "voted": [], "vote_detail": {}, "location": None, "spy": None,
        "timer_msg_id": None, "current_player_index": 0,
        "lobby_msg_id": None, "last_activity": time.time(),
        "max_rounds": 3, "rifle_used": False, "rifle_locked": {}
    }
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Войти в игру", callback_data="join")],
        [InlineKeyboardButton(text="▶️ Начать игру", callback_data="start_game")],
    ])
    sent = await message.answer(
        f"🕵️ Открывается набор в игру\n\n👥 Игроки: {user.first_name}\n\n⏱ Игра начнётся автоматически через 3 минуты!",
        reply_markup=markup
    )
    games[chat_id]["lobby_msg_id"] = sent.message_id
    try:
        await message.bot.pin_chat_message(chat_id, sent.message_id)
    except Exception:
        pass

    async def auto_start():
        await asyncio.sleep(180)
        g = get_game(chat_id)
        if not g or g.get("started"):
            return
        if len(g["players"]) < 3:
            await message.bot.send_message(chat_id, "⏱ Время вышло! Недостаточно игроков. Игра отменена.")
            try:
                await message.bot.unpin_chat_message(chat_id, g["lobby_msg_id"])
                await message.bot.delete_message(chat_id, g["lobby_msg_id"])
            except Exception:
                pass
            games.pop(chat_id, None)
            return
        await message.bot.send_message(chat_id, "⏱ 3 минуты прошло — игра начинается!")
        await start_the_game(message.bot, session, chat_id)

    asyncio.create_task(auto_start())


@router.callback_query(F.data == "join")
async def cb_join(call: CallbackQuery, session: AsyncSession):
    chat_id = call.message.chat.id
    user = call.from_user
    await get_user(session, user.id, user.first_name)
    game = get_game(chat_id)
    if not game or game.get("started"):
        await call.answer("Игра не найдена или уже началась!")
        return
    if any(p.id == user.id for p in game["players"]):
        await call.answer("Ты уже в игре!")
        return
    game["players"].append(user)
    names = ", ".join(p.first_name for p in game["players"])
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Войти в игру", callback_data="join")],
        [InlineKeyboardButton(text="▶️ Начать игру", callback_data="start_game")],
    ])
    try:
        await call.message.edit_text(
            f"🕵️ Открывается набор в игру\n\n👥 Игроки: {names}\n\n⏱ Игра начнётся автоматически через 3 минуты!",
            reply_markup=markup
        )
    except Exception:
        pass
    await call.answer("Ты вошёл в игру!")
    try:
        await call.bot.send_message(user.id, "✅ Ты в игре! Жди начала.")
    except Exception:
        pass


@router.callback_query(F.data == "start_game")
async def cb_start_game(call: CallbackQuery, session: AsyncSession):
    chat_id = call.message.chat.id
    game = get_game(chat_id)
    # Хост немесе бот админдері ғана баса алады
    if not game:
        await call.answer("Игра не найдена!")
        return
    if call.from_user.id != game["host"] and not await is_admin(session, call.from_user.id, SUPER_ADMIN_ID):
        await call.answer("Только организатор может начать!")
        return
    if len(game["players"]) < 3:
        await call.answer("Нужно минимум 3 игрока!")
        return
    await call.answer("Игра началась!")
    await start_the_game(call.bot, session, chat_id)


async def start_the_game(bot, session: AsyncSession, chat_id: int):
    game = get_game(chat_id)
    if not game or game.get("started"):
        return
    enabled_locs = await get_enabled_locations(session)
    if not enabled_locs:
        await bot.send_message(chat_id, "❌ Все локации отключены!")
        return
    location = random.choice(enabled_locs)
    spy = random.choice(game["players"][:])
    max_rounds = get_max_rounds(len(game["players"]))
    max_time = get_max_game_time(len(game["players"]))
    game.update({
        "location": location, "spy": spy.id, "start_time": time.time(),
        "round": 1, "answers": [], "answered": [], "player_answers": {},
        "correct_answer": {}, "spy_guessed": None, "started": True,
        "votes": {}, "voted": [], "vote_detail": {},
        "current_player_index": 0, "max_rounds": max_rounds,
        "last_activity": time.time(), "eliminated": [],
        "rifle_used": False, "rifle_locked": {}
    })
    lobby_msg_id = game.get("lobby_msg_id")
    if lobby_msg_id:
        try:
            await bot.unpin_chat_message(chat_id, lobby_msg_id)
            await bot.edit_message_reply_markup(chat_id, lobby_msg_id, reply_markup=None)
        except Exception:
            pass
    names = ", ".join(p.first_name for p in game["players"])
    await bot.send_message(chat_id,
        f"🎮 Игра началась! Раунд 1 из {max_rounds}\n\n👥 Игроки: {names}\n\n⏱ У каждого 60 секунд на ответ!")
    await add_log(session, 0, "GAME_START", f"chat={chat_id} location={location} spy={spy.id} players={len(game['players'])}")

    async def game_time_limit():
        await asyncio.sleep(max_time)
        g = get_game(chat_id)
        if not g:
            return
        spy_name = next((p.first_name for p in g["players"] if p.id == g["spy"]), "?")
        await end_game(bot, session, chat_id,
            f"⏱ Время игры вышло!\n\nШпионом был: {spy_name}\nЛокация: {g['location']}\n\n❌ Шпион победил!",
            spy_won=True)

    asyncio.create_task(game_time_limit())
    await prepare_questions(chat_id, session)
    await send_next_player_question(bot, session, chat_id)


async def prepare_questions(chat_id: int, session: AsyncSession):
    game = get_game(chat_id)
    if not game:
        return
    location = game["location"]
    players = active_players(game)
    all_questions = LOCATIONS[location]["вопросы"]
    game["player_answers"] = {}
    game["correct_answer"] = {}
    game["player_questions"] = {}
    used_questions = []
    for player in players:
        available = [q for q in all_questions if q not in used_questions]
        if not available:
            used_questions = []
            available = all_questions[:]
        chosen_q = random.choice(available)
        used_questions.append(chosen_q)
        correct = random.choice(chosen_q["правильные"])
        other_correct = []
        for loc_name, loc_data in LOCATIONS.items():
            if loc_name != location:
                for q in loc_data["вопросы"]:
                    other_correct.extend(q["правильные"])
        fakes = random.sample(other_correct, 3)
        ans_list = fakes + [correct]
        random.shuffle(ans_list)
        game["player_answers"][player.id] = ans_list
        game["correct_answer"][player.id] = correct
        game["player_questions"][player.id] = chosen_q["вопрос"]


async def send_next_player_question(bot, session: AsyncSession, chat_id: int):
    game = get_game(chat_id)
    if not game:
        return
    players = active_players(game)
    idx = game.get("current_player_index", 0)
    if idx >= len(players):
        await start_voting(bot, session, chat_id)
        return
    player = players[idx]
    round_num = game["round"]
    question = game["player_questions"][player.id]
    ans_list = game["player_answers"][player.id]
    game["last_activity"] = time.time()

    await bot.send_message(chat_id, f"❓ Раунд {round_num} — Вопрос для {player.first_name}!")

    user = await get_user(session, player.id, player.first_name)

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ans, callback_data=f"ans_{chat_id}_{player.id}_{i}")]
        for i, ans in enumerate(ans_list)
    ])

    if player.id == game["spy"]:
        dm_text = f"🕵️ Ты — ШПИОН!\n\n⚠️ Ты не знаешь локацию!\n\n❓ Вопрос: {question}\n\nВыбери ответ:"
    else:
        dm_text = f"📍 Локация: {game['location']}\n\n🔍 Среди вас есть шпион!\n\n❓ Вопрос: {question}\n\nВыбери ответ:"

    items_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🔫 Винтовка {'✅' if user.rifle > 0 else '❌'}",
            callback_data=f"use_rifle_{chat_id}"
        )],
        [InlineKeyboardButton(
            text=f"📡 Устройство {'✅' if user.spy_device > 0 else '❌'}",
            callback_data=f"use_device_{chat_id}"
        )],
        [InlineKeyboardButton(
            text=f"🎭 Правильный ответ {'✅' if user.correct_answer > 0 else '❌'}",
            callback_data=f"use_correct_{chat_id}_{player.id}"
        )],
    ])

    try:
        await bot.send_message(player.id, dm_text, reply_markup=markup)
        await bot.send_message(player.id, "🎒 Купленные товары:", reply_markup=items_markup)
    except Exception:
        pass

    await start_player_timer(bot, session, chat_id, player.id, player.first_name)


async def start_player_timer(bot, session: AsyncSession, chat_id: int, player_id: int, player_name: str):
    async def timer():
        try:
            timer_msg = await bot.send_message(chat_id, f"⏱ {player_name} — 60 сек на ответ!")
            game = get_game(chat_id)
            if not game:
                return
            game["timer_msg_id"] = timer_msg.message_id
        except Exception:
            return

        for remaining in range(50, 0, -10):
            await asyncio.sleep(10)
            game = get_game(chat_id)
            if not game or player_id in game["answered"]:
                try:
                    await bot.delete_message(chat_id, timer_msg.message_id)
                except Exception:
                    pass
                return
            try:
                await bot.edit_message_text(f"⏱ {player_name} — {remaining} сек на ответ!", chat_id, timer_msg.message_id)
            except Exception:
                pass

        await asyncio.sleep(10)
        game = get_game(chat_id)
        if not game:
            return
        try:
            await bot.delete_message(chat_id, timer_msg.message_id)
        except Exception:
            pass
        if player_id not in game["answered"]:
            game["answered"].append(player_id)
            game["current_player_index"] = game.get("current_player_index", 0) + 1
            await bot.send_message(chat_id, f"⏱ {player_name} не ответил вовремя!")
            await send_next_player_question(bot, session, chat_id)

    asyncio.create_task(timer())


@router.callback_query(F.data.startswith("ans_"))
async def cb_answer(call: CallbackQuery, session: AsyncSession):
    parts = call.data.split("_")
    chat_id = int(parts[1])
    player_id = int(parts[2])
    ans_idx = int(parts[3])
    if call.from_user.id != player_id:
        await call.answer("❌ Это не твой вопрос!")
        return
    game = get_game(chat_id)
    if not game or player_id in game["answered"]:
        await call.answer("Уже ответил!")
        return

    # Жауап берді — заттарды бұғаттау
    game["rifle_locked"][player_id] = True
    game["answered"].append(player_id)
    game["current_player_index"] = game.get("current_player_index", 0) + 1

    ans_list = game["player_answers"].get(player_id, [])
    chosen = ans_list[ans_idx] if ans_idx < len(ans_list) else "?"
    correct = game["correct_answer"].get(player_id, "")
    is_correct = chosen == correct

    await call.answer("✅ Ответ принят!")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    result_text = f"✅ Правильно!" if is_correct else f"❌ Неверно! Правильный: {correct}"
    try:
        await call.bot.send_message(player_id, result_text)
    except Exception:
        pass

    await call.bot.send_message(chat_id, f"💬 {call.from_user.first_name} отвечает:\n➡️ {chosen}")
    await send_next_player_question(call.bot, session, chat_id)


# ─── ЗАТТАРДЫ ҚОЛДАНУ ────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("use_rifle_"))
async def cb_use_rifle(call: CallbackQuery, session: AsyncSession):
    chat_id = int(call.data.split("_")[2])
    game = get_game(chat_id)
    if not game or call.from_user.id != game["spy"]:
        await call.answer("❌ Только шпион может использовать!")
        return
    user = await get_user(session, call.from_user.id, call.from_user.first_name)
    if user.rifle < 1:
        await call.answer("❌ У вас нет винтовки. Купите в /shop", show_alert=True)
        return
    if call.from_user.id in game.get("rifle_locked", {}):
        await call.answer("❌ Вы уже ответили! Винтовку нельзя использовать.", show_alert=True)
        return
    if game.get("rifle_used"):
        await call.answer("❌ Винтовка уже использована в этом раунде!", show_alert=True)
        return
    players = active_players(game)
    targets = [p for p in players if p.id != call.from_user.id]
    if not targets:
        await call.answer("❌ Нет целей!")
        return
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=p.first_name, callback_data=f"rifle_shoot_{chat_id}_{p.id}")]
        for p in targets
    ])
    await call.answer()
    await call.bot.send_message(call.from_user.id, "🔫 Выбери цель:", reply_markup=markup)


@router.callback_query(F.data.startswith("rifle_shoot_"))
async def cb_rifle_shoot(call: CallbackQuery, session: AsyncSession):
    parts = call.data.split("_")
    chat_id = int(parts[2])
    target_id = int(parts[3])
    game = get_game(chat_id)
    if not game or call.from_user.id != game["spy"]:
        await call.answer("Ошибка!")
        return
    if game.get("rifle_used"):
        await call.answer("❌ Уже использована!")
        return
    user = await get_user(session, call.from_user.id, call.from_user.first_name)
    if user.rifle < 1:
        await call.answer("❌ Нет винтовки!")
        return
    target = next((p for p in game["players"] if p.id == target_id), None)
    if not target or target_id in game["eliminated"]:
        await call.answer("❌ Игрок уже выбыл!")
        return

    from handlers.admin import admin_protected_chats
    if target_id in admin_protected_chats:
        await call.answer("🛡 Этот игрок защищён администратором!", show_alert=True)
        return
    await session.execute(
        update(User).where(User.user_id == call.from_user.id).values(rifle=User.rifle - 1)
    )
    await session.commit()
    game["eliminated"].append(target_id)
    game["rifle_used"] = True
    await add_log(session, call.from_user.id, "USE_RIFLE", f"target={target_id} chat={chat_id}")
    await call.answer("✅ Выстрел произведён!")











    death_msg = random.choice(DEATH_MESSAGES).format(name=target.first_name)
    await call.bot.send_message(chat_id, f"🔫 {death_msg}")
    try:
        await call.bot.send_message(target_id, "💀 Вы были устранены шпионом и выбыли из игры.")
    except Exception:
        pass
    await check_min_players(call.bot, session, chat_id)


@router.callback_query(F.data.startswith("use_device_"))
async def cb_use_device(call: CallbackQuery, session: AsyncSession):
    chat_id = int(call.data.split("_")[2])
    game = get_game(chat_id)
    if not game or call.from_user.id != game["spy"]:
        await call.answer("❌ Только шпион может использовать!")
        return
    user = await get_user(session, call.from_user.id, call.from_user.first_name)
    if user.spy_device < 1:
        await call.answer("❌ У вас нет устройства. Купите в /shop", show_alert=True)
        return
    await session.execute(
        update(User).where(User.user_id == call.from_user.id).values(spy_device=User.spy_device - 1)
    )
    await session.commit()
    hint = LOCATION_HINTS.get(game["location"], "Место остаётся загадкой...")
    await add_log(session, call.from_user.id, "USE_DEVICE", f"chat={chat_id}")
    await call.answer()
    await call.bot.send_message(call.from_user.id, f"📡 Шпионское устройство активировано!\n\n🔍 Подсказка: {hint}")


@router.callback_query(F.data.startswith("use_correct_"))
async def cb_use_correct(call: CallbackQuery, session: AsyncSession):
    parts = call.data.split("_")
    chat_id = int(parts[2])
    player_id = int(parts[3])
    if call.from_user.id != player_id:
        await call.answer("❌ Это не твой предмет!")
        return
    game = get_game(chat_id)
    if not game:
        await call.answer("❌ Игра не найдена!")
        return
    # Жауап берді ма тексер
    if player_id in game.get("answered", []):
        await call.answer("❌ Вы уже ответили! Нельзя использовать.", show_alert=True)
        return
    user = await get_user(session, call.from_user.id, call.from_user.first_name)
    if user.correct_answer < 1:
        await call.answer("❌ У вас нет этого предмета. Купите в /shop", show_alert=True)
        return
    correct = game["correct_answer"].get(player_id)
    if not correct:
        await call.answer("❌ Вопрос не найден!")
        return
    await session.execute(
        update(User).where(User.user_id == call.from_user.id).values(correct_answer=User.correct_answer - 1)
    )
    await session.commit()
    await add_log(session, call.from_user.id, "USE_CORRECT", f"chat={chat_id}")
    await call.answer()
    await call.bot.send_message(call.from_user.id, f"🎭 Правильный ответ на вопрос:\n\n✅ {correct}")


# ─── ГОЛОСОВАНИЕ ──────────────────────────────────────────────────────────────
async def start_voting(bot, session: AsyncSession, chat_id: int):
    game = get_game(chat_id)
    if not game:
        return
    players = active_players(game)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=p.first_name, callback_data=f"vote_{chat_id}_{p.id}")]
        for p in players
    ])
    await bot.send_message(chat_id,
        f"🗳 Голосование!\n\nКто шпион? Голосуйте за подозреваемого!\n\n⏱ 60 секунд:",
        reply_markup=markup
    )

    async def vote_timer():
        await asyncio.sleep(60)
        g = get_game(chat_id)
        if not g:
            return
        ap = active_players(g)
        not_voted = [p for p in ap if p.id not in g["voted"]]
        if not_voted:
            await bot.send_message(chat_id, "⏱ Время голосования вышло!")
            await finish_voting(bot, session, chat_id)

    asyncio.create_task(vote_timer())


@router.callback_query(F.data.startswith("vote_"))
async def cb_vote(call: CallbackQuery, session: AsyncSession):
    parts = call.data.split("_")
    chat_id = int(parts[1])
    voted_for_id = int(parts[2])
    voter_id = call.from_user.id
    game = get_game(chat_id)
    if not game or voter_id == voted_for_id or voter_id in game["voted"]:
        await call.answer("Ошибка!")
        return
    ap = active_players(game)
    if voter_id not in [p.id for p in ap]:
        await call.answer("Ты выбыл!")
        return
    game["voted"].append(voter_id)
    game["votes"][voted_for_id] = game["votes"].get(voted_for_id, 0) + 1
    game["vote_detail"][voter_id] = voted_for_id
    game["last_activity"] = time.time()
    voted_name = next((p.first_name for p in game["players"] if p.id == voted_for_id), "?")
    await call.answer(f"Проголосовал за {voted_name}!")
    await call.bot.send_message(chat_id, f"🗳 {call.from_user.first_name} проголосовал!")
    if len(game["voted"]) >= len(ap):
        await finish_voting(call.bot, session, chat_id)


async def finish_voting(bot, session: AsyncSession, chat_id: int):
    game = get_game(chat_id)
    if not game:
        return
    votes = game["votes"]
    spy_id = game["spy"]
    players = game["players"]
    t_str = elapsed_str(game["start_time"])
    spy_name = next((p.first_name for p in players if p.id == spy_id), "?")
    vote_log = []
    for vid, tid in game.get("vote_detail", {}).items():
        vname = next((p.first_name for p in players if p.id == vid), "?")
        tname = next((p.first_name for p in players if p.id == tid), "?")
        vote_log.append(f"  {vname} → {tname}")
    vote_log_text = "\n".join(vote_log) if vote_log else "  —"
    if not votes:
        await bot.send_message(chat_id, "Никто не проголосовал!")
        await next_round(bot, session, chat_id)
        return
    max_votes = max(votes.values())
    top_ids = [uid for uid, v in votes.items() if v == max_votes]
    results = "\n".join(
        f"  {next((p.first_name for p in players if p.id == uid), '?')}: {v} голос(а)"
        for uid, v in sorted(votes.items(), key=lambda x: -x[1])
    )
    if len(top_ids) > 1:
        await bot.send_message(chat_id,
            f"📊 Результаты:\n{vote_log_text}\n\n🔢 Итог:\n{results}\n\n⚖️ Ничья! Шпион остался в тени...")
        await next_round(bot, session, chat_id)
        return
    max_votes_id = top_ids[0]
    max_votes_name = next((p.first_name for p in players if p.id == max_votes_id), "?")
    await bot.send_message(chat_id, f"📊 Результаты:\n{vote_log_text}\n\n🔢 Итог:\n{results}\n\n❌ Выбывает: {max_votes_name}")

    # Защита голоса тексеру
    from handlers.admin import admin_protected_chats
    if max_votes_id in admin_protected_chats:
        await bot.send_message(chat_id, f"🛡 {max_votes_name} защищён администратором и остался в игре!")
        await next_round(bot, session, chat_id)
        return
    from database.requests import get_user as db_get_user
    row = await db_get_user(session, max_votes_id, max_votes_name)
    if row and row.voice_protect > 0:
        await session.execute(
            update(User).where(User.user_id == max_votes_id).values(voice_protect=User.voice_protect - 1)
        )
        await session.commit()
        await bot.send_message(chat_id, f"⚖️ {max_votes_name} использовал защиту голоса и остался в игре!")
        await add_log(session, max_votes_id, "USE_VOICE_PROTECT", f"chat={chat_id}")
        await next_round(bot, session, chat_id)
        return

    if max_votes_id == spy_id:
        await end_game(bot, session, chat_id,
            f"🎉 Шпион найден!\n\nШпионом был: {spy_name}\nЛокация: {game['location']}\n\n✅ Игроки победили!\n\n⏱ {t_str}",
            spy_won=False)
        return
    game["eliminated"].append(max_votes_id)
    await bot.send_message(chat_id, f"❌ {max_votes_name} выбыл! Но это был не шпион...\n\nПродолжаем!")
    try:
        elim = next(p for p in players if p.id == max_votes_id)
        await bot.send_message(elim.id, "❌ Тебя выбрали шпионом, но ты им не был...\nТы выбыл.")
    except Exception:
        pass
    if await check_min_players(bot, session, chat_id):
        return
    await send_spy_guess(bot, session, chat_id)


async def send_spy_guess(bot, session: AsyncSession, chat_id: int):
    game = get_game(chat_id)
    if not game:
        return
    spy_id = game["spy"]
    location = game["location"]
    players = game["players"]
    t_str = elapsed_str(game["start_time"])
    spy_name = next((p.first_name for p in players if p.id == spy_id), "?")
    if spy_id in game["eliminated"]:
        await end_game(bot, session, chat_id,
            f"🎉 Шпион найден!\n\nШпионом был: {spy_name}\nЛокация: {location}\n\n✅ Игроки победили!\n\n⏱ {t_str}",
            spy_won=False)
        return
    enabled_locs = await get_enabled_locations(session)
    other_locs = [l for l in enabled_locs if l != location]
    fake_locs = random.sample(other_locs, min(5, len(other_locs)))
    fake_locs.append(location)
    random.shuffle(fake_locs)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=loc, callback_data=f"spyg_{chat_id}_{loc}")]
        for loc in fake_locs
    ])
    try:
        await bot.send_message(spy_id, f"🗺 Попробуй угадать локацию!\n⏱ У тебя 60 секунд:", reply_markup=markup)
    except Exception:
        pass
    await bot.send_message(chat_id, "🕵️ Шпион пытается угадать локацию... (60 сек)")

    async def spy_timer():
        await asyncio.sleep(60)
        g = get_game(chat_id)
        if not g or g.get("spy_guessed") is not None:
            return
        g["spy_guessed"] = "timeout"
        await bot.send_message(chat_id, "⏱ Шпион не успел угадать!")
        await check_game_end(bot, session, chat_id)

    asyncio.create_task(spy_timer())


@router.callback_query(F.data.startswith("spyg_"))
async def cb_spy_guess(call: CallbackQuery, session: AsyncSession):
    parts = call.data.split("_", 2)
    chat_id = int(parts[1])
    guessed = parts[2]
    game = get_game(chat_id)
    if not game or call.from_user.id != game["spy"] or game.get("spy_guessed") is not None:
        await call.answer("Ошибка!")
        return
    game["spy_guessed"] = guessed
    await call.answer("Ответ принят!")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    t_str = elapsed_str(game["start_time"])
    spy_name = next((p.first_name for p in game["players"] if p.id == game["spy"]), "?")
    if guessed == game["location"]:
        await end_game(call.bot, session, chat_id,
            f"🕵️ ШПИОН УГАДАЛ ЛОКАЦИЮ!\n\nЛокация была: {game['location']}\n\n🏆 Шпион ({spy_name}) победил!\n\n⏱ {t_str}",
            spy_won=True)
    else:
        await call.bot.send_message(chat_id, "❌ Шпион не угадал локацию!\n\nИгра продолжается!")
        try:
            await call.bot.send_message(call.from_user.id, "❌ Неверно! Продолжай!")
        except Exception:
            pass
        await check_game_end(call.bot, session, chat_id)


async def check_game_end(bot, session: AsyncSession, chat_id: int):
    game = get_game(chat_id)
    if not game:
        return
    players = game["players"]
    ap = active_players(game)
    t_str = elapsed_str(game["start_time"])
    spy_name = next((p.first_name for p in players if p.id == game["spy"]), "?")
    max_rounds = game.get("max_rounds", 3)
    if len(ap) <= 2 or game["round"] >= max_rounds:
        await end_game(bot, session, chat_id,
            f"🕵️ Игра окончена!\n\nШпионом был: {spy_name}\nЛокация: {game['location']}\n\n❌ Шпион победил!\n\n⏱ {t_str}",
            spy_won=True)
        return
    await next_round(bot, session, chat_id)


async def next_round(bot, session: AsyncSession, chat_id: int):
    game = get_game(chat_id)
    if not game:
        return
    game["round"] += 1
    game.update({
        "answers": [], "answered": [], "player_answers": {},
        "correct_answer": {}, "player_questions": {},
        "spy_guessed": None, "votes": {}, "voted": [],
        "vote_detail": {}, "timer_msg_id": None,
        "current_player_index": 0, "rifle_used": False, "rifle_locked": {}
    })
    max_rounds = game.get("max_rounds", 3)
    await bot.send_message(chat_id, f"🔄 Начинается Раунд {game['round']} из {max_rounds}!\n\n⏱ У каждого 60 секунд на ответ!")
    await prepare_questions(chat_id, session)
    await send_next_player_question(bot, session, chat_id)


@router.message(Command("endgame"))
async def cmd_endgame(message: Message, session: AsyncSession):
    chat_id = message.chat.id
    game = get_game(chat_id)
    if not game:
        await message.answer("❌ Активная игра не найдена!")
        return
    if message.from_user.id != game["host"] and not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        await message.answer("❌ Только организатор может завершить игру!")
        return
    await end_game(message.bot, session, chat_id, "🛑 Игра завершена!", forced=True)
