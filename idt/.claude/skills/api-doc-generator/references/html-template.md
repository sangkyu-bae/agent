# 커스텀 HTML API 문서 템플릿

CDN 없이 standalone으로 동작하는 HTML 문서입니다.
아래 구조를 기반으로 실제 엔드포인트 데이터를 채워 `docs/index.html`을 생성하세요.

## 특징
- 사이드바 네비게이션 (태그별 그룹)
- 메서드별 컬러 배지 (GET=초록, POST=파랑, PUT=주황, DELETE=빨강, PATCH=보라)
- curl / Python 예시 탭
- 다크모드 지원
- 검색 필터

## 템플릿 구조

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{PROJECT_NAME} API 문서</title>
  <style>
    :root {
      --bg: #ffffff;
      --sidebar-bg: #1e1e2e;
      --sidebar-text: #cdd6f4;
      --accent: #89b4fa;
      --get: #40a02b;
      --post: #1e66f5;
      --put: #fe640b;
      --delete: #d20f39;
      --patch: #8839ef;
      --border: #e0e0e0;
      --code-bg: #1e1e2e;
      --code-text: #cdd6f4;
    }
    @media (prefers-color-scheme: dark) {
      :root { --bg: #181825; --border: #313244; }
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; display: flex; background: var(--bg); }

    /* 사이드바 */
    #sidebar {
      width: 260px; min-height: 100vh; background: var(--sidebar-bg);
      color: var(--sidebar-text); padding: 20px 0; position: fixed; overflow-y: auto;
    }
    #sidebar h1 { font-size: 14px; padding: 0 20px 16px; border-bottom: 1px solid #313244; color: var(--accent); }
    #sidebar input {
      margin: 12px 12px; width: calc(100% - 24px); padding: 6px 10px;
      background: #313244; border: none; border-radius: 6px; color: var(--sidebar-text); font-size: 13px;
    }
    .tag-group { margin-bottom: 8px; }
    .tag-label { padding: 8px 20px; font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #6c7086; }
    .nav-item { padding: 6px 20px; cursor: pointer; font-size: 13px; display: flex; align-items: center; gap: 8px; }
    .nav-item:hover { background: #313244; }
    .nav-item.active { background: #313244; color: var(--accent); }

    /* 메인 */
    #main { margin-left: 260px; padding: 40px; max-width: 900px; width: 100%; }
    .endpoint-card {
      border: 1px solid var(--border); border-radius: 10px; margin-bottom: 24px;
      overflow: hidden;
    }
    .endpoint-header {
      display: flex; align-items: center; gap: 12px; padding: 16px 20px;
      cursor: pointer; background: var(--bg);
    }
    .endpoint-header:hover { background: #f5f5f5; }
    .method-badge {
      padding: 3px 8px; border-radius: 4px; font-size: 12px;
      font-weight: 700; color: white; min-width: 60px; text-align: center;
    }
    .GET { background: var(--get); }
    .POST { background: var(--post); }
    .PUT { background: var(--put); }
    .DELETE { background: var(--delete); }
    .PATCH { background: var(--patch); }
    .endpoint-path { font-family: monospace; font-size: 15px; }
    .endpoint-summary { color: #666; font-size: 13px; margin-left: auto; }
    .auth-badge { font-size: 11px; background: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 4px; }

    .endpoint-body { padding: 20px; border-top: 1px solid var(--border); display: none; }
    .endpoint-body.open { display: block; }

    /* 탭 */
    .tabs { display: flex; gap: 4px; margin-bottom: 12px; }
    .tab { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; background: #f0f0f0; }
    .tab.active { background: var(--accent); color: white; }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    /* 코드 블록 */
    pre {
      background: var(--code-bg); color: var(--code-text);
      padding: 16px; border-radius: 8px; overflow-x: auto;
      font-size: 13px; line-height: 1.6;
    }

    /* 테이블 */
    table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 16px; }
    th { background: #f5f5f5; padding: 8px 12px; text-align: left; font-weight: 600; }
    td { padding: 8px 12px; border-top: 1px solid var(--border); }
    .required { color: #d20f39; font-size: 11px; }
    .optional { color: #999; font-size: 11px; }

    h3 { font-size: 14px; margin: 20px 0 8px; color: #444; }
    .section-title { font-size: 20px; font-weight: 700; margin: 40px 0 20px; padding-bottom: 8px; border-bottom: 2px solid var(--border); }
  </style>
</head>
<body>

<nav id="sidebar">
  <h1>🔌 {PROJECT_NAME} API</h1>
  <input type="text" placeholder="엔드포인트 검색..." id="search" oninput="filterNav(this.value)">
  <!-- 태그별 네비게이션 자동 생성 -->
  <div id="nav-container"></div>
</nav>

<main id="main">
  <div style="margin-bottom:32px">
    <h1 style="font-size:28px;margin-bottom:8px">{PROJECT_NAME} API</h1>
    <p style="color:#666">Base URL: <code>http://localhost:8000</code> &nbsp;|&nbsp; 버전: 1.0.0</p>
    <p style="color:#666;margin-top:8px">🔐 인증: <code>Authorization: Bearer &lt;token&gt;</code></p>
  </div>

  <div id="endpoints-container">
    <!-- 엔드포인트 카드가 JS로 렌더링됨 -->
  </div>
</main>

<script>
// ===== 여기에 추출한 API 데이터를 채우세요 =====
const API_DATA = {
  tags: ["Users", "Auth", "Items"],  // 태그 목록
  endpoints: [
    {
      method: "GET",
      path: "/users",
      tag: "Users",
      summary: "사용자 목록 조회",
      description: "전체 사용자 목록을 페이지네이션으로 반환합니다.",
      auth: true,
      params: [
        { name: "page", in: "query", type: "integer", required: false, default: "1", description: "페이지 번호" },
        { name: "size", in: "query", type: "integer", required: false, default: "20", description: "페이지 크기" },
      ],
      requestBody: null,
      responses: {
        "200": { description: "성공", example: '{\n  "items": [{"id": 1, "email": "user@example.com"}],\n  "total": 100,\n  "page": 1\n}' },
        "401": { description: "인증 실패", example: '{"detail": "Not authenticated"}' },
      },
      curl: 'curl -X GET "http://localhost:8000/users?page=1" \\\n  -H "Authorization: Bearer {token}"',
      python: 'import requests\n\nresp = requests.get(\n  "http://localhost:8000/users",\n  params={"page": 1},\n  headers={"Authorization": "Bearer {token}"}\n)\nprint(resp.json())',
    },
    // ... 추가 엔드포인트
  ]
};
// =================================================

function renderAll() {
  const nav = document.getElementById('nav-container');
  const main = document.getElementById('endpoints-container');

  // 태그별 그룹화
  const grouped = {};
  API_DATA.endpoints.forEach(ep => {
    if (!grouped[ep.tag]) grouped[ep.tag] = [];
    grouped[ep.tag].push(ep);
  });

  // 사이드바 렌더링
  nav.innerHTML = Object.entries(grouped).map(([tag, eps]) => `
    <div class="tag-group">
      <div class="tag-label">${tag}</div>
      ${eps.map((ep, i) => `
        <div class="nav-item" onclick="scrollTo('${tag}-${i}')">
          <span class="method-badge ${ep.method}" style="font-size:10px;padding:2px 5px">${ep.method}</span>
          ${ep.path}
        </div>`).join('')}
    </div>`).join('');

  // 메인 렌더링
  main.innerHTML = Object.entries(grouped).map(([tag, eps]) => `
    <div class="section-title" id="tag-${tag}">${tag}</div>
    ${eps.map((ep, i) => renderCard(ep, `${tag}-${i}`)).join('')}
  `).join('');
}

function renderCard(ep, id) {
  const params = ep.params?.length ? `
    <h3>파라미터</h3>
    <table>
      <tr><th>이름</th><th>위치</th><th>타입</th><th>필수</th><th>설명</th></tr>
      ${ep.params.map(p => `
        <tr>
          <td><code>${p.name}</code></td>
          <td>${p.in}</td>
          <td>${p.type}</td>
          <td>${p.required ? '<span class="required">필수</span>' : '<span class="optional">선택</span>'}</td>
          <td>${p.description}${p.default ? ` (기본: ${p.default})` : ''}</td>
        </tr>`).join('')}
    </table>` : '';

  const reqBody = ep.requestBody ? `
    <h3>Request Body</h3>
    <pre>${ep.requestBody}</pre>` : '';

  const responses = Object.entries(ep.responses || {}).map(([code, r]) => `
    <h3>Response <code>${code}</code> — ${r.description}</h3>
    <pre>${r.example}</pre>`).join('');

  return `
    <div class="endpoint-card" id="${id}">
      <div class="endpoint-header" onclick="toggle('body-${id}')">
        <span class="method-badge ${ep.method}">${ep.method}</span>
        <span class="endpoint-path">${ep.path}</span>
        ${ep.auth ? '<span class="auth-badge">🔐 인증</span>' : ''}
        <span class="endpoint-summary">${ep.summary}</span>
      </div>
      <div class="endpoint-body" id="body-${id}">
        <p style="color:#666;margin-bottom:16px">${ep.description || ''}</p>
        ${params}
        ${reqBody}
        ${responses}
        <h3>예시 코드</h3>
        <div class="tabs">
          <div class="tab active" onclick="switchTab(this, 'curl-${id}')">curl</div>
          <div class="tab" onclick="switchTab(this, 'python-${id}')">Python</div>
        </div>
        <div class="tab-content active" id="curl-${id}"><pre>${ep.curl || ''}</pre></div>
        <div class="tab-content" id="python-${id}"><pre>${ep.python || ''}</pre></div>
      </div>
    </div>`;
}

function toggle(id) {
  document.getElementById(id).classList.toggle('open');
}
function scrollTo(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
}
function switchTab(btn, targetId) {
  const card = btn.closest('.endpoint-body');
  card.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  card.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(targetId).classList.add('active');
}
function filterNav(q) {
  document.querySelectorAll('.nav-item').forEach(el => {
    el.style.display = el.textContent.toLowerCase().includes(q.toLowerCase()) ? '' : 'none';
  });
}

renderAll();
</script>
</body>
</html>
```

## 사용 방법

1. `API_DATA.endpoints` 배열에 추출한 엔드포인트 데이터를 채운다
2. `{PROJECT_NAME}`을 실제 프로젝트명으로 치환
3. `docs/index.html`로 저장
4. 브라우저에서 열기: `open docs/index.html`