from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import enum

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./app.db"

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
# expire_on_commit=False 必须显式关闭：默认 True 时 commit() 会把所有 ORM 实例
# 属性标记为过期，之后再读属性会触发一次同步 refresh 查询，在 async session 下
# 直接抛 MissingGreenlet。异步场景的标准做法就是关掉它。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession,
                            expire_on_commit=False)

Base = declarative_base()

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"

class User(Base):
    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, index=True)
    username: str = Column(String, unique=True, index=True)
    hashed_password: str = Column(String)
    role: str = Column(String, default=UserRole.USER)
    balance: int = Column(Integer, default=1000)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)

class RegistrationCode(Base):
    __tablename__ = "registration_codes"

    id: int = Column(Integer, primary_key=True, index=True)
    code: str = Column(String, unique=True, index=True)
    is_used: bool = Column(Boolean, default=False)
    points: int = Column(Integer, default=1000)
    created_by: int = Column(Integer) # Admin User ID
    created_at: datetime = Column(DateTime, default=datetime.utcnow)

class EndpointCost(Base):
    __tablename__ = "endpoint_costs"

    id: int = Column(Integer, primary_key=True, index=True)
    path: str = Column(String, unique=True, index=True)
    cost: int = Column(Integer, default=1)
    description: str = Column(String, nullable=True)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with SessionLocal() as db:
        yield db
