# 常见问题与手动验证

[返回项目首页](../README.md)

本文记录当前实现相关的故障现象、处理位置和手动检查方法。Docker 版的端口、日志和数据卷问题见[部署指南](DOCKER.md#验收和排错)。会话及前端自动化测试的运行命令见根目录 README。

## 启动和环境配置

| 现象 | 优先检查 |
| --- | --- |
| Pydantic 提示缺少配置字段 | 是否创建 `backend/.env`，变量名是否与 `.env.example` 一致 |
| 数据库提示库不存在或连接拒绝 | MySQL 是否运行、数据库是否已创建、地址端口和账号权限是否正确 |
| 第一次启动长时间等待 | 嵌入模型是否正在下载或加载；检查模型缓存、网络和后端日志 |
| 后端已启动但知识库报错 | 启动会捕获预热异常；回看异常堆栈，单独验证一次检索 |
| 普通 API 正常，聊天请求地址异常 | 检查 `frontend/.env.development` 的 `VITE_API_BASE_URL`，修改配置后重启 Vite |
| 浏览器提示 CORS | 确认前端源为当前允许的 `localhost:5173` 或 `127.0.0.1:5173` |
| 构建预览时无法请求 API 或显示图片 | 生产模式环境变量、CORS、`/uploads` 代理与开发模式不同，见前端 README |

## 数据库事务失效：PendingRollbackError

现象：工具查询抛出 `Can't reconnect until invalid transaction is rolled back`，再次调用工具仍失败。

这说明当前事务需要先回滚。`except` 只捕获 Python 异常，不会自动恢复 SQLAlchemy Session；`rollback()` 用于结束失败事务，并会撤销该会话尚未提交的修改。

当前预约查询工具在异常分支执行：

```python
traceback.print_exc()
db.rollback()
```

验证时保留第一次数据库异常及其前后的工具调用日志。回滚后查询恢复说明事务恢复措施有效，但不能据此认定最初的断连或事务错误已经解决。其他工具的事务边界仍需结合调用链统一设计。

## 预约时间被错误判定为冲突

修复位置：`backend/app/services/reservation_service.py` 的 `create_reservation()`。

过去只判断“已有开始 < 新结束”，会把已经结束的预约算作冲突；另外 `query.filter(...)` 未接回返回值，设备筛选条件没有生效。当前同时检查完整时间区间，并使用 `query = query.filter(...)`。

以某设备已存在 `09:00—10:00` 的有效预约为例，在未来同一天、实验室开放时段内检查：

| 新请求 | 预期 |
| --- | --- |
| 同设备 `09:30—10:30` | 冲突 |
| 同设备 `08:00—11:00` | 冲突，新时段包含旧时段 |
| 同设备 `10:00—11:00` | 允许，首尾相接 |
| 同设备 `11:00—12:00` | 允许 |
| 不同设备 `09:00—10:00` | 当前规则允许 |
| 开始与结束相同 | 拒绝 |
| 设备属于另一实验室 | 拒绝 |
| 管理员提交预约 | 业务错误，只有学生可以提交 |

上述用例只验证时间区间规则。并发提交需要另行验证服务端加锁及幂等行为。

## 知识库预热报 TypeError 或方法不存在

修复位置：`backend/app/services/kb_service.py`。

- `col.count` 是方法对象，`col.count()` 才返回记录数量。判断非空或空库时都需调用方法。
- 查询方法是 `col.query()`，不是 `col.qurey()`。

重启后检查预热异常是否消失，再执行一次知识库查询。根接口正常响应不能证明预热已成功。

## 修改资料后仍回答旧规则

旧实现只在 Collection 为空时导入资料，并在命中内存缓存后提前返回。当前 `get_collection()` 每次比较文件与已存原文，使用 `upsert()` 更新，删除本地已移除或清空的文档记录。

验证顺序：

1. 修改一条知识库规则，保存。Docker 模式下运行 `docker compose up -d --build backend`，使容器读到新资料。
2. 发起会调用知识库的新问题，检查工具输出是否包含新文本。
3. 新文本已召回但最终回答仍旧：点击“新建会话”排除旧上下文影响后再试；刷新页面会恢复历史，不会清空聊天记录。
4. 工具没有被调用：检查提示词、工具说明及模型返回的调用轨迹。
5. 同步或检索报错：检查知识库路径、文件编码、嵌入模型与 Chroma 日志。

资料更新与后端权限是两个机制。禁止某角色操作时，应同时在共享业务函数中校验权限，而非只修改知识库。

## 工具名称显示英文或工具预览不展开

修复位置为 `agent_tools.py`、`agent_service.py` 和 `frontend/src/views/AIChat.vue`。

工具定义与注册列表均使用 `search_lab_docs`，需与 `TOOL_LABELS` 和提示词一致。过去的 `seach_lab_docs` 拼写会导致标签匹配失败，页面退回显示原工具名。

后端事件应使用 `"name": name` 传递变量，而非固定字符串 `"name"`。前端预览应使用模板字符串：

```javascript
assistant.steps.push(`输出结果：${evt.preview}`)
```

如果使用普通单引号，`${evt.preview}` 会作为字面文本显示。

## 流式结束或响应类型不正确

后端 `api/ai.py` 使用 `media_type="text/event-stream"` 和 `Cache-Control: no-cache`。正常完成后，`agent_service.py` 发送 `{"type": "done"}`，前端监听同名事件。

验证时在浏览器开发者工具中查看 `/api/ai/chat/stream` 的响应类型与事件。需要时可在前端 `done` 分支临时打印日志，验证后移除。仅看到页面停止加载不能证明收到了 `done`，因为 `finally` 也会清理界面状态。

## 查询工具报错后，回复保存出现 PendingRollbackError

`Can't reconnect until invalid transaction is rolled back` 表示连接已经失效，但 Session 中仍有尚未结束的事务。应查看它之前最早的数据库异常，不能仅凭这条后续错误确定断线原因。

旧查询工具共用流式回复的 `db`。某个工具遇到连接失效并捕获异常后，如果继续复用该会话，工具重试或最终保存助手回复就可能再次报错。设备查询失败污染回复保存的链路已在隔离 SQLite 中复现；这不等于已查明现场第一次连接失效的原因。

当前查询实验室、查询设备、查询预约记录及生成确认单的数据库操作分别在 `with SessionLocal() as tool_db:` 内完成，结果序列化后退出会话。查询异常记录 traceback 并返回明确失败；不要将错误结果当作空列表或真实库存。预约记录工具在自己的会话中重新加载用户并沿用业务服务的归属校验。

`tests/test_agent_tool_sessions.py` 使用临时 SQLite 文件验证三个查询工具的连接失效、后续重试、回复保存、并行调用，以及预约记录的身份和归属校验。不调用模型、不写项目数据库。

前端曾提示保存结果不确定时，先刷新记录核对，再新建会话重试。完整验收既要确认业务工具查询成功，也要确认没有流式保存错误、刷新后仍能看到助手回复。若仍失败，保留新一次查询开始后的首个数据库异常。

## 首次提交到 GitHub 前

根目录 `.gitignore` 已排除真实环境文件、依赖、生成的向量库、现有上传文件和日志，保留 `.env.example`、锁文件以及 `backend/data/kb/` 资料。

在仓库根目录初始化 Git 后检查：

```powershell
git status --short --untracked-files=all
git check-ignore .env backend/.env frontend/.env.development backend/data/chroma/chroma.sqlite3
```

阶段性添加后，再核对 `git diff --cached --stat` 与暂存文件内容。忽略规则不会自动移除已经被跟踪的文件，也不会清除已有提交中的数据；当前新仓库应从首次提交就保留这条边界。
