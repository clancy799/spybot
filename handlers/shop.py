from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from database.models import User
from database.requests import get_user, add_log
from data.locations import DIAMOND_PACKAGES

router = Router()


def shop_main_markup():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Купить за наличные", callback_data="shop_cash")],
        [InlineKeyboardButton(text="💎 Купить за алмазы", callback_data="shop_diamonds")],
        [InlineKeyboardButton(text="⭐ Купить алмазы за Stars", callback_data="shop_buy_diamonds")],
    ])


@router.message(Command("shop"))
async def cmd_shop(message: Message, session: AsyncSession):
    await get_user(session, message.from_user.id, message.from_user.first_name)
    await message.answer("🛒 Магазин\n\nВыбери категорию:", reply_markup=shop_main_markup())


@router.callback_query(F.data == "shop_back")
async def cb_shop_back(call: CallbackQuery):
    await call.message.edit_text("🛒 Магазин\n\nВыбери категорию:", reply_markup=shop_main_markup())


@router.callback_query(F.data == "shop_cash")
async def cb_shop_cash(call: CallbackQuery, session: AsyncSession):
    user = await get_user(session, call.from_user.id, call.from_user.first_name)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚖️ Защита голоса — 💵 100", callback_data="buy_voice_protect")],
        [InlineKeyboardButton(text="📡 Шпионское устройство — 💵 150", callback_data="buy_spy_device_cash")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="shop_back")],
    ])
    await call.message.edit_text(
        f"💵 Магазин за наличные\n\nБаланс: 💵 {user.cash}\n\n"
        f"⚖️ Защита голоса — если все проголосуют против вас, 1 раз останетесь автоматически\n"
        f"📡 Шпионское устройство — только для шпиона, даёт подсказку о локации\n\nВыберите товар:",
        reply_markup=markup
    )


@router.callback_query(F.data == "shop_diamonds")
async def cb_shop_diamonds(call: CallbackQuery, session: AsyncSession):
    user = await get_user(session, call.from_user.id, call.from_user.first_name)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔫 Винтовка — 💎 1", callback_data="buy_rifle")],
        [InlineKeyboardButton(text="🎭 Один правильный ответ — 💎 1", callback_data="buy_correct_answer_dia")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="shop_back")],
    ])
    await call.message.edit_text(
        f"💎 Магазин за алмазы\n\nБаланс: 💎 {user.diamonds}\n\n"
        f"🔫 Винтовка — только для шпиона, устраняет одного игрока\n"
        f"🎭 Один правильный ответ — показывает правильный ответ на вопрос\n\nВыберите товар:",
        reply_markup=markup
    )


