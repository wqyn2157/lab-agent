import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier, Lock
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.common.exceptions import BusinessException
from app.database import Base
from app.models.chat_message import ChatMessage
from app.models.conversation import Conversation
from app.models.equipment import Equipment
from app.models.lab import Lab
from app.models.reservation import Reservation
from app.models.user import User
from app.services import agent_tools, conversation_service


class AgentToolSessionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="lab-agent-tools-")
        self.addCleanup(temporary.cleanup)
        self.engine = create_engine(
            "sqlite:///" + (Path(temporary.name) / "fixture.db").as_posix(),
            connect_args={"check_same_thread": False},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, autoflush=False)
        with self.factory() as db:
            owner = User(username="fixture-owner", password="fixture", name="Owner", role="student", status=1)
            other = User(username="fixture-other", password="fixture", name="Other", role="student", status=1)
            disabled = User(username="fixture-disabled", password="fixture", name="Disabled", role="student", status=0)
            lab = Lab(name="Fixture lab", status=1, capacity=5, open_time="08:00", close_time="20:00")
            db.add_all([owner, other, disabled, lab])
            db.flush()
            self.owner_id, self.other_id, self.disabled_id, self.lab_id = owner.id, other.id, disabled.id, lab.id
            db.add(Equipment(lab_id=lab.id, name="Fixture equipment", quantity=1, status=1))
            conversation = Conversation(user_id=owner.id, title="Fixture conversation")
            db.add(conversation)
            for user, remark in [(owner, "owner"), (other, "other")]:
                db.add(Reservation(user_id=user.id, lab_id=lab.id, equipment_id=None, date="2099-01-01", start_time="09:00", end_time="10:00", remark=remark, status=0))
            db.flush()
            self.conversation_id = conversation.id
            db.commit()
        self.enterContext(patch.object(agent_tools, "SessionLocal", self.factory))
        self.enterContext(patch.object(agent_tools.traceback, "print_exc"))

    def test_query_failure_does_not_break_reply_save_or_next_invocation(self):
        specs = [
            ("list_open_labs", agent_tools.lab_service, "get_lab_page_list", {}, "labs"),
            ("list_lab_equipments", agent_tools.equipment_service, "get_equipment_page_list", {"lab_id": self.lab_id}, "equipments"),
            ("get_reservation_page_list", agent_tools.reservation_service, "get_reservation_page_list", {}, "reservations"),
        ]
        for tool_name, service, method, arguments, result_key in specs:
            with self.subTest(tool=tool_name), self.factory() as stream_db:
                user = stream_db.get(User, self.owner_id)
                tools = {tool.name: tool for tool in agent_tools.build_tools(stream_db, user)}
                actual_query = getattr(service, method)
                used_sessions = []

                def fail_once(db, *args, **kwargs):
                    used_sessions.append(db)
                    if len(used_sessions) == 1:
                        db.connection().invalidate()
                        raise OperationalError("SELECT fixture", {}, RuntimeError("simulated connection loss"), connection_invalidated=True)
                    return actual_query(db, *args, **kwargs)

                with patch.object(service, method, side_effect=fail_once):
                    failed = json.loads(tools[tool_name].invoke(arguments))
                    self.assertFalse(failed["ok"])
                    self.assertEqual(stream_db.execute(text("SELECT 1")).scalar_one(), 1)
                    message_id = conversation_service.save_assistant_message(
                        stream_db, user, self.conversation_id, "Tool failure reported honestly"
                    )
                    self.assertEqual(stream_db.get(ChatMessage, message_id).role, "assistant")
                    retried = json.loads(tools[tool_name].invoke(arguments))
                    self.assertEqual(retried["total"], 1)
                    self.assertEqual(len(retried[result_key]), 1)
                self.assertTrue(all(db is not stream_db for db in used_sessions))
                self.assertIsNot(used_sessions[0], used_sessions[1])
                self.assertTrue(all(not db.in_transaction() for db in used_sessions))

    def test_equipment_global_scope_distinguishes_records_from_quantity(self):
        with self.factory() as db:
            closed = Lab(name="Closed fixture lab", status=0, capacity=5, open_time="08:00", close_time="20:00")
            db.add(closed)
            db.flush()
            closed_id = closed.id
            db.add_all([
                Equipment(lab_id=self.lab_id, name="Fixture centrifuge", quantity=2, status=1),
                Equipment(lab_id=closed_id, name="Fixture centrifuge", quantity=3, status=0),
            ])
            db.commit()
        with self.factory() as stream_db:
            tool = next(tool for tool in agent_tools.build_tools(stream_db, stream_db.get(User, self.owner_id)) if tool.name == "list_lab_equipments")
            result = json.loads(tool.invoke({"keywords": "  centrifuge  "}))
            scoped = json.loads(tool.invoke({"keywords": "centrifuge", "lab_id": self.lab_id}))
            empty = json.loads(tool.invoke({"keywords": "absent equipment"}))
        self.assertEqual(result["scope"], "全系统设备登记")
        self.assertIsNone(result["lab_id"])
        self.assertEqual(result["keywords"], "centrifuge")
        self.assertEqual((result["total"], result["returned_count"], result["returned_quantity"], result["has_more"]), (2, 2, 5, False))
        self.assertEqual({row["lab_id"] for row in result["equipments"]}, {self.lab_id, closed_id})
        self.assertIn("匹配 2 条设备登记", result["summary"])
        self.assertIn("登记数量合计 5 台", result["summary"])
        self.assertIn("不代表指定时段可预约数量", result["summary"])
        self.assertEqual(scoped["scope"], f"实验室 ID {self.lab_id} 的设备登记")
        self.assertEqual((scoped["total"], scoped["returned_count"], scoped["returned_quantity"]), (1, 1, 2))
        self.assertEqual((empty["total"], empty["returned_count"], empty["returned_quantity"], empty["has_more"]), (0, 0, 0, False))

    def test_equipment_paginated_quantity_only_counts_returned_records(self):
        with self.factory() as db:
            for i in range(12):
                db.add(Equipment(lab_id=self.lab_id, name=f"Fixture centrifuge {i}", quantity=i + 1, status=1))
            db.commit()
        with self.factory() as stream_db:
            tool = next(tool for tool in agent_tools.build_tools(stream_db, stream_db.get(User, self.owner_id)) if tool.name == "list_lab_equipments")
            result = json.loads(tool.invoke({"keywords": "centrifuge"}))
        self.assertEqual((result["total"], result["returned_count"], result["has_more"]), (12, 10, True))
        self.assertEqual(result["returned_quantity"], sum(row["quantity"] for row in result["equipments"]))
        self.assertEqual(result["returned_quantity"], sum(range(3, 13)))
        self.assertNotEqual(result["returned_quantity"], sum(range(1, 13)))
        self.assertIn("不能当作全部库存", result["summary"])

    def test_equipment_invalid_lab_id_does_not_fall_back_to_global_query(self):
        with self.factory() as stream_db, patch.object(agent_tools.equipment_service, "get_equipment_page_list") as query:
            tool = next(tool for tool in agent_tools.build_tools(stream_db, stream_db.get(User, self.owner_id)) if tool.name == "list_lab_equipments")
            for lab_id in [0, -1]:
                with self.subTest(lab_id=lab_id):
                    result = json.loads(tool.invoke({"lab_id": lab_id}))
                    self.assertFalse(result["ok"])
            query.assert_not_called()

    def test_parallel_equipment_calls_have_separate_sessions(self):
        barrier = Barrier(2, timeout=5)
        lock = Lock()
        used_sessions = []
        actual_query = agent_tools.equipment_service.get_equipment_page_list

        def overlapping_query(db, *args, **kwargs):
            db.connection()
            with lock:
                used_sessions.append(db)
            barrier.wait()
            return actual_query(db, *args, **kwargs)

        with self.factory() as stream_db:
            tools = {tool.name: tool for tool in agent_tools.build_tools(stream_db, stream_db.get(User, self.owner_id))}
            with patch.object(agent_tools.equipment_service, "get_equipment_page_list", side_effect=overlapping_query), ThreadPoolExecutor(max_workers=2) as executor:
                pending = [executor.submit(tools["list_lab_equipments"].invoke, {"lab_id": self.lab_id}) for _ in range(2)]
                results = [json.loads(future.result(timeout=10)) for future in pending]
            self.assertTrue(all(result["total"] == 1 for result in results))
            self.assertIsNot(used_sessions[0], used_sessions[1])
            self.assertTrue(all(db is not stream_db for db in used_sessions))

    def test_reservation_query_reloads_role_and_preserves_ownership(self):
        with self.factory() as stream_db:
            user = stream_db.get(User, self.owner_id)
            user.role = "admin"  # Only the stale in-memory object claims this role.
            tools = {tool.name: tool for tool in agent_tools.build_tools(stream_db, user)}
            result = json.loads(tools["get_reservation_page_list"].invoke({"user_id": self.other_id}))
            self.assertEqual(result["total"], 1)
            self.assertEqual([row["remark"] for row in result["reservations"]], ["owner"])

    def test_reservation_query_exposes_creation_time_and_record_id(self):
        with self.factory() as db:
            reservation = db.query(Reservation).filter(Reservation.user_id == self.owner_id).one()
            reservation.create_time = datetime(2026, 11, 16, 23, 55)
            reservation_id = reservation.id
            db.commit()
        with self.factory() as stream_db:
            user = stream_db.get(User, self.owner_id)
            tools = {tool.name: tool for tool in agent_tools.build_tools(stream_db, user)}
            result = json.loads(tools["get_reservation_page_list"].invoke({}))
        row = result["reservations"][0]
        self.assertEqual(row["id"], reservation_id)
        self.assertEqual(datetime.fromisoformat(row["create_time"]), datetime(2026, 11, 16, 23, 55))
        self.assertEqual(row["date"], "2099-01-01")

    def test_disabled_or_missing_user_cannot_query_reservations(self):
        for user_id in [self.disabled_id, 999999]:
            with self.subTest(user_id=user_id), self.factory() as stream_db:
                stale_user = User(id=user_id, role="student", status=1)
                tools = {tool.name: tool for tool in agent_tools.build_tools(stream_db, stale_user)}
                with patch.object(agent_tools.reservation_service, "get_reservation_page_list") as query:
                    result = json.loads(tools["get_reservation_page_list"].invoke({}))
                self.assertFalse(result["ok"])
                query.assert_not_called()

    def test_created_date_filters_before_count_and_pagination(self):
        with self.factory() as db:
            original = db.query(Reservation).filter(Reservation.user_id == self.owner_id).one()
            original.create_time = datetime(2026, 11, 16)
            other = db.query(Reservation).filter(Reservation.user_id == self.other_id).one()
            other.create_time = datetime(2026, 11, 16, 12)
            for created, remark, status in [
                (datetime(2026, 11, 15, 23, 59, 59, 999999), "before", 0),
                (datetime(2026, 11, 16, 23, 59, 59, 999999), "last-microsecond", 1),
                (datetime(2026, 11, 17), "next-midnight", 0),
            ] + [(datetime(2026, 11, 17, 12, minute), "newer", 0) for minute in range(12)]:
                db.add(Reservation(user_id=self.owner_id, lab_id=self.lab_id, equipment_id=None, date="2099-01-01", start_time="09:00", end_time="10:00", remark=remark, status=status, create_time=created))
            db.commit()
            user = db.get(User, self.owner_id)
            unfiltered = agent_tools.reservation_service.get_reservation_page_list(db, user, 1, 10, None, None)
            self.assertTrue(all(row.create_time.date().isoformat() == "2026-11-17" for row in unfiltered.list))
            first = agent_tools.reservation_service.get_reservation_page_list(db, user, 1, 1, None, self.other_id, created_date="2026-11-16")
            second = agent_tools.reservation_service.get_reservation_page_list(db, user, 2, 1, None, None, created_date="2026-11-16")
            self.assertEqual(first.total, 2)
            self.assertEqual(second.total, 2)
            self.assertEqual([first.list[0].remark, second.list[0].remark], ["last-microsecond", "owner"])
            self.assertTrue(all(row.date == "2099-01-01" for row in first.list + second.list))
            approved = agent_tools.reservation_service.get_reservation_page_list(db, user, 1, 10, 1, None, created_date="2026-11-16")
            self.assertEqual(approved.total, 1)
            self.assertEqual(approved.list[0].remark, "last-microsecond")
            empty = agent_tools.reservation_service.get_reservation_page_list(db, user, 1, 10, None, None, created_date="2026-11-14")
            self.assertEqual((empty.total, empty.list), (0, []))

    def test_invalid_created_date_is_rejected(self):
        with self.factory() as db:
            user = db.get(User, self.owner_id)
            for value in ["", "yesterday", "2026-02-30", "2026/11/16"]:
                with self.subTest(created_date=value), self.assertRaises(BusinessException) as caught:
                    agent_tools.reservation_service.get_reservation_page_list(db, user, 1, 10, None, None, created_date=value)
                self.assertEqual(caught.exception.code, 422)

    def test_tool_created_date_finds_older_submission_and_preserves_status(self):
        with self.factory() as db:
            old = db.query(Reservation).filter(Reservation.user_id == self.owner_id).one()
            old.create_time = datetime(2026, 11, 16, 23, 55)
            old.status = 3
            old_id = old.id
            for minute in range(12):
                db.add(Reservation(user_id=self.owner_id, lab_id=self.lab_id, equipment_id=None, date="2099-01-01", start_time="09:00", end_time="10:00", remark="newer", status=0, create_time=datetime(2026, 11, 17, 12, minute)))
            db.commit()
        with self.factory() as stream_db:
            tools = {tool.name: tool for tool in agent_tools.build_tools(stream_db, stream_db.get(User, self.owner_id))}
            tool = tools["get_reservation_page_list"]
            self.assertIn("created_date", tool.args)
            unfiltered = json.loads(tool.invoke({}))
            result = json.loads(tool.invoke({"created_date": "2026-11-16"}))
            approved_only = json.loads(tool.invoke({"created_date": "2026-11-16", "status": 1}))
        self.assertEqual((unfiltered["total"], unfiltered["returned_count"], unfiltered["has_more"]), (13, 10, True))
        self.assertIsNone(unfiltered["created_date"])
        self.assertEqual(result["created_date"], "2026-11-16")
        self.assertIsNone(result["status_filter"])
        self.assertEqual((result["total"], result["returned_count"], result["has_more"]), (1, 1, False))
        self.assertEqual(result["reservations"][0]["id"], old_id)
        self.assertEqual(result["reservations"][0]["status"], 3)
        self.assertEqual(result["reservations"][0]["date"], "2099-01-01")
        self.assertEqual(approved_only["status_filter"], 1)
        self.assertEqual(approved_only["total"], 0)

    def test_tool_created_date_reports_remaining_records(self):
        with self.factory() as db:
            for minute in range(12):
                db.add(Reservation(user_id=self.owner_id, lab_id=self.lab_id, equipment_id=None, date="2099-01-01", start_time="09:00", end_time="10:00", remark="same-submission-day", status=0, create_time=datetime(2026, 11, 16, 12, minute)))
            db.commit()
        with self.factory() as stream_db:
            tool = next(tool for tool in agent_tools.build_tools(stream_db, stream_db.get(User, self.owner_id)) if tool.name == "get_reservation_page_list")
            result = json.loads(tool.invoke({"created_date": "2026-11-16"}))
            empty = json.loads(tool.invoke({"created_date": "2026-11-14"}))
        self.assertGreaterEqual(result["total"], 12)
        self.assertEqual(result["returned_count"], len(result["reservations"]))
        self.assertEqual(result["returned_count"], 10)
        self.assertTrue(result["has_more"])
        self.assertTrue(all(row["create_time"].startswith("2026-11-16T") for row in result["reservations"]))
        self.assertEqual((empty["total"], empty["returned_count"], empty["has_more"], empty["reservations"]), (0, 0, False, []))

    def test_tool_invalid_created_date_returns_error(self):
        with self.factory() as stream_db:
            tool = next(tool for tool in agent_tools.build_tools(stream_db, stream_db.get(User, self.owner_id)) if tool.name == "get_reservation_page_list")
            result = json.loads(tool.invoke({"created_date": "2026-02-30"}))
        self.assertFalse(result["ok"])
        self.assertIn("YYYY-MM-DD", result["error"])


if __name__ == "__main__":
    unittest.main()
