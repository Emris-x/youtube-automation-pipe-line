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

export default function Page() {
  const [pw, setPw] = useState("");
  const [unlocked, setUnlocked] = useState(false);
  const [ytConnected, setYtConnected] = useState(null);
  const [title, setTitle] = useState("");
  const [script, setScript] = useState("");
  const [status, setStatus] = useState(null);
  const [runUrl, setRunUrl] = useState(null);
  const [busy, setBusy] = useState(false);

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

      <div style={{ margin: "16px 0" }}>
        {ytConnected === null && <span style={{ color: DIM }}>checking YouTube connection...</span>}
        {ytConnected === true && <span style={{ color: GREEN }}>✓ YouTube connected</span>}
        {ytConnected === false && (
          <a href="/api/auth/google/start" style={{ ...buttonStyle, display: "inline-block", textDecoration: "none" }}>
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
    </Center>
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
