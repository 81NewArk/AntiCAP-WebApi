import os
import jwt
import AntiCAP
import uvicorn
import logging
import uuid
import asyncio
import secrets
from typing import Optional, Dict
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta, timezone
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from passlib.context import CryptContext
from contextlib import asynccontextmanager
from database import init_db, User, RegistrationCode, UserRole, get_db, EndpointCost, SessionLocal

class KeyedLock:
    """按 key 串行化的锁池。

    用引用计数管理生命周期：最后一个使用者退出后立即回收，
    避免字典随用户数只增不减。不能简单地"清理未被持有的锁"——
    那样会把正在等待获取的锁误删，导致两个请求同时进入临界区。
    """

    def __init__(self):
        # key -> [lock, waiter_count]
        self.locks: Dict[str, list] = {}
        self._global_lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, key: str):
        async with self._global_lock:
            entry = self.locks.get(key)
            if entry is None:
                entry = [asyncio.Lock(), 0]
                self.locks[key] = entry
            entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            async with self._global_lock:
                entry[1] -= 1
                if entry[1] <= 0:
                    self.locks.pop(key, None)

user_locks = KeyedLock()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 直接用 SessionLocal，不要 `async for ... break` 去中断 get_db 这个
    # 异步生成器——那样 session 不走正常关闭路径
    async with SessionLocal() as db:
        await ensure_admin_user(db)
    yield




# Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_secret_key():
    key_file = "secret.key"
    if os.path.exists(key_file):
        with open(key_file, "r") as f:
            return f.read().strip()
    else:
        new_key = os.urandom(32).hex()
        with open(key_file, "w") as f:
            f.write(new_key)
        return new_key

SECRET_KEY = get_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1 * 60 * 24 * 60  # 60 days

description = """
* 通过Http协议 跨语言调用AntiCAP

<img src="https://img.shields.io/badge/GitHub-ffffff"></a> <a href="https://github.com/81NewArk/AntiCAP-WebApi"> <img src="https://img.shields.io/github/stars/81NewArk/AntiCAP-WebApi?style=social"> 

"""

app: FastAPI = FastAPI(
    title="AntiCAP-WebApi",
    description=description,
    version="1.1.1",
    docs_url=None,
    lifespan=lifespan
)

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - 开发者文档",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/swagger/swagger-ui-bundle.js",
        swagger_css_url="/swagger/swagger-ui.css",
    )

# CORS 默认关闭。内置前端由下方 StaticFiles 同源挂载，本身不需要 CORS。
# 需要其他域名调用时，用逗号分隔设置白名单，例如：
#   CORS_ALLOW_ORIGINS=https://a.example.com,https://b.example.com
# 原来的 allow_origins=["*"] 配 allow_credentials=True 会让 Starlette 回显
# 任意 Origin，等于允许任何站点带凭据跨域调用本接口。
_cors_allow_origins = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]
if _cors_allow_origins:
    # 通配符与携带凭据不能共存，否则等于完全放开
    _cors_allow_credentials = "*" not in _cors_allow_origins
    if not _cors_allow_credentials:
        print("WARNING: CORS_ALLOW_ORIGINS 含 '*'，已强制关闭 allow_credentials。")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allow_origins,
        allow_credentials=_cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class ModelImageIn(BaseModel):
    img_base64: str


class ModelOrderImageIn(BaseModel):
    order_img_base64: str
    target_img_base64: str


class SliderImageIn(BaseModel):
    target_base64: str
    background_base64: str


class CompareImageIn(BaseModel):
    img1_base64: str
    img2_base64: str


class DoubleRotateIn(BaseModel):
    inside_base64: str
    outside_base64: str


class UserRegister(BaseModel):
    username: str
    password: str
    registration_code: str


class UserUpdate(BaseModel):
    password: Optional[str] = None
    balance: Optional[int] = None


class EndpointCostIn(BaseModel):
    path: str
    cost: int
    description: Optional[str] = None


class GenerateCodeIn(BaseModel):
    points: int = 1000




class NoStaticFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        is_static_request = (
                '"GET /_next/' in message or
                '"GET /static/' in message or
                '"GET /myhome/' in message or
                '"GET /favicon.ico' in message or
                '"GET /admin/index.txt?' in message or
                '"GET /register/index.txt?' in message or
                '"GET /login/index.txt?_rsc' in message or
                '"GET /index.txt?' in message or
                '"GET /register/' in message or
                '"GET /swagger/' in message or
                '"GET /healthz ' in message  # 容器 HEALTHCHECK 探测，无需记录
        )
        return not is_static_request


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")
Atc = AntiCAP.Handler(show_banner=False)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


async def ensure_admin_user(db: AsyncSession):
    """确保 admin 账号存在。

    只在账号不存在时创建，绝不重置已有密码——否则管理员改过的密码
    会在每次重启后被打回默认值，等于留了个固定口令后门。
    初始密码取自环境变量 ADMIN_PASSWORD，未设置则随机生成并打印一次。
    """
    admin_username = "admin"

    result = await db.execute(select(User).filter(User.username == admin_username))
    admin_user = result.scalars().first()

    if admin_user:
        print("Admin user already exists, password left unchanged.")
        return

    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    generated = not admin_password
    if generated:
        admin_password = secrets.token_urlsafe(12)

    new_admin = User(
        username=admin_username,
        hashed_password=get_password_hash(admin_password),
        role=UserRole.ADMIN,
        balance=1000000
    )
    db.add(new_admin)
    await db.commit()

    if generated:
        print("=" * 78)
        print(f"  已创建 admin 账号，随机初始密码: {admin_password}")
        print("  该密码仅在本次启动日志中出现，请立即登录修改。")
        print("  也可通过环境变量 ADMIN_PASSWORD 指定初始密码。")
        print("=" * 78)
    else:
        print("Admin user created with password from ADMIN_PASSWORD.")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    now_utc = datetime.now(timezone.utc)
    if expires_delta:
        expire = now_utc + expires_delta
    else:
        expire = now_utc + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise credentials_exception


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    username = verify_token(token, credentials_exception)
    result = await db.execute(select(User).filter(User.username == username))
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    return user


async def get_current_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


async def check_balance_and_deduct(request: Request, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == UserRole.ADMIN:
        return current_user  # Admins don't consume credits

    # Determine cost
    path = request.url.path
    result = await db.execute(select(EndpointCost).filter(EndpointCost.path == path))
    cost_entry = result.scalars().first()
    cost = cost_entry.cost if cost_entry else 1

    # Use KeyedLock based on user ID to prevent race conditions
    async with user_locks.acquire(f"user_{current_user.id}"):
        # Refresh user data to ensure up-to-date balance
        await db.refresh(current_user)
        
        if current_user.balance < cost:
            raise HTTPException(status_code=402, detail="Insufficient balance")

        current_user.balance -= cost
        await db.commit()
    
    return current_user


@app.post("/api/register", summary="用户注册", tags=["公共"])
async def register(user_in: UserRegister, db: AsyncSession = Depends(get_db)):
    # Check if user exists
    result = await db.execute(select(User).filter(User.username == user_in.username))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Username already registered")

    # Verify registration code
    result = await db.execute(select(RegistrationCode).filter(
        RegistrationCode.code == user_in.registration_code,
        RegistrationCode.is_used == False
    ))
    code = result.scalars().first()
    
    if not code:
        raise HTTPException(status_code=400, detail="Invalid or used registration code")

    points = code.points

    # 原子占用注册码：把 is_used 的判断和写入压进同一条 UPDATE。
    # 之前是先 SELECT 再改属性，两个并发请求能拿同一个码各建一个账号。
    claim = await db.execute(
        update(RegistrationCode)
        .where(RegistrationCode.id == code.id, RegistrationCode.is_used == False)
        .values(is_used=True)
    )
    if claim.rowcount == 0:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid or used registration code")

    # Create user
    hashed_password = get_password_hash(user_in.password)
    new_user = User(username=user_in.username, hashed_password=hashed_password, role=UserRole.USER, balance=points)
    db.add(new_user)

    try:
        await db.commit()
    except IntegrityError:
        # username 唯一约束兜底：并发注册同名账号时，注册码占用一起回滚
        await db.rollback()
        raise HTTPException(status_code=400, detail="Username already registered")

    return {"message": "Registration successful"}


@app.post("/api/login", summary="登录获取JWT", tags=["公共"])
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).filter(User.username == form_data.username))
    user = result.scalars().first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "balance": user.balance
    }


