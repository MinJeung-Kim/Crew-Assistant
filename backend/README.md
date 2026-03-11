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
	"slack_api_key": "xoxb..."
}
```

- Chat trigger format for onboarding automation:

```text
[이름] [부서] [입사일] [이메일]
```

- Example:

```text
[홍길동] [플랫폼개발팀] [2026-03-17] [hong@example.com]
```

- Triggered actions:
1. Google Drive onboarding files search
2. 입사/온보딩 파일 요약 생성
3. 신규 입사자 이메일 발송 시도 (OAuth 토큰일 때)
4. Slack 초대 API 호출

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