# RAG 지식 베이스

## 개요

회사 문서를 업로드하면 자동으로 텍스트 추출 → 청킹 → 임베딩 → JSON 인덱싱 과정을 거쳐 채팅 컨텍스트에 주입됩니다. 하이브리드 검색(벡터 + 어휘)으로 관련 컨텍스트를 검색합니다.

---

## 파일 위치

```
backend/
├── knowledge_base.py          # CompanyKnowledgeBase 클래스
├── data/
│   └── knowledge/
│       └── company_knowledge.json  # RAG 인덱스 저장소
```

---

## 인제스트 파이프라인

```
파일 업로드 (POST /knowledge/upload)
    │
    ▼
┌──────────────────────────────┐
│ 1. 텍스트 추출                │
│    extract_text_from_upload() │
│    PDF / DOCX / TXT / MD     │
│    CSV / JSON                │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ 2. 텍스트 정규화              │
│    CRLF → LF 변환            │
│    3줄 이상 연속 줄바꿈 축소   │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ 3. 청킹                      │
│    단락 경계 기준 분할         │
│    max_chunk_chars (기본 900) │
│    chunk_overlap (기본 120)   │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ 4. 임베딩                     │
│    OpenAI Embedding API      │
│    모델: text-embedding-3-small│
│    배치 처리                  │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ 5. JSON 저장                  │
│    data/knowledge/ 디렉토리   │
│    기존 동일 문서명 → 교체     │
└──────────────────────────────┘
```

---

## 텍스트 추출

### `extract_text_from_upload(filename: str, content: bytes) -> str`

파일 확장자에 따라 적절한 파서를 선택합니다.

| 확장자 | 파서 | 설명 |
|--------|------|------|
| `.pdf` | pypdf | 페이지별 텍스트 추출 |
| `.docx` | python-docx → XML fallback | 단락 + 테이블 추출 |
| `.txt`, `.md` | 직접 디코딩 | 텍스트 파일 |
| `.csv` | 직접 디코딩 | CSV 텍스트 |
| `.json` | 직접 디코딩 | JSON 텍스트 |

### DOCX 추출 상세

1. **python-docx** 라이브러리로 단락(`paragraphs`) 추출
2. 테이블: 셀을 `" | "` 구분자로 연결 (예: `"셀1 | 셀2 | 셀3"`)
3. python-docx 실패 시 XML fallback: `word/document.xml`에서 `<w:t>` 태그 파싱

### 인코딩 전략

텍스트 파일(.txt, .md, .csv, .json) 디코딩 시 순차 시도:

```
utf-8 → utf-8-sig → cp949 → euc-kr → latin-1
```

---

## 청킹 알고리즘

### 정규화

```python
text = text.replace("\r\n", "\n")  # CRLF → LF
text = re.sub(r"\n{3,}", "\n\n", text)  # 3줄+ → 2줄
```

### 분할 전략

1. **단락 경계 분할**: `\n\n` (빈 줄)로 1차 분할
2. **청크 병합**: 연속 단락을 `max_chunk_chars` 이내로 병합
3. **초과 단락 처리**: 단일 단락이 `max_chunk_chars` 초과 시 오버랩 포함 분할

### 오버랩

```
청크 1: [============================]
                              ↕ overlap (120자)
청크 2:                [============================]
```

- 기본값: 120자 오버랩
- 검색 시 문맥 연속성 보장

### 설정

| 환경 변수 | 기본값 | 범위 | 설명 |
|-----------|--------|------|------|
| `RAG_MAX_CHUNK_CHARS` | 900 | 300~3,000 | 청크 최대 문자 수 |
| `RAG_CHUNK_OVERLAP` | 120 | 0~500 | 청크 겹침 문자 수 |

---

## 임베딩

### 모델

| 설정 | 기본값 |
|------|--------|
| `RAG_EMBEDDING_MODEL` | `text-embedding-3-small` |

### 배치 처리

문서의 모든 청크를 한 번에 OpenAI Embedding API로 전송합니다.

