# WebScan SOP

> 把「单项目 10 步网站漏洞扫描流程」做成可执行、可验收、可复测的轻量工作台。

一个零第三方依赖的 Web 应用：用 Python 标准库提供 JSON API + SQLite，前端是原生 HTML/CSS/JS。  
不内置扫描引擎，专注解决流程、门禁、证据、漏洞台账和复测闭环。

## 功能

- **10 步闭环**：授权 → 资产 → 账号 → 指纹 → 编排 → 扫描 → 验证 → 定级 → 报告 → 复测。
- **五条硬门禁**：无授权不扫、资产不清不扫、生产不限速不扫、未复现不写报告、未复测不关闭。
- **30 项检查表**：每步 3 项，支持“通过 / 不通过 / N/A”、证据编号和步骤备注。
- **第 6 步顺序**：6.1–6.9 内置在流程库和页面说明中。
- **漏洞台账**：严重/高/中/低/信息，支持负责人、期限、状态流转和删除。
- **门禁校验**：前一步未完成、检查项未通过、第 9 步缺少责任人/期限、第 10 步存在未关闭高危，都不能过关。
- **质量指标**：项目数、未关闭高危、逾期漏洞、平均进度、等级分布、状态分布。
- **演示数据**：首次启动自动生成 3 个项目、7 条漏洞，打开即可看效果。
- **导出**：单个项目一键导出 JSON（项目、步骤、检查项、漏洞、活动记录）。
- **零依赖**：不需要 npm、pip、数据库服务；Python 3.10+ 直接跑。

## 快速开始

```bash
python app.py
```

打开 <http://127.0.0.1:8765>。

要求：Python 3.10+，无第三方依赖。

### Windows EXE

已提供 `dist/WebScanSOP.exe`（Windows 10/11 x64，单文件，无需安装 Python）。

- 双击启动：弹出启动器窗口，自动打开浏览器。
- 数据文件：`%APPDATA%\WebScanSOP\sop.db`（不会写进 Program Files）。
- 停止服务：关闭启动器窗口，或点“停止服务并退出”。
- 无界面模式：`WebScanSOP.exe --server --port 8765`。

EXE 未做代码签名，Windows SmartScreen 可能提示“未知发布者”，选择“更多信息 → 仍要运行”即可。  
如不放心，可按下面步骤自行构建。

重新构建 EXE：

```powershell
python -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File scripts/build_exe.ps1
```

构建产物在 `dist\WebScanSOP.exe`。

### Docker

```bash
docker compose up --build
```

打开 <http://127.0.0.1:8765>。数据持久化在 `./data/sop.db`。

## 上传到 GitHub

```bash
cd webscan-sop
git init
git add .
git commit -m "feat: WebScan SOP v1.1"
git branch -M main
git remote add origin https://github.com/<your-name>/webscan-sop.git
git push -u origin main
```

仓库已包含 `.github/workflows/ci.yml`，push 后会自动跑 7 个 API 测试和启动检查。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `HOST` | `127.0.0.1` | 监听地址；Docker 中设为 `0.0.0.0` |
| `PORT` | `8765` | 监听端口 |
| `DB_PATH` | `./sop.db` | SQLite 路径 |
| `SEED_DEMO` | `1` | 设为 `0` 可关闭演示数据 |

## 截图 / 页面

- **总览**：项目进度、未关闭高危、逾期漏洞、10 步速查。
- **项目**：左侧 10 步导航，右侧检查表 / 漏洞台账 / 活动记录。
- **SOP 流程库**：10 步说明、6.1–6.9 顺序、模板、参数基线。
- **质量指标**：等级分布、状态分布、项目进度表。

> 仓库不包含截图，避免放与代码不同步的图片；启动后即可看到完整界面。

## 技术架构

```text
Browser (vanilla JS SPA)
        │  fetch JSON
        ▼
Python http.server  ──►  SQLite (sop.db)
        │
        └── static/index.html, app.js, style.css
```