@app.post("/api/admin/generate_code", summary="生成注册码", tags=["管理员"])
async def generate_code(data: GenerateCodeIn, current_user: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)):
    code_str = str(uuid.uuid4())
    new_code = RegistrationCode(code=code_str, created_by=current_user.id, points=data.points)
    db.add(new_code)
    await db.commit()
    return {"registration_code": code_str, "points": data.points}


@app.get("/api/admin/regcodes", summary="获取注册码列表", tags=["管理员"])
async def get_regcodes(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_admin_user),
                       db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RegistrationCode).order_by(RegistrationCode.id.desc()).offset(skip).limit(limit))
    regcodes = result.scalars().all()
    return regcodes


@app.delete("/api/admin/regcodes/{code_id}", summary="删除注册码", tags=["管理员"])
async def delete_regcode(code_id: int, current_user: User = Depends(get_current_admin_user),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RegistrationCode).filter(RegistrationCode.id == code_id))
    regcode = result.scalars().first()
    if not regcode:
        raise HTTPException(status_code=404, detail="Registration code not found")

    if regcode.is_used:
        raise HTTPException(status_code=400, detail="Cannot delete a used registration code")

    await db.delete(regcode)
    await db.commit()
    return {"message": "Registration code deleted successfully"}


@app.get("/api/admin/users", summary="获取所有用户", tags=["管理员"])
async def get_users(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_admin_user),
                    db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).offset(skip).limit(limit))
    users = result.scalars().all()
    return [{"username": u.username, "role": u.role, "balance": u.balance, "id": u.id} for u in users]


@app.put("/api/admin/users/{username}", summary="修改用户信息", tags=["管理员"])
async def update_user(username: str, user_update: UserUpdate, current_user: User = Depends(get_current_admin_user),
                      db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).filter(User.username == username))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_update.password:
        user.hashed_password = get_password_hash(user_update.password)

    if user_update.balance is not None:
        user.balance = user_update.balance

    await db.commit()
    return {"message": "User updated successfully", "username": user.username, "balance": user.balance}


@app.get("/api/admin/costs", summary="获取所有接口扣点配置", tags=["管理员"])
async def get_endpoint_costs(current_user: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EndpointCost))
    costs = result.scalars().all()
    return costs


@app.post("/api/admin/costs", summary="设置接口扣点", tags=["管理员"])
async def set_endpoint_cost(cost_in: EndpointCostIn, current_user: User = Depends(get_current_admin_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EndpointCost).filter(EndpointCost.path == cost_in.path))
    cost_entry = result.scalars().first()
    if cost_entry:
        cost_entry.cost = cost_in.cost
        cost_entry.description = cost_in.description
    else:
        cost_entry = EndpointCost(path=cost_in.path, cost=cost_in.cost, description=cost_in.description)
        db.add(cost_entry)
    
    await db.commit()
    await db.refresh(cost_entry)
    return cost_entry



@app.get("/healthz", include_in_schema=False)
async def healthz():
    """容器健康检查专用。不查库、不加载模型，仅表示进程能接请求。

    必须定义在文件末尾的 app.mount("/") 之前，否则会被静态文件路由吃掉。
    对应的访问日志由 NoStaticFilter 过滤，避免每 60 秒刷一条。
    """
    return {"status": "ok"}


@app.get("/api/tokens/verification", summary="验证JWT", tags=["公共"])
async def verify_token_endpoint(current_user: User = Depends(get_current_user)):
    return {"username": current_user.username, "role": current_user.role, "balance": current_user.balance}


