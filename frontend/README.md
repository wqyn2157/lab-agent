# Lab Agent 前端

基于 Vue 3、Vite 和 Element Plus 的实验室预约界面。完整的数据库、后端和账号初始化步骤见[根目录 README](../README.md)。

## 本地开发

Node.js 版本要求为 `^22.18.0 || >=24.12.0`。在本目录执行：

```powershell
Copy-Item .env.example .env.development
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

已有 `.env.development` 时保留原配置。访问 <http://127.0.0.1:5173>，并确保后端已在 `http://127.0.0.1:8000` 启动。

`VITE_API_BASE_URL` 用于普通 API 和流式聊天请求。`VITE_*` 会进入前端代码，只能存放公开配置；大模型密钥配置在后端。

## 主要目录

| 目录 | 职责 |
| --- | --- |
| `src/api/` | 普通接口和流式聊天请求 |
| `src/components/` | 预约表单等公共界面 |
| `src/layouts/` | 布局与角色菜单 |
| `src/router/` | 页面路由和登录检查 |
| `src/utils/` | Axios、登录信息和用户状态 |
| `src/views/` | 资源管理、预约审核、个人中心、AI 聊天等页面 |

聊天使用 Fetch 读取 SSE 响应，按事件追加正文和工具步骤。Markdown 展示经过 DOMPurify 清理。菜单显示与路由检查服务于页面交互，实际权限由后端校验。

聊天请求只发送会话 ID 和本条输入；会话及历史文本从后端加载。首次进入加载最近会话，支持新建、切换、查看更早消息和确认删除。历史预约卡片暂不恢复；回复异常时先刷新记录核对保存结果，再继续发送。

## 测试

```powershell
npm test
```

测试编译实际 Vue 组件并模拟接口，覆盖会话交互和预约卡片；另外验证真实流式解析函数。测试不调用真实模型，也不代替浏览器布局验收。

## 构建与本地预览

```powershell
npm run build
npm run preview
```

构建输出位于 `dist/`。构建时应提供正确的 `VITE_API_BASE_URL`；本地 `.env.development` 不会自动成为生产模式配置。`vite.config.js` 中的开发代理不等于静态站点的生产代理，发布时需另行配置 API、`/uploads` 和 History 路由回退。

`preview` 仅用于检查构建产物。其默认端口不在当前后端 CORS 允许列表中，完整联调需相应调整源配置或使用同源代理。
