import os
import jwt
import AntiCAP
import uvicorn
from typing import Optional
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta, timezone
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm


SECRET_KEY = None
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1*60*24* 60  # 60天
VALID_USERNAME = None
VALID_PASSWORD = None
AUTH_FILE = ".env"




description = """
* 通过Http协议 跨语言调用AntiCAP

<img src="https://img.shields.io/badge/GitHub-ffffff"></a> <a href="https://github.com/81NewArk/AntiCAP-WebApi"> <img src="https://img.shields.io/github/stars/81NewArk/AntiCAP-WebApi?style=social"> 

"""


app = FastAPI(
    title="AntiCAP - WebApi",
    description=description,
    version="1.0.5",
    swagger_ui_parameters={
        "swagger_js_url": "https://cdn.bootcdn.net/ajax/libs/swagger-ui/5.22.0/swagger-ui-bundle.js",
        "swagger_css_url": "https://cdn.bootcdn.net/ajax/libs/swagger-ui/5.22.0/swagger-ui.css"
    }
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
    target_img_base64:str


class SliderImageIn(BaseModel):
    target_base64: str
    background_base64:str


class CompareImageIn(BaseModel):
    img1_base64: str
    img2_base64: str



oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

Atc = AntiCAP.Handler(show_banner=False)



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


def save_auth_to_env(username, password, port):
    with open(AUTH_FILE, "w") as f:
        f.write(f"USERNAME={username}\n")
        f.write(f"PASSWORD={password}\n")
        f.write(f"PORT={port}\n")


def load_auth_from_env():
    env = {}
    with open(AUTH_FILE, "r") as f:
        for line in f:
            if "=" in line:
                key, val = line.strip().split("=", 1)
                env[key.strip()] = val.strip()
    username = env.get("USERNAME")
    password = env.get("PASSWORD")
    port = int(env.get("PORT", 6688))
    return username, password, port


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return verify_token(token, credentials_exception)



@app.post("/api/login", summary="登录获取JWT", tags=["公共"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    if form_data.username != VALID_USERNAME or form_data.password != VALID_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": form_data.username},
        expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@app.get("/api/tokens/verification", summary="验证JWT", tags=["公共"])
async def verify_token_endpoint(current_user: str = Depends(get_current_user)):
    return {"username": current_user}


@app.post("/api/ocr",summary="返回字符串",tags=["OCR识别"])
async def ocr(data: ModelImageIn, current_user: str = Depends(get_current_user)):
    result = Atc.OCR(data.img_base64)
    return {"result": result }

@app.post("/api/math",summary="返回计算结果",tags=["计算识别"])
async def math(data: ModelImageIn, current_user: str = Depends(get_current_user)):
    result = Atc.Math(data.img_base64)
    return {"result": result }

@app.post("/api/detection/icon",summary="检测图标,返回坐标",tags=["目标检测"])
async def detection_icon(data: ModelImageIn, current_user: str = Depends(get_current_user)):
    result = Atc.Detection_Icon(data.img_base64)
    return {"result": result }

@app.post("/api/detection/text",summary="侦测文字,返回坐标",tags=["目标检测"])
async def detection_text(data: ModelImageIn, current_user: str = Depends(get_current_user)):
    result = Atc.Detection_Text(data.img_base64)
    return {"result": result}

@app.post("/api/detection/icon/order",summary="按序返回图标的坐标",tags=["目标检测"])
async def detection_icon_order(data: ModelOrderImageIn, current_user: str = Depends(get_current_user)):
    result = Atc.ClickIcon_Order(order_img_base64=data.order_img_base64,target_img_base64=data.target_img_base64)
    return {"result": result }

@app.post("/api/detection/text/order",summary="按序返回文字的坐标",tags=["目标检测"])
async def detection_text_order(data: ModelOrderImageIn, current_user: str = Depends(get_current_user)):
    result = Atc.ClickText_Order(order_img_base64=data.order_img_base64,target_img_base64=data.target_img_base64)
    return {"result": result }

@app.post("/api/slider/match",summary="缺口滑块,返回坐标",tags=["滑块验证码"])
async def slider_match(data: SliderImageIn, current_user: str = Depends(get_current_user)):
    result = Atc.Slider_Match(target_base64=data.target_base64,background_base64=data.background_base64)
    return {"result": result }

@app.post("/api/slider/comparison",summary="阴影滑块,返回坐标",tags=["滑块验证码"])
async def slider_comparison(data: SliderImageIn, current_user: str = Depends(get_current_user)):
    result = Atc.Slider_Comparison(target_base64=data.target_base64,background_base64=data.background_base64)
    return {"result": result }


@app.post("/api/compare/similarity", summary="对比图片相似度", tags=["图片对比"])
async def compare_similarity(data: CompareImageIn, current_user: str = Depends(get_current_user)):
    result = Atc.compare_image_similarity(image1_base64=data.img1_base64, image2_base64=data.img2_base64)
    return {"result": float(result)}




app.mount("/", StaticFiles(directory="static", html=True), name="static")



if __name__ == '__main__':
    print('''
-----------------------------------------------------------
|         Github: https://github.com/81NewArk             |
|         Author: 81NewArk                                |
-----------------------------------------------------------
|                    Version:1.0.5                        |
-----------------------------------------------------------''')


    SECRET_KEY = os.urandom(32).hex()

    if os.path.exists(AUTH_FILE):
        VALID_USERNAME, VALID_PASSWORD, port = load_auth_from_env()
    else:
        VALID_USERNAME = input("Please enter username: ")
        VALID_PASSWORD = input("Please enter password: ")
        port_input = input("Please enter port (default: 6688): ")
        port = int(port_input) if port_input else 6688
        save_auth_to_env(VALID_USERNAME, VALID_PASSWORD, port)


    uvicorn.run(app, host="0.0.0.0", port=port, access_log=True)
