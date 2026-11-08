"use client";
import { useEffect, useRef, useState } from "react";

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
  const [graceTimeItem, setGraceTimeItem] = useState(null); // item currently shown full-screen, or null
  const [necessities, setNecessities] = useState(null); // scanned scenes, or null before first scan
  const [necessitiesLoading, setNecessitiesLoading] = useState(false);
  const [necessitiesError, setNecessitiesError] = useState(null);
  const [uploadingSceneId, setUploadingSceneId] = useState(null);
  const [copiedSceneId, setCopiedSceneId] = useState(null);
  const [createGate, setCreateGate] = useState(null); // {scenes, missing} when create is paused waiting on a decision

  // a stale gate from a previous script shouldn't silently apply to a new one
  useEffect(() => {
    setCreateGate(null);
  }, [script]);

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

  function scanNecessities() {
    if (!script.trim()) {
      setNecessitiesError("Paste a script on the create tab first.");
      return;
    }
    setNecessitiesLoading(true);
    setNecessitiesError(null);
    authedFetch("/api/necessities/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ script_text: script }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (d.error) setNecessitiesError(d.error);
        else setNecessities(d.scenes || []);
      })
      .catch((e) => setNecessitiesError(e.message))
      .finally(() => setNecessitiesLoading(false));
  }

  useEffect(() => {
    if (unlocked && tab === "necessities" && necessities === null && !necessitiesLoading) scanNecessities();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unlocked, tab]);

  function copyPrompt(sceneId, text) {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(text).catch(() => {});
    }
    setCopiedSceneId(sceneId);
    setTimeout(() => setCopiedSceneId((cur) => (cur === sceneId ? null : cur)), 1500);
  }

  // Downscales/re-encodes an uploaded image client-side before it goes over
  // the wire -- keeps payloads small and every library image a consistent
  // max size, regardless of what the generator handed back.
  function resizeImageToDataUrl(file, maxDim = 1080) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const reader = new FileReader();
      reader.onerror = reject;
      reader.onload = () => {
        img.onerror = reject;
        img.onload = () => {
          const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
          const w = Math.max(1, Math.round(img.width * scale));
          const h = Math.max(1, Math.round(img.height * scale));
          const canvas = document.createElement("canvas");
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext("2d");
          ctx.drawImage(img, 0, 0, w, h);
          resolve(canvas.toDataURL("image/png"));
        };
        img.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  }

  async function uploadForScene(scene, file) {
    setUploadingSceneId(scene.id);
    try {
      const dataUrl = await resizeImageToDataUrl(file);
      const res = await authedFetch("/api/necessities/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          data_base64: dataUrl,
          tags: scene.tags.length ? scene.tags : [scene.id],
          title,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setNecessitiesError(data.error || "Upload failed.");
      } else {
        setNecessities((cur) =>
          cur.map((s) => (s.id === scene.id ? { ...s, covered: true, matches: [...s.matches, data.image] } : s))
        );
      }
    } catch (e) {
      setNecessitiesError(e.message);
    }
    setUploadingSceneId(null);
  }

  function enter() {
    localStorage.setItem("grace_pw", pw);
    setUnlocked(true);
  }

  // Checks the picture library before actually starting a build, and pauses
  // with a yes/no instead of building silently with scenes that have no
  // picture. Call it again (e.g. from the gate's "continue anyway" button)
  // once createGate is already set, and it skips straight to the real build.
  async function createVideo() {
    if (!createGate) {
      setBusy(true);
      setStatus("Checking the picture library...");
      try {
        const res = await authedFetch("/api/necessities/scan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ script_text: script }),
        });
        const data = await res.json();
        if (res.ok && data.scenes) {
          const missing = data.scenes.filter((s) => !s.covered);
          if (missing.length > 0) {
            setCreateGate({ scenes: data.scenes, missing });
            setBusy(false);
            setStatus(null);
            return; // wait for the user to pick continue-anyway or go-upload
          }
        }
        // every scene covered (or the check itself came back empty) -> build
      } catch (e) {
        // the coverage check itself failing shouldn't block a build the
        // person explicitly asked to start -- fail open, just like before
        // this feature existed.
      }
    }

    setCreateGate(null);
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
        <TabButton active={tab === "necessities"} onClick={() => setTab("necessities")}>necessities</TabButton>
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

          {createGate && (
            <div style={{ border: "1px solid #ffd84a", borderRadius: 6, padding: "10px 12px", marginTop: 12 }}>
              <p style={{ color: "#ffd84a", margin: 0, fontSize: 13 }}>
                {createGate.scenes.length - createGate.missing.length}/{createGate.scenes.length} scenes have a picture
                in the library. {createGate.missing.length} {createGate.missing.length === 1 ? "scene" : "scenes"} will
                fall back to the old circle/bar look.
              </p>
              <div style={{ display: "flex", gap: 14, marginTop: 10 }}>
                <button onClick={createVideo} style={{ ...buttonStyle, padding: "6px 12px", fontSize: 13 }}>
                  continue anyway
                </button>
                <button
                  onClick={() => {
                    setCreateGate(null);
                    setTab("necessities");
                  }}
                  style={{ ...buttonStyle, padding: "6px 12px", fontSize: 13, borderColor: DIM, color: DIM }}
                >
                  go upload pictures →
                </button>
              </div>
            </div>
          )}

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

      {tab === "necessities" && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <span style={{ color: DIM, fontSize: 13 }}>
              scans the script on the create tab for what pictures it needs
            </span>
            <button onClick={scanNecessities} style={{ ...buttonStyle, padding: "4px 10px", fontSize: 13 }}>
              {necessitiesLoading ? "..." : "rescan"}
            </button>
          </div>

          {necessitiesError && <p style={{ color: "#ff8c8c", fontSize: 13 }}>{necessitiesError}</p>}
          {necessitiesLoading && necessities === null && <p style={{ color: DIM }}>scanning...</p>}
          {!necessitiesLoading && necessities !== null && necessities.length === 0 && (
            <p style={{ color: DIM }}>No scenes found — check the script on the create tab.</p>
          )}

          {necessities && necessities.length > 0 && (
            <p style={{ color: DIM, fontSize: 13, marginBottom: 14 }}>
              {necessities.filter((s) => s.covered).length}/{necessities.length} scenes already have a picture in the library.
            </p>
          )}

          {necessities && necessities.map((scene) => (
            <div
              key={scene.id}
              style={{
                border: `1px solid ${scene.covered ? DIM : "#ff8c8c"}`,
                borderRadius: 6,
                padding: "10px 12px",
                marginBottom: 10,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span style={{ color: "#eafff2", fontSize: 13 }}>{scene.text}</span>
                <span style={{ color: scene.covered ? GREEN : "#ff8c8c", fontSize: 12, whiteSpace: "nowrap" }}>
                  {scene.covered ? "✓ have it" : "needs one"}
                </span>
              </div>

              {scene.tags.length > 0 && (
                <div style={{ color: DIM, fontSize: 12, marginTop: 6 }}>tags: {scene.tags.join(", ")}</div>
              )}

              {scene.matches.length > 0 && (
                <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                  {scene.matches.map((m) => (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      key={m.id}
                      src={m.url}
                      alt={m.tags ? m.tags.join(", ") : m.id}
                      style={{ width: 56, height: 56, objectFit: "cover", borderRadius: 4, border: `1px solid ${DIM}` }}
                    />
                  ))}
                </div>
              )}

              <div
                style={{
                  marginTop: 8,
                  background: "#0b1310",
                  border: `1px solid ${DIM}`,
                  borderRadius: 4,
                  padding: "8px 10px",
                  fontSize: 12,
                  color: "#cfe9db",
                  whiteSpace: "pre-wrap",
                }}
              >
                {scene.prompt}
              </div>

              <div style={{ display: "flex", gap: 14, marginTop: 8, alignItems: "center" }}>
                <button
                  onClick={() => copyPrompt(scene.id, scene.prompt)}
                  style={{ background: "none", border: "none", color: GREEN, fontFamily: "inherit", fontSize: 13, cursor: "pointer", padding: 0 }}
                >
                  {copiedSceneId === scene.id ? "copied ✓" : "copy prompt →"}
                </button>

                <label style={{ color: DIM, fontSize: 13, cursor: "pointer" }}>
                  {uploadingSceneId === scene.id ? "uploading..." : "upload →"}
                  <input
                    type="file"
                    accept="image/*"
                    style={{ display: "none" }}
                    disabled={uploadingSceneId === scene.id}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (file) uploadForScene(scene, file);
                    }}
                  />
                </label>
              </div>
            </div>
          ))}
        </div>
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
                {(item.status === "running" || item.status === "queued") && (
                  <button
                    onClick={() => setGraceTimeItem(item)}
                    style={{ background: "none", border: "none", color: GREEN, fontFamily: "inherit", fontSize: 13, cursor: "pointer", padding: 0 }}
                  >
                    grace time →
                  </button>
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

      {graceTimeItem && (
        <GraceTimeOverlay item={graceTimeItem} onClose={() => setGraceTimeItem(null)} />
      )}
    </Center>
  );
}

/** Full-screen Matrix-style code-rain overlay shown while a build runs,
 * purely aesthetic — polls for real status underneath so it still tells
 * you when the build actually finishes. */
function GraceTimeOverlay({ item, onClose }) {
  const canvasRef = useRef(null);
  const [current, setCurrent] = useState(item);
  const [elapsed, setElapsed] = useState(0);

  // rain animation
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let raf;
    let cols, drops;
    const chars = "01{}[]<>/\\;:=+-#$%&*GRACE".split("");

    function resize() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      cols = Math.floor(canvas.width / 22);
      drops = new Array(cols).fill(0).map(() => Math.random() * -50);
    }
    resize();
    window.addEventListener("resize", resize);

    function frame() {
      ctx.fillStyle = "rgba(6, 10, 8, 0.15)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = GREEN;
      ctx.font = "18px monospace";
      for (let i = 0; i < cols; i++) {
        const ch = chars[Math.floor(Math.random() * chars.length)];
        ctx.fillText(ch, i * 22, drops[i] * 22);
        if (drops[i] * 22 > canvas.height && Math.random() > 0.975) drops[i] = 0;
        drops[i]++;
      }
      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  // elapsed-time ticker
  useEffect(() => {
    const startedAt = current.timestamp ? new Date(current.timestamp).getTime() : Date.now();
    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [current.timestamp]);

  // poll real status while still running/queued
  useEffect(() => {
    if (current.status !== "running" && current.status !== "queued") return;
    const id = setInterval(() => {
      authedFetch("/api/history")
        .then((r) => r.json())
        .then((d) => {
          const match = (d.history || []).find((h) => String(h.run_id) === String(item.run_id));
          if (match) setCurrent(match);
        })
        .catch(() => {});
    }, 4000);
    return () => clearInterval(id);
  }, [current.status, item.run_id]);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");
  const done = current.status === "uploaded" || current.status === "failed";

  return (
    <div style={{ position: "fixed", inset: 0, background: "#060a08", zIndex: 1000 }}>
      <canvas ref={canvasRef} style={{ position: "absolute", inset: 0 }} />
      <button
        onClick={onClose}
        style={{ position: "absolute", top: 16, right: 16, ...buttonStyle, padding: "6px 14px", background: "#060a08" }}
      >
        close ×
      </button>
      <div
        style={{
          position: "absolute", left: 0, right: 0, bottom: 0,
          padding: "18px 20px calc(18px + env(safe-area-inset-bottom))",
          background: "linear-gradient(transparent, #060a08 55%)",
          textAlign: "center",
        }}
      >
        <div style={{ color: "#eafff2", fontWeight: 600, marginBottom: 4 }}>{current.title || "Untitled"}</div>
        <div style={{ color: STATUS_COLOR[current.status] || DIM, fontSize: 14 }}>
          {done ? STATUS_LABEL[current.status] : `building... ${mm}:${ss}`}
        </div>
        {done && (
          <div style={{ marginTop: 8 }}>
            {current.video_url && (
              <a href={current.video_url} target="_blank" rel="noreferrer" style={{ color: GREEN, fontSize: 13 }}>
                watch on YouTube →
              </a>
            )}
            {current.status === "failed" && (
              <span style={{ color: "#ff8c8c", fontSize: 13 }}>
                {current.failed_step ? `failed at: ${current.failed_step}` : "failed"}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
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
