"use client";
import { useEffect, useState } from "react";

const GREEN = "#3cff8c";
const DIM = "#2c7a5a";
const BG = "#060a08";

function authedFetch(url, opts = {}) {
  const pw = typeof window !== "undefined" ? localStorage.getItem("grace_pw") || "" : "";
  return fetch(url, {
    ...opts,
    headers: { ...(opts.headers || {}), "x-grace-password": pw },
  });
}

const STATUS_COLOR = { uploaded: GREEN, running: "#ffd84a", queued: "#ffd84a", failed: "#ff5c5c" };
const STATUS_LABEL = { uploaded: "uploaded", running: "running", queued: "queued", failed: "failed" };

export default function Page() {
  const [pw, setPw] = useState("");
  const [unlocked, setUnlocked] = useState(false);
  const [ytConnected, setYtConnected] = useState(null);
  const [title, setTitle] = useState("");
  const [script, setScript] = useState("");
  const [status, setStatus] = useState(null);
  const [runUrl, setRunUrl] = useState(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState("create");
  const [history, setHistory] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("grace_pw") : null;
    if (saved !== null) {
      setPw(saved);
      setUnlocked(true);
    }
  }, []);

  useEffect(() => {
    if (!unlocked) return;
    authedFetch("/api/youtube-status")
      .then((r) => r.json())
      .then((d) => setYtConnected(!!d.connected))
      .catch(() => setYtConnected(false));
  }, [unlocked]);

  function loadHistory() {
    setHistoryLoading(true);
    authedFetch("/api/history")
      .then((r) => r.json())
      .then((d) => setHistory(d.history || []))
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  }

  useEffect(() => {
    if (unlocked && tab === "history") loadHistory();
  }, [unlocked, tab]);

  function enter() {
    localStorage.setItem("grace_pw", pw);
    setUnlocked(true);
  }

  async function createVideo() {
    setBusy(true);
    setStatus("Sending to the pipeline...");
    setRunUrl(null);
    try {
      const res = await authedFetch("/api/create-video", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ script_text: script, title }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus(`Error: ${data.error || res.statusText}`);
      } else {
        setStatus(
          `Started. It builds and uploads in the background — ` +
          `watch progress or grab the link when it's done:`
        );
        setRunUrl(data.run_url);
      }
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
    setBusy(false);
  }

  if (!unlocked) {
    return (
      <Center>
        <h1 style={{ color: GREEN }}>&gt; GRACE_</h1>
        <input
          type="password"
          placeholder="password"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          style={inputStyle}
        />
        <button onClick={enter} style={buttonStyle}>unlock</button>
      </Center>
    );
  }

  return (
    <Center wide>
      <h1 style={{ color: GREEN, marginBottom: 4 }}>&gt; GRACE_</h1>
      <p style={{ color: DIM, marginTop: 0 }}>How It Actually Broke — script in, video out.</p>

      <div style={{ display: "flex", gap: 8, margin: "16px 0" }}>
        <TabButton active={tab === "create"} onClick={() => setTab("create")}>create</TabButton>
        <TabButton active={tab === "history"} onClick={() => setTab("history")}>history</TabButton>
      </div>

      {tab === "create" && (
        <>
          <div style={{ marginBottom: 16 }}>
            {ytConnected === null && <span style={{ color: DIM }}>checking YouTube connection...</span>}
            {ytConnected === true && <span style={{ color: GREEN }}>✓ YouTube connected</span>}
            {ytConnected === false && (
              <a href={`/api/auth/google/start?pw=${encodeURIComponent(pw)}`} style={{ ...buttonStyle, display: "inline-block", textDecoration: "none" }}>
                connect YouTube
              </a>
            )}
          </div>

          <input
            placeholder="title (optional — first line used if blank)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }}
          />
          <textarea
            placeholder={"Paste or type your script.\nLeave a blank line between scenes.\nFirst scene = hook, last = call-to-action."}
            value={script}
            onChange={(e) => setScript(e.target.value)}
            rows={14}
            style={{ ...inputStyle, width: "100%", boxSizing: "border-box", marginTop: 10, resize: "vertical" }}
          />

          <button
            onClick={createVideo}
            disabled={busy || !script.trim()}
            style={{ ...buttonStyle, width: "100%", marginTop: 12, opacity: busy || !script.trim() ? 0.5 : 1 }}
          >
            {busy ? "working..." : "./create_video"}
          </button>

          {status && (
            <p style={{ color: GREEN, marginTop: 16, whiteSpace: "pre-wrap" }}>
              {status}
              {runUrl && (
                <>
                  {" "}
                  <a href={runUrl} target="_blank" rel="noreferrer" style={{ color: GREEN }}>
                    open run →
                  </a>
                </>
              )}
            </p>
          )}
        </>
      )}

      {tab === "history" && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <span style={{ color: DIM, fontSize: 13 }}>every video GRACE has attempted</span>
            <button onClick={loadHistory} style={{ ...buttonStyle, padding: "4px 10px", fontSize: 13 }}>
              {historyLoading ? "..." : "refresh"}
            </button>
          </div>

          {historyLoading && history === null && <p style={{ color: DIM }}>loading...</p>}
          {!historyLoading && history !== null && history.length === 0 && (
            <p style={{ color: DIM }}>Nothing yet — create a video and it'll show up here.</p>
          )}

          {history && history.map((item) => (
            <div
              key={item.run_id}
              style={{
                border: `1px solid ${DIM}`,
                borderRadius: 6,
                padding: "10px 12px",
                marginBottom: 8,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span style={{ color: "#eafff2", fontWeight: 600 }}>{item.title || "Untitled"}</span>
                <span style={{ color: STATUS_COLOR[item.status] || DIM, fontSize: 13, whiteSpace: "nowrap" }}>
                  {STATUS_LABEL[item.status] || item.status}
                </span>
              </div>
              {item.status === "failed" && (
                <div style={{ color: "#ff8c8c", fontSize: 13, marginTop: 4 }}>
                  {item.failed_step ? `failed at: ${item.failed_step}` : "failed"}
                  {item.error ? ` — ${item.error.slice(0, 140)}` : ""}
                </div>
              )}
              <div style={{ marginTop: 6, fontSize: 13, display: "flex", gap: 14 }}>
                {item.run_url && (
                  <a href={item.run_url} target="_blank" rel="noreferrer" style={{ color: DIM }}>
                    build log →
                  </a>
                )}
                {item.video_url && (
                  <a href={item.video_url} target="_blank" rel="noreferrer" style={{ color: GREEN }}>
                    watch on YouTube →
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </Center>
  );
}

function TabButton({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      style={{
        ...buttonStyle,
        padding: "6px 14px",
        fontSize: 14,
        borderColor: active ? GREEN : DIM,
        color: active ? GREEN : DIM,
      }}
    >
      {children}
    </button>
  );
}

function Center({ children, wide }) {
  return (
    <div style={{ minHeight: "100vh", display: "flex", justifyContent: "center", padding: "24px 16px" }}>
      <div style={{ width: "100%", maxWidth: wide ? 560 : 320 }}>{children}</div>
    </div>
  );
}

const inputStyle = {
  display: "block",
  width: "100%",
  padding: "10px 12px",
  margin: "8px 0",
  background: "#0b1310",
  border: `1px solid ${DIM}`,
  color: "#eafff2",
  borderRadius: 6,
  fontFamily: "inherit",
  fontSize: 15,
};

const buttonStyle = {
  padding: "10px 16px",
  background: "transparent",
  border: `2px solid ${GREEN}`,
  color: GREEN,
  borderRadius: 6,
  fontFamily: "inherit",
  fontSize: 15,
  cursor: "pointer",
};