设计取舍：

- **标准库优先**：降低部署和审计成本，GitHub 上 clone 即跑。
- **单文件后端**：`app.py` 包含路由、SOP 定义、SQLite 访问和种子数据，便于阅读和二次开发。
- **无构建前端**：没有 Node 工具链，适合内网、离线、投标演示环境。
- **单用户/本地优先**：默认只监听 `127.0.0.1`，不内置登录和多租户；生产化部署需自行加反向代理、认证和权限。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/projects` | 项目列表（含进度、未关闭高危） |
| POST | `/api/projects` | 创建项目，自动初始化 10 步/30 项检查 |
| GET | `/api/projects/{id}` | 项目详情（步骤、检查项、漏洞、门禁） |
| PATCH | `/api/projects/{id}` | 更新项目信息 |
| GET | `/api/projects/{id}/export` | 导出项目 JSON |
| PATCH | `/api/checks/{id}` | 更新检查结果/证据/备注 |
| PATCH | `/api/projects/{id}/steps/{no}` | 保存步骤备注 |
| POST | `/api/projects/{id}/steps/{no}/complete` | 完成步骤（服务端校验门禁） |
| POST | `/api/projects/{id}/findings` | 新增漏洞 |
| PATCH | `/api/findings/{id}` | 更新漏洞 |
| DELETE | `/api/findings/{id}` | 删除漏洞 |
| GET | `/api/metrics` | 全局指标 |
| GET | `/api/activity` | 最近活动 |
| GET | `/api/library` | SOP 流程库内容 |

详细请求/响应见 [docs/api.md](docs/api.md)。

## 目录结构

```text
webscan-sop/
├── app.py                  # 后端 + SOP 定义 + SQLite
├── static/
│   ├── index.html          # SPA 外壳
│   ├── app.js              # 路由、渲染、交互
│   └── style.css           # 设计系统与响应式
├── tests/
│   └── test_api.py         # 7 个 API 测试
├── docs/
│   ├── api.md
│   └── sop.md
├── assets/app.ico          # 应用图标
├── packaging/version_info.txt
├── scripts/build_exe.ps1   # Windows EXE 构建脚本
├── WebScanSOP.spec         # PyInstaller 配置
├── .github/workflows/ci.yml
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── Makefile
├── SECURITY.md
├── .env.example
└── LICENSE
```

## 测试

```bash
python -m unittest discover -s tests -v
```

覆盖：健康检查与首页、种子项目、创建项目初始化 10 步/30 项检查、门禁拦截、完成步骤、漏洞新增、步骤备注、指标接口。

## 门禁规则

服务端在 `POST /api/projects/{id}/steps/{no}/complete` 统一校验，前端无法绕过：

1. 上一步未完成 → 阻断。
2. 当前步骤存在 `pending` / `fail` 检查项 → 阻断。
3. 第 1 步检查项 `1.1` 未通过 → 阻断（授权书必须确认）。
4. 第 9 步存在漏洞缺少负责人或期限 → 阻断。
5. 第 10 步存在未关闭的严重/高危漏洞 → 阻断。

第 10 步完成后项目自动置为“已完成”。

## 安全边界

- 本项目是**流程管理工具**，不发起扫描、不包含漏洞利用代码。
- 仅用于已获得书面授权的安全测试与防御性建设。
- 默认只监听 `127.0.0.1`；不要直接暴露到公网。
- 演示数据是虚构的，不包含真实客户信息。
- 生产化需要：反向代理 + HTTPS、身份认证、RBAC、审计日志、数据库备份。

## Roadmap

- [ ] 项目模板导入/导出（YAML）
- [ ] Jira / 飞书 / 企业微信工单同步
- [ ] 多用户与 RBAC
- [ ] 资产台账与子域名导入
- [ ] 报告导出 PDF/Word
- [ ] 定时扫描任务与变更触发

## License

MIT © 2026 WebScan SOP contributors
