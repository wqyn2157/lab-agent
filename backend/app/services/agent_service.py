from importlib import metadata
import traceback
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from sqlalchemy.orm import Session
from app.common.exceptions import BusinessException
from app.config import settings
from app.models.user import User
from app.schemas.ai import ChatRequest
from app.services import agent_tools
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

SYSTEM_PROMPT = """你是智能实验室预约系统的 Agent，回答要简洁、准确。

## 可使用的工具
1. search_lab_docs：查询实验室规则、安全要求、开放时间等知识。
2. list_open_labs：查询数据库中真实开放的实验室。
3. list_lab_equipments：查询实验室设备信息。
4. create_lab_reservation：在用户明确确认后，创建真实预约记录。
5. get_today：获取当前日期，用于今天、明天、后天等日期换算。
6. get_reservation_page_list：查询预约记录及其审核状态。

## 预约记录查询
当用户询问自己的预约记录、预约历史或审核状态时，调用 get_reservation_page_list。

预约状态 status 对应关系：
- 0：待审核
- 1：已通过
- 2：已拒绝
- 3：已取消

向用户展示预约记录时，将数字状态转换为对应中文，不要直接展示状态数字。

普通用户只能查询自己的预约记录。
管理员可以在后端授权范围内查询其他用户的预约记录。
不得自行编造预约记录、状态或用户身份。

## 日期处理
当用户提到今天、明天、后天等相对日期时，先调用 get_today 获取当前日期，再计算具体日期。
不要直接回答“需要确定明天的具体日期”。

## 预约创建规则
提交预约之前，必须向用户复述：
- 实验室 ID 和名称（或设备 ID 和名称）
- 预约日期
- 开始时间
- 结束时间

必须得到用户明确确认后，才能调用 create_lab_reservation。
用户没有明确表示“确认”“确认预约”“就这样预约”等同意意图时，不得创建预约。

如果缺少 lab_id，先调用 list_open_labs 查询。
如果缺少 equipment_id，先调用 list_lab_equipments 查询。
不得编造实验室 ID 或设备 ID。

预约成功后的状态为“待审核”，必须经管理员审核通过后才能使用。

## 其他规则
1. 不得编造数据库中不存在的实验室、设备和预约记录。
2. 查询开放时间、实验室规则时，优先使用 search_lab_docs。
3. 查询真实实验室、设备或预约记录时，优先调用对应数据库工具。
4. 工具执行失败时，如实说明，不得假装操作成功。
5. 回答保持简洁，使用清晰、自然的中文。
"""
TOOL_LABELS = {
    "search_lab_docs": "检索实验室知识库",
    "list_open_labs": "查询开放的实验室",
    "list_lab_equipments": "查询实验室设备",
    "create_lab_reservation": "创建预约单",
    "get_today": "获取今天的日期",
    "get_reservation_page_list": "查询预约记录",
}


def _build_history(data: ChatRequest) -> list:
    """前端的消息 转成LangChain的消息对象"""
    history = []
    for message in data.messages:
        if message.role == "user" and message.content.strip():
            history.append(HumanMessage(content=message.content.strip()))
        elif message.role == "assistant" and message.content.strip():
            history.append(AIMessage(content=message.content.strip()))
    if not history:
        raise BusinessException(message="请输入您的对话内容")
    return history


def _tool_output_preview(output: Any, limit: int = 200):
    """把工具输出的结果收成短文本预览，避免整段的json污染了输出的区域"""
    if isinstance(output, ToolMessage):
        output = output.content
    text = output if isinstance(output, str) else str(output)
    return text if len(text) <= limit else text[:limit] + "..."


def _chunk_text(chunk: Any):
    """
    从模型的流式输出中 拿到纯文本
    chunk.content 可能是 str [{type,text},...] 等类型 这个需要统一处理成字符串
    """
    if chunk is None:
        return ""
    # chunk 如果是 AIMessage 类型的，则可以取出 content
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text") or "")
        return "".join(parts)
    return str(content) if content is not None else ""


