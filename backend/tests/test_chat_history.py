import asyncio
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk, ToolMessage
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import ai as ai_api
from app.common.exceptions import http_exception_hadler
from app.database import Base, get_db
from app.dependencies.auth import get_current_user
from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.models.user import User
from app.services import agent_service, conversation_service


class ChatHistoryTests(unittest.TestCase):
    """Run the actual routes against isolated SQLite, without model API calls."""

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, Conversation.__table__, ChatMessage.__table__],
        )
        self.factory = sessionmaker(bind=self.engine, autoflush=False)
        with self.factory() as db:
            owner = User(username="fixture_a", password="fixture", name="A", role="student", status=1)
            other = User(username="fixture_b", password="fixture", name="B", role="student", status=1)
            db.add_all([owner, other])
            db.flush()
            self.owner_id = owner.id
            private = Conversation(user_id=other.id, title="private")
            db.add(private)
            db.flush()
            self.private_id = private.id
            db.add(ChatMessage(conversation_id=private.id, role="user", content="private message"))
            db.commit()

        self.mode = "success"
        self.inputs = []
        tests = self

        class FakeAgent:
            async def astream_events(self, inputs, **kwargs):
                tests.inputs.append(inputs)
                if tests.mode == "empty":
                    return
                yield {"event": "on_chat_model_stream", "metadata": {"langgraph_node": "agent"}, "data": {"chunk": AIMessageChunk(content="hello ")}}
                if tests.mode == "failure":
                    raise RuntimeError("simulated model failure")
                if tests.mode == "card":
                    yield {"event": "on_tool_end", "name": "prepare_lab_reservation", "data": {"output": ToolMessage(content="draft ready", tool_call_id="fixture", artifact={"ok": True, "draft_id": 42, "confirmation_token": "fixture-secret"})}}
                yield {"event": "on_chat_model_stream", "metadata": {"langgraph_node": "agent"}, "data": {"chunk": AIMessageChunk(content="reply")}}

        self.app = FastAPI()
        self.app.include_router(ai_api.router, prefix="/api")
        self.app.add_exception_handler(HTTPException, http_exception_hadler)

        def override_db():
            with self.factory() as db:
                yield db

        def override_user(db: Session = Depends(get_db)):
            return db.get(User, self.owner_id)

        self.app.dependency_overrides[get_db] = override_db
        self.app.dependency_overrides[get_current_user] = override_user
        self.enterContext(patch.object(ai_api, "SessionLocal", self.factory))
        self.enterContext(patch.object(agent_service, "build_agent", return_value=FakeAgent()))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.client = self.enterContext(TestClient(self.app))
        self.addCleanup(self.engine.dispose)

    def send(self, message, conversation_id=None):
        response = self.client.post("/api/ai/chat/stream", json={"conversation_id": conversation_id, "message": message})
        self.assertEqual(response.status_code, 200)
        return [json.loads(frame[6:]) for frame in response.text.strip().split("\n\n")]

    def messages(self, conversation_id):
        with self.factory() as db:
            return [(m.role, m.content) for m in db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).order_by(ChatMessage.id))]

    def test_new_and_continued_chat_save_exactly_one_complete_reply(self):
        events = self.send(" first ")
        chat_id = events[0]["conversation_id"]
        self.assertEqual(events[0]["type"], "conversation")
        self.assertEqual([e["type"] for e in events], ["conversation", "status", "token", "token", "done"])
        self.assertEqual(self.messages(chat_id), [("user", "first"), ("assistant", "hello reply")])
        self.send("second", chat_id)
        self.assertEqual([m.content for m in self.inputs[-1]["messages"][1:]], ["first", "hello reply", "second"])
        self.assertEqual(len(self.messages(chat_id)), 4)

    def test_foreign_and_missing_conversations_are_http_404(self):
        for chat_id in [self.private_id, 999999]:
            with self.subTest(chat_id=chat_id):
                url = f"/api/ai/conversations/{chat_id}"
                self.assertEqual(self.client.get(url + "/messages").status_code, 404)
                self.assertEqual(self.client.delete(url).status_code, 404)
                response = self.client.post("/api/ai/chat/stream", json={"conversation_id": chat_id, "message": "blocked"})
                self.assertEqual(response.status_code, 404)
                self.assertNotIn("text/event-stream", response.headers.get("content-type", ""))
        self.assertEqual(self.messages(self.private_id), [("user", "private message")])
        self.assertEqual(self.inputs, [])

    def test_bad_inputs_are_rejected_before_creating_any_conversation(self):
        for payload in [{"messages": []}, {"message": "hi", "messages": []}, {"message": "  "}, {"message": "x" * 2001}, {"message": "hi", "conversation_id": 0}]:
            self.assertEqual(self.client.post("/api/ai/chat/stream", json=payload).status_code, 422)
        response = self.client.get("/api/ai/conversations")
        self.assertEqual(response.json()["data"]["total"], 0)

    def test_failures_keep_user_message_without_partial_assistant_or_done(self):
        for mode in ["failure", "empty"]:
            self.mode = mode
            events = self.send(mode)
            self.assertEqual(events[-1]["type"], "error")
            self.assertFalse(any(e["type"] == "done" for e in events))
            self.assertEqual(self.messages(events[0]["conversation_id"]), [("user", mode)])

        self.mode = "success"
        actual_save = conversation_service.save_assistant_message

        def fail_commit(db, user, conversation_id, content):
            with patch.object(db, "commit", side_effect=RuntimeError("simulated commit failure")):
                return actual_save(db, user, conversation_id, content)

        with patch.object(conversation_service, "save_assistant_message", side_effect=fail_commit):
            events = self.send("write failure")
        self.assertEqual(events[-1]["type"], "error")
        self.assertFalse(any(e["type"] == "done" for e in events))
        self.assertEqual(self.messages(events[0]["conversation_id"]), [("user", "write failure")])

    def test_history_is_latest_twenty_in_order_without_duplicate_new_input(self):
        chat_id = self.send("start")[0]["conversation_id"]
        with self.factory() as db:
            user = db.get(User, self.owner_id)
            for i in range(25):
                conversation_service.save_user_message(db, user, chat_id, str(i))
        self.send("latest", chat_id)
        history = self.inputs[-1]["messages"][1:]
        self.assertEqual([m.content for m in history], [str(i) for i in range(6, 25)] + ["latest"])
        self.assertEqual(len(self.messages(chat_id)), 29)

    def test_card_event_is_preserved_but_credential_is_not_stored(self):
        self.mode = "card"
        events = self.send("card")
        self.assertTrue(any(e["type"] == "reservation_draft" for e in events))
        self.assertNotIn("fixture-secret", str(self.messages(events[0]["conversation_id"])))

    def test_delete_is_atomic_and_preserves_other_users_messages(self):
        chat_id = self.send("question")[0]["conversation_id"]
        with self.factory() as db:
            user = db.get(User, self.owner_id)
            with patch.object(db, "commit", side_effect=RuntimeError("simulated commit failure")):
                with self.assertRaises(RuntimeError):
                    conversation_service.delete_conversation(db, user, chat_id)
        self.assertEqual(len(self.messages(chat_id)), 2)
        self.assertEqual(self.client.delete(f"/api/ai/conversations/{chat_id}").status_code, 200)
        self.assertEqual(self.messages(chat_id), [])
        self.assertEqual(self.client.get(f"/api/ai/conversations/{chat_id}/messages").status_code, 404)
        self.assertEqual(self.messages(self.private_id), [("user", "private message")])

    def test_cancelling_generation_does_not_save_partial_reply(self):
        async def run():
            with self.factory() as db:
                user = db.get(User, self.owner_id)
                chat_id = conversation_service.save_user_message(db, user, None, "cancel")
                history = agent_service._build_conversation_history(db, user, chat_id)
                generator = agent_service.stream_agent(db, user, chat_id, history)
                self.assertEqual((await anext(generator))["type"], "status")
                self.assertEqual((await anext(generator))["type"], "token")
                await generator.aclose()
            self.assertEqual(self.messages(chat_id), [("user", "cancel")])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
