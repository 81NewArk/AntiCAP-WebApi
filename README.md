<div align="center">

# AntiCAP WebApi

</div>

## 🌍环境说明
```
python 3.8+
```

<div align="center">

## 📁 安装

</div>

###  1.Git克隆仓库 或 手动下载

```
git clone https://github.com/81NewArk/AntiCAP-WebApi

cd AntiCAP-WebApi
```



### 2.使用清华源下载项目所需依赖
```
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```


### 3.运行main.py
```
python main.py
```


###  Web页面
❗ 服务器部署打开6688端口

```
# Web主页:

http://127.0.0.1:6688/
http://localhost:6688/

# 开发者文档：

http://127.0.0.1:6688/docs
http://localhost:6688/docs
```
<div align="center">

## 📄 调用说明

</div>


## 🔠 通用OCR识别
调用说明：

适用类型为数字、汉字、字母

![image.png](https://img.picui.cn/free/2025/05/30/6839c849174f6.png)

| URL       | 方法  | 请求                           | 响应                   |
|-----------|----------|------------------------------|----------------------|
| `/ocr`    | `POST` | { "img_base64": "Base64编码" } | { "result": "识别结果" } |


## 1. ➗计算类验证码识别
调用说明：

适用类型为加减乘除运算

![math.png](https://img.picui.cn/free/2025/05/30/6839ccef3f14d.png) ![math.png](https://img.picui.cn/free/2025/05/30/6839cd33974b1.png)

![math.png](https://img.picui.cn/free/2025/05/30/6839cd55380d3.png) ![math.png](https://img.picui.cn/free/2025/05/30/6839cda564683.png)

| URL    | 方法  | 请求                           | 响应                  |
|--------|----------|------------------------------|---------------------|
| `/math`    | `POST` | { "img_base64": "Base64编码" } | { "result": "计算结果"} |


## 2. 🎯图标侦测
调用说明：

图标侦测 返回坐标

![DetICO.png](https://img.picui.cn/free/2025/05/30/6839d08b04eaf.png)

| URL       | 方法  | 请求                           | 响应                                  |
|-----------|----------|------------------------------|-------------------------------------|
| `/detection/icon`    | `POST` | { "img_base64": "Base64编码" } | {"result": [[x1, y1], [x2, y2]...]} |


## 3. 🎯图标侦测 按序返回坐标
调用说明： 上传两张图片的Base64

提示图片：

![tpis.png](https://img.picui.cn/free/2025/05/30/6839d3026e2f3.png)

目标图片：

![target.png](https://img.picui.cn/free/2025/05/30/6839d08b04eaf.png)

| URL       | 方法  | 请求                                                     | 响应                                  |
|-----------|----------|--------------------------------------------------------|-------------------------------------|
| `/detection/icon/order`    | `POST` | {"order_img_base64": "提示图","target_img_base64": "目标图"} | {"result": [[x1, y1], [x2, y2]...]} |

## 4. 🔤文字侦测
调用说明：

文字侦测 返回坐标

![DetText.jpg](https://img.picui.cn/free/2025/05/30/6839d4771db7c.jpg)

| URL       | 方法  | 请求                         | 响应                                                            |
|-----------|----------|----------------------------|---------------------------------------------------------------|
| `/detection/text`    | `POST` | {"img_base64": "Base64编码"} | {"result": [{"text": "勘","box": [x1, y1], [x2, y2]}...} |

## 5. 后面不想写了 等有空再写
