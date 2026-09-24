import {
  ButtonItem,
  DialogBody,
  DialogButton,
  DialogFooter,
  DialogHeader,
  ModalRoot,
  PanelSection,
  PanelSectionRow,
  showModal,
  staticClasses,
  TextField,
  ToggleField,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { useState, useEffect, useCallback } from "react";
import { FaShieldAlt } from "react-icons/fa";

// ── types ──────────────────────────────────────────────────────

interface VPNError {
  timestamp: number;
  operation: string;
  error_type: string;
  message: string;
  details: Record<string, any>;
}

interface Profile {
  id: string;
  protocol: string;
  name: string;
  server: string;
  port: number;
  raw_uri: string;
  source: string;
  added_at: number;
  active: boolean;
}

interface SubscriptionUserinfo {
  upload: number | null;
  download: number | null;
  total: number | null;
  expire: number | null;
}

interface Subscription {
  id: string;
  url: string;
  title: string;
  announce: string;
  support_url: string;
  update_interval_hours: string;
  userinfo: SubscriptionUserinfo;
  last_refreshed: number;
  profile_ids: string[];
}

interface OpResult {
  success: boolean;
  error: string | null;
  [key: string]: any;
}

interface ConnectionStatus {
  running: boolean;
  pid: number | null;
  uptime_s: number | null;
  active_profile_id: string | null;
  active_profile_name: string | null;
}

interface DiagnosticsProbe {
  name: string;
  kind: "ping" | "http";
  target: string;
  ok: boolean;
  detail: string;
  latency_ms: number | null;
}

// ── RPC bindings ───────────────────────────────────────────────

const listProfiles = callable<[], Profile[]>("list_profiles");
const addProfile = callable<[{ uri: string }], OpResult>("add_profile");
const deleteProfile = callable<[{ profile_id: string }], OpResult>("delete_profile");

const listSubscriptions = callable<[], Subscription[]>("list_subscriptions");
const addSubscription = callable<[{ url: string }], OpResult>("add_subscription");
const refreshSubscription = callable<[{ sub_id: string }], OpResult>("refresh_subscription");
const deleteSubscription = callable<[{ sub_id: string; delete_profiles: boolean }], OpResult>(
  "delete_subscription",
);

const connectProfile = callable<[{ profile_id: string }], OpResult>("connect");
const disconnectVpn = callable<[], OpResult>("disconnect");
const getStatus = callable<[], ConnectionStatus>("status");

const diagnoseConnectivity = callable<[], DiagnosticsProbe[]>("diagnose_connectivity");
const getErrors = callable<[], VPNError[]>("get_errors");
const clearErrors = callable<[], boolean>("clear_errors");

// ── helpers ────────────────────────────────────────────────────

function formatTimestamp(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString();
}

function formatExpire(expire: number | null): string {
  if (!expire) return "";
  const days = Math.round((expire * 1000 - Date.now()) / 86400000);
  if (days < 0) return "истекла";
  return `осталось ~${days} дн.`;
}

function formatBytes(n: number | null): string {
  if (n === null || n === undefined) return "?";
  if (n === 0) return "0";
  const units = ["Б", "КБ", "МБ", "ГБ", "ТБ"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(1)} ${units[i]}`;
}

// ── modals ─────────────────────────────────────────────────────

function ImportModal({
  closeModal,
  onSuccess,
}: {
  closeModal?: () => void;
  onSuccess: () => void;
}) {
  const [mode, setMode] = useState<"link" | "subscription">("link");
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);

  const handleImport = async () => {
    const trimmed = value.trim();
    if (!trimmed) {
      toaster.toast({ title: "Ошибка", body: "Поле не может быть пустым" });
      return;
    }
    setLoading(true);
    try {
      const result =
        mode === "link"
          ? await addProfile({ uri: trimmed })
          : await addSubscription({ url: trimmed });

      if (result.success) {
        toaster.toast({
          title: mode === "link" ? "Профиль добавлен" : "Подписка добавлена",
          body:
            mode === "subscription" && result.profiles_added !== undefined
              ? `Найдено профилей: ${result.profiles_added}`
              : trimmed,
        });
        onSuccess();
        closeModal?.();
      } else {
        toaster.toast({ title: "Ошибка импорта", body: result.error ?? "Неизвестная ошибка" });
      }
    } catch (e) {
      toaster.toast({ title: "Ошибка", body: String(e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <DialogHeader>Добавить</DialogHeader>
      <DialogBody>
        <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
          <DialogButton
            onClick={() => setMode("link")}
            style={{ opacity: mode === "link" ? 1 : 0.6 }}
          >
            Ссылка
          </DialogButton>
          <DialogButton
            onClick={() => setMode("subscription")}
            style={{ opacity: mode === "subscription" ? 1 : 0.6 }}
          >
            Подписка
          </DialogButton>
        </div>
        <TextField
          label={mode === "link" ? "Ссылка профиля" : "URL подписки"}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          description={
            mode === "link"
              ? "vless:// vmess:// trojan:// ss:// hysteria2://"
              : "https://..."
          }
        />
      </DialogBody>
      <DialogFooter>
        <DialogButton onClick={handleImport} disabled={loading}>
          {loading ? "Добавление..." : "Добавить"}
        </DialogButton>
        <DialogButton onClick={closeModal}>Отмена</DialogButton>
      </DialogFooter>
    </ModalRoot>
  );
}

function DeleteProfileModal({
  profile,
  closeModal,
  onSuccess,
}: {
  profile: Profile;
  closeModal?: () => void;
  onSuccess: () => void;
}) {
  const [loading, setLoading] = useState(false);

  const handleDelete = async () => {
    setLoading(true);
    try {
      const result = await deleteProfile({ profile_id: profile.id });
      if (result.success) {
        toaster.toast({ title: "Профиль удалён", body: profile.name });
        onSuccess();
        closeModal?.();
      } else {
        toaster.toast({ title: "Ошибка удаления", body: result.error ?? "Неизвестная ошибка" });
      }
    } catch (e) {
      toaster.toast({ title: "Ошибка", body: String(e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <DialogHeader>Удалить профиль</DialogHeader>
      <DialogBody>
        <div style={{ fontSize: "14px" }}>
          Удалить профиль «{profile.name}»?
          {profile.active && " Активное соединение будет разорвано."}
        </div>
      </DialogBody>
      <DialogFooter>
        <DialogButton onClick={handleDelete} disabled={loading}>
          {loading ? "Удаление…" : "Удалить"}
        </DialogButton>
        <DialogButton onClick={closeModal}>Отмена</DialogButton>
      </DialogFooter>
    </ModalRoot>
  );
}

function DeleteSubscriptionModal({
  subscription,
  closeModal,
  onSuccess,
}: {
  subscription: Subscription;
  closeModal?: () => void;
  onSuccess: () => void;
}) {
  const [loading, setLoading] = useState(false);

  const handleDelete = async () => {
    setLoading(true);
    try {
      const result = await deleteSubscription({ sub_id: subscription.id, delete_profiles: true });
      if (result.success) {
        toaster.toast({ title: "Подписка удалена", body: subscription.title || subscription.url });
        onSuccess();
        closeModal?.();
      } else {
        toaster.toast({ title: "Ошибка удаления", body: result.error ?? "Неизвестная ошибка" });
      }
    } catch (e) {
      toaster.toast({ title: "Ошибка", body: String(e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <DialogHeader>Удалить подписку</DialogHeader>
      <DialogBody>
        <div style={{ fontSize: "14px" }}>
          Удалить подписку «{subscription.title || subscription.url}» и все её профили?
        </div>
      </DialogBody>
      <DialogFooter>
        <DialogButton onClick={handleDelete} disabled={loading}>
          {loading ? "Удаление…" : "Удалить"}
        </DialogButton>
        <DialogButton onClick={closeModal}>Отмена</DialogButton>
      </DialogFooter>
    </ModalRoot>
  );
}

// ── main content ───────────────────────────────────────────────

function Content() {
  const [status, setStatus] = useState<ConnectionStatus>({
    running: false,
    pid: null,
    uptime_s: null,
    active_profile_id: null,
    active_profile_name: null,
  });
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [loadingMap, setLoadingMap] = useState<Record<string, boolean>>({});
  const [refreshingMap, setRefreshingMap] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<VPNError[]>([]);
  const [showErrors, setShowErrors] = useState(false);
  const [probes, setProbes] = useState<DiagnosticsProbe[] | null>(null);
  const [probesLoading, setProbesLoading] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await getStatus());
    } catch (e) {
      console.error("Failed to refresh status:", e);
    }
  }, []);

  const refreshProfiles = useCallback(async () => {
    try {
      setProfiles(await listProfiles());
    } catch (e) {
      console.error("Failed to refresh profiles:", e);
    }
  }, []);

  const refreshSubscriptions = useCallback(async () => {
    try {
      setSubscriptions(await listSubscriptions());
    } catch (e) {
      console.error("Failed to refresh subscriptions:", e);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshStatus(), refreshProfiles(), refreshSubscriptions()]);
  }, [refreshStatus, refreshProfiles, refreshSubscriptions]);

  const loadErrors = useCallback(async () => {
    try {
      setErrors(await getErrors());
    } catch (e) {
      console.error("Failed to load errors:", e);
    }
  }, []);

  const handleToggleProfile = useCallback(
    async (profile: Profile, enabled: boolean) => {
      setLoadingMap((prev) => ({ ...prev, [profile.id]: true }));
      try {
        const result = enabled ? await connectProfile({ profile_id: profile.id }) : await disconnectVpn();
        if (!result.success) {
          toaster.toast({ title: "Ошибка", body: result.error ?? "Неизвестная ошибка" });
          await loadErrors();
        } else {
          toaster.toast({
            title: enabled ? "Подключено" : "Отключено",
            body: profile.name,
          });
        }
      } catch (e) {
        toaster.toast({ title: "Ошибка", body: String(e) });
        await loadErrors();
      } finally {
        setLoadingMap((prev) => ({ ...prev, [profile.id]: false }));
        await refreshStatus();
        await refreshProfiles();
      }
    },
    [refreshStatus, refreshProfiles, loadErrors],
  );

  const handleRefreshSubscription = useCallback(
    async (sub: Subscription) => {
      setRefreshingMap((prev) => ({ ...prev, [sub.id]: true }));
      try {
        const result = await refreshSubscription({ sub_id: sub.id });
        if (result.success) {
          toaster.toast({
            title: "Подписка обновлена",
            body: `Профилей: ${result.profiles_added ?? "?"}`,
          });
        } else {
          toaster.toast({ title: "Ошибка обновления", body: result.error ?? "Неизвестная ошибка" });
        }
      } catch (e) {
        toaster.toast({ title: "Ошибка", body: String(e) });
      } finally {
        setRefreshingMap((prev) => ({ ...prev, [sub.id]: false }));
        await refreshAll();
      }
    },
    [refreshAll],
  );

  const handleDiagnose = useCallback(async () => {
    setProbesLoading(true);
    try {
      const res = await diagnoseConnectivity();
      setProbes(res);
      const ok = res.filter((p) => p.ok).length;
      toaster.toast({ title: "Проверка связи", body: `${ok}/${res.length} доступно` });
    } catch (e) {
      toaster.toast({ title: "Ошибка диагностики", body: String(e) });
    } finally {
      setProbesLoading(false);
    }
  }, []);

  const handleClearErrors = useCallback(async () => {
    try {
      await clearErrors();
      setErrors([]);
      toaster.toast({ title: "История ошибок очищена", body: "" });
    } catch (e) {
      toaster.toast({ title: "Ошибка очистки", body: String(e) });
    }
  }, []);

  useEffect(() => {
    refreshAll();
    loadErrors();

    const statusInterval = setInterval(refreshStatus, 3000);
    const errorsInterval = setInterval(loadErrors, 10000);

    return () => {
      clearInterval(statusInterval);
      clearInterval(errorsInterval);
    };
  }, [refreshAll, refreshStatus, loadErrors]);

  const subById: Record<string, Subscription> = {};
  for (const s of subscriptions) {
    for (const pid of s.profile_ids) subById[pid] = s;
  }

  return (
    <>
      <PanelSection title="Соединение">
        <PanelSectionRow>
          <div style={{ fontSize: "14px", padding: "4px 0" }}>
            {status.running ? (
              <>
                <span style={{ color: "#4ade80" }}>● Подключено</span>
                {status.active_profile_name && <>: {status.active_profile_name}</>}
              </>
            ) : (
              <span style={{ color: "#8b929a" }}>○ Отключено</span>
            )}
          </div>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Профили">
        {profiles.length === 0 && (
          <PanelSectionRow>
            <div style={{ color: "#888", fontSize: "14px" }}>Нет добавленных профилей</div>
          </PanelSectionRow>
        )}
        {profiles.map((p) => (
          <PanelSectionRow key={p.id}>
            <ToggleField
              label={p.name}
              description={
                subById[p.id]
                  ? `${p.protocol} · ${subById[p.id].title || "подписка"}`
                  : `${p.protocol} · ${p.server}`
              }
              checked={p.active}
              disabled={!!loadingMap[p.id]}
              onChange={(val) => handleToggleProfile(p, val)}
            />
            <div style={{ marginTop: "4px" }}>
              <ButtonItem
                layout="below"
                onClick={() =>
                  showModal(<DeleteProfileModal profile={p} onSuccess={refreshAll} />)
                }
              >
                Удалить профиль
              </ButtonItem>
            </div>
          </PanelSectionRow>
        ))}
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => showModal(<ImportModal onSuccess={refreshAll} />)}>
            Добавить
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Подписки">
        {subscriptions.length === 0 && (
          <PanelSectionRow>
            <div style={{ color: "#888", fontSize: "14px" }}>Нет добавленных подписок</div>
          </PanelSectionRow>
        )}
        {subscriptions.map((s) => (
          <PanelSectionRow key={s.id}>
            <div style={{ padding: "6px 0" }}>
              <div style={{ fontWeight: "bold" }}>{s.title || s.url}</div>
              <div style={{ fontSize: "12px", color: "#8b929a" }}>
                {s.profile_ids.length} профилей
                {s.userinfo.total ? ` · ${formatBytes(s.userinfo.total)}` : ""}
                {s.userinfo.expire ? ` · ${formatExpire(s.userinfo.expire)}` : ""}
              </div>
              {s.announce && (
                <div style={{ fontSize: "12px", color: "#8b929a", marginTop: "2px" }}>{s.announce}</div>
              )}
            </div>
            <div style={{ display: "flex", gap: "4px", marginTop: "4px" }}>
              <ButtonItem
                layout="below"
                disabled={!!refreshingMap[s.id]}
                onClick={() => handleRefreshSubscription(s)}
              >
                {refreshingMap[s.id] ? "Обновление…" : "Обновить"}
              </ButtonItem>
              <ButtonItem
                layout="below"
                onClick={() =>
                  showModal(<DeleteSubscriptionModal subscription={s} onSuccess={refreshAll} />)
                }
              >
                Удалить
              </ButtonItem>
            </div>
          </PanelSectionRow>
        ))}
      </PanelSection>

      <PanelSection title="Диагностика">
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={probesLoading} onClick={handleDiagnose}>
            {probesLoading ? "Проверка…" : "Проверить соединение"}
          </ButtonItem>
        </PanelSectionRow>
        {probes &&
          probes.map((p, i) => (
            <PanelSectionRow key={`${p.name}-${i}`}>
              <div
                style={{
                  padding: "8px",
                  fontSize: "12px",
                  borderLeft: `3px solid ${p.ok ? "#4ade80" : "#f87171"}`,
                  paddingLeft: "10px",
                  marginBottom: "4px",
                }}
              >
                <div style={{ fontWeight: "bold" }}>
                  {p.ok ? "✓" : "✗"} {p.name}
                </div>
                <div style={{ color: "#8b929a" }}>{p.detail}</div>
              </div>
            </PanelSectionRow>
          ))}
      </PanelSection>

      <PanelSection title="Ошибки">
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => {
              setShowErrors(!showErrors);
              if (!showErrors) loadErrors();
            }}
          >
            {showErrors ? "Скрыть ошибки" : `Просмотр ошибок${errors.length > 0 ? ` (${errors.length})` : ""}`}
          </ButtonItem>
        </PanelSectionRow>

        {showErrors && (
          <>
            {errors.length > 0 && (
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={handleClearErrors}>
                  Очистить историю ошибок
                </ButtonItem>
              </PanelSectionRow>
            )}

            {errors.length === 0 ? (
              <PanelSectionRow>
                <div style={{ padding: "10px", textAlign: "center", color: "#888", fontSize: "14px" }}>
                  Ошибок не обнаружено
                </div>
              </PanelSectionRow>
            ) : (
              errors
                .slice()
                .reverse()
                .map((error) => (
                  <PanelSectionRow key={`${error.timestamp}-${error.operation}`}>
                    <div
                      style={{
                        padding: "12px",
                        backgroundColor: "rgba(255, 0, 0, 0.1)",
                        borderRadius: "4px",
                        marginBottom: "8px",
                        fontSize: "12px",
                      }}
                    >
                      <div style={{ marginBottom: "4px", fontWeight: "bold" }}>
                        {formatTimestamp(error.timestamp)} - {error.operation}
                      </div>
                      <div style={{ marginBottom: "4px", color: "#FF6B6B" }}>
                        <strong>Тип:</strong> {error.error_type}
                      </div>
                      <div style={{ marginBottom: "4px" }}>
                        <strong>Сообщение:</strong> {error.message}
                      </div>
                      {Object.keys(error.details).length > 0 && (
                        <details style={{ marginTop: "8px" }}>
                          <summary style={{ cursor: "pointer", color: "#888" }}>Детали</summary>
                          <pre
                            style={{
                              marginTop: "4px",
                              padding: "8px",
                              backgroundColor: "rgba(0, 0, 0, 0.3)",
                              borderRadius: "4px",
                              fontSize: "11px",
                              overflow: "auto",
                            }}
                          >
                            {JSON.stringify(error.details, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                  </PanelSectionRow>
                ))
            )}
          </>
        )}
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  console.log("Ultimate VPN Deck plugin initializing");

  return {
    name: "Ultimate VPN Deck",
    titleView: <div className={staticClasses.Title}>Ultimate VPN Deck</div>,
    content: <Content />,
    icon: <FaShieldAlt />,
    onDismount() {
      console.log("Ultimate VPN Deck plugin unloading");
    },
  };
});
