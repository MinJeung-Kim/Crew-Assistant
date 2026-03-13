# 온보딩 자동화 워크플로우

## 개요

채팅 인터페이스에서 신규 직원 정보를 입력하면 자동으로 온보딩 프로세스가 실행됩니다. Google Drive 문서 검색, Gmail 온보딩 이메일 발송, Slack 초대까지 한 번에 처리합니다.

---

## 파일 위치

```
backend/
├── onboarding_workflow.py     # 온보딩 전체 로직
├── main.py                    # 온보딩 세션 관리 + 라우팅
└── services/
    ├── chat_service.py        # LLM 요약 생성
    ├── drive_context.py       # Drive 파일 검색
    └── google_oauth.py        # OAuth 토큰 관리
```

---

## 실행 흐름

```
사용자 입력: "홍길동 개발팀 2026-04-01 gildong@company.com"
    │
    ▼
┌─────────────────────────────────────┐
│ 1. 프로필 파싱                       │
│    parse_onboarding_profile(query)   │
│    → OnboardingProfile 반환          │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 2. Slack 초대 수단 확인              │
│    ├→ slack_invite_link 있음 → 계속  │
│    ├→ slack_api_key 있음   → 계속    │
│    └→ 둘 다 없음 → 대기 상태 진입     │
│       → "Slack 초대 링크 입력해주세요" │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 3. Google Drive 검색                 │
│    키워드: 온보딩/입사/서류 + 부서/이름│
│    → 관련 문서 링크 수집              │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 4. LLM 요약 생성                     │
│    입사 서류 + 온보딩 파일 +          │
│    첫 주 체크리스트                   │
│    → 마크다운 형식                    │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 5. 마크다운 → HTML 변환              │
│    python-markdown + 인라인 스타일    │
│    fenced code, tables, lists 지원   │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 6. Gmail 이메일 발송                  │
│    OAuth 토큰 + gmail.send 스코프    │
│    text/plain + text/html multipart  │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 7. Slack 초대                        │
│    ├→ shared_invite_link → 이메일 포함│
│    └→ admin token → API 호출          │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ 8. 결과 리포트 SSE 전송              │
│    source: "onboarding"              │
└─────────────────────────────────────┘
```

---

## 프로필 파싱

### `parse_onboarding_profile(query: str) -> OnboardingProfile | None`

사용자 입력에서 신규 직원 정보를 추출합니다.

**인식 패턴:**
```
[이름] [부서] [날짜] [이메일]
```

**예시:**
```
홍길동 개발팀 2026-04-01 gildong@company.com
김철수 마케팅팀 2026.04.01 chulsoo@company.com
Jane Smith Engineering 2026/04/01 jane@company.com
```

### OnboardingProfile

```python
@dataclass
class OnboardingProfile:
    name: str           # 이름
    department: str     # 부서
    join_date: str      # 입사일 (YYYY-MM-DD 정규화)
    email: str          # 이메일
```

### 날짜 정규화

입력된 날짜 구분자(`.`, `/`, `-`)를 모두 `YYYY-MM-DD` 형식으로 정규화합니다.

### 이메일 검증

```python
re.match(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
```

---

## Slack 초대 수단

### 우선순위

1. **Shared Invite Link** (권장): `https://join.slack.com/t/<workspace>/shared_invite/<token>`
2. **Admin Token** (폴백): `xoxp-...` 또는 `xoxa-2-...`

> `xoxb-` (Bot Token)은 초대 권한이 없어 거부됩니다.

### 설정 경로

- **Tools 페이지**: `/integrations/env`로 사전 저장 → 채팅 시 자동 사용
- **채팅 런타임**: 저장된 키가 없으면 세션 내에서 입력 요청

### 토큰 입력 대기 세션

Slack 키가 없는 상태에서 온보딩을 시작하면:

1. `pending_onboarding_by_session`에 프로필 저장
2. 사용자에게 Slack 초대 링크 입력 요청 메시지 전송
3. **TTL: 10분** (만료 시 자동 폐기)
4. `취소` 또는 `cancel` 입력으로 대기 취소 가능

### 취소 명령어

```python
ONBOARDING_CANCEL_COMMANDS = {
    "cancel", "onboarding cancel",
    "취소", "온보딩 취소",
}
```

---

## Slack API 호출

### Admin Token 사용 시

1차 시도: `admin.users.invite`
```json
{
  "email": "gildong@company.com",
  "real_name": "홍길동",
  "resend": true,
  "team_id": "<SLACK_TEAM_ID>"  // 설정된 경우
}
```

2차 시도 (1차 실패 시): `users.admin.invite`

### Shared Invite Link 사용 시

이메일 본문에 Slack 초대 버튼 + 링크를 포함합니다.

---

## 이메일 발송

### 필수 조건