```python
response = await client.embeddings.create(
    model=embedding_model,
    input=[chunk.text for chunk in chunks],
)
```

### 임베딩 실패 시

임베딩 API 호출이 실패하면 `embedded=False`로 저장되며, 검색 시 **어휘 기반 폴백**으로 동작합니다.

---

## 하이브리드 검색

### `retrieve(query: str, top_k: int) -> list[dict]`

#### 1. 벡터 검색 (임베딩 존재 시)

```python
score = cosine_similarity(query_embedding, chunk_embedding)
```

- 쿼리를 임베딩 API로 벡터화
- 모든 청크와 코사인 유사도 계산
- `score > 0` 필터링 후 상위 `top_k` 반환

#### 2. 어휘 검색 (폴백)

```python
tokens = re.findall(r"[a-z0-9가-힣]{2,}", text.lower())
score = len(query_tokens & chunk_tokens) / len(query_tokens)
```

- 토크나이저: `[a-z0-9가-힣]{2,}` (영문+숫자+한글, 2자 이상)
- 쿼리 토큰과 청크 토큰의 교집합 비율로 스코어링
- `score > 0` 필터링 후 상위 `top_k` 반환

### 검색 결과 형식

```python
[
    {
        "document": "company_policy.pdf",
        "text": "청크 텍스트...",
        "score": 0.85,
        "chunk_index": 3
    },
    ...
]
```

### 설정

| 환경 변수 | 기본값 | 범위 | 설명 |
|-----------|--------|------|------|
| `RAG_TOP_K` | 4 | 1~12 | 검색 결과 수 |

---

## 저장 형식

### JSON 인덱스 (`company_knowledge.json`)

```json
{
  "updated_at": "2026-03-13T09:00:00Z",
  "chunks": [
    {
      "id": "company_policy.pdf_0",
      "document_name": "company_policy.pdf",
      "chunk_index": 0,
      "text": "청크 텍스트...",
      "embedding": [0.012, -0.034, ...]
    },
    {
      "id": "company_policy.pdf_1",
      "document_name": "company_policy.pdf",
      "chunk_index": 1,
      "text": "다음 청크 텍스트...",
      "embedding": [0.008, -0.021, ...]
    }
  ]
}
```

### 문서 재업로드

동일한 파일명으로 재업로드 시 기존 해당 문서의 청크가 제거되고 새 청크로 교체됩니다 (버전 관리).

---

## 컨텍스트 주입

### `inject_company_context(messages, context) -> list[dict]`

RAG 검색 결과가 시스템 프롬프트에 `[Company Knowledge]` 섹션으로 주입됩니다.

```
[Company Knowledge]
(1) company_policy.pdf: 청크 텍스트...
(2) onboarding_guide.docx: 청크 텍스트...

[Google Drive Shared Files]
(1) project_plan.docx: 파일 컨텍스트...
```

### `load_company_context(query, settings, ...) -> (context_str, sources)`

RAG 컨텍스트와 Google Drive 컨텍스트를 병합하여 하나의 컨텍스트 문자열을 생성합니다.

---

## 설정 전체

| 환경 변수 | 기본값 | 범위 | 설명 |
|-----------|--------|------|------|
| `RAG_ENABLED` | `true` | - | RAG 기능 활성화 |
| `RAG_STORAGE_PATH` | `./data/knowledge` | - | 인덱스 저장 경로 |
| `RAG_EMBEDDING_MODEL` | `text-embedding-3-small` | - | 임베딩 모델 |
| `RAG_TOP_K` | `4` | 1~12 | 검색 결과 수 |
| `RAG_MAX_CHUNK_CHARS` | `900` | 300~3,000 | 청크 최대 크기 |
| `RAG_CHUNK_OVERLAP` | `120` | 0~500 | 오버랩 크기 |
| `RAG_MAX_UPLOAD_MB` | `20` | 1~200 | 최대 업로드 크기 (MB) |
