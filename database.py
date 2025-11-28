from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import enum

SQLALCHEMY_DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default=UserRole.USER)
    balance = Column(Integer, default=1000)
    created_at = Column(DateTime, default=datetime.utcnow)

class RegistrationCode(Base):
    __tablename__ = "registration_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    is_used = Column(Boolean, default=False)
    points = Column(Integer, default=1000)
    created_by = Column(Integer) # Admin User ID
    created_at = Column(DateTime, default=datetime.utcnow)

class EndpointCost(Base):
    __tablename__ = "endpoint_costs"

    id = Column(Integer, primary_key=True, index=True)
    path = Column(String, unique=True, index=True)
    cost = Column(Integer, default=1)
    description = Column(String, nullable=True)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
