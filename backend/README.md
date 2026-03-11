## Backend Setup

```bash
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## CrewAI Integration

- CrewAI is automatically invoked when the latest user message includes trend/research/report style intent.
- `requirements.txt` includes `litellm` and `ddgs` so custom OpenAI-compatible model IDs and lightweight web research can work with CrewAI.
- Example trigger query:

```text
2026년 IT 트랜드 조사해서 보고서 형식으로 요약해줘
```

- Environment variables:

```env
CREWAI_ENABLED=true
CREWAI_MODEL=
CREWAI_WEB_SEARCH_RESULTS=6
```

- `CREWAI_MODEL` is optional. If empty, the backend will use `openai/<LLM_MODEL>`.