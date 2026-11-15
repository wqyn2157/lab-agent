# Lab Agent · 智能实验室预约系统

基于 Vue、FastAPI 和 LangGraph 的实验室预约应用。学生浏览实验室与设备、提交预约，管理员负责资源管理和预约审核；AI 助手通过工具查询业务数据、检索本地规则，并在对话中协助提交预约。

项目目前用于学习与本地演示，尚未提供线上演示地址、默认账号或性能指标。

## 已实现功能

- 用户注册、登录、JWT 鉴权、个人信息和密码修改。
- 管理员管理用户、实验室和设备，审核预约。
- 学生提交实验室或设备预约、查看自己的记录、取消待审核预约。
- 校验开放时间、设备归属和同一资源的预约时间冲突。
- AI 工具查询开放实验室、设备、预约记录及当前日期，协助创建预约。
- MySQL 保存用户所属会话及聊天文本，支持新建、切换、分页和删除；模型上下文由后端读取最近 20 条消息。
- 检索本地 Markdown 知识库，在检索前同步资料的新增、修改和删除。
- 使用 SSE 展示模型文本、工具调用步骤和结果预览。

AI 提交前的确认目前由系统提示词约束；角色、资源和时间校验在后端业务函数中执行。服务端确认状态与幂等机制尚待实现。

## 技术栈

| 层 | 使用技术 |
| --- | --- |
| 前端 | Vue 3、Vue Router、Vite、Element Plus、Axios、Fetch |
| 后端 | Python、FastAPI、SQLAlchemy、PyMySQL、Pydantic Settings |
| 认证 | PyJWT、bcrypt |
| Agent | LangGraph、LangChain OpenAI 集成、工具调用 |
| 知识库 | Chroma、Sentence Transformers、`BAAI/bge-small-zh-v1.5` |
| 展示 | SSE、Marked、DOMPurify |

后端依赖见 [requirements.txt](backend/requirements.txt)，前端依赖及锁定结果见 [package.json](frontend/package.json) 和 [package-lock.json](frontend/package-lock.json)。

## 项目结构

```text
lab-agent/
├── README.md
├── .gitignore
├── docs/
│   ├── ARCHITECTURE.md
│   ├── RAG.md
│   └── TROUBLESHOOTING.md
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── app/
│   │   ├── api/           # HTTP 接口
│   │   ├── services/      # 业务、Agent 和检索逻辑
│   │   ├── models/        # SQLAlchemy 模型
│   │   ├── schemas/       # 请求与响应结构
│   │   └── dependencies/  # 登录和管理员权限校验
│   └── data/kb/           # 纳入版本管理的知识资料
└── frontend/
    ├── .env.example
    └── src/
        ├── api/
        ├── components/
        ├── layouts/
        ├── router/
        ├── utils/
        └── views/
```

运行时生成的 `backend/data/chroma/`、`backend/uploads/` 以及本地环境配置不随仓库提交。

## 本地运行

以下命令使用 Windows PowerShell，均注明执行位置。首次克隆时按示例创建环境文件；已有环境文件时保留原文件，核对配置项即可。

### 1. 准备环境和数据库

- Python 3.12：当前开发环境使用此版本。
- Node.js：要求 `^22.18.0 || >=24.12.0`，本地曾使用 Node.js 24.14.0。
- MySQL 8.x 和可用的数据库连接账号。
- 支持工具调用、Chat Completions 兼容接口及流式输出的大模型服务。
- 首次使用嵌入模型时，需要能够获取 `BAAI/bge-small-zh-v1.5` 模型文件，或提前准备本地缓存。

使用有管理权限的 MySQL 账号连接数据库，在 MySQL 客户端执行初始化示例。将示例密码替换为自己的密码；使用已有账号时，只需创建数据库并配置该账号的权限。

```sql
CREATE DATABASE IF NOT EXISTS lab_agent
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER 'lab_user'@'127.0.0.1'
    IDENTIFIED BY 'CHANGE_ME_DB_PASSWORD';
GRANT ALL PRIVILEGES ON lab_agent.* TO 'lab_user'@'127.0.0.1';
```

应用启动时通过 `Base.metadata.create_all()` 创建缺失的表，数据库必须先存在，账号需要具有该库的建表、查询和写入权限。当前没有数据库迁移脚本；`create_all()` 不会自动升级已有表结构。

### 2. 配置并启动后端

从仓库根目录执行：

```powershell
Set-Location backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `backend/.env`：

| 变量 | 含义 |
| --- | --- |
| `Database_URL` | MySQL 连接地址；账号、密码和库名与本机配置一致 |
| `JWT_SECRET_KEY` | 自己生成的随机密钥 |
| `JWT_EXPIRE_HOURS` | 登录凭证有效小时数 |
| `JWT_ALGORITHM` | 默认 `HS256` |
| `LLM_API_KEY` | 模型服务密钥，仅放在后端 |
| `LLM_MODEL` | 服务支持的工具调用模型名称 |
| `LLM_BASE_URL` | API 根地址，路径按服务商要求填写 |

数据库密码包含 `@`、`:`、`/` 等字符时，需要在连接 URL 中进行百分号编码。在本机生成 JWT 密钥后填入配置：

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

仍在 `backend/` 目录中启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- 根接口：<http://127.0.0.1:8000/>
- Swagger 接口说明：<http://127.0.0.1:8000/docs>
- ReDoc：<http://127.0.0.1:8000/redoc>

启动时会预热知识库。首次加载模型可能耗时较长；预热失败会打印异常，但后端仍会继续启动，因此还需查看日志并实际验证知识库查询。

### 3. 配置并启动前端

新开终端，从仓库根目录执行：

```powershell
Set-Location frontend
Copy-Item .env.example .env.development
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

