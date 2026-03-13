import { useEffect, useMemo, useState } from "react";
import { API_BASE } from "../../constants";
import { IconMenu } from "../icons";
import styles from "./ToolsPage.module.css";

interface ToolsPageProps {
  onToggleSidebar: () => void;
}

interface ToolsStatus {
  has_google_api_key: boolean;
  has_slack_api_key: boolean;
  has_slack_invite_link: boolean;
  google_api_key_masked: string | null;
  slack_api_key_masked: string | null;
  slack_invite_link_masked: string | null;
  updated_at: string | null;
}

interface GoogleScopeStatus {
  token_configured: boolean;
  token_type: string | null;
  granted_scopes: string[];
  drive_scope_ready: boolean;
  gmail_scope_ready: boolean;
  drive_scope_hints: string[];
  gmail_scope_hints: string[];
  tokeninfo_error: string | null;
}

interface GoogleOAuthClientStatus {
  configured: boolean;
  client_type: string | null;
  project_id: string | null;
  client_id_masked: string | null;
  redirect_uri: string | null;
}

interface GoogleOAuthStartResponse {
  auth_url: string;
  expires_in_seconds: number;
}

interface GoogleOAuthInstalledIssueResponse {
  message: string;
  access_token_masked: string | null;
  token_type: string | null;
  expires_in_seconds: number | null;
  granted_scopes: string[];
}

type OAuthFlowStepKey =
  | "client_upload"
  | "auth_url"
  | "consent"
  | "token_exchange"
  | "token_save";

type OAuthFlowStepState = "idle" | "active" | "done" | "error";

interface GoogleOAuthTokenMeta {
  token_type: string | null;
  expires_in_seconds: number | null;
  granted_scopes: string[];
  access_token_masked: string | null;
}

interface GoogleOAuthPopupEvent {
  type?: string;
  message?: string;
  token_type?: unknown;
  expires_in_seconds?: unknown;
  granted_scopes?: unknown;
  access_token_masked?: unknown;
}

const OAUTH_FLOW_STEPS: Array<{
  key: OAuthFlowStepKey;
  title: string;
  description: string;
}> = [
  {
    key: "client_upload",
    title: "1) OAuth Client JSON 검증",
    description: "업로드된 JSON에서 client_id/client_secret/redirect_uri를 확인합니다.",
  },
  {
    key: "auth_url",
    title: "2) 인증 URL 생성",
    description: "서버가 state 포함 Google 인증 URL을 생성합니다.",
  },
  {
    key: "consent",
    title: "3) Google 로그인/권한 동의",
    description: "팝업에서 계정 로그인 후 Drive/Gmail 권한에 동의합니다.",
  },
  {
    key: "token_exchange",
    title: "4) Authorization Code 토큰 교환",
    description: "백엔드가 code를 받아 Google token endpoint로 교환 요청합니다.",
  },
  {
    key: "token_save",
    title: "5) access_token 저장 및 사용",
    description: "발급된 access_token을 Tools 설정 저장소에 저장해 온보딩에 사용합니다.",
  },
];

const OAUTH_FLOW_STATE_LABEL: Record<OAuthFlowStepState, string> = {
  idle: "대기",
  active: "진행중",
  done: "완료",
  error: "실패",
};

const EMPTY_GOOGLE_OAUTH_TOKEN_META: GoogleOAuthTokenMeta = {
  token_type: null,
  expires_in_seconds: null,
  granted_scopes: [],
  access_token_masked: null,
};

const createEmptyOAuthFlowStates = (): Record<OAuthFlowStepKey, OAuthFlowStepState> => ({
  client_upload: "idle",
  auth_url: "idle",
  consent: "idle",
  token_exchange: "idle",
  token_save: "idle",
});

const EMPTY_TOOLS_STATUS: ToolsStatus = {
  has_google_api_key: false,
  has_slack_api_key: false,
  has_slack_invite_link: false,
  google_api_key_masked: null,
  slack_api_key_masked: null,
  slack_invite_link_masked: null,
  updated_at: null,
};