@app.post("/api/ocr", summary="返回字符串", tags=["OCR识别"])
async def ocr(data: ModelImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = await run_in_threadpool(Atc.OCR, data.img_base64)
    return {"result": result}


@app.post("/api/math", summary="返回计算结果", tags=["计算识别"])
async def math(data: ModelImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = await run_in_threadpool(Atc.Math, data.img_base64)
    return {"result": result}


@app.post("/api/detection/icon", summary="检测图标,返回坐标", tags=["目标检测"])
async def detection_icon(data: ModelImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = await run_in_threadpool(Atc.Detection_Icon, data.img_base64)
    return {"result": result}


@app.post("/api/detection/text", summary="侦测文字,返回坐标", tags=["目标检测"])
async def detection_text(data: ModelImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = await run_in_threadpool(Atc.Detection_Text, data.img_base64)
    return {"result": result}


@app.post("/api/detection/icon/order", summary="按序返回图标的坐标", tags=["目标检测"])
async def detection_icon_order(data: ModelOrderImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = await run_in_threadpool(Atc.ClickIcon_Order, order_img_base64=data.order_img_base64, target_img_base64=data.target_img_base64)
    return {"result": result}


@app.post("/api/detection/text/order", summary="按序返回文字的坐标", tags=["目标检测"])
async def detection_text_order(data: ModelOrderImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = await run_in_threadpool(Atc.ClickText_Order, order_img_base64=data.order_img_base64, target_img_base64=data.target_img_base64)
    return {"result": result}


@app.post("/api/slider/match", summary="缺口滑块,返回坐标", tags=["滑块验证码，OpenCV算法"])
async def slider_match(data: SliderImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = await run_in_threadpool(Atc.Slider_Match, target_base64=data.target_base64, background_base64=data.background_base64)
    return {"result": result}


@app.post("/api/slider/comparison", summary="阴影滑块,返回坐标", tags=["滑块验证码，OpenCV算法"])
async def slider_comparison(data: SliderImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = await run_in_threadpool(Atc.Slider_Comparison, target_base64=data.target_base64, background_base64=data.background_base64)
    return {"result": result}


@app.post("/api/compare/similarity", summary="对比图片相似度", tags=["图片对比，孪生神经经网络模型"])
async def compare_similarity(data: CompareImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = await run_in_threadpool(Atc.Compare_Image_Similarity, image1_base64=data.img1_base64, image2_base64=data.img2_base64)
    return {"result": float(result)}


@app.post("/api/rotate/single/rotate", summary="单图旋转验证码", tags=["旋转验证码，模型识别"])
async def single_rotate(data: ModelImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = await run_in_threadpool(Atc.Single_Rotate, img_base64=data.img_base64)
    return {"result": result}


@app.post("/api/rotate/double/rotate", summary="双图旋转验证码", tags=["旋转验证码，OpenCV算法"])
async def double_rotate(data: DoubleRotateIn, current_user: User = Depends(check_balance_and_deduct)):
    result = await run_in_threadpool(Atc.Double_Rotate, inside_base64=data.inside_base64, outside_base64=data.outside_base64)
    return {"result": result}


app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == '__main__':
    print("""

    +--------------------------------------------------------------------------------------+
    |                         Github: https://github.com/81NewArk                          |
    |                                Version: 1.1.2                                        |
    +--------------------------------------------------------------------------------------+
    |  免责声明：                                                                           |
    |  本项目基于MIT开源协议发布,欢迎自由使用,修改和分发,但必须遵守中华人民共和国法律法规。       |
    |  使用本项目即表示您已阅读并同意以下条款:                                                |
    |  1.合法使用:不得将本项目用于任何违法,违规或侵犯他人权益的行为。                           |
    |  2.风险自负:任何因使用本项目而产生的法律责任由使用者自行承担，项目作者不承担责任。          |
    |  3.禁止滥用:不得将本项目用于黑产或其他不当商业用途                                       |
    |  使用视为同意上述条款,如不同意请立即停止使用并删除本项目。                                |
    +--------------------------------------------------------------------------------------+
    
""")

    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.addFilter(NoStaticFilter())
    uvicorn.run(app, host="0.0.0.0", port=6688, access_log=True)