访问 <http://127.0.0.1:5173>。示例配置将 API 请求发送到 `http://127.0.0.1:8000`；Vite 将 `/uploads` 转发到后端，供头像和资源图片使用。

当前 CORS 允许 `http://localhost:5173` 和 `http://127.0.0.1:5173`。修改前端端口或域名时，需要同步修改后端允许的源。

### 4. 初始化学生和管理员账号

仓库没有预置账号，也不包含本地用户数据库或上传图片。

1. 在注册页面创建账号，注册接口默认创建 `student` 角色。
2. 若需初始化首个管理员，在自己的开发数据库执行：

   ```sql
   USE lab_agent;
   UPDATE users
   SET role = 'admin'
   WHERE username = 'YOUR_REGISTERED_ADMIN_USERNAME';
   ```

3. 将占位用户名换成刚注册的账号，核对只更新了目标账号，然后退出并重新登录，刷新前端保存的身份信息。
4. 管理员在页面创建实验室和设备；另注册学生账号测试预约。数据库中没有默认实验室和设备数据。

密码应通过注册或用户管理接口生成 bcrypt 哈希，不要将明文密码直接写入 `users.password`。

## 演示流程

1. 管理员创建开放的实验室，设置开放时间，并添加状态正常的设备。
2. 学生在页面提交未来日期的预约，检查状态为“待审核”。
3. 管理员审核，学生查看结果。
4. 在 AI 助手中询问“有哪些开放的实验室？”“查询我的预约记录”，查看工具步骤和真实结果。
5. 提供具体资源、日期和时段，核对 AI 生成的确认卡片，点击确认后在预约列表核对。
6. 询问知识库规则；修改对应 Markdown 并保存，再次查询，检查工具预览是否使用新内容。
7. 刷新聊天页面或重新登录同一账号，选择旧会话继续聊天。历史会话目前只恢复文字，不恢复预约确认卡片。

AI 相对日期按后端服务器的本地日期解释；日期格式使用 `YYYY-MM-DD`，时段使用 `HH:mm`。

## 接口约定

普通业务接口返回：

```json
{"code": 200, "message": "请求成功", "data": null}
```

受保护接口携带 `Authorization: Bearer <登录返回的token>`。登录接口使用 JSON 用户名和密码；手动调试时先调用 `/api/auth/login` 获取 token，再设置 Bearer 请求头。

业务异常目前可能以 HTTP 200 返回非 200 的业务 `code`，客户端需要同时检查响应体。流式对话使用 `POST /api/ai/chat/stream`，通过 `data: <JSON>` 事件返回，不套用普通响应结构。旧的非流式 `/api/ai/chat` 路由当前未启用。

聊天请求为 `{"conversation_id": null, "message": "你好"}`，`null` 表示新建会话；继续聊天时传会话 ID。旧 `messages` 入参返回 422。首条 `conversation` 事件返回会话 ID，助手完整回复写库成功后发送 `done`。会话列表、消息分页和删除接口见[会话持久化说明](docs/CHAT_HISTORY_PLAN.md)。

## 自动化验证

在 `backend` 目录执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

会话测试使用隔离 SQLite 和模拟模型，不修改项目数据库。覆盖保存、上下文顺序、越权、异常、取消生成及删除回滚。

在 `frontend` 目录执行：

```powershell
npm test
npm run build
```

前端测试覆盖会话恢复、分页、删除确认、流式解析和预约卡片确认/取消。自动化测试不替代真实 MySQL、模型服务和浏览器的联调验收。

## 当前边界与后续计划

- 对话文本已保存到 MySQL；历史卡片恢复、同会话多客户端并发控制尚未实现，也未配置 LangGraph checkpoint。
- 预约确认单已有行锁与幂等保护；不同预约入口通过共享资源锁校验冲突。
- 整间实验室预约与设备预约分开判断；设备 `quantity` 暂未参与预约容量计算。
- 取消接口目前只允许取消本人的待审核记录；知识库中“已通过也可取消”的描述尚待与代码统一。
- 日期和时间使用字符串，依赖统一格式，格式校验仍需完善。
- RAG 当前采用少量短文档整篇入库，尚未实现长文档分块、混合检索和正式评测集。
- 已提供会话与前端回归测试；CI、Docker 部署配置和数据库迁移尚未实现。
- 当前前端配置用于 Vite 本地开发；静态生产部署需要配置 API、`/uploads` 代理和 History 路由回退。

## 更多说明

- [系统架构与权限](docs/ARCHITECTURE.md)
- [RAG 设计与资料更新](docs/RAG.md)
- [常见问题与手动验证](docs/TROUBLESHOOTING.md)
- [前端运行说明](frontend/README.md)