const EMPTY_GOOGLE_SCOPE_STATUS: GoogleScopeStatus = {
  token_configured: false,
  token_type: null,
  granted_scopes: [],
  drive_scope_ready: false,
  gmail_scope_ready: false,
  drive_scope_hints: [],
  gmail_scope_hints: [],
  tokeninfo_error: null,
};

const EMPTY_GOOGLE_OAUTH_CLIENT_STATUS: GoogleOAuthClientStatus = {
  configured: false,
  client_type: null,
  project_id: null,
  client_id_masked: null,
  redirect_uri: null,
};

export function ToolsPage({ onToggleSidebar }: ToolsPageProps) {
  const [status, setStatus] = useState<ToolsStatus>(EMPTY_TOOLS_STATUS);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isScopeLogsOpen, setIsScopeLogsOpen] = useState(false);
  const [scopeStatus, setScopeStatus] = useState<GoogleScopeStatus>(EMPTY_GOOGLE_SCOPE_STATUS); 
  const [oauthClientStatus, setOauthClientStatus] = useState<GoogleOAuthClientStatus>(EMPTY_GOOGLE_OAUTH_CLIENT_STATUS);
  const [isOAuthClientLoading, setIsOAuthClientLoading] = useState(false);
  const [isOAuthClientUploading, setIsOAuthClientUploading] = useState(false);
  const [isIssuingGoogleToken, setIsIssuingGoogleToken] = useState(false);
  const [googleOAuthClientFile, setGoogleOAuthClientFile] = useState<File | null>(null);
  const [oauthFlowStates, setOauthFlowStates] = useState<Record<OAuthFlowStepKey, OAuthFlowStepState>>(
    createEmptyOAuthFlowStates
  );
  const [oauthTokenMeta, setOauthTokenMeta] = useState<GoogleOAuthTokenMeta>(
    EMPTY_GOOGLE_OAUTH_TOKEN_META
  );

  const [googleApiKey, setGoogleApiKey] = useState("");
  const [slackInviteLink, setSlackInviteLink] = useState("");

  const apiOrigin = useMemo(() => {
    try {
      return new URL(API_BASE).origin;
    } catch {
      return null;
    }
  }, []);

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

      const payload = (await res.json()) as Partial<ToolsStatus>;
      setStatus({
        has_google_api_key: Boolean(payload.has_google_api_key),
        has_slack_api_key: Boolean(payload.has_slack_api_key),
        has_slack_invite_link: Boolean(payload.has_slack_invite_link),
        google_api_key_masked:
          typeof payload.google_api_key_masked === "string"
            ? payload.google_api_key_masked
            : null,
        slack_api_key_masked:
          typeof payload.slack_api_key_masked === "string"
            ? payload.slack_api_key_masked
            : null,
        slack_invite_link_masked:
          typeof payload.slack_invite_link_masked === "string"
            ? payload.slack_invite_link_masked
            : null,
        updated_at:
          typeof payload.updated_at === "string" ? payload.updated_at : null,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(`Tools status 조회 실패: ${msg}`);
    } finally {
      setIsLoading(false);
    }
  };

  const loadGoogleScopeStatus = async () => { 
    try {
      const res = await fetch(`${API_BASE}/integrations/google/scope-status`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const payload = (await res.json()) as Partial<GoogleScopeStatus>;
      setScopeStatus({
        token_configured: Boolean(payload.token_configured),
        token_type: typeof payload.token_type === "string" ? payload.token_type : null,
        granted_scopes: Array.isArray(payload.granted_scopes)
          ? payload.granted_scopes.filter((scope): scope is string => typeof scope === "string")
          : [],
        drive_scope_ready: Boolean(payload.drive_scope_ready),
        gmail_scope_ready: Boolean(payload.gmail_scope_ready),
        drive_scope_hints: Array.isArray(payload.drive_scope_hints)
          ? payload.drive_scope_hints.filter((scope): scope is string => typeof scope === "string")
          : [],
        gmail_scope_hints: Array.isArray(payload.gmail_scope_hints)
          ? payload.gmail_scope_hints.filter((scope): scope is string => typeof scope === "string")
          : [],
        tokeninfo_error: typeof payload.tokeninfo_error === "string" ? payload.tokeninfo_error : null,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(`Google scope 진단 실패: ${msg}`);
    }  
  };

  const loadGoogleOAuthClientStatus = async () => {
    setIsOAuthClientLoading(true);

    try {
      const res = await fetch(`${API_BASE}/integrations/google/oauth-client/status`);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const payload = (await res.json()) as Partial<GoogleOAuthClientStatus>;
      setOauthClientStatus({
        configured: Boolean(payload.configured),
        client_type: typeof payload.client_type === "string" ? payload.client_type : null,
        project_id: typeof payload.project_id === "string" ? payload.project_id : null,
        client_id_masked: typeof payload.client_id_masked === "string" ? payload.client_id_masked : null,
        redirect_uri: typeof payload.redirect_uri === "string" ? payload.redirect_uri : null,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(`Google OAuth client 상태 조회 실패: ${msg}`);
    } finally {
      setIsOAuthClientLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
    loadGoogleScopeStatus();
    loadGoogleOAuthClientStatus();
  }, []);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (apiOrigin && event.origin !== apiOrigin) {
        return;
      }

      if (!event.data || typeof event.data !== "object") {
        return;
      }

      const payload = event.data as GoogleOAuthPopupEvent;
      if (payload.type === "google-oauth-success") {
        const grantedScopes = Array.isArray(payload.granted_scopes)
          ? payload.granted_scopes.filter((scope): scope is string => typeof scope === "string")
          : [];
        const expiresInSeconds =
          typeof payload.expires_in_seconds === "number" && Number.isFinite(payload.expires_in_seconds)
            ? Math.max(0, Math.floor(payload.expires_in_seconds))
            : null;

        setOauthFlowStates((prev) => ({
          ...prev,
          consent: "done",
          token_exchange: "done",
          token_save: "done",
        }));
        setOauthTokenMeta({
          token_type: typeof payload.token_type === "string" ? payload.token_type : null,
          expires_in_seconds: expiresInSeconds,
          granted_scopes: grantedScopes,
          access_token_masked:
            typeof payload.access_token_masked === "string" ? payload.access_token_masked : null,
        });
        setError(null);
        setNotice(payload.message ?? "Google OAuth Access Token 발급이 완료되었습니다.");
        void loadStatus();
        void loadGoogleScopeStatus();
      } else if (payload.type === "google-oauth-error") {
        setOauthFlowStates((prev) => ({
          ...prev,
          consent: prev.consent === "done" ? "done" : "error",
          token_exchange: prev.token_exchange === "done" ? "done" : "error",
          token_save: prev.token_save === "done" ? "done" : "error",
        }));
        setError(payload.message ?? "Google OAuth Access Token 발급에 실패했습니다.");
      }
    };

    window.addEventListener("message", onMessage);
    return () => {
      window.removeEventListener("message", onMessage);
    };
  }, [apiOrigin]);

  useEffect(() => {
    if (!isScopeLogsOpen) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsScopeLogsOpen(false);
      }
    };

    const previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousBodyOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isScopeLogsOpen]);

  const handleUploadGoogleOAuthClient = async () => {
    if (!googleOAuthClientFile) {
      setNotice("먼저 Google OAuth client JSON 파일을 선택해 주세요.");
      return;
    }

    setOauthFlowStates((prev) => ({
      ...createEmptyOAuthFlowStates(),
      client_upload: "active",
      auth_url: prev.auth_url === "done" ? "done" : "idle",
      consent: prev.consent === "done" ? "done" : "idle",
      token_exchange: prev.token_exchange === "done" ? "done" : "idle",
      token_save: prev.token_save === "done" ? "done" : "idle",
    }));
    setOauthTokenMeta(EMPTY_GOOGLE_OAUTH_TOKEN_META);
    setIsOAuthClientUploading(true);
    setError(null);
    setNotice(null);

    try {
      const formData = new FormData();
      formData.append("file", googleOAuthClientFile);

      const res = await fetch(`${API_BASE}/integrations/google/oauth-client`, {
        method: "POST",
        headers: {
          "X-Frontend-Origin": window.location.origin,
        },
        body: formData,
      });

      const result = (await res.json().catch(() => ({}))) as {
        detail?: unknown;
      } & Partial<GoogleOAuthClientStatus>;

      if (!res.ok) {
        const detail = typeof result.detail === "string" ? result.detail : `HTTP ${res.status}`;
        throw new Error(detail);
      }

      setOauthClientStatus({
        configured: Boolean(result.configured),
        client_type: typeof result.client_type === "string" ? result.client_type : null,
        project_id: typeof result.project_id === "string" ? result.project_id : null,
        client_id_masked: typeof result.client_id_masked === "string" ? result.client_id_masked : null,
        redirect_uri: typeof result.redirect_uri === "string" ? result.redirect_uri : null,
      });
      setOauthFlowStates((prev) => ({
        ...prev,
        client_upload: "done",
      }));
      setGoogleOAuthClientFile(null);
      setNotice("Google OAuth client JSON 등록 완료. 이제 'key 발급' 버튼을 누르세요.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setOauthFlowStates((prev) => ({
        ...prev,
        client_upload: "error",
      }));
      setError(`Google OAuth client JSON 등록 실패: ${msg}`);
    } finally {
      setIsOAuthClientUploading(false);
    }
  };

  const handleIssueGoogleToken = async () => {
    if (!oauthClientStatus.configured) {
      setError("먼저 Google OAuth client JSON을 등록해 주세요.");
      setOauthFlowStates((prev) => ({
        ...prev,
        auth_url: "error",
      }));
      return;
    }

    let authUrlReady = false;
    setOauthFlowStates((prev) => ({
      ...prev,
      client_upload: prev.client_upload === "done" ? "done" : prev.client_upload,
      auth_url: "active",
      consent: "idle",
      token_exchange: "idle",
      token_save: "idle",
    }));
    setOauthTokenMeta(EMPTY_GOOGLE_OAUTH_TOKEN_META);
    setIsIssuingGoogleToken(true);
    setError(null);
    setNotice(null);

    try {
      if (oauthClientStatus.client_type === "installed") {
        setOauthFlowStates((prev) => ({
          ...prev,
          auth_url: "active",
          consent: "active",
        }));
        setNotice("브라우저 로그인 창에서 권한 동의를 완료해 주세요. 완료될 때까지 잠시 기다립니다.");

        const installedRes = await fetch(`${API_BASE}/integrations/google/oauth/installed/issue`, {
          method: "POST",
        });
        const installedResult = (await installedRes.json().catch(() => ({}))) as {
          detail?: unknown;
        } & Partial<GoogleOAuthInstalledIssueResponse>;

        if (!installedRes.ok) {
          const detail =
            typeof installedResult.detail === "string"
              ? installedResult.detail
              : `HTTP ${installedRes.status}`;
          throw new Error(detail);
        }

        const grantedScopes = Array.isArray(installedResult.granted_scopes)
          ? installedResult.granted_scopes.filter((scope): scope is string => typeof scope === "string")
          : [];
        const expiresInSeconds =
          typeof installedResult.expires_in_seconds === "number" && Number.isFinite(installedResult.expires_in_seconds)
            ? Math.max(0, Math.floor(installedResult.expires_in_seconds))
            : null;

        setOauthFlowStates((prev) => ({
          ...prev,
          auth_url: "done",
          consent: "done",
          token_exchange: "done",
          token_save: "done",
        }));
        setOauthTokenMeta({
          token_type:
            typeof installedResult.token_type === "string"
              ? installedResult.token_type
              : null,
          expires_in_seconds: expiresInSeconds,
          granted_scopes: grantedScopes,
          access_token_masked:
            typeof installedResult.access_token_masked === "string"
              ? installedResult.access_token_masked
              : null,
        });
        setNotice(
          typeof installedResult.message === "string"
            ? installedResult.message
            : "Installed OAuth 발급이 완료되었습니다."
        );
        await loadStatus();
        await loadGoogleScopeStatus();
        return;
      }

      const res = await fetch(`${API_BASE}/integrations/google/oauth/start`);
      const result = (await res.json().catch(() => ({}))) as {
        detail?: unknown;
      } & Partial<GoogleOAuthStartResponse>;

      if (!res.ok) {
        const detail = typeof result.detail === "string" ? result.detail : `HTTP ${res.status}`;
        throw new Error(detail);
      }

      const authUrl = typeof result.auth_url === "string" ? result.auth_url : "";
      if (!authUrl) {
        throw new Error("OAuth 인증 URL 생성에 실패했습니다.");
      }

      authUrlReady = true;
      setOauthFlowStates((prev) => ({
        ...prev,
        auth_url: "done",
        consent: "active",
      }));

      const popup = window.open(authUrl, "google-oauth-issue", "width=560,height=760");
      if (!popup) {
        throw new Error("팝업이 차단되었습니다. 팝업 차단을 해제한 뒤 다시 시도해 주세요.");
      }

      setNotice("Google 로그인 팝업에서 권한 동의를 완료하면 access_token이 자동 저장됩니다.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setOauthFlowStates((prev) => ({
        ...prev,
        auth_url: authUrlReady ? prev.auth_url : "error",
        consent: authUrlReady ? "error" : prev.consent,
      }));
      setError(`Google OAuth 토큰 발급 시작 실패: ${msg}`);
    } finally {
      setIsIssuingGoogleToken(false);
    }
  };

  const handleSave = async () => {
    const trimmedGoogle = googleApiKey.trim();
    const trimmedSlackInviteLink = slackInviteLink.trim();

    const payload: Record<string, string> = {};
    if (trimmedGoogle) payload.google_api_key = trimmedGoogle;
    if (trimmedSlackInviteLink) payload.slack_invite_link = trimmedSlackInviteLink;

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
      } & Partial<ToolsStatus>;

      if (!res.ok) {
        const detail = typeof result.detail === "string" ? result.detail : `HTTP ${res.status}`;
        throw new Error(detail);
      }

      setGoogleApiKey("");
      setSlackInviteLink("");
      setNotice("키가 저장되었습니다.");
      setStatus({
        has_google_api_key: Boolean(result.has_google_api_key),
        has_slack_api_key: Boolean(result.has_slack_api_key),
        has_slack_invite_link: Boolean(result.has_slack_invite_link),
        google_api_key_masked:
          typeof result.google_api_key_masked === "string"
            ? result.google_api_key_masked
            : null,
        slack_api_key_masked:
          typeof result.slack_api_key_masked === "string"
            ? result.slack_api_key_masked
            : null,
        slack_invite_link_masked:
          typeof result.slack_invite_link_masked === "string"
            ? result.slack_invite_link_masked
            : null,
        updated_at:
          typeof result.updated_at === "string" ? result.updated_at : null,
      });
      await loadGoogleScopeStatus();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setError(`Tools 저장 실패: ${msg}`);
    } finally {
      setIsSaving(false);
    }
  };

  const openScopeLogsModal = () => {
    setIsScopeLogsOpen(true);
  };

  const closeScopeLogsModal = () => {
    setIsScopeLogsOpen(false);
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
            <div className={styles.title}>Tools</div>
            <div className={styles.subtitle}>
              Google OAuth 토큰과 Slack 초대 링크를 저장해 온보딩 자동화를 활성화합니다.
            </div>
          </div>
        </div>
      </div>

      <div className={styles.body}>
        <section className={styles.card}>
          <h2>Integration Keys</h2>
          <p className={styles.cardDescription}>
            저장된 값은 백엔드 런타임 메모리에만 유지됩니다.
          </p>

          <div className={styles.fieldGroup}>
            <div className={styles.labelWithHelp}>
              <label htmlFor="google-key" className={styles.label}>Google OAuth Access Token</label>
              <div className={styles.helpTrigger}>
                <button
                  type="button"
                  className={styles.helpIconButton}
                  aria-label="Onboarding Trigger 안내"
                  aria-describedby="onboarding-trigger-help-tooltip"
                >
                  ?
                </button>
                <div
                  id="onboarding-trigger-help-tooltip"
                  role="tooltip"
                  className={styles.helpTooltip}
                >
                  <div className={styles.helpTooltipTitle}>Onboarding Trigger</div>
                  <p className={styles.helpTooltipText}>
                    채팅 입력이 아래 형식이면 자동으로 입사 온보딩 워크플로우를 실행합니다.
                  </p>
                  <pre className={styles.helpTooltipCode}>[이름] [부서] [입사일] [이메일]</pre>
                  <pre className={styles.helpTooltipCode}>[홍길동] [플랫폼개발팀] [2026-03-17] [hong@example.com]</pre>

                  <ul className={styles.helpTooltipList}>
                    <li>Google Drive에서 온보딩/입사 파일 탐색</li>
                    <li>입사 서류 및 온보딩 자료 요약 생성</li>
                    <li>신규 입사자 이메일 발송 시도</li>
                    <li>Slack 초대 링크를 이메일에 포함하거나 워크스페이스 초대 시도</li>
                  </ul>

                  <p className={styles.helpTooltipWarning}>
                    Gmail/Drive 연동은 OAuth token(ya29...)에 필요한 scope가 포함되어야 합니다:
                    gmail.send, drive.readonly(또는 drive.metadata.readonly).
                  </p>
                </div>
              </div>
            </div>
            <input
              id="google-key"
              type="password"
              value={googleApiKey}
              onChange={(event) => setGoogleApiKey(event.target.value)}
              placeholder="ya29..."
              className={styles.input}
            />
            <div className={styles.fieldHint}>
              현재 상태: {status.has_google_api_key ? `설정됨 (${status.google_api_key_masked ?? "hidden"})` : "미설정"}
            </div>
          </div>

          <div className={styles.fieldGroup}>
            <div className={styles.scopeHeaderRow}>
              <label htmlFor="google-oauth-client-file" className={styles.label}>Google OAuth Client JSON</label>
              <button
                type="button"
                onClick={openScopeLogsModal}
                className={styles.logsButton}
              >
                logs
              </button>
            </div>
            <input
              id="google-oauth-client-file"
              type="file"
              accept=".json,application/json"
              onChange={(event) => setGoogleOAuthClientFile(event.target.files?.[0] ?? null)}
              className={styles.input}
            />
            <div className={styles.fieldHint}>
              상태: {oauthClientStatus.configured
                ? `등록됨 (type=${oauthClientStatus.client_type ?? "unknown"}, client=${oauthClientStatus.client_id_masked ?? "hidden"})`
                : "미등록"}
            </div>
            {oauthClientStatus.client_type === "installed" && (
              <div className={styles.fieldHint}>
                Installed 타입은 로컬 브라우저 로그인 후 token.json 저장 + refresh_token 자동 갱신으로 동작합니다.
              </div>
            )}
            {oauthClientStatus.redirect_uri && (
              <div className={styles.codeBlock}>Redirect URI: {oauthClientStatus.redirect_uri}</div>
            )}
            <div className={styles.actions}>
              <button
                type="button"
                onClick={handleUploadGoogleOAuthClient}
                disabled={isOAuthClientUploading || isOAuthClientLoading || isSaving}
                className={styles.refreshButton}
              >
                {isOAuthClientUploading ? "등록 중..." : "JSON 등록"}
              </button>
              <button
                type="button"
                onClick={handleIssueGoogleToken}
                disabled={isIssuingGoogleToken || isOAuthClientUploading || isOAuthClientLoading || isSaving}
                className={styles.saveButton}
              >
                {isIssuingGoogleToken ? "발급 준비 중..." : "key 발급"}
              </button>
              <button
                type="button"
                onClick={loadGoogleOAuthClientStatus}
                disabled={isOAuthClientUploading || isOAuthClientLoading || isIssuingGoogleToken || isSaving}
                className={styles.refreshButton}
              >
                {isOAuthClientLoading ? "조회 중..." : "OAuth 상태 새로고침"}
              </button>
            </div>

            <div className={styles.scopeCard}>
              <div className={styles.scopeHeader}>OAuth 내부 자동 처리 흐름</div>
              <div className={styles.scopeHint}>
                이미지의 수동 절차(Authorization Code 복사/토큰 교환)를 서버가 자동으로 수행합니다.
              </div>
              <ul className={styles.oauthFlowList}>
                {OAUTH_FLOW_STEPS.map((step) => {
                  const state = oauthFlowStates[step.key];
                  const badgeClassName = [
                    styles.oauthFlowBadge,
                    state === "done"
                      ? styles.oauthFlowDone
                      : state === "active"
                        ? styles.oauthFlowActive
                        : state === "error"
                          ? styles.oauthFlowError
                          : styles.oauthFlowIdle,
                  ].join(" ");

                  return (
                    <li key={step.key} className={styles.oauthFlowItem}>
                      <div className={styles.oauthFlowText}>
                        <div className={styles.oauthFlowTitle}>{step.title}</div>
                        <div className={styles.oauthFlowDescription}>{step.description}</div>
                      </div>
                      <span className={badgeClassName}>{OAUTH_FLOW_STATE_LABEL[state]}</span>
                    </li>
                  );
                })}
              </ul> 

              {oauthTokenMeta.granted_scopes.length > 0 && (
                <div className={styles.scopeGroup}>
                  <div className={styles.scopeLabel}>Issued Token Scopes</div>
                  <ul className={styles.scopeList}>
                    {oauthTokenMeta.granted_scopes.map((scope) => (
                      <li key={scope}>{scope}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div> 

          <div className={styles.sectionDivider} aria-hidden="true" />

          <div className={styles.fieldGroup}>
            <label htmlFor="slack-key" className={styles.label}>Slack Shared Invite Link</label>
            <input
              id="slack-key"
              type="text"
              value={slackInviteLink}
              onChange={(event) => setSlackInviteLink(event.target.value)}
              placeholder="https://join.slack.com/t/.../shared_invite/..."
              className={styles.input}
            />
            <div className={styles.fieldHint}>
              현재 상태: {status.has_slack_invite_link ? `설정됨 (${status.slack_invite_link_masked ?? "hidden"})` : "미설정"}
            </div>
            <div className={styles.fieldHint}>
              참고: 저장된 초대 링크는 온보딩 이메일 본문에 자동 포함됩니다.
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
          {isLoading && <div className={styles.loadingText}>Tools 상태를 불러오는 중...</div>} 
        </section>
      </div>

      {isScopeLogsOpen && (
        <div
          className={styles.modalBackdrop}
          role="presentation"
          onClick={closeScopeLogsModal}
        >
          <div
            className={styles.modal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="google-scope-logs-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className={styles.modalHeader}>
              <h3 id="google-scope-logs-title" className={styles.modalTitle}>Google OAuth Scope Logs</h3>
              <button
                type="button"
                onClick={closeScopeLogsModal}
                className={styles.modalCloseButton}
              >
                닫기
              </button>
            </div>

            <div className={styles.modalBody}>
              {!scopeStatus.token_configured && (
                <div className={styles.scopeHint}>Google 키가 설정되지 않았습니다.</div>
              )}

              {scopeStatus.token_configured && (
                <>
                  <div className={styles.scopeStatusRow}>
                    <span>Token Type: {scopeStatus.token_type ?? "unknown"}</span>
                    <span className={scopeStatus.drive_scope_ready ? styles.scopeReady : styles.scopeMissing}>
                      Drive: {scopeStatus.drive_scope_ready ? "OK" : "Missing"}
                    </span>
                    <span className={scopeStatus.gmail_scope_ready ? styles.scopeReady : styles.scopeMissing}>
                      Gmail: {scopeStatus.gmail_scope_ready ? "OK" : "Missing"}
                    </span>
                  </div>

                  {scopeStatus.tokeninfo_error && (
                    <div className={styles.scopeError}>{scopeStatus.tokeninfo_error}</div>
                  )}

                  <div className={styles.scopeGroup}>
                    <div className={styles.scopeLabel}>Granted Scopes</div>
                    {scopeStatus.granted_scopes.length > 0 ? (
                      <ul className={styles.scopeList}>
                        {scopeStatus.granted_scopes.map((scope) => (
                          <li key={scope}>{scope}</li>
                        ))}
                      </ul>
                    ) : (
                      <div className={styles.scopeHint}>scope 정보 없음</div>
                    )}
                  </div>

                  <div className={styles.scopeGroup}>
                    <div className={styles.scopeLabel}>Required Scopes</div>
                    <ul className={styles.scopeList}>
                      {scopeStatus.drive_scope_hints.map((scope) => (
                        <li key={scope}>Drive: {scope}</li>
                      ))}
                      {scopeStatus.gmail_scope_hints.map((scope) => (
                        <li key={scope}>Gmail: {scope}</li>
                      ))}
                    </ul>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
