from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select

from database.models import User
from database.requests import get_user, add_cash, get_top_players
from utils.helpers import format_profile, get_rank, ACHIEVEMENTS
from config import SUPER_ADMIN_ID

router = Router()


@router.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message, session: AsyncSession):
    user = message.from_user
    await get_user(session, user.id, user.first_name)

    # Referral тексеру
    args = message.text.split()
    if len(args) > 1:
        try:
            ref_id = int(args[1].replace("ref", ""))
            if ref_id != user.id:
                db_user = await get_user(session, user.id, user.first_name)
                if db_user.referred_by == 0:
                    await session.execute(
                        update(User).where(User.user_id == user.id).values(referred_by=ref_id)
                    )
                    await session.execute(
                        update(User).where(User.user_id == ref_id).values(
                            referral_count=User.referral_count + 1,
                            cash=User.cash + 50
                        )
                    )
                    await session.commit()
                    try:
                        await message.bot.send_message(
                            ref_id,
                            f"🎉 По вашей ссылке зарегистрировался {user.first_name}!\n\nНаграда: 💵 50"
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    await message.answer(
        f"🕵️ Игра Шпион\n👋 Привет, {user.first_name}!\n\n"
        f"Чтобы начать игру используй /game в групповом чате.\n\n"
        f"Команды:\n/profile — статистика\n/achievements — достижения\n"
        f"/rating — рейтинг\n/shop — магазин\n/rules — правила\n"
        f"/referral — пригласить друга\n"
        f"/endgame — завершить игру (только хост)"
    )
    await message.answer(
        f"📢 Новостной канал: https://t.me/SpyGameNews\n\n"
        f"🎮 Игровая группа: https://t.me/SpyArenaChat"
    )


@router.message(Command("profile"))
async def cmd_profile(message: Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id, message.from_user.first_name)
    await message.answer(f"👤 Профиль\n\n{format_profile(user)}")


@router.message(Command("achievements"))
async def cmd_achievements(message: Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id, message.from_user.first_name)
    text = "🏆 Достижения\n\n"
    for req, name, desc, bonus in ACHIEVEMENTS:
        if user.missions_success >= req:
            text += f"✅ {name} — {desc} (💵 {bonus})\n"
        else:
            text += f"🔒 {name} — {desc} (💵 {bonus}) — нужно {req} побед\n"
    await message.answer(text)


@router.message(Command("rating"))
async def cmd_rating(message: Message, session: AsyncSession):
    rows = await get_top_players(session)
    if not rows:
        await message.answer("📊 Рейтинг пуст. Сыграй в игру!")
        return
    text = "📊 Топ игроков:\n\n"
    for i, (name, wins, total) in enumerate(rows, 1):
        text += f"{i}. {name} — 🎯 {wins} побед / 🎲 {total} игр\n"
    await message.answer(text)


@router.message(Command("rules"))
async def cmd_rules(message: Message):
    await message.answer(
        "📖 Правила игры Шпион:\n\n"
        "1. Один игрок — шпион, остальные знают локацию\n"
        "2. Каждому приходит вопрос в личку — 60 секунд на ответ\n"
        "3. Вопросы задаются по очереди\n"
        "4. После всех ответов — голосование: кто шпион?\n"
        "5. Шпион пытается угадать локацию\n"
        "6. Шпион угадал — шпион победил!\n"
        "7. Игроки нашли шпиона — игроки победили!\n\n🕵️ Удачи!"
    )


@router.message(Command("referral"))
async def cmd_referral(message: Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id, message.from_user.first_name)
    try:
        bot_info = await message.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=ref{message.from_user.id}"
    except Exception:
        link = "Ошибка получения ссылки"
    await message.answer(
        f"👥 Реферальная система\n\n"
        f"Приглашай друзей и получай 💵 50 за каждого!\n\n"
        f"Твоя ссылка:\n{link}\n\n"
        f"Приглашено друзей: {user.referral_count}"
    )
