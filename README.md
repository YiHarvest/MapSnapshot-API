# Map Snapshot API

基于 FastAPI、Playwright、Jinja2 和高德地图 JS API 的地图截图服务。支持全国、省级和市级三种截图范围。

## 环境要求

- Python 3.11+
- uv
- 可访问高德地图 JS API 的网络环境

## 安装

```bash
uv sync --group dev
uv run playwright install chromium
cp .env.example .env
```

在 `.env` 中配置：

```text
VITE_AMAP_KEY=你的高德 Web JS API Key
VITE_AMAP_SECURITY_CODE=你的高德安全密钥
```

## 启动

开发模式：

```bash
uv run main.py --reload
```

普通模式：

```bash
uv run main.py
```

默认监听 `http://0.0.0.0:28787`，Swagger 地址为 `http://127.0.0.1:28787/docs`。

可选环境变量：

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `MAP_SNAPSHOT_PORT` / `PORT` | `28787` | 服务端口 |
| `PLAYWRIGHT_EXECUTABLE_PATH` | 空 | 指定 Chromium/Edge 可执行文件 |
| `SNAPSHOT_BASE_URL` | 空 | 反向代理路径前缀 |

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/health` | 健康检查 |
| `POST` | `/api/v1/snapshot` | 创建全国截图任务 |
| `POST` | `/api/v1/province-snapshot` | 创建省级截图任务 |
| `POST` | `/api/v1/city-snapshot` | 创建市级截图任务 |
| `GET` | `/api/v1/snapshot/{task_id}` | 查询任务 |
| `GET` | `/api/v1/map-share?taskId=...` | 全国分享页 |
| `GET` | `/api/v1/province-share?taskId=...` | 省级分享页 |
| `GET` | `/api/v1/city-share?taskId=...` | 市级分享页 |
| `GET` | `/api/v1/snapshots/{file_name}` | 获取 PNG |
| `GET` | `/static/...` | 公共页面资源 |

创建任务后会立即返回 `processing` 状态。服务在后台生成：

- `public/snapshots/{taskId}.png`
- `public/snapshots/{taskId}.json`

截图和任务结果默认保留 7 天。

## 目录

```text
.
├── main.py                   # Uvicorn CLI 入口
├── server/
│   ├── app.py                # FastAPI 应用工厂
│   ├── api/                  # HTTP 路由
│   ├── core/                 # 配置、context、生命周期和运行时状态
│   ├── model.py              # Pydantic BaseModel 与全部请求模型
│   ├── services/             # GeoJSON、任务、截图、回调和模板服务
│   ├── templates/            # Jinja 分享页
│   └── static/               # 分享页公共 CSS/JS
├── public/
│   ├── geojson/              # 行政区 GeoJSON
│   └── snapshots/            # 运行时输出，Git 忽略
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/
```

公共配置统一从 `server.core` 导入；配置实现位于 `server.core.config`。

## 开发检查

```bash
uv run ruff format --check .
uv run ruff check .
uv run python -m pytest -m "not e2e"
```

真实截图测试需要有效的高德 Key、浏览器和已启动的本地服务：

```bash
uv run python -m pytest -m e2e
```

## 运行数据

- `public/geojson/` 是运行必需的行政区数据，应纳入版本控制。
- `public/snapshots/` 是运行产物，不纳入版本控制。
- `docs/` 和 `uv.lock` 按项目约定保留在本地但不纳入版本控制。
