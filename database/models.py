from sqlalchemy import BigInteger, Integer, Text, Boolean, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=True)
    cash: Mapped[int] = mapped_column(Integer, default=0)
    diamonds: Mapped[int] = mapped_column(Integer, default=0)
    spy_device: Mapped[int] = mapped_column(Integer, default=0)
    voice_protect: Mapped[int] = mapped_column(Integer, default=0)
    correct_answer: Mapped[int] = mapped_column(Integer, default=0)
    rifle: Mapped[int] = mapped_column(Integer, default=0)
    missions_success: Mapped[int] = mapped_column(Integer, default=0)
    total_games: Mapped[int] = mapped_column(Integer, default=0)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_donor: Mapped[bool] = mapped_column(Boolean, default=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    referral_count: Mapped[int] = mapped_column(Integer, default=0)
    referred_by: Mapped[int] = mapped_column(BigInteger, default=0)


class Admin(Base):
    __tablename__ = "admins"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    added_by: Mapped[int] = mapped_column(BigInteger, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, default=0)
    action: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DisabledLocation(Base):
    __tablename__ = "disabled_locations"

    location_name: Mapped[str] = mapped_column(Text, primary_key=True)
