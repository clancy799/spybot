from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, delete
from database.models import User, Admin, Log, DisabledLocation
from data.locations import LOCATION_CHOICES


async def get_user(session: AsyncSession, user_id: int, name: str) -> User:
    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(user_id=user_id, name=name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def add_cash(session: AsyncSession, user_id: int, amount: int):
    await session.execute(
        update(User).where(User.user_id == user_id).values(cash=User.cash + amount)
    )
    await session.commit()


async def add_diamonds(session: AsyncSession, user_id: int, amount: int):
    await session.execute(
        update(User).where(User.user_id == user_id).values(diamonds=User.diamonds + amount)
    )
    await session.commit()


async def add_game(session: AsyncSession, user_id: int, won: bool):
    if won:
        await session.execute(
            update(User).where(User.user_id == user_id).values(
                total_games=User.total_games + 1,
                missions_success=User.missions_success + 1
            )
        )
    else:
        await session.execute(
            update(User).where(User.user_id == user_id).values(total_games=User.total_games + 1)
        )
    await session.commit()


async def is_admin(session: AsyncSession, user_id: int, super_admin_id: int) -> bool:
    if user_id == super_admin_id:
        return True
    result = await session.execute(select(Admin).where(Admin.user_id == user_id))
    return result.scalar_one_or_none() is not None


async def add_log(session: AsyncSession, user_id: int, action: str, details: str = ""):
    log = Log(user_id=user_id, action=action, details=details)
    session.add(log)
    await session.commit()


async def get_enabled_locations(session: AsyncSession) -> list[str]:
    result = await session.execute(select(DisabledLocation.location_name))
    disabled = [r[0] for r in result.fetchall()]
    return [loc for loc in LOCATION_CHOICES if loc not in disabled]


async def get_top_players(session: AsyncSession):
    result = await session.execute(
        select(User.name, User.missions_success, User.total_games)
        .where(User.total_games > 0)
        .order_by(User.missions_success.desc())
        .limit(10)
    )
    return result.fetchall()


async def get_stats(session: AsyncSession):
    total_users = (await session.execute(select(func.count(User.user_id)))).scalar()
    total_games = (await session.execute(select(func.sum(User.total_games)))).scalar() or 0
    total_cash = (await session.execute(select(func.sum(User.cash)))).scalar() or 0
    total_diamonds = (await session.execute(select(func.sum(User.diamonds)))).scalar() or 0
    banned = (await session.execute(select(func.count(User.user_id)).where(User.is_banned == True))).scalar()
    return total_users, total_games, total_cash, total_diamonds, banned


async def get_all_user_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(select(User.user_id))
    return [r[0] for r in result.fetchall()]


async def get_last_logs(session: AsyncSession, limit: int = 15):
    result = await session.execute(
        select(Log.user_id, Log.action, Log.details, Log.timestamp)
        .order_by(Log.id.desc())
        .limit(limit)
    )
    return result.fetchall()