async def stream_agent(db: Session, current_user: User, data: ChatRequest):
    """
    生成器： 边跑 agent 边 yield 事件 提供 SSE 输出给前端
    事件的类型：status | tool_start | tool_end | token | done | error
    """
    try:
        history = _build_history(data)
        agent = build_agent(db, current_user)
        inputs = {"messages": [SystemMessage(content=SYSTEM_PROMPT), *history]}

        yield {"type": "status", "message": "正在思考..."}

        async for event in agent.astream_events(
            inputs, version="v2", config={"recursion_limit": 10}
        ):
            print("event:", event.get("event"), event.get("name"))
            kind = event.get("event")
            if kind == "on_tool_start":
                name = event.get("name") or ""
                yield {
                    "type": "tool_start",
                    "name": name,
                    "label": TOOL_LABELS.get(name, name),
                }
            elif kind == "on_tool_end":
                name = event.get("name") or ""
                yield {
                    "type": "tool_end",
                    "name": name,
                    "label": TOOL_LABELS.get(name, name),
                    "preview": _tool_output_preview(
                        (event.get("data") or {}).get("output")
                    ),
                }
            elif kind == "on_chat_model_stream":
                metadata = event.get("metadata") or {}
                if metadata.get("langgraph_node") not in (None, "agent"):
                    continue
                text = _chunk_text((event.get("data") or {}).get("chunk"))
                yield {"type": "token", "content": text}
        yield {"type": "done"}
    except BusinessException as e:
        yield {"type": "error", "message": e.message}
    except Exception as e:
        traceback.print_exc()
        yield {"type": "error", "message": "大模型调用失败，请稍候重试"}


def build_agent(db: Session, current_user: User):
    tools = agent_tools.build_tools(db, current_user)
    llm = ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=0,
        streaming=True,  # 开始流式输出  stream_event 接收逐字输出的token
    ).bind_tools(tools)

    async def agent_node(state: MessagesState):
        """langGraph 执行的工作流的节点"""
        response = await llm.ainvoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)  # 调用大模型的节点
    graph.add_node("tools", ToolNode(tools))  # tool call的节点
    graph.add_edge(START, "agent")  # 流程的起点
    graph.add_conditional_edges(
        "agent", tools_condition
    )  # 看有无tool_call，有就继续call  没有就END输出
    graph.add_edge("tools", "agent")  # 让agent看tool调用的结果
    return graph.compile()


# def run_agent(db: Session, current_user: User, data: ChatRequest):
#     """大模型对话"""
#     if not data.messages:
#         raise BusinessException(message="对话内容为空")
#     history = []
#     for message in data.messages:
#         if message.role == "user" and message.content.strip():
#             history.append(HumanMessage(content=message.content.strip()))
#         elif message.role == "assistant" and message.content.strip():
#             history.append(AIMessage(content=message.content.strip()))
#     if not history:
#         raise BusinessException(message="请输入您要对话的内容")

#     agent = build_agent(db, current_user)
#     try:
#         result = agent.invoke(
#             {"messages": [SystemMessage(content=SYSTEM_PROMPT), *history]},
#             config={"recursion_limit": 10},
#         )  # 设置对话循环的上限是10轮
#     except BusinessException:
#         raise
#     except Exception as e:
#         print("大模型调用失败，真实错误：", repr(e))
#         raise BusinessException(message="大模型调用失败，请稍候重试")

#     messages = result.get("messages") or []
#     if not messages:
#         raise BusinessException(message="大模型没有返回内容")
#     for message in reversed(messages):
#         if isinstance(message, AIMessage) and message.content.strip():
#             content = message.content.strip()
#             if isinstance(content, list):
#                 content = "".join(
#                     part.get("text", "") if isinstance(part, dict) else str(part)
#                     for part in content
#                 )
#             if str(content).strip():
#                 return str(content).strip()
