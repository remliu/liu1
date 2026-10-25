# -*- coding: utf-8 -*-
"""API tests for WebScan SOP. Run: python -m unittest discover -s tests -v"""

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import app as webapp


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = Path(__file__).resolve().parent / "test_runtime.db"
        if cls.db_path.exists():
            cls.db_path.unlink()
        webapp.DB_PATH = cls.db_path
        webapp.SEED_DEMO = True
        webapp.init_db()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), webapp.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        try:
            cls.db_path.unlink()
        except OSError:
            pass

    def request(self, method, path, body=None):
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=10) as res:
                raw = res.read().decode("utf-8")
                return res.status, json.loads(raw) if raw else None
        except HTTPError as e:
            raw = e.read().decode("utf-8")
            return e.code, json.loads(raw) if raw else None

    def create_project(self, name="测试项目"):
        status, project = self.request("POST", "/api/projects", {
            "name": name, "client": "测试客户", "owner": "测试负责人",
            "scope": "test.local", "start_date": "2026-10-01", "due_date": "2026-10-31",
        })
        self.assertEqual(status, 201)
        return project

    def test_health_and_index(self):
        status, data = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        with urlopen(self.base + "/", timeout=10) as res:
            html = res.read().decode("utf-8")
        self.assertIn("WebScan SOP", html)
        self.assertIn("/static/app.js", html)

    def test_seed_projects(self):
        status, projects = self.request("GET", "/api/projects")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(projects), 3)
        self.assertTrue(any(p["code"] == "WEB-2026-001" for p in projects))

    def test_create_project_initializes_workflow(self):
        project = self.create_project("初始化测试")
        self.assertEqual(len(project["steps"]), 10)
        checks = [c for s in project["steps"] for c in s["checks"]]
        self.assertEqual(len(checks), 30)
        self.assertEqual(project["progress"], 0)
        self.assertTrue(project["steps"][0]["can_complete"] is False)
        self.assertTrue(project["steps"][1]["locked"] is True)

    def test_step_two_is_blocked_before_step_one(self):
        project = self.create_project("门禁测试")
        status, data = self.request("POST", f"/api/projects/{project['id']}/steps/2/complete", {})
        self.assertEqual(status, 409)
        self.assertIn("门禁未通过", data["error"])

    def test_complete_step_and_add_finding(self):
        project = self.create_project("完成步骤测试")
        step1 = project["steps"][0]
        for check in step1["checks"]:
            status, _ = self.request("PATCH", f"/api/checks/{check['id']}", {"result": "pass"})
            self.assertEqual(status, 200)
        status, updated = self.request("POST", f"/api/projects/{project['id']}/steps/1/complete", {})
        self.assertEqual(status, 200)
        self.assertEqual(updated["steps"][0]["status"], "done")
        self.assertFalse(updated["steps"][1]["locked"])

        status, updated = self.request("POST", f"/api/projects/{project['id']}/findings", {
            "title": "测试越权", "severity": "严重", "status": "待确认",
            "endpoint": "/api/test", "owner": "研发", "due_date": "2026-11-01",
        })
        self.assertEqual(status, 201)
        self.assertEqual(len(updated["findings"]), 1)
        self.assertEqual(updated["findings"][0]["severity"], "严重")

    def test_step_notes(self):
        project = self.create_project("备注测试")
        status, data = self.request("PATCH", f"/api/projects/{project['id']}/steps/1", {
            "notes": "授权书编号 AUTH-001",
        })
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        status, updated = self.request("GET", f"/api/projects/{project['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(updated["steps"][0]["notes"], "授权书编号 AUTH-001")

    def test_metrics(self):
        status, data = self.request("GET", "/api/metrics")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["total_projects"], 3)
        self.assertIn("severity", data)
        self.assertIn("upcoming", data)


if __name__ == "__main__":
    unittest.main()
