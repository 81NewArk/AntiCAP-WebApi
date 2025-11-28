import os
import jwt
import AntiCAP
import uvicorn
import logging
import uuid
from typing import Optional
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta, timezone
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from database import  init_db, User, RegistrationCode, UserRole, get_db, EndpointCost

# Initialize Database
init_db()



# Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.urandom(32).hex()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1 * 60 * 24 * 60  # 60 days

description = """
* 通过Http协议 跨语言调用AntiCAP

<img src="https://img.shields.io/badge/GitHub-ffffff"></a> <a href="https://github.com/81NewArk/AntiCAP-WebApi"> <img src="https://img.shields.io/github/stars/81NewArk/AntiCAP-WebApi?style=social"> 

"""

app = FastAPI(
    title="AntiCAP - WebApi",
    description=description,
    version="1.0.9",
    docs_url=None
)

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.bootcdn.net/ajax/libs/swagger-ui/5.29.0/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.bootcdn.net/ajax/libs/swagger-ui/5.29.0/swagger-ui.css",
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
                '"GET /register/' in message
        )
        return not is_static_request


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")
Atc = AntiCAP.Handler(show_banner=False)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


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


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    username = verify_token(token, credentials_exception)
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


async def get_current_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


async def check_balance_and_deduct(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role == UserRole.ADMIN:
        return current_user  # Admins don't consume credits

    # Determine cost
    path = request.url.path
    cost_entry = db.query(EndpointCost).filter(EndpointCost.path == path).first()
    cost = cost_entry.cost if cost_entry else 1

    if current_user.balance < cost:
        raise HTTPException(status_code=402, detail="Insufficient balance")

    current_user.balance -= cost
    db.commit()
    return current_user


@app.post("/api/register", summary="用户注册", tags=["公共"])
async def register(user_in: UserRegister, db: Session = Depends(get_db)):
    # Check if user exists
    if db.query(User).filter(User.username == user_in.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")

    # Verify registration code
    code = db.query(RegistrationCode).filter(RegistrationCode.code == user_in.registration_code,
                                             RegistrationCode.is_used == False).first()
    if not code:
        raise HTTPException(status_code=400, detail="Invalid or used registration code")

    # Create user
    hashed_password = get_password_hash(user_in.password)
    new_user = User(username=user_in.username, hashed_password=hashed_password, role=UserRole.USER, balance=code.points)
    db.add(new_user)

    # Mark code as used
    code.is_used = True
    db.commit()
    db.refresh(new_user)
    return {"message": "Registration successful"}


@app.post("/api/login", summary="登录获取JWT", tags=["公共"])
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
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
async def generate_code(data: GenerateCodeIn, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    code_str = str(uuid.uuid4())
    new_code = RegistrationCode(code=code_str, created_by=current_user.id, points=data.points)
    db.add(new_code)
    db.commit()
    return {"registration_code": code_str, "points": data.points}


@app.get("/api/admin/regcodes", summary="获取注册码列表", tags=["管理员"])
async def get_regcodes(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_admin_user),
                       db: Session = Depends(get_db)):
    regcodes = db.query(RegistrationCode).order_by(RegistrationCode.id.desc()).offset(skip).limit(limit).all()
    return regcodes


@app.delete("/api/admin/regcodes/{code_id}", summary="删除注册码", tags=["管理员"])
async def delete_regcode(code_id: int, current_user: User = Depends(get_current_admin_user),
                         db: Session = Depends(get_db)):
    regcode = db.query(RegistrationCode).filter(RegistrationCode.id == code_id).first()
    if not regcode:
        raise HTTPException(status_code=404, detail="Registration code not found")

    if regcode.is_used:
        raise HTTPException(status_code=400, detail="Cannot delete a used registration code")

    db.delete(regcode)
    db.commit()
    return {"message": "Registration code deleted successfully"}


@app.get("/api/admin/users", summary="获取所有用户", tags=["管理员"])
async def get_users(skip: int = 0, limit: int = 100, current_user: User = Depends(get_current_admin_user),
                    db: Session = Depends(get_db)):
    users = db.query(User).offset(skip).limit(limit).all()
    return [{"username": u.username, "role": u.role, "balance": u.balance, "id": u.id} for u in users]


@app.put("/api/admin/users/{username}", summary="修改用户信息", tags=["管理员"])
async def update_user(username: str, user_update: UserUpdate, current_user: User = Depends(get_current_admin_user),
                      db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_update.password:
        user.hashed_password = get_password_hash(user_update.password)

    if user_update.balance is not None:
        user.balance = user_update.balance

    db.commit()
    return {"message": "User updated successfully", "username": user.username, "balance": user.balance}


@app.get("/api/admin/costs", summary="获取所有接口扣点配置", tags=["管理员"])
async def get_endpoint_costs(current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    costs = db.query(EndpointCost).all()
    return costs


@app.post("/api/admin/costs", summary="设置接口扣点", tags=["管理员"])
async def set_endpoint_cost(cost_in: EndpointCostIn, current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    cost_entry = db.query(EndpointCost).filter(EndpointCost.path == cost_in.path).first()
    if cost_entry:
        cost_entry.cost = cost_in.cost
        cost_entry.description = cost_in.description
    else:
        cost_entry = EndpointCost(path=cost_in.path, cost=cost_in.cost, description=cost_in.description)
        db.add(cost_entry)
    
    db.commit()
    db.refresh(cost_entry)
    return cost_entry



@app.get("/api/tokens/verification", summary="验证JWT", tags=["公共"])
async def verify_token_endpoint(current_user: User = Depends(get_current_user)):
    return {"username": current_user.username, "role": current_user.role, "balance": current_user.balance}


@app.post("/api/ocr", summary="返回字符串", tags=["OCR识别"])
async def ocr(data: ModelImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = Atc.OCR(data.img_base64)
    return {"result": result}


@app.post("/api/math", summary="返回计算结果", tags=["计算识别"])
async def math(data: ModelImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = Atc.Math(data.img_base64)
    return {"result": result}


@app.post("/api/detection/icon", summary="检测图标,返回坐标", tags=["目标检测"])
async def detection_icon(data: ModelImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = Atc.Detection_Icon(data.img_base64)
    return {"result": result}


@app.post("/api/detection/text", summary="侦测文字,返回坐标", tags=["目标检测"])
async def detection_text(data: ModelImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = Atc.Detection_Text(data.img_base64)
    return {"result": result}


@app.post("/api/detection/icon/order", summary="按序返回图标的坐标", tags=["目标检测"])
async def detection_icon_order(data: ModelOrderImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = Atc.ClickIcon_Order(order_img_base64=data.order_img_base64, target_img_base64=data.target_img_base64)
    return {"result": result}


@app.post("/api/detection/text/order", summary="按序返回文字的坐标", tags=["目标检测"])
async def detection_text_order(data: ModelOrderImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = Atc.ClickText_Order(order_img_base64=data.order_img_base64, target_img_base64=data.target_img_base64)
    return {"result": result}


@app.post("/api/slider/match", summary="缺口滑块,返回坐标", tags=["滑块验证码，OpenCV算法"])
async def slider_match(data: SliderImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = Atc.Slider_Match(target_base64=data.target_base64, background_base64=data.background_base64)
    return {"result": result}


@app.post("/api/slider/comparison", summary="阴影滑块,返回坐标", tags=["滑块验证码，OpenCV算法"])
async def slider_comparison(data: SliderImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = Atc.Slider_Comparison(target_base64=data.target_base64, background_base64=data.background_base64)
    return {"result": result}


@app.post("/api/compare/similarity", summary="对比图片相似度", tags=["图片对比，孪生神经经网络模型"])
async def compare_similarity(data: CompareImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = Atc.Compare_Image_Similarity(image1_base64=data.img1_base64, image2_base64=data.img2_base64)
    return {"result": float(result)}


@app.post("/api/rotate/single/rotate", summary="单图旋转验证码", tags=["旋转验证码，模型识别"])
async def single_rotate(data: ModelImageIn, current_user: User = Depends(check_balance_and_deduct)):
    result = Atc.Single_Rotate(img_base64=data.img_base64)
    return {"result": result}


@app.post("/api/rotate/double/rotate", summary="双图旋转验证码", tags=["旋转验证码，OpenCV算法"])
async def double_rotate(data: DoubleRotateIn, current_user: User = Depends(check_balance_and_deduct)):
    result = Atc.Double_Rotate(inside_base64=data.inside_base64, outside_base64=data.outside_base64)
    return {"result": result}


app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == '__main__':
    print('''
-------------------------------------------------------------------------------------------------------------
|                                Github: https://github.com/81NewArk                                        |
|                                               Version:1.0.9                                               |
-------------------------------------------------------------------------------------------------------------
|                                                  免责声明：                                                 |
| 本项目基于MIT开源协议发布，欢迎自由使用、修改和分发，但必须遵守中华人民共和国法律法规。使用本项目即表示您已阅读并同意以下条款:   |
| 1. 合法使用:不得将本项目用于任何违法、违规或侵犯他人权益的行为，包括但不限于网络攻击、诈骗、绕过身份验证、未经授权的数据抓取等   |
| 2. 风险自负:任何因使用本项目而产生的法律责任、技术风险或经济损失，由使用者自行承担,项目作者不承担任何形式的责任               |
| 3. 禁止滥用:不得将本项目用于违法牟利,黑产活动或其他不当商业用途                                                      |
| 使用视为同意上述条款,即"谁使用,谁负责"  如不同意,请立即停止使用并删除本项目                                            |
-------------------------------------------------------------------------------------------------------------
''')



    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.addFilter(NoStaticFilter())
    uvicorn.run(app, host="0.0.0.0", port=6688, access_log=True)