- Google OAuth 토큰 (`google_api_key`)이 설정되어 있어야 합니다
- `gmail.send` 스코프가 부여되어 있어야 합니다

### 이메일 구성

**Plain Text:**
```
인사말 + 프로필 정보 + 요약 + Drive 링크
```

**HTML:**
```
┌─────────────────────────────────┐
│ Header (다크 배경)               │
│ "신규 직원 온보딩 안내"            │
├─────────────────────────────────┤
│ 프로필 정보 테이블                │
│ 이름 | 부서 | 입사일 | 이메일     │
├─────────────────────────────────┤
│ 온보딩 요약 섹션                  │
│ (마크다운 → HTML 변환)            │
│ - 입사 서류 체크리스트             │
│ - 온보딩 파일 목록                │
│ - 첫 주 할 일                    │
├─────────────────────────────────┤
│ Slack 초대 버튼 (해당 시)         │
├─────────────────────────────────┤
│ Footer (HR 연락처)               │
└─────────────────────────────────┘
```

### HTML 렌더링

- python `markdown` 라이브러리 사용
- 확장 지원: fenced code, tables, lists, blockquotes
- 인라인 email-friendly 스타일 적용 (Tailwind-inspired)
- 최대 너비: 680px (반응형)

---

## Google Drive 검색

### 검색 키워드

프로필 정보 기반으로 검색 키워드를 조합합니다:
- `온보딩`, `입사`, `서류`
- 부서명 (예: `개발팀`)
- 이름 (예: `홍길동`)

### 검색 조건

```
trashed=false
mimeType != 'application/vnd.google-apps.folder'
fullText contains '키워드'
orderBy: modifiedTime desc
```

### 결과 제한

| 설정 | 기본값 | 범위 |
|------|--------|------|
| `ONBOARDING_DRIVE_FILE_LIMIT` | 8 | 1~20 |

---

## IntegrationSecrets

온보딩 워크플로우에서 사용하는 통합 키 저장소입니다.

```python
@dataclass
class IntegrationSecrets:
    google_api_key: str       # Google OAuth 토큰 또는 API 키
    slack_api_key: str        # Slack 관리자 토큰
    slack_invite_link: str    # Slack 공유 초대 URL
    updated_at: str | None    # 마지막 업데이트 시각 (ISO 8601)
```

---

## 유틸리티 함수

| 함수 | 설명 |
|------|------|
| `parse_onboarding_profile(query)` | 쿼리에서 프로필 추출 |
| `extract_slack_invite_link(text)` | 텍스트에서 Slack 초대 URL 추출 |
| `extract_slack_token(text)` | 텍스트에서 Slack 토큰 추출 |
| `validate_slack_invite_token(text)` | 초대 링크/토큰 유효성 검증 |
| `looks_like_google_oauth_token(token)` | `ya29...` 패턴 확인 |
| `fetch_google_token_scopes(token)` | tokeninfo API로 스코프 조회 |
| `has_any_required_scope(scopes, hints)` | 필요 스코프 존재 여부 확인 |
| `mask_secret(secret)` | 비밀키 마스킹 (앞4 + ... + 뒤3) |
| `utc_now_iso()` | 현재 UTC 시각 ISO 8601 문자열 |
| `run_onboarding_workflow(...)` | 온보딩 전체 실행 |

---

## SSE 스트리밍 진행 이벤트

온보딩 워크플로우 실행 중 SSE로 진행 상황이 전송됩니다:

```
data: {"source": "onboarding", "token": "온보딩 대상자 정보를 확인했습니다.\n"}\n\n
data: {"source": "onboarding", "token": "[Drive 문서 검색 중...]\n"}\n\n
data: {"source": "onboarding", "token": "[온보딩 요약 생성 중...]\n"}\n\n
data: {"source": "onboarding", "token": "[이메일 발송 중...]\n"}\n\n
data: {"source": "onboarding", "token": "[Slack 초대 중...]\n"}\n\n
data: {"source": "onboarding", "token": "# 온보딩 완료 리포트\n..."}\n\n
data: [DONE]\n\n
```

---

## 설정

| 환경 변수 | 기본값 | 설명 |
|-----------|--------|------|
| `GOOGLE_API_KEY` | `""` | Google OAuth 토큰 |
| `SLACK_API_KEY` | `""` | Slack 관리자 토큰 |
| `SLACK_INVITE_LINK` | `""` | Slack 공유 초대 URL |
| `SLACK_TEAM_ID` | `""` | Slack 팀 ID (멀티워크스페이스용) |
| `ONBOARDING_DRIVE_FILE_LIMIT` | `8` | Drive 검색 결과 제한 |
| `GOOGLE_OAUTH_TOKEN_PATH` | `./data/oauth/token.json` | OAuth 토큰 파일 경로 |
