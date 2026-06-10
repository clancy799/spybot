from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select, func

from database.models import User, Admin, Log
from database.requests import add_spy_device, get_user, add_cash, add_diamonds, add_log, is_admin, get_stats, get_all_user_ids, get_last_logs
from config import SUPER_ADMIN_ID
import asyncio

router = Router()

games_ref = {}  # bot.py-дан games сілтемесі


def set_games_ref(games: dict):
    global games_ref
    games_ref = games


def admin_main_markup(user_id: int):
    buttons = [
        [InlineKeyboardButton(text="🎮 Ойынды басқару", callback_data="adm_game")],
        [InlineKeyboardButton(text="🕵️ Рөлдерді басқару", callback_data="adm_roles")],
        [InlineKeyboardButton(text="📍 Локациялар", callback_data="adm_locs")],
        [InlineKeyboardButton(text="👥 Ойыншылар", callback_data="adm_players")],
        [InlineKeyboardButton(text="💰 Экономика", callback_data="adm_economy")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast_menu")],
        [InlineKeyboardButton(text="📊 Логи", callback_data="adm_logs")],
    ]
    if user_id == SUPER_ADMIN_ID:
        buttons.append([InlineKeyboardButton(text="👑 Super Admin", callback_data="adm_super")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("admin"))
async def cmd_admin(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    total_users, total_games, _, _, _ = await get_stats(session)
    await message.answer(
        f"⚙️ Панель администратора\n\n"
        f"👥 Игроков: {total_users}\n"
        f"🎲 Всего игр: {total_games}\n"
        f"🎮 Активных игр: {len(games_ref)}\n\n"
        f"Выбери раздел:",
        reply_markup=admin_main_markup(message.from_user.id)
    )


@router.callback_query(F.data == "adm_back")
async def cb_adm_back(call: CallbackQuery, session: AsyncSession):
    if not await is_admin(session, call.from_user.id, SUPER_ADMIN_ID):
        return
    total_users, total_games, _, _, _ = await get_stats(session)
    await call.message.edit_text(
        f"⚙️ Панель администратора\n\n👥 Игроков: {total_users}\n🎲 Всего игр: {total_games}\n🎮 Активных: {len(games_ref)}\n\nВыбери раздел:",
        reply_markup=admin_main_markup(call.from_user.id)
    )


@router.callback_query(F.data == "adm_game")
async def cb_adm_game(call: CallbackQuery, session: AsyncSession):
    if not await is_admin(session, call.from_user.id, SUPER_ADMIN_ID):
        return
    if not games_ref:
        await call.answer("Нет активных игр!", show_alert=True)
        return
    text = "🎮 Активные игры:\n\n"
    buttons = []
    for chat_id, game in games_ref.items():
        status = "▶️" if game.get("started") else "⏳"
        spy_id = game.get("spy")
        spy_name = next((p.first_name for p in game["players"] if p.id == spy_id), "?")
        location = game.get("location", "?")
        text += f"{status} Chat: {chat_id} | {len(game["players"])} игр.\n🕵️ Шпион: {spy_name}\n📍 Локация: {location}\n\n"
        buttons.append([InlineKeyboardButton(text=f"🛑 Остановить {chat_id}", callback_data=f"adm_stop_{chat_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("adm_stop_"))
async def cb_adm_stop(call: CallbackQuery, session: AsyncSession):
    if not await is_admin(session, call.from_user.id, SUPER_ADMIN_ID):
        return
    chat_id = int(call.data.replace("adm_stop_", ""))
    if chat_id in games_ref:
        games_ref.pop(chat_id)
        await call.bot.send_message(chat_id, "🛑 Игра остановлена администратором!")
        await add_log(session, call.from_user.id, "ADMIN_STOP_GAME", f"chat={chat_id}")
    await call.answer("✅ Остановлено!")


@router.callback_query(F.data == "adm_locs")
async def cb_adm_locs(call: CallbackQuery, session: AsyncSession):
    from data.locations import LOCATION_CHOICES
    from database.models import DisabledLocation
    if not await is_admin(session, call.from_user.id, SUPER_ADMIN_ID):
        return
    result = await session.execute(select(DisabledLocation.location_name))
    disabled = [r[0] for r in result.fetchall()]
    buttons = []
    for loc in LOCATION_CHOICES:
        status = "❌" if loc in disabled else "✅"
        buttons.append([InlineKeyboardButton(text=f"{status} {loc}", callback_data=f"adm_loc_{loc}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")])
    await call.message.edit_text("📍 Управление локациями:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("adm_loc_"))
async def cb_adm_loc_toggle(call: CallbackQuery, session: AsyncSession):
    from database.models import DisabledLocation
    if not await is_admin(session, call.from_user.id, SUPER_ADMIN_ID):
        return
    loc = call.data.replace("adm_loc_", "")
    result = await session.execute(select(DisabledLocation).where(DisabledLocation.location_name == loc))
    existing = result.scalar_one_or_none()
    if existing:
        await session.delete(existing)
        msg = f"✅ {loc} включена!"
    else:
        session.add(DisabledLocation(location_name=loc))
        msg = f"❌ {loc} отключена!"
    await session.commit()
    await add_log(session, call.from_user.id, "ADMIN_TOGGLE_LOC", loc)
    await call.answer(msg)
    await cb_adm_locs(call, session)


@router.callback_query(F.data == "adm_players")
async def cb_adm_players(call: CallbackQuery, session: AsyncSession):
    if not await is_admin(session, call.from_user.id, SUPER_ADMIN_ID):
        return
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 /ban [id]", callback_data="adm_info_ban")],
        [InlineKeyboardButton(text="✅ /unban [id]", callback_data="adm_info_unban")],
        [InlineKeyboardButton(text="🔇 /mute [id]", callback_data="adm_info_mute")],
        [InlineKeyboardButton(text="🗑 /resetuser [id]", callback_data="adm_info_reset")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")],
    ])
    await call.message.edit_text("👥 Управление игроками:", reply_markup=markup)


@router.callback_query(F.data.startswith("adm_info_"))
async def cb_adm_info(call: CallbackQuery):
    info = {
        "adm_info_ban":   "🚫 Бан:\n/ban [user_id]",
        "adm_info_unban": "✅ Разбан:\n/unban [user_id]",
        "adm_info_mute":  "🔇 Мут:\n/mute [user_id]",
        "adm_info_reset": "🗑 Сброс профиля:\n/resetuser [user_id]",
    }
    await call.answer(info.get(call.data, ""), show_alert=True)


@router.callback_query(F.data == "adm_economy")
async def cb_adm_economy(call: CallbackQuery, session: AsyncSession):
    if not await is_admin(session, call.from_user.id, SUPER_ADMIN_ID):
        return
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 /addcash [id] [сумма]", callback_data="adm_eco_cash")],
        [InlineKeyboardButton(text="💎 /adddiamonds [id] [сумма]", callback_data="adm_eco_dia")],
        [InlineKeyboardButton(text="⭐ /setdonor [id]", callback_data="adm_eco_donor")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")],
    ])
    await call.message.edit_text("💰 Управление экономикой:", reply_markup=markup)


@router.callback_query(F.data.startswith("adm_eco_"))
async def cb_adm_eco_info(call: CallbackQuery):
    info = {
        "adm_eco_cash":  "💵 Добавить наличные:\n/addcash [user_id] [сумма]",
        "adm_eco_dia":   "💎 Добавить алмазы:\n/adddiamonds [user_id] [сумма]",
        "adm_eco_donor": "⭐ Статус донатора:\n/setdonor [user_id]",
    }
    await call.answer(info.get(call.data, ""), show_alert=True)


@router.callback_query(F.data == "adm_broadcast_menu")
async def cb_adm_broadcast_menu(call: CallbackQuery, session: AsyncSession):
    if not await is_admin(session, call.from_user.id, SUPER_ADMIN_ID):
        return
    total_users, _, _, _, _ = await get_stats(session)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]
    ])
    await call.message.edit_text(
        f"📢 Рассылка сообщений\n\n👥 Всего игроков: {total_users}\n\n"
        f"Команда:\n/broadcast [текст]",
        reply_markup=markup
    )


@router.callback_query(F.data == "adm_logs")
async def cb_adm_logs(call: CallbackQuery, session: AsyncSession):
    if not await is_admin(session, call.from_user.id, SUPER_ADMIN_ID):
        return
    rows = await get_last_logs(session)
    if not rows:
        await call.answer("Лог пуст!", show_alert=True)
        return
    text = "📊 Последние 15 действий:\n\n"
    for uid, action, details, ts in rows:
        text += f"[{str(ts)[:16]}] {uid} → {action}"
        if details:
            text += f" ({details})"
        text += "\n"
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")]])
    try:
        await call.message.edit_text(text, reply_markup=markup)
    except Exception:
        await call.message.answer(text)


@router.callback_query(F.data == "adm_super")
async def cb_adm_super(call: CallbackQuery):
    if call.from_user.id != SUPER_ADMIN_ID:
        await call.answer("❌ Нет доступа!")
        return
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 /addadmin [id]", callback_data="adm_s_info_add")],
        [InlineKeyboardButton(text="🗑 /removeadmin [id]", callback_data="adm_s_info_remove")],
        [InlineKeyboardButton(text="⚠️ Сбросить всю статистику", callback_data="adm_s_resetall")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back")],
    ])
    await call.message.edit_text("👑 Super Admin панель:", reply_markup=markup)


@router.callback_query(F.data.in_(["adm_s_info_add", "adm_s_info_remove"]))
async def cb_adm_s_info(call: CallbackQuery):
    info = {
        "adm_s_info_add":    "👤 Добавить админа:\n/addadmin [user_id]",
        "adm_s_info_remove": "🗑 Убрать админа:\n/removeadmin [user_id]",
    }
    await call.answer(info.get(call.data, ""), show_alert=True)


@router.callback_query(F.data == "adm_s_resetall")
async def cb_adm_s_resetall(call: CallbackQuery):
    if call.from_user.id != SUPER_ADMIN_ID:
        return
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, сбросить!", callback_data="adm_s_resetall_confirm")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="adm_super")],
    ])
    await call.message.edit_text("⚠️ Вся статистика будет сброшена!\n\nПодтвердить?", reply_markup=markup)


