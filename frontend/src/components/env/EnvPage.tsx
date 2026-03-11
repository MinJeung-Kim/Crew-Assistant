import { useEffect, useMemo, useState } from "react";
import { API_BASE } from "../../constants";
import { IconMenu } from "../icons";
import styles from "./EnvPage.module.css";

interface EnvPageProps {
  onToggleSidebar: () => void;
}

interface EnvStatus {
  has_google_api_key: boolean;
  has_slack_api_key: boolean;
  google_api_key_masked: string | null;
  slack_api_key_masked: string | null;
  updated_at: string | null;
}

const EMPTY_STATUS: EnvStatus = {
  has_google_api_key: false,
  has_slack_api_key: false,
  google_api_key_masked: null,
  slack_api_key_masked: null,
  updated_at: null,
};

export function EnvPage({ onToggleSidebar }: EnvPageProps) {
  const [status, setStatus] = useState<EnvStatus>(EMPTY_STATUS);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [googleApiKey, setGoogleApiKey] = useState("");
  const [slackApiKey, setSlackApiKey] = useState("");

  const lastUpdatedLabel = useMemo(() => {
    if (!status.updated_at) return "-";
    const date = new Date(status.updated_at);
    if (Number.isNaN(date.getTime())) return "-";
    return date.toLocaleString();
  }, [status.updated_at]);

  const loadStatus = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/integrations/env`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const payload = (await res.json()) as Partial<EnvStatus>;
      setStatus({
        has_google_api_key: Boolean(payload.has_google_api_key),
        has_slack_api_key: Boolean(payload.has_slack_api_key),
        google_api_key_masked:
          typeof payload.google_api_key_masked === "string"
            ? payload.google_api_key_masked
            : null,
        slack_api_key_masked:
          typeof payload.slack_api_key_masked === "string"
            ? payload.slack_api_key_masked
            : null,
        updated_at:
          typeof payload.updated_at === "string" ? payload.updated_at : null,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(`Env status 조회 실패: ${msg}`);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const handleSave = async () => {
    const trimmedGoogle = googleApiKey.trim();
    const trimmedSlack = slackApiKey.trim();

    const payload: Record<string, string> = {};
    if (trimmedGoogle) payload.google_api_key = trimmedGoogle;
    if (trimmedSlack) payload.slack_api_key = trimmedSlack;

    if (!Object.keys(payload).length) {
      setNotice("저장할 새 키가 없습니다. 입력 후 저장해 주세요.");
      return;
    }

    setIsSaving(true);
    setError(null);
    setNotice(null);

    try {
      const res = await fetch(`${API_BASE}/integrations/env`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const result = (await res.json().catch(() => ({}))) as {
        detail?: unknown;
      } & Partial<EnvStatus>;

      if (!res.ok) {
        const detail = typeof result.detail === "string" ? result.detail : `HTTP ${res.status}`;
        throw new Error(detail);
      }

      setGoogleApiKey("");
      setSlackApiKey("");
      setNotice("API 키가 저장되었습니다.");
      setStatus({
        has_google_api_key: Boolean(result.has_google_api_key),
        has_slack_api_key: Boolean(result.has_slack_api_key),
        google_api_key_masked:
          typeof result.google_api_key_masked === "string"
            ? result.google_api_key_masked
            : null,
        slack_api_key_masked:
          typeof result.slack_api_key_masked === "string"
            ? result.slack_api_key_masked
            : null,
        updated_at:
          typeof result.updated_at === "string" ? result.updated_at : null,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(`Env 저장 실패: ${msg}`);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <button
            type="button"
            onClick={onToggleSidebar}
            className={styles.menuButton}
          >
            <IconMenu />
          </button>
          <div>
            <div className={styles.title}>Env</div>
            <div className={styles.subtitle}>
              Google/Slack 키를 저장하고 온보딩 자동화를 활성화합니다.
            </div>
          </div>
        </div>
      </div>

      <div className={styles.body}>
        <section className={styles.card}>
          <h2>Integration Keys</h2>
          <p className={styles.cardDescription}>
            저장된 키는 백엔드 런타임 메모리에만 유지됩니다.
          </p>

          <div className={styles.fieldGroup}>
            <label htmlFor="google-key" className={styles.label}>Google API Key</label>
            <input
              id="google-key"
              type="password"
              value={googleApiKey}
              onChange={(event) => setGoogleApiKey(event.target.value)}
              placeholder="AIza... 또는 ya29..."
              className={styles.input}
            />
            <div className={styles.fieldHint}>
              현재 상태: {status.has_google_api_key ? `설정됨 (${status.google_api_key_masked ?? "hidden"})` : "미설정"}
            </div>
          </div>

          <div className={styles.fieldGroup}>
            <label htmlFor="slack-key" className={styles.label}>Slack API Key</label>
            <input
              id="slack-key"
              type="password"
              value={slackApiKey}
              onChange={(event) => setSlackApiKey(event.target.value)}
              placeholder="xoxb..."
              className={styles.input}
            />
            <div className={styles.fieldHint}>
              현재 상태: {status.has_slack_api_key ? `설정됨 (${status.slack_api_key_masked ?? "hidden"})` : "미설정"}
            </div>
          </div>

          <div className={styles.actions}>
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving || isLoading}
              className={styles.saveButton}
            >
              {isSaving ? "저장 중..." : "저장"}
            </button>
            <button
              type="button"
              onClick={loadStatus}
              disabled={isSaving || isLoading}
              className={styles.refreshButton}
            >
              새로고침
            </button>
          </div>

          <div className={styles.metaRow}>마지막 업데이트: {lastUpdatedLabel}</div>

          {error && <div className={styles.errorText}>{error}</div>}
          {notice && <div className={styles.noticeText}>{notice}</div>}
          {isLoading && <div className={styles.loadingText}>Env 상태를 불러오는 중...</div>}
        </section>

        <section className={styles.card}>
          <h2>Onboarding Trigger</h2>
          <p className={styles.cardDescription}>
            채팅 입력이 아래 형식이면 자동으로 입사 온보딩 워크플로우를 실행합니다.
          </p>
          <pre className={styles.codeBlock}>[이름] [부서] [입사일] [이메일]</pre>
          <pre className={styles.codeBlock}>[홍길동] [플랫폼개발팀] [2026-03-17] [hong@example.com]</pre>

          <ul className={styles.checklist}>
            <li>Google Drive에서 온보딩/입사 파일 탐색</li>
            <li>입사 서류 및 온보딩 자료 요약 생성</li>
            <li>신규 입사자 이메일 발송 시도</li>
            <li>Slack 워크스페이스 초대 시도</li>
          </ul>

          <p className={styles.warning}>
            Gmail 실제 발송은 Google OAuth access token(ya29...)이 필요합니다.
          </p>
        </section>
      </div>
    </div>
  );
}
