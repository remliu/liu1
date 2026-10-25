# API Reference

Base URL: `http://127.0.0.1:8765`

All request/response bodies are UTF-8 JSON. Errors return an HTTP 4xx/5xx with:

```json
{ "error": "门禁未通过", "blockers": ["2 项检查未通过 / 未完成"] }
```

## Health

```http
GET /api/health
```

```json
{ "ok": true, "time": "2026-10-25 22:00:00" }
```

## Projects

### List projects

```http
GET /api/projects
```

Each row includes `progress`, `done_steps`, `open_high`, `total_findings`.

### Create project

```http
POST /api/projects
Content-Type: application/json

{
  "name": "集团门户与会员中心",
  "client": "某集团",
  "owner": "张工",
  "scope": "www.example.com、member.example.com",
  "description": "门户 + 会员中心 + 开放 API",
  "start_date": "2026-10-01",
  "due_date": "2026-10-31"
}
```

Creates 10 steps and 30 checks automatically. Returns the full project.

### Get project

```http
GET /api/projects/{id}
```

Returns:

```json
{
  "id": 1,
  "code": "WEB-2026-001",
  "name": "集团门户与会员中心",
  "progress": 40,
  "steps": [
    {
      "step_no": 1,
      "status": "done",
      "locked": false,
      "blockers": [],
      "can_complete": false,
      "definition": { "name": "授权与范围", "owner": "项目经理", "gate": "无授权不启动" },
      "checks": [
        { "id": 1, "item_no": "1.1", "result": "pass", "evidence": "AUTH-001" }
      ]
    }
  ],
  "findings": []
}
```

### Update project

```http
PATCH /api/projects/{id}
Content-Type: application/json

{ "owner": "李工", "due_date": "2026-11-15" }
```

Allowed fields: `name`, `client`, `owner`, `scope`, `description`, `start_date`, `due_date`, `status`.

### Export project

```http
GET /api/projects/{id}/export
```

Returns a downloadable JSON file with the full project.

## Checks

### Update a check

```http
PATCH /api/checks/{id}
Content-Type: application/json

{
  "result": "pass",
  "evidence": "请求/响应截图编号 EV-001",
  "note": "已在测试环境复现"
}
```

`result` must be one of `pass`, `fail`, `na`, `pending`.

### Save step notes

```http
PATCH /api/projects/{id}/steps/{step_no}
Content-Type: application/json

{ "notes": "授权书编号 AUTH-001；测试窗口 10-20 至 10-25。" }
```

## Complete a step

```http
POST /api/projects/{id}/steps/{step_no}/complete
Content-Type: application/json

{}
```

Server-side gate checks:

1. Previous step must be `done`.
2. All checks must be `pass` or `na`.
3. Step 1: check `1.1` must be `pass`.
4. Step 9: every finding must have an owner and due date.
5. Step 10: no open critical/high findings.

On failure:

```json
HTTP 409
{
  "error": "门禁未通过",
  "blockers": ["2 项检查未通过 / 未完成", "1 个高危 / 严重漏洞未关闭"]
}
```

Completing step 10 marks the project as `已完成`.

## Findings

### Create

```http
POST /api/projects/{id}/findings
Content-Type: application/json

{
  "title": "会员中心订单查询 IDOR",
  "severity": "严重",
  "endpoint": "/api/member/orders/{id}",
  "status": "待确认",
  "owner": "研发-张工",
  "due_date": "2026-11-01",
  "note": "A 账号可读取 B 账号订单详情"
}
```

`severity`: `严重` / `高` / `中` / `低` / `信息`  
`status`: `待确认` / `已确认` / `修复中` / `待复测` / `已关闭` / `风险接受`

### Update

```http
PATCH /api/findings/{id}
Content-Type: application/json

{ "status": "待复测", "owner": "研发-李工" }
```

### Delete

```http
DELETE /api/findings/{id}
```

## Metrics

```http
GET /api/metrics
```

```json
{
  "total_projects": 3,
  "active_projects": 2,
  "completed_projects": 1,
  "avg_progress": 70,
  "open_high": 3,
  "overdue": 1,
  "total_findings": 7,
  "checks_done": 65,
  "checks_total": 90,
  "severity": { "严重": 3, "高": 2, "中": 2, "低": 0, "信息": 0 },
  "status": { "待确认": 1, "已确认": 0, "修复中": 2, "待复测": 1, "已关闭": 3, "风险接受": 0 },
  "upcoming": []
}
```

## Activity

```http
GET /api/activity
```

Returns the latest 30 activity records, newest first.

## SOP library

```http
GET /api/library
```

Returns `steps`, `order`, `templates`, `params`, `gates`, `sizing`, `maintenance`.