@router.callback_query(F.data == "shop_buy_diamonds")
async def cb_shop_buy_diamonds(call: CallbackQuery):
    buttons = []
    for pkg in DIAMOND_PACKAGES:
        buttons.append([InlineKeyboardButton(
            text=f"💎 {pkg['diamonds']} алмаз — ⭐ {pkg['stars']} Stars",
            callback_data=f"buy_stars_{pkg['diamonds']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="shop_back")])
    await call.message.edit_text(
        "⭐ Купить алмазы за Telegram Stars\n\n💎 1 алмаз = ⭐ 15 Stars\n\nВыберите пакет:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("buy_stars_"))
async def cb_buy_stars(call: CallbackQuery):
    amount = int(call.data.replace("buy_stars_", ""))
    pkg = next((p for p in DIAMOND_PACKAGES if p["diamonds"] == amount), None)
    if not pkg:
        await call.answer("❌ Пакет не найден!")
        return
    await call.answer()
    await call.bot.send_invoice(
        chat_id=call.from_user.id,
        title=f"💎 {pkg['diamonds']} алмаз",
        description=f"{pkg['diamonds']} алмаз — ойында қолдануға болады",
        payload=f"{pkg['payload']}_{call.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"💎 {pkg['diamonds']} алмаз", amount=pkg["stars"])],
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, session: AsyncSession):
    payload = message.successful_payment.invoice_payload
    parts = payload.rsplit("_", 1)
    pkg_payload = parts[0]
    user_id = int(parts[1]) if len(parts) == 2 else message.from_user.id
    pkg = next((p for p in DIAMOND_PACKAGES if p["payload"] == pkg_payload), None)
    if not pkg:
        return
    await session.execute(
        update(User).where(User.user_id == user_id).values(diamonds=User.diamonds + pkg["diamonds"])
    )
    await session.commit()
    await add_log(session, user_id, "BUY_STARS", f"diamonds={pkg['diamonds']}")
    await message.answer(f"✅ Оплата прошла успешно!\n\n💎 {pkg['diamonds']} алмаз аккаунтыңа қосылды!")


@router.callback_query(F.data == "buy_voice_protect")
async def cb_buy_voice_protect(call: CallbackQuery, session: AsyncSession):
    user = await get_user(session, call.from_user.id, call.from_user.first_name)
    if user.cash < 100:
        await call.answer("❌ Недостаточно наличных!")
        return
    await session.execute(
        update(User).where(User.user_id == call.from_user.id).values(
            cash=User.cash - 100, voice_protect=User.voice_protect + 1
        )
    )
    await session.commit()
    await add_log(session, call.from_user.id, "BUY", "voice_protect")
    await call.answer("✅ Куплено!")
    await call.bot.send_message(
        call.from_user.id,
        "✅ Куплено: ⚖️ Защита голоса\n\nЕсли все проголосуют против вас — автоматически останетесь в игре!"
    )


@router.callback_query(F.data == "buy_spy_device_cash")
async def cb_buy_spy_device_cash(call: CallbackQuery, session: AsyncSession):
    user = await get_user(session, call.from_user.id, call.from_user.first_name)
    if user.cash < 150:
        await call.answer("❌ Недостаточно наличных!")
        return
    await session.execute(
        update(User).where(User.user_id == call.from_user.id).values(
            cash=User.cash - 150, spy_device=User.spy_device + 1
        )
    )
    await session.commit()
    await add_log(session, call.from_user.id, "BUY", "spy_device")
    await call.answer("✅ Куплено!")
    await call.bot.send_message(
        call.from_user.id,
        "✅ Куплено: 📡 Шпионское устройство\n\nТолько для шпиона! Во время игры нажмите кнопку в купленных товарах."
    )


@router.callback_query(F.data == "buy_rifle")
async def cb_buy_rifle(call: CallbackQuery, session: AsyncSession):
    user = await get_user(session, call.from_user.id, call.from_user.first_name)
    if user.diamonds < 1:
        await call.answer("❌ Недостаточно алмазов!")
        return
    await session.execute(
        update(User).where(User.user_id == call.from_user.id).values(
            diamonds=User.diamonds - 1, rifle=User.rifle + 1
        )
    )
    await session.commit()
    await add_log(session, call.from_user.id, "BUY", "rifle")
    await call.answer("✅ Куплено!")
    await call.bot.send_message(
        call.from_user.id,
        "✅ Куплено: 🔫 Винтовка\n\nТолько для шпиона! Во время игры нажмите кнопку в купленных товарах."
    )


@router.callback_query(F.data == "buy_correct_answer_dia")
async def cb_buy_correct_answer_dia(call: CallbackQuery, session: AsyncSession):
    user = await get_user(session, call.from_user.id, call.from_user.first_name)
    if user.diamonds < 1:
        await call.answer("❌ Недостаточно алмазов!")
        return
    await session.execute(
        update(User).where(User.user_id == call.from_user.id).values(
            diamonds=User.diamonds - 1, correct_answer=User.correct_answer + 1
        )
    )
    await session.commit()
    await add_log(session, call.from_user.id, "BUY", "correct_answer")
    await call.answer("✅ Куплено!")
    await call.bot.send_message(
        call.from_user.id,
        "✅ Куплено: 🎭 Один правильный ответ\n\nВо время игры нажмите кнопку чтобы активировать!"
    )
