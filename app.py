#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WebScan SOP - a zero-dependency web app for running the 10-step
website vulnerability scanning workflow.

Run:
    python app.py
Then open:
    http://127.0.0.1:8765

The app uses only the Python standard library (http.server + sqlite3).
"""

import argparse
import json
import mimetypes
import os
import re
import socket
import sqlite3
import sys
import threading
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

FROZEN = bool(getattr(sys, "frozen", False))
# PyInstaller extracts bundled files to sys._MEIPASS.
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
STATIC_DIR = BASE_DIR / "static"
ASSETS_DIR = BASE_DIR / "assets"

if FROZEN:
    # Never write next to the EXE (Program Files may be read-only).
    default_data_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / "WebScanSOP"
else:
    default_data_dir = BASE_DIR

DB_PATH = Path(os.environ.get("DB_PATH", str(default_data_dir / "sop.db")))
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))
SEED_DEMO = os.environ.get("SEED_DEMO", "1").lower() not in ("0", "false", "no")

SEVERITIES = ["严重", "高", "中", "低", "信息"]
FINDING_STATUSES = ["待确认", "已确认", "修复中", "待复测", "已关闭", "风险接受"]
RESULTS = ["pass", "fail", "na", "pending"]


# ---------------------------------------------------------------------------
# SOP definition
# ---------------------------------------------------------------------------
SOP_STEPS = [
    {
        "no": 1, "name": "授权与范围", "owner": "项目经理", "gate": "无授权不启动",
        "intro": "先确认“能不能测、测哪里、什么时候测、出了事找谁”，再谈工具。",
        "checks": [
            ("授权书已签署，授权主体有权限", "授权书编号 / 盖章页"),
            ("目标清单到域名、IP、端口、API、H5/小程序", "范围清单 / 边界图"),
            ("时间窗、禁止动作、应急联系人、数据条款已确认", "RoE / 测试方案"),
        ],
    },
    {
        "no": 2, "name": "资产与入口", "owner": "信息收集", "gate": "资产不清不扫",
        "intro": "漏掉资产，后面扫得再快也是在别人家体检。",
        "checks": [
            ("子域名、IP、端口、URL、API、后台、第三方已盘点", "资产台账"),
            ("存活与归属确认，测试/灰度/旧版未遗漏", "存活清单 / 归属确认"),
            ("资产重要性、环境、负责人已标注并版本化", "台账版本号 / 更新时间"),
        ],
    },
    {
        "no": 3, "name": "账号与角色", "owner": "客户对接 / 项目经理", "gate": "关键角色缺失先补",
        "intro": "登录后的业务才是主战场，账号矩阵决定覆盖率。",
        "checks": [
            ("未登录、普通、VIP、管理员、多租户账号已准备", "账号清单"),
            ("账号权限匹配角色，登录态可复现", "角色矩阵 / Cookie 配置"),
            ("测试数据/订单已准备，不触碰真实个人信息", "测试数据说明"),
        ],
    },
    {
        "no": 4, "name": "指纹与画像", "owner": "信息收集", "gate": "关键系统未识别不扫",
        "intro": "先看清对手是 Java 还是 PHP、有没有 WAF，再决定打什么专项。",
        "checks": [
            ("语言、框架、中间件、数据库、前端已识别", "指纹表"),
            ("组件版本、WAF/CDN、端口、历史泄露已记录", "指纹表 / 截图"),
            ("核心入口、API 文档、扫描优先级已确认", "入口清单 / 优先级"),
        ],
    },
    {
        "no": 5, "name": "方案与编排", "owner": "扫描工程师", "gate": "未评审、未限速不跑生产",
        "intro": "把“扫得全”和“扫不崩”同时做到，靠的是模板和参数，不是胆子。",
        "checks": [
            ("模板已选：基础包 / 登录包 / API 包 / 专项包", "扫描配置单"),
            ("并发、限速、超时、排除路径已配置", "配置截图"),
            ("生产时间窗、灰度批次、停止方案已评审", "任务计划 / 评审记录"),
        ],
    },
    {
        "no": 6, "name": "自动化扫描", "owner": "扫描工程师", "gate": "异常立即停",
        "intro": "按 6.1–6.9 的顺序跑，不跳项；先只读后写入。",
        "checks": [
            ("6.1–6.9 按顺序执行，未跳项", "任务日志"),
            ("请求响应、时间戳、账号证据完整", "证据包"),
            ("生产监控到位，异常立即停止", "监控截图 / 事件记录"),
        ],
    },
    {
        "no": 7, "name": "人工验证", "owner": "渗透工程师", "gate": "不能复现不写报告",
        "intro": "扫描器说“可能”，工程师说“确实”；三次复现才算确认。",
        "checks": [
            ("高危至少三次复现，结果一致", "复现记录"),
            ("已排除 WAF、缓存、业务正常现象", "对照请求"),
            ("证据链完整，影响未夸大", "证据包 / 影响说明"),
        ],
    },
    {
        "no": 8, "name": "定级与确认", "owner": "技术负责人", "gate": "无依据不定级",
        "intro": "CVSS 是温度计，业务影响是体质；定级要能解释，不是拍脑袋。",
        "checks": [
            ("CVSS 技术分已计算", "评分记录"),
            ("资产重要性、暴露面、数据敏感度已加权", "定级表"),
            ("业务方确认影响、优先级、时限", "确认邮件 / 会议记录"),
        ],
    },
    {
        "no": 9, "name": "报告与工单", "owner": "项目经理", "gate": "建议不可执行就重写",
        "intro": "报告不是漏洞清单，是给研发的修复工单和给管理层的风险账本。",
        "checks": [
            ("摘要、范围、统计、详情、修复、复测齐全", "报告初稿"),
            ("敏感数据脱敏，密级和分发范围明确", "脱敏检查表"),
            ("修复工单、责任人、时限可跟踪", "工单 / 台账"),
        ],
    },
    {
        "no": 10, "name": "复测与归档", "owner": "项目经理 / 复核", "gate": "未复测不关闭",
        "intro": "高危 100% 复测，中危抽样；修复前后要能对比。",
        "checks": [
            ("高危 100%、中危抽样 ≥30% 已复测", "复测记录"),
            ("修复前后对比清晰，未修复项有风险说明", "复测报告"),
            ("台账更新，数据销毁/账号注销", "归档 / 销毁记录"),
        ],
    },
]

STEP6_ORDER = [
    ("6.1", "暴露面与未授权", "后台、Actuator、Swagger、Druid、.git、目录列表、云存储", "只读、低影响、覆盖快；先排除“门没锁”"),
    ("6.2", "认证与会话", "弱口令、验证码、锁定、JWT、Cookie、密码重置", "先拿到合法身份，后面才能测登录后"),
    ("6.3", "访问控制", "水平/垂直越权、IDOR、多租户隔离", "多账号只读验证，风险低、价值高"),
    ("6.4", "注入", "SQL、NoSQL、命令、SSTI、CRLF", "用只读/带外方式验证，避免写数据"),
    ("6.5", "客户端", "XSS、CSRF、CORS、点击劫持、开放重定向", "需要浏览器确认，放在注入后"),
    ("6.6", "文件与解析", "上传、包含、路径遍历、XXE、反序列化", "风险高、可能影响文件，放在中后段"),
    ("6.7", "服务端请求与配置", "SSRF、配置错误、组件 CVE、信息泄露", "依赖环境和版本，适合指纹后做"),
    ("6.8", "业务逻辑", "支付、优惠券、库存、验证码、并发", "需要业务建模，放最后人工做"),
    ("6.9", "复测回归", "高危全量、中危抽样", "闭环，不放在扫描阶段"),
]

LIBRARY = {
    "steps": SOP_STEPS,
    "order": STEP6_ORDER,
    "templates": [
        ("基础包", "所有站点", "暴露面/未授权、配置、组件、注入、XSS、信息泄露", "默认加载"),
        ("登录包", "有账号体系", "认证、会话、越权、后台、密码重置", "提供账号"),
        ("API 包", "有 REST/GraphQL", "JSON 参数、Swagger/Postman、越权、速率限制", "提供文档/抓包"),
        ("专项包", "按指纹命中", "Java：Fastjson/Shiro/Log4j；PHP：上传/包含；中间件 CVE", "指纹命中"),
    ],
    "params": [
        ("并发", "5–10（生产减半）", "避免连接池耗尽、触发 WAF 或拖慢业务"),
        ("请求速率", "10–20 req/s（生产 5–10）", "模拟正常用户访问，避免被当成 CC 攻击"),
        ("超时 / 重试", "15–20 秒 / 最多 2 次", "区分“业务慢”和“漏洞导致的延迟”"),
        ("爬虫深度", "5–8 层", "覆盖登录后菜单，避免陷入无限日历/分页"),
        ("排除路径", "/logout /delete /pay /refund /export /sms", "防止误操作产生真实业务副作用"),
        ("登录态", "至少普通用户 + 管理员", "登录后漏洞占多数，未登录扫描只查了门面"),
        ("危险插件", "关闭命令执行、文件写入、拒绝服务类", "默认配置也可能造成破坏，必须人工确认"),
    ],
    "gates": [
        ("01", "无授权不扫"),
        ("02", "资产不清不扫"),
        ("03", "生产不限速不扫"),
        ("04", "未复现不写报告"),
        ("05", "未复测不关闭"),
    ],
    "sizing": [
        ("小型官网/门户", "3–5 个工作日", "基础包 + 人工验证"),
        ("中型业务系统", "1–2 周", "基础包 + 登录包 + API 包"),
        ("大型/多租户/集团站", "3–4 周", "分域分批 + 业务逻辑 + 持续运营"),
    ],
    "maintenance": [
        ("每次上线/变更", "变更影响面扫描，重点新接口、新参数、新组件、新权限", "增量报告"),
        ("每月", "资产盘点 + 增量扫描 + 高危复测", "资产/漏洞台账"),
        ("每季度", "全量扫描 + 模板/规则评审 + 指标复盘", "SOP/模板版本记录"),
        ("每半年/年", "深度人工渗透 + 应急演练 + 流程回放", "深度报告/改进项"),
    ],
}


# ---------------------------------------------------------------------------
# database
# ---------------------------------------------------------------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            client TEXT DEFAULT '',
            owner TEXT DEFAULT '',
            scope TEXT DEFAULT '',
            description TEXT DEFAULT '',
            start_date TEXT DEFAULT '',
            due_date TEXT DEFAULT '',
            status TEXT DEFAULT '进行中',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            step_no INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            completed_at TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            UNIQUE(project_id, step_no)
        );
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            step_no INTEGER NOT NULL,
            item_no TEXT NOT NULL,
            label TEXT NOT NULL,
            evidence_hint TEXT DEFAULT '',
            result TEXT DEFAULT 'pending',
            evidence TEXT DEFAULT '',
            note TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            severity TEXT DEFAULT '中',
            endpoint TEXT DEFAULT '',
            status TEXT DEFAULT '待确认',
            owner TEXT DEFAULT '',
            due_date TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            detail TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"]
    if count == 0 and SEED_DEMO:
        seed(conn)
    conn.close()


def insert_project(conn, data):
    conn.execute(
        """INSERT INTO projects
           (code, name, client, owner, scope, description, start_date, due_date, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            data["code"], data["name"], data.get("client", ""), data.get("owner", ""),
            data.get("scope", ""), data.get("description", ""),
            data.get("start_date", ""), data.get("due_date", ""),
            data.get("status", "进行中"), now(),
        ),
    )
    pid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    for step in SOP_STEPS:
        conn.execute(
            "INSERT INTO steps (project_id, step_no, status) VALUES (?,?,?)",
            (pid, step["no"], "pending"),
        )
        for idx, (label, hint) in enumerate(step["checks"], 1):
            conn.execute(
                """INSERT INTO checks
                   (project_id, step_no, item_no, label, evidence_hint, result, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (pid, step["no"], f"{step['no']}.{idx}", label, hint, "pending", now()),
            )
    conn.execute(
        "INSERT INTO activity (project_id, action, detail, created_at) VALUES (?,?,?,?)",
        (pid, "创建项目", f"创建 {data['name']}，初始化 10 个步骤 / 30 项检查", now()),
    )
    return pid


def seed(conn):
    today = date.today()
    projects = [
        {
            "code": "WEB-2026-001", "name": "集团门户与会员中心", "client": "某集团",
            "owner": "张工", "scope": "www.example.com、member.example.com、开放 API",
            "description": "门户、会员中心、积分与订单查询；含普通用户、VIP、管理员三类角色。",
            "start_date": (today - timedelta(days=17)).isoformat(),
            "due_date": (today + timedelta(days=5)).isoformat(),
            "status": "进行中", "done_steps": [1, 2, 3, 4], "active_step": 5,
        },
        {
            "code": "WEB-2026-002", "name": "支付结算 API", "client": "某支付公司",
            "owner": "李工", "scope": "api.example.com、商户后台、回调接口",
            "description": "商户接入、交易查询、退款、回调；多租户隔离与资金相关逻辑重点。",
            "start_date": (today - timedelta(days=13)).isoformat(),
            "due_date": (today + timedelta(days=11)).isoformat(),
            "status": "进行中", "done_steps": [1, 2, 3, 4, 5, 6, 7], "active_step": 8,
        },
        {
            "code": "WEB-2026-003", "name": "旧版 OA 系统", "client": "某制造企业",
            "owner": "王工", "scope": "oa.example.com、移动端 H5",
            "description": "旧版 OA 上线前检查；重点组件漏洞、弱口令与文件上传。",
            "start_date": (today - timedelta(days=35)).isoformat(),
            "due_date": (today - timedelta(days=5)).isoformat(),
            "status": "已完成", "done_steps": list(range(1, 11)), "active_step": None,
        },
    ]
    for p in projects:
        pid = insert_project(conn, p)
        for s in p["done_steps"]:
            conn.execute(
                "UPDATE steps SET status='done', completed_at=? WHERE project_id=? AND step_no=?",
                (now(), pid, s),
            )
            conn.execute(
                "UPDATE checks SET result='pass', evidence='已按检查表完成', updated_at=? WHERE project_id=? AND step_no=?",
                (now(), pid, s),
            )
        if p["active_step"]:
            step = p["active_step"]
            conn.execute(
                "UPDATE steps SET status='in_progress' WHERE project_id=? AND step_no=?",
                (pid, step),
            )
            conn.execute(
                """UPDATE checks SET result='pass', evidence='已确认', updated_at=?
                   WHERE project_id=? AND step_no=? AND item_no=?""",
                (now(), pid, step, f"{step}.1"),
            )
    findings = [
        (1, "会员中心订单查询 IDOR", "严重", "/api/member/orders/{id}", "待复测", "张工",
         (today - timedelta(days=3)).isoformat(), "A 账号可读取 B 账号订单详情，已修复待复测。"),
        (1, "门户搜索反射型 XSS", "中", "/search?q=", "修复中", "张工",
         (today + timedelta(days=4)).isoformat(), "搜索关键词未编码，已提交前端修复。"),
        (2, "商户 API 越权查询交易", "严重", "/api/merchant/trades", "修复中", "李工",
         (today + timedelta(days=2)).isoformat(), "缺少商户归属校验，可跨商户查询。"),
        (2, "回调地址 SSRF", "高", "/api/pay/notify", "待确认", "李工",
         (today + timedelta(days=6)).isoformat(), "回调 URL 可指向内网，需人工确认。"),
        (2, "Swagger 文档未授权", "中", "/v2/api-docs", "已关闭", "李工",
         (today - timedelta(days=1)).isoformat(), "已加网关鉴权。"),
        (3, "旧版组件反序列化 CVE", "高", "weblogic:7001", "已关闭", "王工",
         (today - timedelta(days=8)).isoformat(), "已升级补丁并复测。"),
        (3, "OA 管理员弱口令", "严重", "/login", "已关闭", "王工",
         (today - timedelta(days=6)).isoformat(), "已改强口令并启用 MFA。"),
    ]
    for pid, title, sev, endpoint, status, owner, due, note in findings:
        conn.execute(
            """INSERT INTO findings
               (project_id, title, severity, endpoint, status, owner, due_date, note, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (pid, title, sev, endpoint, status, owner, due, note, now(), now()),
        )
    conn.execute(
        "INSERT INTO activity (project_id, action, detail, created_at) VALUES (?,?,?,?)",
        (1, "完成步骤", "步骤 4 指纹与画像 已完成", now()),
    )
    conn.execute(
        "INSERT INTO activity (project_id, action, detail, created_at) VALUES (?,?,?,?)",
        (2, "更新漏洞", "回调地址 SSRF 标记为待确认", now()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# query helpers
# ---------------------------------------------------------------------------
def project_progress(conn, pid):
    total = conn.execute("SELECT COUNT(*) c FROM steps WHERE project_id=?", (pid,)).fetchone()["c"]
    done = conn.execute("SELECT COUNT(*) c FROM steps WHERE project_id=? AND status='done'", (pid,)).fetchone()["c"]
    return int(done / total * 100) if total else 0


def step_blockers(step, checks, prev_status, findings):
    if step["status"] == "done":
        return []
    blockers = []
    if step["step_no"] > 1 and prev_status != "done":
        blockers.append("上一步未完成")
    pending = [c for c in checks if c["result"] not in ("pass", "na")]
    if pending:
        blockers.append(f"{len(pending)} 项检查未通过 / 未完成")
    if step["step_no"] == 1:
        auth = next((c for c in checks if c["item_no"] == "1.1"), None)
        if not auth or auth["result"] != "pass":
            blockers.append("授权书未确认（1.1 必须通过）")
    if step["step_no"] == 9:
        missing = [f for f in findings if not f.get("owner") or not f.get("due_date")]
        if missing:
            blockers.append(f"{len(missing)} 个漏洞缺少负责人或期限")
    if step["step_no"] == 10:
        open_high = [f for f in findings if f["severity"] in ("严重", "高")
                     and f["status"] not in ("已关闭", "风险接受")]
        if open_high:
            blockers.append(f"{len(open_high)} 个高危 / 严重漏洞未关闭")
    return blockers


def get_project(conn, pid):
    row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not row:
        return None
    project = dict(row)
    project["progress"] = project_progress(conn, pid)
    steps = [dict(s) for s in conn.execute(
        "SELECT * FROM steps WHERE project_id=? ORDER BY step_no", (pid,)).fetchall()]
    checks = [dict(c) for c in conn.execute(
        "SELECT * FROM checks WHERE project_id=? ORDER BY step_no, item_no", (pid,)).fetchall()]
    findings = [dict(f) for f in conn.execute(
        "SELECT * FROM findings WHERE project_id=? ORDER BY id", (pid,)).fetchall()]
    by_step = {}
    for c in checks:
        by_step.setdefault(c["step_no"], []).append(c)
    prev = "done"
    for s in steps:
        s["checks"] = by_step.get(s["step_no"], [])
        s["blockers"] = step_blockers(s, s["checks"], prev, findings)
        s["can_complete"] = s["status"] != "done" and not s["blockers"]
        s["locked"] = s["step_no"] > 1 and prev != "done"
        s["definition"] = next((x for x in SOP_STEPS if x["no"] == s["step_no"]), None)
        prev = s["status"]
    project["steps"] = steps
    project["findings"] = findings
    return project


def project_summary_rows(conn):
    rows = conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
    out = []
    for r in rows:
        p = dict(r)
        p["progress"] = project_progress(conn, p["id"])
        p["done_steps"] = conn.execute(
            "SELECT COUNT(*) c FROM steps WHERE project_id=? AND status='done'", (p["id"],)
        ).fetchone()["c"]
        p["open_high"] = conn.execute(
            """SELECT COUNT(*) c FROM findings WHERE project_id=?
               AND severity IN ('严重','高') AND status NOT IN ('已关闭','风险接受')""",
            (p["id"],),
        ).fetchone()["c"]
        p["total_findings"] = conn.execute(
            "SELECT COUNT(*) c FROM findings WHERE project_id=?", (p["id"],)
        ).fetchone()["c"]
        out.append(p)
    return out


def metrics(conn):
    projects = project_summary_rows(conn)
    total = len(projects)
    active = sum(1 for p in projects if p["status"] == "进行中")
    completed = sum(1 for p in projects if p["status"] == "已完成")
    avg = round(sum(p["progress"] for p in projects) / total) if total else 0
    open_high = sum(p["open_high"] for p in projects)
    today = date.today().isoformat()
    overdue = conn.execute(
        """SELECT COUNT(*) c FROM findings
           WHERE due_date != '' AND due_date < ? AND status NOT IN ('已关闭','风险接受')""",
        (today,),
    ).fetchone()["c"]
    total_findings = conn.execute("SELECT COUNT(*) c FROM findings").fetchone()["c"]
    checks_done = conn.execute(
        "SELECT COUNT(*) c FROM checks WHERE result IN ('pass','na')"
    ).fetchone()["c"]
    checks_total = conn.execute("SELECT COUNT(*) c FROM checks").fetchone()["c"]
    sev_rows = conn.execute(
        "SELECT severity, COUNT(*) c FROM findings GROUP BY severity").fetchall()
    sev = {s: 0 for s in SEVERITIES}
    for r in sev_rows:
        sev[r["severity"]] = r["c"]
    status_rows = conn.execute(
        "SELECT status, COUNT(*) c FROM findings GROUP BY status").fetchall()
    stat = {s: 0 for s in FINDING_STATUSES}
    for r in status_rows:
        stat[r["status"]] = r["c"]
    upcoming = [dict(f) for f in conn.execute(
        """SELECT f.*, p.name AS project_name FROM findings f
           JOIN projects p ON p.id=f.project_id
           WHERE f.severity IN ('严重','高') AND f.status NOT IN ('已关闭','风险接受')
           ORDER BY CASE f.severity WHEN '严重' THEN 0 ELSE 1 END, f.due_date LIMIT 8"""
    ).fetchall()]
    return {
        "total_projects": total, "active_projects": active, "completed_projects": completed,
        "avg_progress": avg, "open_high": open_high, "overdue": overdue,
        "total_findings": total_findings, "checks_done": checks_done, "checks_total": checks_total,
        "severity": sev, "status": stat, "upcoming": upcoming,
    }


def add_activity(conn, pid, action, detail):
    conn.execute(
        "INSERT INTO activity (project_id, action, detail, created_at) VALUES (?,?,?,?)",
        (pid, action, detail, now()),
    )


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "WebScanSOP/1.0"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), fmt % args))

    # -- response helpers -------------------------------------------------
    def security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'",
        )

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, status=400):
        self.send_json({"error": message}, status)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            raise ValueError("请求体不是合法 JSON")

    def serve_static(self, path):
        if path in ("/", ""):
            file = STATIC_DIR / "index.html"
        else:
            rel = path.lstrip("/")
            if rel.startswith("static/"):
                rel = rel[len("static/"):]
            file = (STATIC_DIR / rel).resolve()
        try:
            file.relative_to(STATIC_DIR.resolve())
        except ValueError:
            return self.send_error_json("not found", 404)
        if not file.is_file():
            return self.send_error_json("not found", 404)
        body = file.read_bytes()
        ctype = mimetypes.guess_type(str(file))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.security_headers()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    # -- routes -----------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self.api_get(path)
        return self.serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        return self.api_post(path)

    def do_PATCH(self):
        path = urlparse(self.path).path
        return self.api_patch(path)

    def do_DELETE(self):
        path = urlparse(self.path).path
        m = re.fullmatch(r"/api/findings/(\d+)", path)
        if not m:
            return self.send_error_json("not found", 404)
        conn = db()
        conn.execute("DELETE FROM findings WHERE id=?", (int(m.group(1)),))
        conn.commit()
        conn.close()
        return self.send_json({"ok": True})

    def api_get(self, path):
        conn = db()
        try:
            if path == "/api/health":
                return self.send_json({"ok": True, "time": now()})
            if path == "/api/library":
                return self.send_json(LIBRARY)
            if path == "/api/projects":
                return self.send_json(project_summary_rows(conn))
            if path == "/api/metrics":
                return self.send_json(metrics(conn))
            if path == "/api/activity":
                rows = conn.execute(
                    """SELECT a.*, p.name AS project_name FROM activity a
                       LEFT JOIN projects p ON p.id=a.project_id
                       ORDER BY a.id DESC LIMIT 30"""
                ).fetchall()
                return self.send_json([dict(r) for r in rows])
            m = re.fullmatch(r"/api/projects/(\d+)", path)
            if m:
                p = get_project(conn, int(m.group(1)))
                if not p:
                    return self.send_error_json("项目不存在", 404)
                return self.send_json(p)
            m = re.fullmatch(r"/api/projects/(\d+)/export", path)
            if m:
                p = get_project(conn, int(m.group(1)))
                if not p:
                    return self.send_error_json("项目不存在", 404)
                data = json.dumps(p, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(200)
                self.security_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Disposition",
                                 f'attachment; filename="webscan-{p["code"]}.json"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            return self.send_error_json("not found", 404)
        finally:
            conn.close()

    def api_post(self, path):
        try:
            body = self.read_json()
        except ValueError as e:
            return self.send_error_json(str(e), 400)
        conn = db()
        try:
            if path == "/api/projects":
                name = (body.get("name") or "").strip()
                if not name:
                    return self.send_error_json("项目名称不能为空", 400)
                seq = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] + 1
                code = body.get("code") or f"WEB-{date.today().year}-{seq:03d}"
                if conn.execute("SELECT 1 FROM projects WHERE code=?", (code,)).fetchone():
                    code = f"WEB-{date.today().year}-{seq:03d}-{datetime.now().strftime('%H%M%S')}"
                pid = insert_project(conn, {
                    "code": code, "name": name, "client": body.get("client", ""),
                    "owner": body.get("owner", ""), "scope": body.get("scope", ""),
                    "description": body.get("description", ""),
                    "start_date": body.get("start_date", ""),
                    "due_date": body.get("due_date", ""), "status": "进行中",
                })
                conn.commit()
                return self.send_json(get_project(conn, pid), 201)
            m = re.fullmatch(r"/api/projects/(\d+)/findings", path)
            if m:
                pid = int(m.group(1))
                if not conn.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone():
                    return self.send_error_json("项目不存在", 404)
                title = (body.get("title") or "").strip()
                if not title:
                    return self.send_error_json("漏洞标题不能为空", 400)
                sev = body.get("severity", "中")
                if sev not in SEVERITIES:
                    return self.send_error_json("风险等级不合法", 400)
                status = body.get("status", "待确认")
                if status not in FINDING_STATUSES:
                    return self.send_error_json("漏洞状态不合法", 400)
                conn.execute(
                    """INSERT INTO findings
                       (project_id, title, severity, endpoint, status, owner, due_date, note, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (pid, title, sev, body.get("endpoint", ""), status,
                     body.get("owner", ""), body.get("due_date", ""),
                     body.get("note", ""), now(), now()),
                )
                add_activity(conn, pid, "新增漏洞", f"{title}（{sev}）")
                conn.commit()
                return self.send_json(get_project(conn, pid), 201)
            m = re.fullmatch(r"/api/projects/(\d+)/steps/(\d+)/complete", path)
            if m:
                pid, step_no = int(m.group(1)), int(m.group(2))
                p = get_project(conn, pid)
                if not p:
                    return self.send_error_json("项目不存在", 404)
                step = next((s for s in p["steps"] if s["step_no"] == step_no), None)
                if not step:
                    return self.send_error_json("步骤不存在", 404)
                if step["status"] == "done":
                    return self.send_error_json("该步骤已完成", 409)
                if step["blockers"]:
                    return self.send_json({"error": "门禁未通过", "blockers": step["blockers"]}, 409)
                conn.execute(
                    "UPDATE steps SET status='done', completed_at=? WHERE project_id=? AND step_no=?",
                    (now(), pid, step_no),
                )
                add_activity(conn, pid, "完成步骤", f"步骤 {step_no} {step['definition']['name']} 已完成")
                if step_no == 10:
                    conn.execute("UPDATE projects SET status='已完成' WHERE id=?", (pid,))
                    add_activity(conn, pid, "项目完成", "10 个步骤全部完成，项目关闭")
                conn.commit()
                return self.send_json(get_project(conn, pid))
            return self.send_error_json("not found", 404)
        finally:
            conn.close()

    def api_patch(self, path):
        try:
            body = self.read_json()
        except ValueError as e:
            return self.send_error_json(str(e), 400)
        conn = db()
        try:
            m = re.fullmatch(r"/api/checks/(\d+)", path)
            if m:
                cid = int(m.group(1))
                row = conn.execute("SELECT * FROM checks WHERE id=?", (cid,)).fetchone()
                if not row:
                    return self.send_error_json("检查项不存在", 404)
                result = body.get("result", row["result"])
                if result not in RESULTS:
                    return self.send_error_json("检查结果不合法", 400)
                conn.execute(
                    """UPDATE checks SET result=?, evidence=?, note=?, updated_at=?
                       WHERE id=?""",
                    (result, body.get("evidence", row["evidence"]),
                     body.get("note", row["note"]), now(), cid),
                )
                conn.commit()
                return self.send_json(dict(conn.execute("SELECT * FROM checks WHERE id=?", (cid,)).fetchone()))
            m = re.fullmatch(r"/api/projects/(\d+)/steps/(\d+)", path)
            if m:
                pid, step_no = int(m.group(1)), int(m.group(2))
                row = conn.execute(
                    "SELECT * FROM steps WHERE project_id=? AND step_no=?", (pid, step_no)
                ).fetchone()
                if not row:
                    return self.send_error_json("步骤不存在", 404)
                notes = str(body.get("notes", row["notes"]))[:4000]
                conn.execute(
                    "UPDATE steps SET notes=? WHERE project_id=? AND step_no=?",
                    (notes, pid, step_no),
                )
                add_activity(conn, pid, "更新步骤", f"步骤 {step_no} 备注已更新")
                conn.commit()
                return self.send_json({"ok": True, "notes": notes})
            m = re.fullmatch(r"/api/projects/(\d+)", path)
            if m:
                pid = int(m.group(1))
                if not conn.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone():
                    return self.send_error_json("项目不存在", 404)
                allowed = ["name", "client", "owner", "scope", "description",
                           "start_date", "due_date", "status"]
                sets, vals = [], []
                for key in allowed:
                    if key in body:
                        sets.append(f"{key}=?")
                        vals.append(body[key])
                if sets:
                    vals.append(pid)
                    conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", vals)
                    add_activity(conn, pid, "更新项目", "项目信息已更新")
                    conn.commit()
                return self.send_json(get_project(conn, pid))
            m = re.fullmatch(r"/api/findings/(\d+)", path)
            if m:
                fid = int(m.group(1))
                row = conn.execute("SELECT * FROM findings WHERE id=?", (fid,)).fetchone()
                if not row:
                    return self.send_error_json("漏洞不存在", 404)
                if "severity" in body and body["severity"] not in SEVERITIES:
                    return self.send_error_json("风险等级不合法", 400)
                if "status" in body and body["status"] not in FINDING_STATUSES:
                    return self.send_error_json("漏洞状态不合法", 400)
                allowed = ["title", "severity", "endpoint", "status", "owner", "due_date", "note"]
                sets, vals = [], []
                for key in allowed:
                    if key in body:
                        sets.append(f"{key}=?")
                        vals.append(body[key])
                if sets:
                    sets.append("updated_at=?")
                    vals.extend([now(), fid])
                    conn.execute(f"UPDATE findings SET {', '.join(sets)} WHERE id=?", vals)
                    add_activity(conn, int(row["project_id"]), "更新漏洞",
                                 f"{body.get('title', row['title'])} 状态/信息已更新")
                    conn.commit()
                return self.send_json(dict(conn.execute(
                    "SELECT * FROM findings WHERE id=?", (fid,)).fetchone()))
            return self.send_error_json("not found", 404)
        finally:
            conn.close()


def find_free_port(start):
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((HOST, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"无法在 {start}–{start + 29} 找到空闲端口")


def run_server(port):
    server = ThreadingHTTPServer((HOST, port), Handler)
    print(f"WebScan SOP running at http://{HOST}:{port}")
    print(f"Database: {DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
        server.server_close()


def launch_desktop(port):
    """Small Tkinter launcher for the windowed EXE."""
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("WebScan SOP")
    root.configure(bg="#07192a")
    root.resizable(False, False)
    width, height = 580, 390
    root.update_idletasks()
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")
    try:
        icon = ASSETS_DIR / "app.ico"
        if icon.exists():
            root.iconbitmap(default=str(icon))
    except Exception:
        pass

    try:
        server = ThreadingHTTPServer((HOST, port), Handler)
    except OSError as exc:
        messagebox.showerror("WebScan SOP", f"端口 {port} 启动失败：{exc}")
        root.destroy()
        return

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{HOST}:{port}"

    header = tk.Frame(root, bg="#07192a")
    header.pack(fill="x", padx=28, pady=(26, 0))
    logo = tk.Label(header, text="WS", bg="#c8a45c", fg="#0b2239",
                    font=("Microsoft YaHei UI", 14, "bold"), width=3, height=1)
    logo.pack(side="left", padx=(0, 12))
    titles = tk.Frame(header, bg="#07192a")
    titles.pack(side="left", anchor="w")
    tk.Label(titles, text="WebScan SOP", bg="#07192a", fg="#ffffff",
             font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
    tk.Label(titles, text="网站漏洞扫描标准作业平台", bg="#07192a", fg="#8fa6bd",
             font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(2, 0))

    status = tk.Frame(root, bg="#0d2a42")
    status.pack(fill="x", padx=28, pady=(24, 0))
    tk.Label(status, text="●", bg="#0d2a42", fg="#22c55e",
             font=("Segoe UI", 12, "bold")).pack(side="left", padx=(14, 6), pady=10)
    tk.Label(status, text="服务运行中", bg="#0d2a42", fg="#d7f5e5",
             font=("Microsoft YaHei UI", 9, "bold")).pack(side="left", pady=10)
    tk.Label(status, text=f"SQLite · 本地数据", bg="#0d2a42", fg="#6f8aa3",
             font=("Microsoft YaHei UI", 8)).pack(side="right", padx=14, pady=10)

    tk.Label(root, text="本地访问地址", bg="#07192a", fg="#6f8aa3",
             font=("Microsoft YaHei UI", 8)).pack(anchor="w", padx=28, pady=(18, 4))
    entry = tk.Entry(root, bg="#0d2035", fg="#dbe7f3", insertbackground="#ffffff",
                     relief="flat", font=("Consolas", 10), highlightthickness=0)
    entry.insert(0, url)
    entry.configure(state="readonly")
    entry.pack(fill="x", padx=28, ipady=8)

    btns = tk.Frame(root, bg="#07192a")
    btns.pack(fill="x", padx=28, pady=(16, 0))

    def open_browser():
        webbrowser.open(url)

    def copy_url():
        root.clipboard_clear()
        root.clipboard_append(url)
        copy_btn.configure(text="已复制")
        root.after(1400, lambda: copy_btn.configure(text="复制地址"))

    def open_data():
        try:
            os.startfile(str(DB_PATH.parent))  # type: ignore[attr-defined]
        except Exception:
            pass

    def stop():
        try:
            server.shutdown()
            server.server_close()
        finally:
            root.destroy()

    primary = tk.Button(btns, text="打开浏览器", command=open_browser, bg="#0f766e", fg="#ffffff",
                        activebackground="#0d9488", activeforeground="#ffffff", relief="flat",
                        bd=0, padx=18, pady=9, cursor="hand2",
                        font=("Microsoft YaHei UI", 9, "bold"))
    primary.pack(side="left")
    copy_btn = tk.Button(btns, text="复制地址", command=copy_url, bg="#12314f", fg="#dbe7f3",
                         activebackground="#1b4266", activeforeground="#ffffff", relief="flat",
                         bd=0, padx=14, pady=9, cursor="hand2",
                         font=("Microsoft YaHei UI", 9))
    copy_btn.pack(side="left", padx=8)
    tk.Button(btns, text="数据目录", command=open_data, bg="#12314f", fg="#dbe7f3",
              activebackground="#1b4266", activeforeground="#ffffff", relief="flat",
              bd=0, padx=14, pady=9, cursor="hand2",
              font=("Microsoft YaHei UI", 9)).pack(side="left")

    tk.Button(root, text="停止服务并退出", command=stop, bg="#07192a", fg="#8fa6bd",
              activebackground="#07192a", activeforeground="#fca5a5", relief="flat",
              bd=0, cursor="hand2", font=("Microsoft YaHei UI", 9)).pack(side="bottom", pady=16)

    tk.Label(root, text=f"数据文件：{DB_PATH}", bg="#07192a", fg="#4f6a82",
             font=("Consolas", 7), anchor="w").pack(side="bottom", fill="x", padx=28)

    root.protocol("WM_DELETE_WINDOW", stop)
    root.after(350, open_browser)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="WebScan SOP")
    parser.add_argument("--server", action="store_true", help="run as a blocking server (no GUI)")
    parser.add_argument("--port", type=int, default=PORT, help="port to listen on")
    args = parser.parse_args()

    init_db()
    port = args.port
    if FROZEN and not args.server:
        port = find_free_port(port)
        launch_desktop(port)
    else:
        run_server(port)


if __name__ == "__main__":
    main()
