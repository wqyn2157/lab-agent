import asyncio
import contextlib
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import Field

from app.services import agent_service, agent_tools


class RecordingModel(GenericFakeChatModel):
    seen: list = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class AgentRetrievalTests(unittest.TestCase):
    """Exercise the real graph and tools without a model API or project database."""

    def setUp(self):
        self.user = SimpleNamespace(id=7)
        self.search = self.enterContext(patch.object(agent_tools.kb_service, "search", return_value="[规则.md · 片段 1]\n只有学生能预约"))

    def build(self, replies):
        model = RecordingModel(messages=iter(replies))
        client = MagicMock()
        client.bind_tools.return_value = model
        with patch.object(agent_service, "ChatOpenAI", return_value=client):
            graph = agent_service.build_agent(MagicMock(), self.user)
        return graph, model

    def test_retrieves_current_question_before_a_model_that_would_answer_directly(self):
        graph, model = self.build([AIMessage(content="fixture answer")])
        history = [SystemMessage(content="system"), HumanMessage(content="old question"), AIMessage(content="old answer"), HumanMessage(content="current question")]
        result = asyncio.run(graph.ainvoke({"messages": history}))
        self.search.assert_called_once_with("current question")
        self.assertEqual(len(model.seen), 1)
        messages = model.seen[0]
        self.assertIsInstance(messages[-3], AIMessage)
        self.assertEqual(messages[-3].tool_calls[0]["name"], "search_lab_docs")
        self.assertIsInstance(messages[-2], ToolMessage)
        self.assertEqual(messages[-2].name, "search_lab_docs")
        self.assertEqual(messages[-2].tool_call_id, messages[-3].tool_calls[0]["id"])
        self.assertIn("只有学生", messages[-2].content)
        self.assertIsInstance(messages[-1], SystemMessage)
        self.assertEqual(result["messages"][-1].content, "fixture answer")
        self.assertEqual(len(history), 4)

    def test_each_new_turn_retrieves_latest_question_with_a_new_call_id(self):
        graph, model = self.build([AIMessage(content="first"), AIMessage(content="second")])
        async def run():
            first = await graph.ainvoke({"messages": [HumanMessage(content="question one")]})
            return await graph.ainvoke({"messages": [*first["messages"], HumanMessage(content="question two")]})
        result = asyncio.run(run())
        self.assertEqual([call.args[0] for call in self.search.call_args_list], ["question one", "question two"])
        docs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
        self.assertEqual(len(docs), 2)
        self.assertNotEqual(docs[0].tool_call_id, docs[1].tool_call_id)
        self.assertEqual(len(model.seen), 2)

    def test_database_tool_still_executes_after_automatic_retrieval(self):
        call = {"name": "list_open_labs", "args": {"keywords": "计算机"}, "id": "database-call", "type": "tool_call"}
        graph, model = self.build([AIMessage(content="", tool_calls=[call]), AIMessage(content="database answer")])
        page = SimpleNamespace(total=1, list=[SimpleNamespace(id=11, name="数据库中的实验室", location="A101", capacity=20, open_time="08:00", close_time="20:00")])
        with patch.object(agent_tools, "SessionLocal") as sessions, patch.object(agent_tools.lab_service, "get_lab_page_list", return_value=page) as query:
            result = asyncio.run(graph.ainvoke({"messages": [HumanMessage(content="查询真实计算机实验室")]}))
        self.assertEqual(query.call_args.kwargs["keywords"], "计算机")
        query.assert_called_once()
        sessions.assert_called_once()
        self.assertEqual(len(model.seen), 2)
        self.assertIsInstance(model.seen[-1][-1], ToolMessage)
        self.assertEqual(model.seen[-1][-1].name, "list_open_labs")
        self.assertEqual(json.loads(model.seen[-1][-1].content)["labs"][0]["id"], 11)
        self.assertEqual(result["messages"][-1].content, "database answer")

    def test_missing_or_failed_retrieval_reaches_model_as_an_explicit_result(self):
        for failure in [False, True]:
            with self.subTest(failure=failure):
                self.search.return_value = ""
                self.search.side_effect = RuntimeError("fixture retrieval failed") if failure else None
                graph, model = self.build([AIMessage(content="insufficient evidence")])
                asyncio.run(graph.ainvoke({"messages": [HumanMessage(content="question")]}))
                tool_message = model.seen[0][-2]
                if failure:
                    self.assertFalse(json.loads(tool_message.content)["ok"])
                else:
                    self.assertEqual(tool_message.content, "没有检索到相关的资料")
                self.assertIn("检索失败或资料不足", model.seen[0][-1].content)

    def test_real_graph_stream_emits_retrieval_before_tokens_and_saves_only_answer(self):
        graph, _ = self.build([AIMessage(content="fixture final answer")])
        db = MagicMock()
        async def run():
            return [item async for item in agent_service.stream_agent(db, self.user, 21, [HumanMessage(content="question")])]
        with patch.object(agent_service, "build_agent", return_value=graph), patch.object(agent_service.conversation_service, "save_assistant_message", return_value=31) as save, contextlib.redirect_stdout(io.StringIO()):
            events = asyncio.run(run())
        kinds = [item["type"] for item in events]
        self.assertNotIn("error", kinds)
        self.assertLess(kinds.index("tool_start"), kinds.index("tool_end"))
        self.assertLess(kinds.index("tool_end"), kinds.index("token"))
        self.assertEqual(next(item for item in events if item["type"] == "tool_end")["name"], "search_lab_docs")
        save.assert_called_once_with(db, self.user, 21, "fixture final answer")
        self.assertEqual(events[-1], {"type": "done", "conversation_id": 21, "message_id": 31})


if __name__ == "__main__":
    unittest.main()
