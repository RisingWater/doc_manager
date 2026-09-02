# 试卷文档管理系统

管理试卷文档的轻量系统：自动扫描目录、按 年份/科目/地市/考试/试卷答案 分类入库，提供网页端筛选、模糊搜索、下载和上传。

- 后端：Python + FastAPI + SQLite（`data/doc_manager.db`）
- 前端：React + Ant Design（bun 构建，由后端静态托管）
- 定时扫描：APScheduler，默认每 30 分钟（环境变量 `SCAN_INTERVAL_MINUTES` 可调）

## 功能

- **定时扫描**：扫描 docs.json 中配置的目录，新文件自动入库；已扫过的文件跳过，每次扫描会按最新分类规则重新分类
- **自动分类**：根据相对路径（目录名 + 文件名）识别五个维度：
  - 年份：`2023`、`2021-2022学年`(取末年)、`22-24`、`25一检` 等写法
  - 科目：数学/语文/英语/物理/化学/道法/体育等
  - 地市：福建省九地市
  - 考试：一检/二检/中考/期中/期末/质检（含"第二次质量监测"→二检）等
  - 试卷/答案：`试卷` / `答案` / `试卷+答案`，都没提默认 `试卷`
  - 四项（年份/科目/地市/考试）齐全才算"已分类"，缺失项可在前端悬停查看
- **前端**：多条件筛选、模糊搜索（文件名/路径/分类字段）、单选/批量下载、上传（指定分类，默认存到 `uploads/`）
- **分类规则可调**：关键词列表在 `src/backend/config.py`（`SUBJECTS` / `CITIES`），考试和年份模式在 `src/backend/classifier.py`

## 目录结构

```
doc_manager/
├── docs.json              # 扫描目录配置（数组，相对路径基于项目根）
├── requirements.txt
├── API.md                 # 后端接口文档（供其它程序调用）
├── start.bat              # Windows 启动脚本
├── data/                  # SQLite 数据库（自动创建）
├── uploads/               # 默认上传目录（自动创建）
├── src/backend/           # FastAPI 后端
│   ├── config.py          # 路径、分类关键词、扫描扩展名等配置
│   ├── classifier.py      # 分类规则
│   ├── scanner.py         # 目录扫描入库
│   ├── scheduler.py       # 定时任务
│   ├── api.py             # REST 接口
│   └── main.py            # 应用入口
├── src/frontend/          # React + antd 前端
└── deploy/                # Docker 部署（Dockerfile / build.sh / start.sh / run.sh）
```

## Windows 快速开始

```bat
:: 首次
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
cd src\frontend && bun install && bun run build && cd ..\..

:: 启动（或直接双击 start.bat）
start.bat
```

浏览器访问 http://127.0.0.1:8000

## 配置扫描目录

编辑根目录 `docs.json`：

```json
[
  "D:\\yuqiao\\九年级\\乔宝卷子",
  "uploads"
]
```

相对路径基于项目根目录。改完后在前端点"立即扫描"，或等下一轮定时扫描。

## Docker 部署（Linux）

```bash
deploy/build.sh            # 构建镜像
HOST_PORT=8000 deploy/start.sh   # 启动容器（项目目录挂载到 /workdir，数据持久化）
deploy/run.sh              # 容器内启动逻辑：pip install → bun run build → 启动服务
```

容器内自动完成依赖安装和前端构建；`data/`、`uploads/`、`docs.json` 都在挂载目录中，可直接修改。

## 前端开发模式

```bash
cd src/frontend
bun install
bun run dev        # http://localhost:5173，API 代理到 127.0.0.1:8000
```

## API

详见 [API.md](API.md)：文档查询（分类筛选 + 模糊搜索 + 分页）、下载、上传、扫描触发与状态等接口。
