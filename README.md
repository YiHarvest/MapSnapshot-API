# Map Snapshot API

基于 FastAPI、Playwright 和高德地图 JS API 的地图截图服务。

## 环境地址

| 环境 | 地址 |
|---|---|
| 本地服务 | `http://0.0.0.0:28787` |
| 服务端地址 | 待填写 |
| Swagger | `http://0.0.0.0:28787/docs` |

本机调试使用 `http://0.0.0.0:28787`。
## 安装

```bash
uv sync
uv run playwright install
pnpm approve-builds
```

需要在 `.env` 或系统环境变量中配置：

```text
VITE_AMAP_KEY=你的高德 Web JS API Key
VITE_AMAP_SECURITY_CODE=你的高德安全密钥
```

## 启动

```bash
pnpm snapshot:server
```

等价的底层命令：

```bash
uv run python server/app.py
```

本地开发默认开启热重载，修改 `server/` 或 `public/geojson/` 下的文件后服务会自动重启。
如需关闭热重载，可设置：

```bash
MAP_SNAPSHOT_RELOAD=0 pnpm snapshot:server
```

启动成功后会看到：

```text
Uvicorn running on http://0.0.0.0:28787
```

任务清理由后台定时执行，默认每 7 天检查一次；清理时会删除创建时间超过 7 天的任务记录和对应截图文件。

## 接口概览

项目提供 10 个接口，分为系统接口、任务管理接口和资源接口三类。

### 系统接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/health` | 健康检查 |
| `GET` | `/api/v1/map-share?taskId=xxx` | 全国地图渲染页 |
| `GET` | `/api/v1/province-share?taskId=xxx` | 省级地图渲染页 |
| `GET` | `/api/v1/city-share?taskId=xxx` | 市级地图渲染页 |

### 任务管理接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/snapshot` | 创建全国地图截图任务 |
| `POST` | `/api/v1/province-snapshot` | 创建省级地图截图任务 |
| `POST` | `/api/v1/city-snapshot` | 创建市级地图截图任务 |
| `GET` | `/api/v1/snapshot/{taskId}` | 查询截图任务 |

### 资源接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/snapshots/{file_name}` | 获取截图 PNG |
| `GET` | `/static/...` | 公开静态资源 |

## 静态资源

`server/static/` 已挂载为公开静态目录，文件可通过 `/static/...` 直接访问。

示例：

```text
http://0.0.0.0:28787/static/dO3j6iTFfD.txt
```

对应文件：

```text
server/static/dO3j6iTFfD.txt
```

## 目录

- `server/app.py`：服务入口，注册原有接口和静态资源挂载，全国地图截图接口
- `server/scope_snapshot.py`：省级地图截图接口
- `server/city_snapshot.py`：市级地图截图接口
- `server/templates/map_share.html`：全国地图截图页面
- `server/templates/scope_share.html`：省级地图截图页面
- `server/templates/city_share.html`：市级地图截图页面
- `server/static/`：公开静态资源目录
- `public/geojson/`：行政区 GeoJSON 数据
- `public/snapshots/`：截图 PNG 和任务 JSON 输出目录
- `doc/`：接口文档