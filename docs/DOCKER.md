# Docker 部署与数据管理

[返回项目首页](../README.md)

这套配置用于在 Windows 上演示 Lab Agent。Compose 管理 `frontend`（Vue/Nginx）、`backend`（FastAPI）和 `mysql`（MySQL 8.4）。浏览器访问前端，Nginx 把 `/api/` 和 `/uploads/` 转给 `backend:8000`。后端在 Compose 网络内用 `mysql:3306` 访问数据库。

## 首次启动

启动 Docker Desktop，使用 WSL2 后端和 Linux 容器。当前后端 Dockerfile 固定使用 `linux/amd64` 的 CPU 版 PyTorch 安装包。下面的命令在仓库根目录的 PowerShell 中执行。

```powershell
docker version
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
```

| 文件 | 要填写的值 |
| --- | --- |
| 根目录 `.env` | `MYSQL_ROOT_PASSWORD` 和 `MYSQL_PASSWORD`。使用两个不同的随机十六进制字符串，后者也会被拼入后端数据库连接串。 |
| `backend/.env` | 随机 `JWT_SECRET_KEY`、实际的 `LLM_API_KEY` 和 `LLM_MODEL`。模型服务需要支持 Chat Completions、工具调用和流式回复。 |

Compose 使用 `compose.yaml` 的 `environment` 覆盖后端的 `DATABASE_URL` 和 `LLM_BASE_URL`。如果已有的 `backend/.env` 用的是 `Database_URL`，把变量名统一为 `DATABASE_URL` 并保留原值，避免容器里出现两个仅大小写不同的变量。

默认模型地址是 `http://host.docker.internal:8788/v1`，它指向 Windows 上的模型网关。用这个默认值时，先在 Windows 上启动网关。使用其他兼容模型服务时，修改 `compose.yaml` 中 `backend.environment.LLM_BASE_URL`，并在 `backend/.env` 配好对应的密钥和模型名。

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

| 用途 | 从 Windows 访问 |
| --- | --- |
| Docker 前端 | [http://127.0.0.1:8080](http://127.0.0.1:8080) |
| FastAPI 接口文档 | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) |
| HeidiSQL 或其他 MySQL 客户端 | `127.0.0.1:3307`，用户名 `lab_user`，数据库 `lab_agent`，密码为根目录 `.env` 的 `MYSQL_PASSWORD` |

首次构建会下载基础镜像和依赖。MySQL 初始化后会创建数据库和账号。通过数据库健康检查后，后端启动并创建缺失的应用表。首次预热知识库还需从 Hugging Face 获取 `BAAI/bge-small-zh-v1.5`，可以用 `docker compose logs -f backend` 查看进展。

首次启动的 Docker 数据库为空。可以注册学生账号，需要管理员时，按[账号初始化步骤](../README.md#4-初始化学生和管理员账号)操作。已有旧数据库时，可以按下文迁移数据。

## 查看状态、更新和停止

| 操作 | 在仓库根目录执行 |
| --- | --- |
| 查看服务、状态和端口 | `docker compose ps` |
| 看最近的后端和前端日志 | `docker compose logs --tail 100 backend frontend` |
| 修改前端代码或 Nginx 配置后更新 | `docker compose up -d --build frontend` |
| 修改后端代码、依赖或知识库 Markdown 后更新 | `docker compose up -d --build backend` |
| 修改 Compose 或后端运行配置后应用 | `docker compose up -d` |
| 停止服务或恢复启动 | `docker compose stop` 或 `docker compose up -d` |

在 Docker Desktop 的 **Containers** 中展开 `lab-agent` 也能查看三个容器。开发时可以继续用 Windows 上的 Vite 前端，它在 `5173`，可连接 Docker 后端的 `8000`。整套 Docker 运行时用 `8080`。

## 数据保存位置

| 数据 | 位置 | 重建容器后的行为 |
| --- | --- | --- |
| 账号、预约、聊天等 MySQL 数据 | `mysql_data` 数据卷，挂载到 MySQL 的 `/var/lib/mysql` | 使用同一个卷继续读取 |
| 头像、实验室和设备图片等上传文件 | `uploads_data` 数据卷，挂载到后端的 `/app/uploads` | 使用同一个卷继续读取 |
| 知识库 Markdown | 构建后端镜像时从 `backend/data/kb/` 复制 | 更新资料后重建后端镜像 |
| Chroma 索引和嵌入模型缓存 | 后端容器的可写空间 | 容器重建后会重新生成索引，可能需要重新下载模型 |

`docker compose down` 会移除服务容器和网络，默认保留命名数据卷。`docker compose down -v` 会一并删除项目数据卷，其中包括数据库记录和上传文件。已有 MySQL 数据卷时，修改 `.env` 里的初始化密码不会替换数据库里现存账号的密码。

## 迁移已有数据和图片

以下步骤适用于表结构一致、应用表已经创建且目标表为空的情况。如果目标库已有记录，先备份两边并处理主键和账号冲突，再执行导入。

1. 在 HeidiSQL 连接旧数据库，根据旧后端配置确认端口。在旧库选择项目表并导出为 UTF-8 SQL 文件。**Data** 选 **INSERT**，数据库和表的 **Drop**、**Create** 都不勾选，保留记录 ID 和表之间的关联。[HeidiSQL 导出说明](https://www.heidisql.com/help.php?place=btnHelpSQLExport)
2. 打开 Docker MySQL 的 `3307` 会话，选中 `lab_agent`，通过 **File → Run SQL file** 执行该文件。导入后核对 `users`、`reservation` 和 `chat_messages` 等表的行数，登录验证旧账号和预约记录。SQL 文件包含业务数据和密码哈希，应保存在 Git 仓库之外。
3. 如果旧项目使用 `backend/uploads/` 保存图片，先核对 Docker 上传卷是否为空，并备份目标卷里已有的文件。目标为空时，可在仓库根目录执行下面这条命令。数据库和图片文件对应的是两份数据，只导入 SQL 不会带上图片。

   ```powershell
   docker compose cp ./backend/uploads/. backend:/app/uploads/
   ```

启动后刷新前端页面，检查用户头像、实验室和设备图片。已有上传文件时，先逐个处理同名冲突，避免复制命令覆盖目标文件。

## 验收和排错

| 现象 | 检查方式 |
| --- | --- |
| 网页打不开 | 先访问 `http://127.0.0.1:8080`，再用 `docker compose ps` 检查 `frontend`。`5173` 由本地 Vite 开发服务器提供。 |
| 页面打开但接口返回 502 | 查看 `docker compose logs --tail 100 backend frontend`，确认 FastAPI 已完成启动、MySQL 健康。 |
| 登录提示账号不存在 | 检查当前连接的是 Docker MySQL 的 `3307`，确认是否已注册账号或导入旧库。 |
| 头像或资源图片 404 | 检查对应文件是否在后端的 `/app/uploads` 挂载卷中。 |
| 聊天请求报错 | 确认 Windows 模型网关正在运行，检查 Compose 里的 `LLM_BASE_URL` 和 `backend/.env` 的模型、密钥，再查后端日志。 |
| 问知识库时报错 | 检查模型下载和预热日志。`/docs` 可访问后仍需实际查询一次，验证检索和回复。 |

启动后可以用同一个账号查看预约、刷新登录页、打开头像或设备图片，再问一次知识库规则。观察回答是否流式显示，以及刷新页面后聊天记录是否仍在。业务层的更多检查见[常见问题与手动验证](TROUBLESHOOTING.md)。