@router.callback_query(F.data == "adm_s_resetall_confirm")
async def cb_adm_s_resetall_confirm(call: CallbackQuery, session: AsyncSession):
    if call.from_user.id != SUPER_ADMIN_ID:
        return
    await session.execute(
        update(User).values(cash=0, diamonds=0, missions_success=0, total_games=0,
                            spy_device=0, voice_protect=0, correct_answer=0, rifle=0)
    )
    await session.commit()
    await add_log(session, call.from_user.id, "SUPER_RESET_ALL", "")
    await call.answer("✅ Вся статистика сброшена!")


# ─── ADMIN COMMANDS ───────────────────────────────────────────────────────────
@router.message(Command("addcash"))
async def cmd_addcash(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Формат: /addcash [user_id] [сумма]")
        return
    try:
        user_id, amount = int(parts[1]), int(parts[2])
        await add_cash(session, user_id, amount)
        await add_log(session, message.from_user.id, "ADMIN_ADDCASH", f"target={user_id} amount={amount}")
        await message.answer(f"✅ Игроку {user_id} добавлено 💵 {amount}!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("adddiamonds"))
async def cmd_adddiamonds(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Формат: /adddiamonds [user_id] [сумма]")
        return
    try:
        user_id, amount = int(parts[1]), int(parts[2])
        await add_diamonds(session, user_id, amount)
        await add_log(session, message.from_user.id, "ADMIN_ADDDIAMONDS", f"target={user_id} amount={amount}")
        await message.answer(f"✅ Игроку {user_id} добавлено 💎 {amount}!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("ban"))
async def cmd_ban(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Формат: /ban [user_id]")
        return
    user_id = int(parts[1])
    await session.execute(update(User).where(User.user_id == user_id).values(is_banned=True))
    await session.commit()
    await add_log(session, message.from_user.id, "ADMIN_BAN", f"target={user_id}")
    await message.answer(f"🚫 Игрок {user_id} заблокирован!")


@router.message(Command("unban"))
async def cmd_unban(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Формат: /unban [user_id]")
        return
    user_id = int(parts[1])
    await session.execute(update(User).where(User.user_id == user_id).values(is_banned=False))
    await session.commit()
    await add_log(session, message.from_user.id, "ADMIN_UNBAN", f"target={user_id}")
    await message.answer(f"✅ Игрок {user_id} разблокирован!")


@router.message(Command("mute"))
async def cmd_mute(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Формат: /mute [user_id]")
        return
    user_id = int(parts[1])
    await session.execute(update(User).where(User.user_id == user_id).values(is_muted=True))
    await session.commit()
    await add_log(session, message.from_user.id, "ADMIN_MUTE", f"target={user_id}")
    await message.answer(f"🔇 Игрок {user_id} замьючен!")


@router.message(Command("setdonor"))
async def cmd_setdonor(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Формат: /setdonor [user_id]")
        return
    user_id = int(parts[1])
    await session.execute(update(User).where(User.user_id == user_id).values(is_donor=True))
    await session.commit()
    await add_log(session, message.from_user.id, "ADMIN_SETDONOR", f"target={user_id}")
    await message.answer(f"⭐ Игроку {user_id} выдан статус донатора!")


@router.message(Command("resetuser"))
async def cmd_resetuser(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Формат: /resetuser [user_id]")
        return
    user_id = int(parts[1])
    await session.execute(
        update(User).where(User.user_id == user_id).values(
            cash=0, diamonds=0, spy_device=0, voice_protect=0,
            correct_answer=0, rifle=0, missions_success=0, total_games=0
        )
    )
    await session.commit()
    await add_log(session, message.from_user.id, "ADMIN_RESETUSER", f"target={user_id}")
    await message.answer(f"✅ Профиль игрока {user_id} сброшен!")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("❌ Формат: /broadcast [текст]")
        return
    user_ids = await get_all_user_ids(session)
    sent = 0
    for uid in user_ids:
        try:
            await message.bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await add_log(session, message.from_user.id, "ADMIN_BROADCAST", f"sent={sent}")
    await message.answer(f"✅ Отправлено {sent} игрокам!")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    total_users, total_games, total_cash, total_diamonds, banned = await get_stats(session)
    await message.answer(
        f"📊 Статистика:\n\n"
        f"👥 Игроков: {total_users}\n"
        f"🎲 Всего игр: {total_games}\n"
        f"💵 Всего наличных: {total_cash}\n"
        f"💎 Всего алмазов: {total_diamonds}\n"
        f"🚫 В бане: {banned}\n"
        f"🎮 Активных игр: {len(games_ref)}"
    )


@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message, session: AsyncSession):
    if message.from_user.id != SUPER_ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Формат: /addadmin [user_id]")
        return
    user_id = int(parts[1])
    existing = await session.execute(select(Admin).where(Admin.user_id == user_id))
    if not existing.scalar_one_or_none():
        session.add(Admin(user_id=user_id, name="Admin", added_by=message.from_user.id))
        await session.commit()
    await add_log(session, message.from_user.id, "SUPER_ADDADMIN", f"target={user_id}")
    await message.answer(f"✅ Игрок {user_id} добавлен в админы!")


@router.message(Command("removeadmin"))
async def cmd_removeadmin(message: Message, session: AsyncSession):
    if message.from_user.id != SUPER_ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Формат: /removeadmin [user_id]")
        return
    user_id = int(parts[1])
    await session.execute(select(Admin).where(Admin.user_id == user_id))
    result = await session.execute(select(Admin).where(Admin.user_id == user_id))
    admin = result.scalar_one_or_none()
    if admin:
        await session.delete(admin)
        await session.commit()
    await add_log(session, message.from_user.id, "SUPER_REMOVEADMIN", f"target={user_id}")
    await message.answer(f"✅ Игрок {user_id} убран из админов!")




@router.message(Command("setspy"))
async def cmd_setspy(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Формат: /setspy [chat_id] [user_id]")
        return
    try:
        chat_id, user_id = int(parts[1]), int(parts[2])
        from handlers.game import games
        game = games.get(chat_id)
        if not game or not game.get("started"):
            await message.answer("❌ В этом чате нет активной игры!")
            return
        player_ids = [p.id for p in game["players"]]
        if user_id not in player_ids:
            await message.answer("❌ Этот игрок не участвует в игре!")
            return
        old_spy = game["spy"]
        game["spy"] = user_id
        await add_log(session, message.from_user.id, "ADMIN_SETSPY", f"chat={chat_id} old={old_spy} new={user_id}")
        await message.answer(f"✅ Шпион изменён на {user_id}!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# Админ защита активті чаттар
admin_protected_chats = set()


@router.message(Command("forcewin"))
async def cmd_forcewin(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Формат: /forcewin [chat_id] [user_id]")
        return
    try:
        chat_id, user_id = int(parts[1]), int(parts[2])
        from handlers.game import games, end_game
        game = games.get(chat_id)
        if not game or not game.get("started"):
            await message.answer("❌ Активная игра не найдена!")
            return
        players = game.get("players", [])
        winner = next((p for p in players if p.id == user_id), None)
        if not winner:
            await message.answer("❌ Игрок не найден в игре!")
            return
        await add_log(session, message.from_user.id, "ADMIN_FORCEWIN", f"chat={chat_id} winner={user_id}")
        await end_game(
            message.bot, session, chat_id,
            f"👑 Администратор завершил игру!\n\n🏆 Победитель: {winner.first_name}",
            spy_won=False, forced=True
        )
        await message.answer(f"✅ Игра завершена! Победитель: {winner.first_name}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("adminshield"))
async def cmd_adminshield(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Формат: /adminshield [chat_id]")
        return
    try:
        chat_id = int(parts[1])
        if chat_id in admin_protected_chats:
            admin_protected_chats.remove(chat_id)
            await message.answer(f"🛡 Защита администратора ВЫКЛЮЧЕНА для {chat_id}")
        else:
            admin_protected_chats.add(chat_id)
            await message.answer(f"🛡 Защита администратора ВКЛЮЧЕНА для {chat_id}\n\nТеперь винтовка и голосование не действуют на администраторов!")
        await add_log(session, message.from_user.id, "ADMIN_SHIELD", f"chat={chat_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# Админ защита активті чаттар
admin_protected_chats = set()


@router.message(Command("forcewin"))
async def cmd_forcewin(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Формат: /forcewin [chat_id] [user_id]")
        return
    try:
        chat_id, user_id = int(parts[1]), int(parts[2])
        from handlers.game import games, end_game
        game = games.get(chat_id)
        if not game or not game.get("started"):
            await message.answer("❌ Активная игра не найдена!")
            return
        players = game.get("players", [])
        winner = next((p for p in players if p.id == user_id), None)
        if not winner:
            await message.answer("❌ Игрок не найден в игре!")
            return
        await add_log(session, message.from_user.id, "ADMIN_FORCEWIN", f"chat={chat_id} winner={user_id}")
        await end_game(
            message.bot, session, chat_id,
            f"👑 Администратор завершил игру!\n\n🏆 Победитель: {winner.first_name}",
            spy_won=False, forced=True
        )
        await message.answer(f"✅ Игра завершена! Победитель: {winner.first_name}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("adminshield"))
async def cmd_adminshield(message: Message, session: AsyncSession):
    if not await is_admin(session, message.from_user.id, SUPER_ADMIN_ID):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Формат: /adminshield [chat_id]")
        return
    try:
        chat_id = int(parts[1])
        if chat_id in admin_protected_chats:
            admin_protected_chats.remove(chat_id)
            await message.answer(f"🛡 Защита администратора ВЫКЛЮЧЕНА для {chat_id}")
        else:
            admin_protected_chats.add(chat_id)
            await message.answer(f"🛡 Защита администратора ВКЛЮЧЕНА для {chat_id}\n\nТеперь винтовка и голосование не действуют на администраторов!")
        await add_log(session, message.from_user.id, "ADMIN_SHIELD", f"chat={chat_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
