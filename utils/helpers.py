from database.models import User


def get_rank(missions: int) -> str:
    if missions < 3:   return "🟤 Новичок"
    elif missions < 7:  return "🔵 Агент"
    elif missions < 15: return "🟣 Оперативник"
    elif missions < 30: return "🟡 Мастер"
    else:               return "🔴 Легенда"


def format_profile(user: User) -> str:
    rank = get_rank(user.missions_success)
    donor = "⭐ Донатор\n" if user.is_donor else ""
    return (
        f"👤 {user.name}\n{rank}\n{donor}\n"
        f"💵 Наличные: {user.cash}\n"
        f"💎 Алмазы: {user.diamonds}\n\n"
        f"🎒 Купленные товары:\n"
        f"📡 Шпионское устройство: {user.spy_device}\n"
        f"⚖️ Защита голоса: {user.voice_protect}\n"
        f"🎭 Один правильный ответ: {user.correct_answer}\n"
        f"🔫 Винтовка: {user.rifle}\n\n"
        f"🎯 Успешные миссии: {user.missions_success}\n"
        f"🎲 Всего операций: {user.total_games}\n"
        f"👥 Приглашено друзей: {user.referral_count}"
    )


ACHIEVEMENTS = [
    (1,  "🕵️ Первый шаг",  "Первая миссия", 50),
    (3,  "🎯 Агент",        "3 победы",      100),
    (7,  "👁 Оперативник",  "7 побед",       200),
    (15, "🔥 Мастер",       "15 побед",      350),
    (30, "💀 Легенда",      "30 побед",      500),
]


def get_max_rounds(player_count: int) -> int:
    if player_count <= 4:  return 2
    elif player_count <= 7: return 3
    elif player_count <= 10: return 4
    else: return 5


def get_max_game_time(player_count: int) -> int:
    if player_count <= 4:  return 15 * 60
    elif player_count <= 7: return 17 * 60
    else: return 20 * 60


def elapsed_str(start_time: float) -> str:
    import time
    e = int(time.time() - start_time)
    return f"{e // 60} мин {e % 60} сек"
