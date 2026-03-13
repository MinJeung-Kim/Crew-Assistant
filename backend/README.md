## Backend Setup

```bash
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## CrewAI Integration

- `requirements.txt` includes `litellm` and `ddgs` so custom OpenAI-compatible model IDs and lightweight web research can work with CrewAI.
- Example trigger query:

```text
2026년 IT 트랜드 조사해서 보고서 형식으로 요약해줘

- Environment variables:

```env
CREWAI_ENABLED=true
CREWAI_WEB_SEARCH_RESULTS=6

- `CREWAI_MODEL` is optional. If empty, the backend will use `openai/<LLM_MODEL>`.

## Company RAG Integration

- Upload company documents to build retrieval context:

```bash
POST /knowledge/upload
```

## Translation Endpoint

- Translate assistant output into Korean while preserving markdown formatting:

```bash
POST /translate
```

- Request body example:

```json
{
	"text": "English report markdown...",
	"target_language": "ko",
	"preserve_markdown": true
}
```

## Env Integrations + Onboarding Automation

- Save Google/Slack keys used by onboarding workflow:

```bash
GET /integrations/env
POST /integrations/env
```

- Example save payload:

```json
{
	"google_api_key": "AIza... or ya29...",
	"slack_invite_link": "https://join.slack.com/t/<workspace>/shared_invite/<token>"
}
```

- Optional fallback (legacy):

```json
{
	"slack_api_key": "xoxp... or xoxa-2..."
}
```

- OAuth client JSON upload + key issuance endpoints:

```bash
GET /integrations/google/oauth-client/status
POST /integrations/google/oauth-client
GET /integrations/google/oauth/start
POST /integrations/google/oauth/installed/issue
```

- Installed client JSON(`{"installed": {...}}`) flow:
1. Upload installed JSON on Env page
2. Click `key 발급` (backend runs InstalledAppFlow local server)
3. Google login/consent once
4. `data/oauth/token.json` saved
5. access_token auto refreshes from refresh_token on next runs

- Related environment variables:

```env
GOOGLE_OAUTH_TOKEN_PATH=./data/oauth/token.json
GOOGLE_OAUTH_INSTALLED_PORT=8080
```

- Chat trigger format for onboarding automation:

```text
[이름] [부서] [입사일] [이메일]
```

- Example:

```text
[홍길동] [플랫폼개발팀] [2026-03-17] [hong@example.com]
```

- If Slack Invite Link is saved in Tools, onboarding email includes that link automatically.
- If Slack Invite Link is missing, chat asks for runtime shared invite URL.
- Legacy fallback: if admin token is configured, backend can still call Slack invite API.

```text
https://join.slack.com/t/<workspace>/shared_invite/<token>
```

- Notes for Slack invite step:
1. Input is session-scoped pending state (default TTL: 10 minutes).
2. 공유 초대 링크(shared_invite URL)는 온보딩 이메일 본문에 그대로 포함됩니다.
3. Admin token 경로를 사용할 때는 `xoxp-` 또는 `xoxa-2-` 형식과 `auth.test` 검증이 필요합니다.
4. You can cancel pending onboarding input with `취소` or `cancel`.

- Triggered actions:
1. Google Drive onboarding files search
2. 입사/온보딩 파일 요약 생성
3. 신규 입사자 이메일 발송 시도 (OAuth 토큰일 때)
4. Slack 초대 링크 이메일 포함 또는 Slack 초대 API 호출(legacy)

- Google OAuth scope requirements:
1. Drive search: `https://www.googleapis.com/auth/drive.readonly` or `https://www.googleapis.com/auth/drive.metadata.readonly`
2. Gmail send: `https://www.googleapis.com/auth/gmail.send`

- Check ingestion status:

```bash
GET /knowledge/status
```

- Once documents are uploaded, `/chat` and `/chat/stream` automatically inject top company knowledge chunks into prompts.

- RAG environment variables:

```env
RAG_ENABLED=true
RAG_STORAGE_PATH=./data/knowledge
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_TOP_K=4
RAG_MAX_CHUNK_CHARS=900
RAG_CHUNK_OVERLAP=120
RAG_MAX_UPLOAD_MB=20
```