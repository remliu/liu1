(() => {
  'use strict';

  const state = {
    route: 'dashboard',
    projects: [],
    metrics: null,
    activity: [],
    project: null,
    selectedStep: null,
    tab: 'checklist',
    library: null,
    search: '',
    loading: true,
  };

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
  const view = () => $('#view');

  const PAGE_META = {
    dashboard: ['WORKSPACE', '总览'],
    projects: ['PROJECTS', '项目'],
    library: ['SOP LIBRARY', 'SOP 流程库'],
    metrics: ['QUALITY', '质量指标'],
    about: ['ABOUT', '关于与使用'],
    project: ['PROJECT', '项目详情'],
  };

  // ---------------------------------------------------------------------
  // helpers
  // ---------------------------------------------------------------------
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));

  const pad = (n) => String(n).padStart(2, '0');

  function todayISO(offset = 0) {
    const d = new Date();
    d.setDate(d.getDate() + offset);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function formatDate(value) {
    if (!value) return '—';
    const s = String(value).slice(0, 10);
    return s.replace(/-/g, '.');
  }

  function shortDate(value) {
    if (!value) return '—';
    const s = String(value).slice(5, 10);
    return s.replace('-', '.');
  }

  function severityClass(sev) {
    return { 严重: 'critical', 高: 'high', 中: 'medium', 低: 'low', 信息: 'info' }[sev] || 'info';
  }

  function severityBadge(sev) {
    return `<span class="badge sev-${severityClass(sev)}">${esc(sev)}</span>`;
  }

  function statusClass(status) {
    if (['已完成', '已关闭'].includes(status)) return 'st-done';
    if (['进行中', '修复中'].includes(status)) return 'st-running';
    if (['待复测', '待确认'].includes(status)) return 'st-warn';
    if (['风险接受'].includes(status)) return 'st-pending';
    return 'st-pending';
  }

  function statusBadge(status) {
    return `<span class="badge ${statusClass(status)}">${esc(status)}</span>`;
  }

  function stepStatusBadge(step) {
    if (step.status === 'done') return '<span class="badge st-done">已完成</span>';
    if (step.blockers?.length) return '<span class="badge st-warn">门禁未过</span>';
    return '<span class="badge st-running">进行中</span>';
  }

  function toast(message, type = '') {
    const root = $('#toast-root');
    if (!root) return;
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    root.appendChild(el);
    setTimeout(() => el.remove(), 3600);
  }

  async function api(path, options = {}) {
    const opts = { credentials: 'same-origin', ...options };
    if (options.body && !opts.headers) {
      opts.headers = { 'Content-Type': 'application/json' };
    }
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch (_) { /* no body */ }
    if (!res.ok) {
      const err = new Error((data && data.error) || `请求失败（${res.status}）`);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function setPageMeta(page) {
    const [eyebrow, title] = PAGE_META[page] || PAGE_META.dashboard;
    $('#page-eyebrow').textContent = eyebrow;
    $('#page-title').textContent = title;
    $$('.nav-item').forEach((el) => {
      const nav = el.dataset.nav;
      el.classList.toggle('active', nav === page || (page === 'project' && nav === 'projects'));
    });
  }

  function setLoading() {
    view().innerHTML = '<div class="loading-state"><div class="spinner"></div><p>正在加载工作台…</p></div>';
  }

  function showError(err) {
    view().innerHTML = `<div class="card"><div class="empty">
      <div class="empty-ico">!</div><h3>加载失败</h3>
      <p>${esc(err.message || err)}</p>
      <p style="margin-top:12px"><button class="btn" data-action="retry">重新加载</button></p>
    </div></div>`;
  }

  function emptyState(icon, title, text, action = '') {
    return `<div class="empty"><div class="empty-ico">${icon}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>${action}</div>`;
  }

  function progressBar(value, done = false) {
    const p = Math.max(0, Math.min(100, Number(value) || 0));
    return `<div class="progress ${done ? 'done' : ''}"><span style="width:${p}%"></span></div>`;
  }

  // ---------------------------------------------------------------------
  // routing
  // ---------------------------------------------------------------------
  let routeSeq = 0;

  function parseRoute() {
    const raw = (location.hash || '#/dashboard').replace(/^#\/?/, '');
    const parts = raw.split('/').filter(Boolean);
    return { page: parts[0] || 'dashboard', id: parts[1] || null };
  }

  async function route() {
    const seq = ++routeSeq;
    const { page, id } = parseRoute();
    state.route = page;
    setPageMeta(page);
    setLoading();
    try {
      if (page === 'dashboard') await loadDashboard(seq);
      else if (page === 'projects') await loadProjects(seq);
      else if (page === 'project') await loadProject(seq, id);
      else if (page === 'library') await loadLibrary(seq);
      else if (page === 'metrics') await loadMetrics(seq);
      else if (page === 'about') renderAbout();
      else if (seq === routeSeq) view().innerHTML = emptyState('?', '页面不存在', '请从左侧导航进入。');
    } catch (err) {
      if (seq === routeSeq) showError(err);
    }
  }

  // ---------------------------------------------------------------------
  // data loaders
  // ---------------------------------------------------------------------
  async function loadDashboard(seq) {
    const [metrics, projects, activity] = await Promise.all([
      api('/api/metrics'), api('/api/projects'), api('/api/activity'),
    ]);
    if (seq !== routeSeq) return;
    state.metrics = metrics;
    state.projects = projects;
    state.activity = activity;
    renderDashboard();
  }

  async function loadProjects(seq) {
    const projects = await api('/api/projects');
    if (seq !== routeSeq) return;
    state.projects = projects;
    renderProjects();
  }

  async function loadProject(seq, id) {
    const pid = Number(id);
    if (!pid) throw new Error('项目 ID 不合法');
    const [project, activity] = await Promise.all([
      api(`/api/projects/${pid}`), api('/api/activity'),
    ]);
    if (seq !== routeSeq) return;
    state.project = project;
    state.activity = activity.filter((a) => a.project_id === pid);
    const steps = project.steps || [];
    const valid = steps.some((s) => s.step_no === Number(state.selectedStep));
    if (!valid || state.projectId !== pid) {
      const next = steps.find((s) => s.status !== 'done' && !s.locked) || steps.find((s) => s.status !== 'done') || steps[0];
      state.selectedStep = next ? next.step_no : 1;
      state.tab = 'checklist';
    }
    state.projectId = pid;
    renderProject();
  }

  async function loadLibrary(seq) {
    const library = await api('/api/library');
    if (seq !== routeSeq) return;
    state.library = library;
    renderLibrary();
  }

  async function loadMetrics(seq) {
    const [metrics, projects] = await Promise.all([api('/api/metrics'), api('/api/projects')]);
    if (seq !== routeSeq) return;
    state.metrics = metrics;
    state.projects = projects;
    renderMetrics();
  }

  async function refreshProject() {
    if (!state.project?.id) return;
    const [project, activity] = await Promise.all([
      api(`/api/projects/${state.project.id}`), api('/api/activity'),
    ]);
    state.project = project;
    state.activity = activity.filter((a) => a.project_id === project.id);
    renderProject();
  }

  // ---------------------------------------------------------------------
  // dashboard
  // ---------------------------------------------------------------------
  function projectCard(p) {
    const done = p.status === '已完成' || p.progress >= 100;
    const initial = (p.owner || '?').trim().slice(0, 1).toUpperCase();
    return `<a class="project-card fade-in ${done ? 'is-done' : ''}" href="#/project/${p.id}">
      <span class="project-stripe"></span>
      <div class="project-top">
        <div><div class="project-code">${esc(p.code)}</div>
        <div class="project-name">${esc(p.name)}</div>
        <div class="project-client">${esc(p.client || '未填写客户')}</div></div>
        ${statusBadge(p.status)}
      </div>
      <div class="project-mid">
        <div class="project-meta"><span>执行进度</span><span><b>${p.done_steps}</b> / 10 · ${p.progress}%</span></div>
        ${progressBar(p.progress, done)}
      </div>
      <div class="project-bottom">
        <span class="project-owner"><span class="avatar">${esc(initial)}</span>${esc(p.owner || '未指定')}</span>
        <span class="small">${p.open_high ? `<span class="badge sev-critical">${p.open_high} 个高危</span>` : (p.due_date ? `截止 ${formatDate(p.due_date)}` : '无未关闭高危')}</span>
      </div>
    </a>`;
  }

  function riskDonut(sev) {
    const s = sev || {};
    const critical = s['严重'] || 0;
    const high = s['高'] || 0;
    const medium = s['中'] || 0;
    const low = (s['低'] || 0) + (s['信息'] || 0);
    const total = critical + high + medium + low;
    const p1 = total ? critical / total * 100 : 0;
    const p2 = p1 + (total ? high / total * 100 : 0);
    const p3 = p2 + (total ? (medium + low) / total * 100 : 0);
    return `<div class="risk-donut" style="--p1:${p1}%;--p2:${p2}%;--p3:${p3}%${total ? '' : ';background:#e8eef5'}">
      <div class="risk-center"><b>${total}</b><span>漏洞总数</span></div>
    </div>
    <div class="risk-legend">
      <span><i class="sev-dot critical"></i>严重 <b>${critical}</b></span>
      <span><i class="sev-dot high"></i>高 <b>${high}</b></span>
      <span><i class="sev-dot medium"></i>中 <b>${medium}</b></span>
      <span><i class="sev-dot low"></i>低/信息 <b>${low}</b></span>
    </div>`;
  }

  function renderDashboard() {
    const m = state.metrics || {};
    const projects = state.projects || [];
    const upcoming = m.upcoming || [];
    const recent = projects.slice(0, 6);
    view().innerHTML = `<div class="fade-in">
      <section class="hero">
        <div class="hero-content">
          <span class="tag">WEBSCAN SOP · 10-STEP WORKFLOW</span>
          <h1>把漏洞扫描流程，<br><em>变成可执行的项目</em></h1>
          <p>单项目 10 步闭环 · 第 6 步 6.1–6.9 扫描顺序 · 五条硬门禁。每个项目都有检查表、证据、漏洞台账和复测闭环，不再靠“扫完再说”。</p>
          <div class="hero-actions">
            <button class="btn btn-primary" data-action="new-project"><svg class="ico"><use href="#i-plus"/></svg>新建扫描项目</button>
            <a class="btn btn-ghost" href="#/library">查看 SOP 流程库 <svg class="ico"><use href="#i-arrow"/></svg></a>
          </div>
        </div>
        <div class="hero-side">
          <div class="hero-stat"><b>10</b><span>步骤闭环</span></div>
          <div class="hero-stat"><b>30</b><span>检查项</span></div>
          <div class="hero-stat"><b>5</b><span>硬门禁</span></div>
        </div>
      </section>

      <div class="metric-grid">
        <div class="metric info">
          <div class="metric-top"><span class="metric-ico"><svg class="ico"><use href="#i-folder"/></svg></span><span class="label">进行中项目</span></div>
          <div class="num">${m.active_projects || 0}<small>/ ${m.total_projects || 0}</small></div><div class="hint">已完成 ${m.completed_projects || 0} 个</div>
        </div>
        <div class="metric danger">
          <div class="metric-top"><span class="metric-ico"><svg class="ico"><use href="#i-shield"/></svg></span><span class="label">未关闭高危</span></div>
          <div class="num">${m.open_high || 0}<small>个</small></div><div class="hint">严重 + 高，未关闭/未接受</div>
        </div>
        <div class="metric">
          <div class="metric-top"><span class="metric-ico"><svg class="ico"><use href="#i-chart"/></svg></span><span class="label">平均执行进度</span></div>
          <div class="num">${m.avg_progress || 0}<small>%</small></div><div class="hint">${m.checks_done || 0} / ${m.checks_total || 0} 项检查已完成</div>
        </div>
        <div class="metric warn">
          <div class="metric-top"><span class="metric-ico"><svg class="ico"><use href="#i-help"/></svg></span><span class="label">逾期漏洞</span></div>
          <div class="num">${m.overdue || 0}<small>个</small></div><div class="hint">超过期限且未关闭</div>
        </div>
      </div>

      <div class="dashboard-split">
        <div class="dashboard-main">
          <div class="section-head"><div><h2>项目</h2><p>按 10 步流程推进，门禁通过才能进入下一步。</p></div><a href="#/projects">全部项目 →</a></div>
          ${recent.length ? `<div class="project-grid dashboard-projects">${recent.map(projectCard).join('')}</div>` : `<div class="card">${emptyState('□', '还没有项目', '新建一个项目，开始跑 10 步流程。', '<button class="btn btn-primary" data-action="new-project" style="margin-top:12px">新建项目</button>')}</div>`}
        </div>
        <aside class="dashboard-rail">
          <div class="card risk-panel">
            <div class="panel-mini-head"><h3>风险概览</h3><a href="#/metrics">详情 →</a></div>
            ${riskDonut(m.severity || {})}
          </div>
          <div class="card quick-panel">
            <div class="panel-mini-head"><h3>快捷入口</h3></div>
            <button class="quick-link" data-action="new-project"><span class="quick-ico"><svg class="ico"><use href="#i-plus"/></svg></span><span><b>新建扫描项目</b><small>初始化 10 步 / 30 项检查</small></span></button>
            <a class="quick-link" href="#/library"><span class="quick-ico"><svg class="ico"><use href="#i-book"/></svg></span><span><b>SOP 流程库</b><small>10 步 + 6.1–6.9 顺序</small></span></a>
            <a class="quick-link" href="#/metrics"><span class="quick-ico"><svg class="ico"><use href="#i-chart"/></svg></span><span><b>质量指标</b><small>覆盖率、误报、复测与 MTTR</small></span></a>
          </div>
        </aside>
      </div>

      <div class="section-head"><div><h2>待处理高危</h2><p>按等级和期限排序，优先处理会直接影响数据的项。</p></div><a href="#/metrics">质量指标 →</a></div>
      <div class="card table-card">
        ${upcoming.length ? `<div class="table-wrap"><table class="data">
          <thead><tr><th>等级</th><th>漏洞</th><th>项目</th><th>负责人</th><th>期限</th></tr></thead>
          <tbody>${upcoming.map((f) => `<tr>
            <td>${severityBadge(f.severity)}</td>
            <td class="title-cell">${esc(f.title)}</td>
            <td>${esc(f.project_name)}</td>
            <td>${esc(f.owner || '未指定')}</td>
            <td>${formatDate(f.due_date)}</td>
          </tr>`).join('')}</tbody>
        </table></div>` : emptyState('✓', '没有待处理高危', '当前项目的高危漏洞都已关闭或风险接受。')}
      </div>

      <div class="section-head"><div><h2>10 步速查</h2><p>从授权到复测，顺序固定；第 6 步内部再按 6.1–6.9 执行。</p></div><a href="#/library">完整说明 →</a></div>
      <div class="step-strip">
        ${(state.library?.steps || DEFAULT_STEPS).map((s) => `<div class="step-chip">
          <span class="step-chip-no">${pad(s.no)}</span>
          <div><b>${esc(s.name)}</b><small>${esc(s.gate)}</small></div>
        </div>`).join('')}
      </div>
    </div>`;
  }

  // ---------------------------------------------------------------------
  // projects list
  // ---------------------------------------------------------------------
  function renderProjects() {
    view().innerHTML = `<div class="fade-in">
      <div class="section-head" style="margin-top:0">
        <div><h2>全部项目</h2><p>共 ${state.projects.length} 个项目；点击进入执行检查表。</p></div>
        <div style="display:flex;gap:8px;align-items:center">
          <div style="position:relative"><svg class="ico" style="position:absolute;left:10px;top:9px;color:#94a3b8;width:15px;height:15px"><use href="#i-search"/></svg>
            <input id="project-search" data-search placeholder="搜索项目 / 客户 / 编号" value="${esc(state.search)}" style="border:1px solid #e2e8f0;border-radius:9px;padding:8px 10px 8px 32px;font-size:12px;width:230px;background:#fff">
          </div>
          <button class="btn btn-primary" data-action="new-project"><svg class="ico"><use href="#i-plus"/></svg>新建</button>
        </div>
      </div>
      <div id="project-grid">${projectGrid()}</div>
    </div>`;
  }

  function projectGrid() {
    const q = state.search.trim().toLowerCase();
    const list = state.projects.filter((p) => !q || [p.name, p.client, p.code, p.owner].some((x) => String(x || '').toLowerCase().includes(q)));
    if (!list.length) return `<div class="card">${emptyState('□', '没有匹配的项目', q ? '换个关键词试试。' : '新建一个项目，开始跑 10 步流程。')}</div>`;
    return `<div class="project-grid">${list.map(projectCard).join('')}</div>`;
  }

  function refreshProjectGrid() {
    const el = $('#project-grid');
    if (el) el.innerHTML = projectGrid();
  }

  // ---------------------------------------------------------------------
  // project detail
  // ---------------------------------------------------------------------
  function renderProject() {
    const p = state.project;
    if (!p) return;
    const step = p.steps.find((s) => s.step_no === Number(state.selectedStep)) || p.steps[0];
    state.selectedStep = step.step_no;
    view().innerHTML = `<div class="fade-in">
      <div class="card project-head">
        <div class="progress-ring" style="--p:${p.progress}"><span>${p.progress}%</span></div>
        <div class="project-head-main">
          <div class="project-code">${esc(p.code)}</div>
          <h2>${esc(p.name)}</h2>
          <div class="meta">
            <span>客户 <b>${esc(p.client || '—')}</b></span>
            <span>负责人 <b>${esc(p.owner || '—')}</b></span>
            <span>周期 <b>${formatDate(p.start_date)} — ${formatDate(p.due_date)}</b></span>
            <span>${statusBadge(p.status)}</span>
          </div>
        </div>
        <div class="project-head-actions">
          <a class="btn btn-sm" href="/api/projects/${p.id}/export"><svg class="ico"><use href="#i-download"/></svg>导出</a>
          <button class="btn btn-sm" data-action="refresh-project">刷新</button>
          <a class="btn btn-sm btn-ghost" href="#/projects">返回</a>
        </div>
      </div>
      <div class="project-layout">
        <aside class="card step-rail">
          <div class="rail-head"><strong>执行进度</strong><span>${p.steps.filter((s) => s.status === 'done').length} / 10</span></div>
          ${p.steps.map(stepItem).join('')}
        </aside>
        <section class="card step-panel">
          <div class="panel-head">
            <div class="panel-title">
              <div class="kicker">STEP ${pad(step.step_no)} / 10</div>
              <h3>${esc(step.definition.name)}</h3>
              <p>${esc(step.definition.intro)}</p>
            </div>
            ${stepStatusBadge(step)}
          </div>
          <div class="tabs">
            <button class="tab ${state.tab === 'checklist' ? 'active' : ''}" data-action="tab" data-tab="checklist">检查表</button>
            <button class="tab ${state.tab === 'findings' ? 'active' : ''}" data-action="tab" data-tab="findings">漏洞台账 (${p.findings.length})</button>
            <button class="tab ${state.tab === 'activity' ? 'active' : ''}" data-action="tab" data-tab="activity">活动记录</button>
          </div>
          <div class="panel-body">
            ${state.tab === 'checklist' ? checklistHtml(step) : state.tab === 'findings' ? findingsHtml() : activityHtml()}
          </div>
          ${state.tab === 'checklist' ? checklistFoot(step) : ''}
        </section>
      </div>
    </div>`;
  }

  function stepItem(step) {
    const active = step.step_no === Number(state.selectedStep);
    return `<button class="step-item ${active ? 'active' : ''} ${step.status === 'done' ? 'done' : ''} ${step.locked ? 'locked' : ''}" data-action="select-step" data-step="${step.step_no}">
      <span class="step-dot">${step.status === 'done' ? '✓' : pad(step.step_no)}</span>
      <span class="step-main"><span class="step-name">${esc(step.definition.name)}</span>
        <span class="step-sub">${step.locked ? '<svg class="ico" style="width:11px;height:11px"><use href="#i-lock"/></svg> 上一步未完成' : esc(step.definition.owner)}</span>
      </span>
      ${step.status === 'done' ? '<span class="step-check">✓</span>' : ''}
    </button>`;
  }

  function checklistHtml(step) {
    const done = step.status === 'done';
    let gate;
    if (done) gate = `<div class="gate done"><svg class="ico"><use href="#i-check"/></svg><div><strong>本步骤已完成</strong> · ${esc(step.completed_at || '')}</div></div>`;
    else if (step.blockers?.length) gate = `<div class="gate block"><svg class="ico"><use href="#i-lock"/></svg><div><strong>门禁未通过：</strong><ul>${step.blockers.map((b) => `<li>${esc(b)}</li>`).join('')}</ul></div></div>`;
    else gate = `<div class="gate ok"><svg class="ico"><use href="#i-check"/></svg><div><strong>门禁已满足</strong> · 可以完成本步骤。</div></div>`;

    const rows = step.checks.map((c) => {
      const disabled = step.locked ? 'disabled' : '';
      return `<div class="check-row ${c.result}">
        <div class="check-main">
          <div class="check-title"><span class="check-no">${esc(c.item_no)}</span><span>${esc(c.label)}</span></div>
          <div class="check-hint">证据：${esc(c.evidence_hint || '—')}</div>
          <input class="evidence" data-evidence="${c.id}" value="${esc(c.evidence || '')}" placeholder="填写证据编号、链接或备注，失焦自动保存" ${disabled}>
        </div>
        <div class="seg" role="group">
          <button class="seg-btn pass ${c.result === 'pass' ? 'active' : ''}" data-action="set-check" data-check="${c.id}" data-result="pass" ${disabled}>通过</button>
          <button class="seg-btn fail ${c.result === 'fail' ? 'active' : ''}" data-action="set-check" data-check="${c.id}" data-result="fail" ${disabled}>不通过</button>
          <button class="seg-btn na ${c.result === 'na' ? 'active' : ''}" data-action="set-check" data-check="${c.id}" data-result="na" ${disabled}>N/A</button>
        </div>
      </div>`;
    }).join('');

    return `${gate}<div class="check-list">${rows}</div>
      <div class="notes-block"><label>步骤备注</label>
        <textarea class="notes" data-notes="${step.step_no}" placeholder="记录负责人、时间、工具、异常情况或需要交接的信息…" ${step.locked ? 'disabled' : ''}>${esc(step.notes || '')}</textarea>
      </div>`;
  }

  function checklistFoot(step) {
    const passed = step.checks.filter((c) => ['pass', 'na'].includes(c.result)).length;
    const done = step.status === 'done';
    const disabled = done || !step.can_complete ? 'disabled' : '';
    return `<div class="panel-foot">
      <div class="hint">${passed} / ${step.checks.length} 项已完成 · ${step.definition.gate}</div>
      <div class="actions">
        <button class="btn btn-sm" data-action="save-notes" data-step="${step.step_no}" ${step.locked ? 'disabled' : ''}>保存备注</button>
        <button class="btn btn-sm btn-teal" data-action="complete-step" data-step="${step.step_no}" ${disabled}>${done ? '已完成' : '完成本步骤'}</button>
      </div>
    </div>`;
  }

  function findingsHtml() {
    const p = state.project;
    if (!p.findings.length) {
      return `${emptyState('◇', '还没有漏洞记录', '扫描和人工验证确认后，把问题登记到这里，才能做定级、工单和复测。', '<button class="btn btn-primary" data-action="add-finding" style="margin-top:12px"><svg class="ico"><use href="#i-plus"/></svg>新增漏洞</button>')}`;
    }
    return `<div class="finding-toolbar"><div><h4>${p.findings.length} 个问题</h4><p>状态可直接修改；复测通过后再关闭。</p></div><button class="btn btn-sm btn-primary" data-action="add-finding"><svg class="ico"><use href="#i-plus"/></svg>新增</button></div>
    <div class="table-wrap"><table class="data"><thead><tr><th>等级</th><th>漏洞</th><th>位置</th><th>负责人</th><th>期限</th><th>状态</th><th></th></tr></thead><tbody>
      ${p.findings.map((f) => `<tr>
        <td>${severityBadge(f.severity)}</td>
        <td class="title-cell">${esc(f.title)}</td>
        <td><code>${esc(f.endpoint || '—')}</code></td>
        <td>${esc(f.owner || '未指定')}</td>
        <td>${formatDate(f.due_date)}</td>
        <td><select class="status-select" data-finding-status="${f.id}">
          ${['待确认', '已确认', '修复中', '待复测', '已关闭', '风险接受'].map((s) => `<option value="${s}" ${f.status === s ? 'selected' : ''}>${s}</option>`).join('')}
        </select></td>
        <td><button class="btn btn-sm btn-danger" data-action="delete-finding" data-id="${f.id}">删除</button></td>
      </tr>`).join('')}
    </tbody></table></div>`;
  }

  function activityHtml() {
    if (!state.activity.length) return emptyState('◷', '还没有活动记录', '完成检查项、更新漏洞或完成步骤后，会在这里留下记录。');
    return `<ul class="timeline">${state.activity.map((a) => `<li>
      <div class="when">${esc((a.created_at || '').slice(5, 16))}</div>
      <div class="what"><strong>${esc(a.action)}</strong> · ${esc(a.detail || '')}</div>
    </li>`).join('')}</ul>`;
  }

  // ---------------------------------------------------------------------
  // library
  // ---------------------------------------------------------------------
  function renderLibrary() {
    const lib = state.library;
    if (!lib) return;
    view().innerHTML = `<div class="fade-in">
      <div class="lib-hero"><h2>SOP 流程库</h2><p>单项目 10 步通用流程 + 第 6 步 6.1–6.9 扫描顺序。这套流程不绑定工具、语言和框架；换扫描器只改配置，流程不变。</p></div>
      <div class="section-head" style="margin-top:0"><div><h2>10 步通用流程</h2><p>顺序执行，前一步门禁未通过，不进入下一步。</p></div></div>
      <div class="lib-grid">${lib.steps.map((s) => `<div class="card lib-card">
        <h3><span class="no">STEP ${pad(s.no)}</span>${esc(s.name)}</h3>
        <p>${esc(s.intro)}</p>
        <ul class="lib-list" style="margin-top:8px">${s.checks.map((c) => `<li><b>□</b><span>${esc(c[0])}<br><span class="small">证据：${esc(c[1])}</span></span></li>`).join('')}</ul>
        <p style="margin-top:8px"><span class="badge st-warn">门禁</span> ${esc(s.gate)} · 责任人 ${esc(s.owner)}</p>
      </div>`).join('')}</div>

      <div class="section-head"><div><h2>第 6 步内部扫描顺序</h2><p>先只读后写入、先低影响后高风险、先未登录后登录、先通用后业务。</p></div></div>
      <div class="table-wrap"><table class="data"><thead><tr><th>顺序</th><th>先测什么</th><th>典型内容</th><th>为什么排这里</th></tr></thead><tbody>
        ${lib.order.map((o) => `<tr><td><code>${esc(o[0])}</code></td><td class="title-cell">${esc(o[1])}</td><td>${esc(o[2])}</td><td>${esc(o[3])}</td></tr>`).join('')}
      </tbody></table></div>

      <div class="section-head"><div><h2>通用扫描模板</h2><p>80% 的站点用同一套基线，剩下 20% 按指纹加专项包。</p></div></div>
      <div class="table-wrap"><table class="data"><thead><tr><th>模板</th><th>适用</th><th>必含内容</th><th>加载条件</th></tr></thead><tbody>
        ${lib.templates.map((t) => `<tr><td class="title-cell">${esc(t[0])}</td><td>${esc(t[1])}</td><td>${esc(t[2])}</td><td>${esc(t[3])}</td></tr>`).join('')}
      </tbody></table></div>

      <div class="section-head"><div><h2>参数基线</h2><p>生产从低强度开始，观察 CPU、内存、错误率后再加量。</p></div></div>
      <div class="card" style="padding:8px 18px"><table class="mini-table">${lib.params.map((p) => `<tr><td>${esc(p[0])}</td><td><b>${esc(p[1])}</b><br><span class="small">${esc(p[2])}</span></td></tr>`).join('')}</table></div>
    </div>`;
  }

  // ---------------------------------------------------------------------
  // metrics
  // ---------------------------------------------------------------------
  function renderMetrics() {
    const m = state.metrics || {};
    const sev = m.severity || {};
    const max = Math.max(1, ...Object.values(sev));
    view().innerHTML = `<div class="fade-in">
      <div class="section-head" style="margin-top:0"><div><h2>质量指标</h2><p>别只看漏洞数量，看覆盖率、误报率、复现率、复测率和 MTTR。</p></div></div>
      <div class="metric-grid">
        <div class="metric"><div class="label">资产/项目</div><div class="num">${m.total_projects || 0}<small>个</small></div><div class="hint">进行中 ${m.active_projects || 0} · 已完成 ${m.completed_projects || 0}</div></div>
        <div class="metric danger"><div class="label">未关闭高危</div><div class="num">${m.open_high || 0}<small>个</small></div><div class="hint">严重 + 高</div></div>
        <div class="metric warn"><div class="label">逾期漏洞</div><div class="num">${m.overdue || 0}<small>个</small></div><div class="hint">超过期限未关闭</div></div>
        <div class="metric"><div class="label">平均进度</div><div class="num">${m.avg_progress || 0}<small>%</small></div><div class="hint">${m.checks_done || 0} / ${m.checks_total || 0} 项检查</div></div>
      </div>

      <div class="lib-grid" style="margin-top:16px">
        <div class="card lib-card"><h3>漏洞等级分布</h3>
          ${['严重', '高', '中', '低', '信息'].map((s) => `<div style="display:grid;grid-template-columns:44px 1fr 34px;gap:8px;align-items:center;margin:10px 0">
            <span class="small">${s}</span><div class="progress"><span style="width:${Math.round((sev[s] || 0) / max * 100)}%;background:${s === '严重' ? '#dc2626' : s === '高' ? '#ea580c' : s === '中' ? '#d97706' : '#16a34a'}"></span></div><span class="small" style="text-align:right">${sev[s] || 0}</span>
          </div>`).join('')}
        </div>
        <div class="card lib-card"><h3>状态分布</h3>
          <table class="mini-table">${['待确认', '已确认', '修复中', '待复测', '已关闭', '风险接受'].map((s) => `<tr><td>${s}</td><td style="text-align:right">${m.status?.[s] || 0} 个</td></tr>`).join('')}</table>
        </div>
      </div>

      <div class="section-head"><div><h2>项目进度</h2><p>按执行进度排序，优先关注长期停在同一步的项目。</p></div></div>
      <div class="table-wrap"><table class="data"><thead><tr><th>项目</th><th>客户</th><th>负责人</th><th>进度</th><th>未关闭高危</th><th>截止</th><th>状态</th></tr></thead><tbody>
        ${state.projects.map((p) => `<tr>
          <td><a class="title-cell" href="#/project/${p.id}">${esc(p.name)}</a><div class="small mono">${esc(p.code)}</div></td>
          <td>${esc(p.client || '—')}</td><td>${esc(p.owner || '—')}</td>
          <td style="min-width:130px"><div style="display:flex;gap:8px;align-items:center"><div class="progress" style="flex:1"><span style="width:${p.progress}%"></span></div><span class="small">${p.progress}%</span></div></td>
          <td>${p.open_high ? `<span class="badge sev-critical">${p.open_high}</span>` : '<span class="muted">0</span>'}</td>
          <td>${formatDate(p.due_date)}</td><td>${statusBadge(p.status)}</td>
        </tr>`).join('')}
      </tbody></table></div>
    </div>`;
  }

  // ---------------------------------------------------------------------
  // about
  // ---------------------------------------------------------------------
  function renderAbout() {
    view().innerHTML = `<div class="fade-in about-grid">
      <div class="card prose">
        <h2>关于 WebScan SOP</h2>
        <p>这是一个把「单项目 10 步通用流程 + 第 6 步 6.1–6.9 扫描顺序」做成可执行项目的轻量工作台。它不替代扫描器，也不替代渗透测试；它解决的是流程、证据、门禁和闭环。</p>
        <h3>它解决什么问题</h3>
        <ul>
          <li>项目做到哪一步、谁负责、门禁有没有过，一眼能看到。</li>
          <li>每项检查有结果、有证据，不能只写“已扫”。</li>
          <li>漏洞有台账、有负责人、有期限、有复测。</li>
          <li>模板、参数、第 6 步顺序固化成团队基线。</li>
        </ul>
        <h3>不做什么</h3>
        <ul>
          <li>不内置扫描引擎，不自动攻击目标。</li>
          <li>不替代代码审计、业务逻辑测试和红队。</li>
          <li>不承诺 100% 覆盖；覆盖率要靠资产治理和人工补测。</li>
        </ul>
        <h3>本地运行</h3>
        <div class="code-block"><span class="c"># Python 3.10+，零第三方依赖</span><br>python app.py<br><span class="c"># open http://127.0.0.1:8765</span></div>
        <h3>安全边界</h3>
        <p>本工具用于合法授权的安全测试与防御性建设。任何未经授权的扫描、渗透或攻击行为都可能违反法律法规。演示数据仅用于本地演示。</p>
      </div>
      <div class="about-side">
        <div class="card"><h4>技术栈</h4><p class="small muted">Python 标准库 · http.server · sqlite3 · 原生 HTML/CSS/JS。无构建步骤，无外部 CDN。</p></div>
        <div class="card"><h4>数据</h4><p class="small muted">默认写入 <code>sop.db</code>；可用 <code>DB_PATH</code> 指定路径。演示数据可用 <code>SEED_DEMO=0</code> 关闭。</p></div>
        <div class="card"><h4>API</h4><p class="small muted">项目、检查项、漏洞、指标均提供 JSON API。完整说明见仓库 <code>docs/api.md</code>。</p></div>
        <div class="card"><h4>版本</h4><p class="small muted">v1.0.0 · MIT License</p></div>
      </div>
    </div>`;
  }

  // ---------------------------------------------------------------------
  // modals
  // ---------------------------------------------------------------------
  function modalHtml(title, subtitle, body, footer) {
    return `<div class="modal-backdrop" data-action="modal-backdrop">
      <div class="modal" role="dialog" aria-modal="true" aria-label="${esc(title)}">
        <div class="modal-head"><div><h2>${esc(title)}</h2><p>${esc(subtitle)}</p></div>
          <button class="icon-btn modal-close" data-action="close-modal" aria-label="关闭"><svg class="ico"><use href="#i-close"/></svg></button></div>
        <div class="modal-body">${body}</div>
        <div class="modal-foot">${footer}</div>
      </div>
    </div>`;
  }

  function openProjectModal() {
    const body = `<form data-form="project" id="project-form">
      <div class="form-grid">
        <div class="field full"><label>项目名称 <em>*</em></label><input name="name" required placeholder="例如：集团门户与会员中心"></div>
        <div class="field"><label>客户</label><input name="client" placeholder="客户名称"></div>
        <div class="field"><label>负责人</label><input name="owner" placeholder="项目经理"></div>
        <div class="field full"><label>测试范围</label><input name="scope" placeholder="域名 / IP / API / H5，多个用顿号分隔"></div>
        <div class="field"><label>开始日期</label><input type="date" name="start_date" value="${todayISO()}"></div>
        <div class="field"><label>截止日期</label><input type="date" name="due_date" value="${todayISO(14)}"></div>
        <div class="field full"><label>项目说明</label><textarea name="description" placeholder="业务特点、角色、重点风险…"></textarea></div>
      </div>
      <div class="form-error" id="project-error"></div>
    </form>`;
    const footer = `<button class="btn" data-action="close-modal">取消</button><button class="btn btn-primary" data-action="submit-project">创建项目</button>`;
    $('#modal-root').innerHTML = modalHtml('新建扫描项目', '创建后会初始化 10 个步骤、30 项检查和五条门禁。', body, footer);
    setTimeout(() => $('#project-form input[name="name"]')?.focus(), 50);
  }

  function openFindingModal() {
    if (!state.project) return;
    const body = `<form data-form="finding" id="finding-form">
      <div class="form-grid">
        <div class="field full"><label>漏洞标题 <em>*</em></label><input name="title" required placeholder="例如：会员中心订单查询 IDOR"></div>
        <div class="field"><label>风险等级</label><select name="severity">${['严重', '高', '中', '低', '信息'].map((s) => `<option value="${s}" ${s === '中' ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
        <div class="field"><label>状态</label><select name="status">${['待确认', '已确认', '修复中', '待复测', '已关闭', '风险接受'].map((s) => `<option value="${s}" ${s === '待确认' ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
        <div class="field full"><label>位置 / 接口</label><input name="endpoint" placeholder="/api/orders/{id}"></div>
        <div class="field"><label>负责人</label><input name="owner" placeholder="研发 / 运维负责人"></div>
        <div class="field"><label>修复期限</label><input type="date" name="due_date" value="${todayISO(7)}"></div>
        <div class="field full"><label>备注</label><textarea name="note" placeholder="复现条件、影响、修复建议…"></textarea></div>
      </div>
      <div class="form-error" id="finding-error"></div>
    </form>`;
    const footer = `<button class="btn" data-action="close-modal">取消</button><button class="btn btn-primary" data-action="submit-finding">保存漏洞</button>`;
    $('#modal-root').innerHTML = modalHtml('新增漏洞', '登记后会进入漏洞台账，并参与第 9/10 步门禁。', body, footer);
    setTimeout(() => $('#finding-form input[name="title"]')?.focus(), 50);
  }

  function closeModal() {
    $('#modal-root').innerHTML = '';
  }

  async function submitProject() {
    const form = $('#project-form');
    if (!form) return;
    const err = $('#project-error');
    const data = Object.fromEntries(new FormData(form).entries());
    if (!data.name || !data.name.trim()) {
      err.textContent = '项目名称不能为空';
      err.style.display = 'block';
      return;
    }
    try {
      const project = await api('/api/projects', { method: 'POST', body: JSON.stringify(data) });
      closeModal();
      toast('项目已创建', 'success');
      location.hash = `#/project/${project.id}`;
    } catch (e) {
      err.textContent = e.message;
      err.style.display = 'block';
    }
  }

  async function submitFinding() {
    const form = $('#finding-form');
    if (!form || !state.project) return;
    const err = $('#finding-error');
    const data = Object.fromEntries(new FormData(form).entries());
    if (!data.title || !data.title.trim()) {
      err.textContent = '漏洞标题不能为空';
      err.style.display = 'block';
      return;
    }
    try {
      await api(`/api/projects/${state.project.id}/findings`, { method: 'POST', body: JSON.stringify(data) });
      closeModal();
      toast('漏洞已登记', 'success');
      await refreshProject();
    } catch (e) {
      err.textContent = e.message;
      err.style.display = 'block';
    }
  }

  // ---------------------------------------------------------------------
  // actions
  // ---------------------------------------------------------------------
  async function setCheck(id, result) {
    try {
      await api(`/api/checks/${id}`, { method: 'PATCH', body: JSON.stringify({ result }) });
      await refreshProject();
      toast('检查结果已保存', 'success');
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  async function saveEvidence(id, value) {
    try {
      await api(`/api/checks/${id}`, { method: 'PATCH', body: JSON.stringify({ evidence: value }) });
      const check = state.project?.steps.flatMap((s) => s.checks).find((c) => c.id === id);
      if (check) check.evidence = value;
      toast('证据已保存', 'success');
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  async function saveNotes(stepNo) {
    const el = $(`[data-notes="${stepNo}"]`);
    if (!el || !state.project) return;
    try {
      await api(`/api/projects/${state.project.id}/steps/${stepNo}`, { method: 'PATCH', body: JSON.stringify({ notes: el.value }) });
      const step = state.project.steps.find((s) => s.step_no === Number(stepNo));
      if (step) step.notes = el.value;
      toast('备注已保存', 'success');
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  async function completeStep(stepNo) {
    if (!state.project) return;
    try {
      await api(`/api/projects/${state.project.id}/steps/${stepNo}/complete`, { method: 'POST', body: '{}' });
      toast('步骤已完成，进入下一节点', 'success');
      const next = state.project.steps.find((s) => s.step_no === Number(stepNo) + 1);
      if (next) state.selectedStep = next.step_no;
      await refreshProject();
    } catch (e) {
      if (e.data?.blockers?.length) {
        toast(`门禁未通过：${e.data.blockers.join('；')}`, 'error');
      } else {
        toast(e.message, 'error');
      }
    }
  }

  async function patchFindingStatus(id, status) {
    try {
      await api(`/api/findings/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) });
      toast('漏洞状态已更新', 'success');
      await refreshProject();
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  async function deleteFinding(id) {
    if (!confirm('确认删除这条漏洞记录？')) return;
    try {
      await api(`/api/findings/${id}`, { method: 'DELETE' });
      toast('漏洞已删除', 'success');
      await refreshProject();
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  // ---------------------------------------------------------------------
  // events
  // ---------------------------------------------------------------------
  document.addEventListener('click', async (e) => {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    const action = el.dataset.action;

    if (action === 'new-project') { openProjectModal(); return; }
    if (action === 'add-finding') { openFindingModal(); return; }
    if (action === 'close-modal') { closeModal(); return; }
    if (action === 'modal-backdrop' && e.target === el) { closeModal(); return; }
    if (action === 'submit-project') { await submitProject(); return; }
    if (action === 'submit-finding') { await submitFinding(); return; }
    if (action === 'retry') { route(); return; }
    if (action === 'refresh-project') { await refreshProject(); toast('已刷新', 'success'); return; }
    if (action === 'select-step') { state.selectedStep = Number(el.dataset.step); state.tab = 'checklist'; renderProject(); return; }
    if (action === 'tab') { state.tab = el.dataset.tab; renderProject(); return; }
    if (action === 'set-check') { await setCheck(Number(el.dataset.check), el.dataset.result); return; }
    if (action === 'save-notes') { await saveNotes(el.dataset.step); return; }
    if (action === 'complete-step') { await completeStep(Number(el.dataset.step)); return; }
    if (action === 'delete-finding') { await deleteFinding(Number(el.dataset.id)); return; }
  });

  document.addEventListener('submit', async (e) => {
    if (e.target.id === 'project-form') {
      e.preventDefault();
      await submitProject();
    } else if (e.target.id === 'finding-form') {
      e.preventDefault();
      await submitFinding();
    }
  });

  document.addEventListener('change', async (e) => {
    const evidence = e.target.closest('[data-evidence]');
    if (evidence) {
      await saveEvidence(Number(evidence.dataset.evidence), evidence.value);
      return;
    }
    const findingStatus = e.target.closest('[data-finding-status]');
    if (findingStatus) {
      await patchFindingStatus(Number(findingStatus.dataset.findingStatus), findingStatus.value);
    }
  });

  document.addEventListener('input', (e) => {
    const search = e.target.closest('[data-search]');
    if (search) {
      state.search = search.value;
      refreshProjectGrid();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });

  function toggleSidebar(open) {
    $('#sidebar').classList.toggle('open', open);
    $('#sidebar-overlay').classList.toggle('show', open);
  }

  function init() {
    $('#new-project-btn').addEventListener('click', openProjectModal);
    $('#refresh-btn').addEventListener('click', () => route());
    $('#menu-btn').addEventListener('click', () => toggleSidebar(true));
    $('#sidebar-overlay').addEventListener('click', () => toggleSidebar(false));
    $$('.nav-item').forEach((a) => a.addEventListener('click', () => toggleSidebar(false)));
    window.addEventListener('hashchange', route);
    if (!location.hash) {
      location.replace('#/dashboard');
    } else {
      route();
    }
  }

  // fallback step names for the dashboard before /api/library is loaded
  const DEFAULT_STEPS = [
    { no: 1, name: '授权与范围', gate: '无授权不启动' },
    { no: 2, name: '资产与入口', gate: '资产不清不扫' },
    { no: 3, name: '账号与角色', gate: '关键角色缺失先补' },
    { no: 4, name: '指纹与画像', gate: '关键系统未识别不扫' },
    { no: 5, name: '方案与编排', gate: '未评审/未限速不跑生产' },
    { no: 6, name: '自动化扫描', gate: '异常立即停' },
    { no: 7, name: '人工验证', gate: '不能复现不写报告' },
    { no: 8, name: '定级与确认', gate: '无依据不定级' },
    { no: 9, name: '报告与工单', gate: '建议不可执行就重写' },
    { no: 10, name: '复测与归档', gate: '未复测不关闭' },
  ];

  document.addEventListener('DOMContentLoaded', init);
})();
