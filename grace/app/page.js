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
const SESSION_MS = 60 * 60 * 1000; // auto-logout after 1 hour

export default function Page() {
  const [pw, setPw] = useState("");
  const [unlocked, setUnlocked] = useState(false);
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState(null);
  const [view, setView] = useState("home"); // "home" | "workspace"
  const [ytConnected, setYtConnected] = useState(null);
  const [title, setTitle] = useState("");
  const [script, setScript] = useState("");
  const [draftRunId, setDraftRunId] = useState(null); // run_id of a build this draft is tied to, until it finishes
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
  const [pendingBuild, setPendingBuild] = useState(false); // true after "go upload pictures" -- shows a "continue build" button on necessities
  const [scriptFocused, setScriptFocused] = useState(false); // is the script textarea currently focused -- drives Grace's "looking at your script" expression

  // a stale gate/pending-build from a previous script shouldn't silently apply to a new one
  useEffect(() => {
    setCreateGate(null);
    setPendingBuild(false);
  }, [script]);

  // Session: auto-login only within SESSION_MS of the last successful
  // password check, instead of forever -- previously a saved password never
  // expired, so the login screen never came back even after a long time away.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = localStorage.getItem("grace_pw");
    const savedAt = Number(localStorage.getItem("grace_pw_at") || 0);
    if (saved !== null && savedAt && Date.now() - savedAt < SESSION_MS) {
      setPw(saved);
      setUnlocked(true);
    } else {
      localStorage.removeItem("grace_pw");
      localStorage.removeItem("grace_pw_at");
    }
  }, []);

  function lock() {
    localStorage.removeItem("grace_pw");
    localStorage.removeItem("grace_pw_at");
    setUnlocked(false);
    setPw("");
  }

  // If the app stays open past the 1-hour mark, lock it right there instead
  // of only checking at the next page load.
  useEffect(() => {
    if (!unlocked) return;
    const savedAt = Number(localStorage.getItem("grace_pw_at") || Date.now());
    const remaining = SESSION_MS - (Date.now() - savedAt);
    if (remaining <= 0) {
      lock();
      return;
    }
    const id = setTimeout(lock, remaining);
    return () => clearTimeout(id);
  }, [unlocked]);

  // Draft script/title: restored from localStorage on load, saved as you
  // type, so a refresh doesn't wipe an unfinished script. Clears only on an
  // explicit "new project" or once a build tied to this draft finishes.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const s = localStorage.getItem("grace_draft_script");
    const t = localStorage.getItem("grace_draft_title");
    const r = localStorage.getItem("grace_draft_run_id");
    if (s) setScript(s);
    if (t) setTitle(t);
    if (r) setDraftRunId(r);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (script) localStorage.setItem("grace_draft_script", script);
    else localStorage.removeItem("grace_draft_script");
  }, [script]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (title) localStorage.setItem("grace_draft_title", title);
    else localStorage.removeItem("grace_draft_title");
  }, [title]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (draftRunId) localStorage.setItem("grace_draft_run_id", draftRunId);
    else localStorage.removeItem("grace_draft_run_id");
  }, [draftRunId]);

  function clearDraft() {
    setScript("");
    setTitle("");
    setDraftRunId(null);
    setCreateGate(null);
    setPendingBuild(false);
    setStatus(null);
    setRunUrl(null);
  }

  // Watches a draft's dispatched build and clears the draft once it finishes
  // (uploaded or failed) -- runs regardless of which tab is open, since the
  // person asked for the script to stay "until you have finished that
  // build", not just while they're looking at the create tab.
  useEffect(() => {
    if (!unlocked || !draftRunId) return;
    const check = () => {
      authedFetch("/api/history")
        .then((r) => r.json())
        .then((d) => {
          const match = (d.history || []).find((h) => String(h.run_id) === String(draftRunId));
          if (match && (match.status === "uploaded" || match.status === "failed")) clearDraft();
        })
        .catch(() => {});
    };
    check();
    const id = setInterval(check, 8000);
    return () => clearInterval(id);
  }, [unlocked, draftRunId]);

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
          scene_text: scene.text,
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

  // Actually checks the password against the server before unlocking --
  // previously any text typed here "unlocked" the UI client-side, and a
  // wrong password only surfaced later as silent 401s on every API call.
  async function enter() {
    setLoginBusy(true);
    setLoginError(null);
    try {
      const res = await fetch("/api/youtube-status", { headers: { "x-grace-password": pw } });
      if (res.status === 401) {
        setLoginError("Wrong password.");
        setLoginBusy(false);
        return;
      }
      localStorage.setItem("grace_pw", pw);
      localStorage.setItem("grace_pw_at", String(Date.now()));
      setUnlocked(true);
    } catch (e) {
      setLoginError("Couldn't reach GRACE — try again.");
    }
    setLoginBusy(false);
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
        if (data.run_id) setDraftRunId(String(data.run_id));
      }
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
    setBusy(false);
  }

  // Resumes a build that paused at the necessities gate. Clears the pending
  // flag, switches to create (where the status/gate actually render), and
  // re-runs the same check -- if pictures still aren't all there it shows
  // the gate again instead of silently building, same as a fresh create.
  function continueBuild() {
    setPendingBuild(false);
    setTab("create");
    createVideo();
  }

  // Grace's expression for the workspace header: working/dispatching a
  // build takes priority, then whatever the create tab is doing (looking
  // down while the script is actively being typed, looking up once it's
  // not empty but you've stopped), otherwise just idly present.
  const graceMood =
    busy || necessitiesLoading
      ? "waiting"
      : tab === "create" && scriptFocused
        ? "watching"
        : tab === "create" && script.trim()
          ? "attentive"
          : "idle";

  if (!unlocked) {
    return (
      <Center>
        <h1 style={{ color: GREEN }}>&gt; GRACE_</h1>
        <input
          type="password"
          placeholder="password"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !loginBusy && enter()}
          style={inputStyle}
        />
        {loginError && <p style={{ color: "#ff8c8c", fontSize: 13, margin: "4px 0 0" }}>{loginError}</p>}
        <button onClick={enter} disabled={loginBusy} style={{ ...buttonStyle, opacity: loginBusy ? 0.5 : 1 }}>
          {loginBusy ? "checking..." : "unlock"}
        </button>
      </Center>
    );
  }

  if (view === "home") {
    const preview = script.trim().replace(/\s+/g, " ").slice(0, 86);
    return (
      <HomeView
        hasDraft={!!script.trim()}
        title={title}
        preview={preview}
        onResume={() => { setTab("create"); setView("workspace"); }}
        onNew={() => { clearDraft(); setTab("create"); setView("workspace"); }}
        onHistory={() => { setTab("history"); setView("workspace"); }}
      />
    );
  }

  return (
    <Center wide>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <GraceFace mood={graceMood} size={52} />
          <div>
            <h1 style={{ color: GREEN, margin: 0, lineHeight: 1 }}>&gt; GRACE_</h1>
            {graceMood === "waiting" && (
              <div style={{ color: DIM, fontSize: 12, marginTop: 3 }}>hold on, working on it...</div>
            )}
          </div>
        </div>
        <button
          onClick={() => setView("home")}
          style={{ background: "none", border: "none", color: DIM, fontFamily: "inherit", fontSize: 13, cursor: "pointer", padding: 0 }}
        >
          ‹ home
        </button>
      </div>

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
            onFocus={() => setScriptFocused(true)}
            onBlur={() => setScriptFocused(false)}
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
                    setPendingBuild(true);
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
          {pendingBuild && (
            <div style={{ border: `1px solid ${GREEN}`, borderRadius: 6, padding: "10px 12px", marginBottom: 14 }}>
              <p style={{ color: GREEN, margin: 0, fontSize: 13 }}>
                A build is waiting on this — upload what you need, then continue.
              </p>
              <button
                onClick={continueBuild}
                disabled={busy}
                style={{ ...buttonStyle, padding: "6px 12px", fontSize: 13, marginTop: 10, opacity: busy ? 0.5 : 1 }}
              >
                {busy ? "working..." : "continue build →"}
              </button>
            </div>
          )}

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

/** Grace's face -- the app's mascot/personality, present on every screen.
 * Sly, narrow cat-eyes + an asymmetric raised eyebrow + a smirk, drawn as
 * plain SVG so it's free and matches the line-art terminal look exactly.
 * `mood` drives where she's looking and what her mouth is doing:
 *   idle      - centered pupils, slow idle drift, for "just here, present"
 *   watching  - pupils down, for "reading your script as you type it"
 *   attentive - pupils centered/up, for "done typing, looking at you"
 *   waiting   - pupils scanning side to side + flat mouth, for "working on it" */
function GraceFace({ mood = "idle", size = 120, bubble }) {
  const pupilYByMood = { idle: 0, watching: 6, attentive: -1, waiting: 0 };
  const pupilY = pupilYByMood[mood] ?? 0;
  const pupilClass = mood === "idle" ? "grace-pupils-idle" : mood === "waiting" ? "grace-pupils-waiting" : "";

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
      <style>{`
        @keyframes grace-face-blink { 0%, 92%, 100% { transform: scaleY(1); } 95% { transform: scaleY(0.12); } }
        @keyframes grace-face-drift { 0%, 100% { transform: translateX(0); } 50% { transform: translateX(2.5px); } }
        @keyframes grace-face-scan { 0% { transform: translateX(-5px); } 50% { transform: translateX(5px); } 100% { transform: translateX(-5px); } }
        .grace-eye-group { transform-origin: center; animation: grace-face-blink 4.6s ease-in-out infinite; }
        .grace-pupils-idle { animation: grace-face-drift 3.2s ease-in-out infinite; }
        .grace-pupils-waiting { animation: grace-face-scan 1s ease-in-out infinite; }
      `}</style>
      <svg width={size} height={size * 0.62} viewBox="0 0 120 74" style={{ overflow: "visible", flexShrink: 0 }}>
        <rect
          x="2" y="2" width="116" height="70" rx="14"
          fill={BG} stroke={GREEN} strokeWidth="2.5"
          style={{ filter: `drop-shadow(0 0 ${Math.max(4, size * 0.045)}px rgba(60,255,140,0.55))` }}
        />
        {/* asymmetric brows -- one raised higher for a sly, clever look */}
        <line x1="20" y1="27" x2="50" y2="16" stroke={GREEN} strokeWidth="3.5" strokeLinecap="round" />
        <line x1="70" y1="23" x2="99" y2="21" stroke={GREEN} strokeWidth="3.5" strokeLinecap="round" />
        {/* left eye */}
        <g className="grace-eye-group">
          <path d="M22 36 Q36 24 50 36 Q36 44 22 36 Z" fill="none" stroke={GREEN} strokeWidth="3" strokeLinejoin="round" />
          <circle className={pupilClass} cx="36" cy={36 + pupilY} r="5" fill={GREEN} />
        </g>
        {/* right eye */}
        <g className="grace-eye-group">
          <path d="M70 36 Q84 26 99 34 Q85 44 70 36 Z" fill="none" stroke={GREEN} strokeWidth="3" strokeLinejoin="round" />
          <circle className={pupilClass} cx="85" cy={35 + pupilY} r="5" fill={GREEN} />
        </g>
        {/* mouth -- smirk, or a flat line while waiting on something */}
        {mood === "waiting" ? (
          <line x1="52" y1="58" x2="72" y2="58" stroke={GREEN} strokeWidth="3" strokeLinecap="round" />
        ) : (
          <path d="M50 56 Q62 66 76 54" fill="none" stroke={GREEN} strokeWidth="3" strokeLinecap="round" />
        )}
      </svg>
      {bubble && (
        <div
          style={{
            border: `1.5px solid ${GREEN}`,
            borderRadius: 10,
            padding: "8px 14px",
            color: "#eafff2",
            fontSize: 13,
            maxWidth: 280,
            textAlign: "center",
            background: "rgba(60,255,140,0.05)",
          }}
        >
          {bubble}
        </div>
      )}
    </div>
  );
}

/** The landing screen. Same hacker-terminal palette as the rest of the app,
 * just laid out with more care: a glowing wordmark, a short numbered
 * explainer instead of one dense paragraph, a real draft-preview card, and
 * a NEW button that actually reads as the one big action on the screen. */
function HomeView({ hasDraft, title, preview, onResume, onNew, onHistory }) {
  return (
    <div
      style={{
        minHeight: "100vh",
        padding: "24px 16px 40px",
        backgroundImage:
          "linear-gradient(rgba(60,255,140,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(60,255,140,0.05) 1px, transparent 1px)",
        backgroundSize: "28px 28px",
        backgroundColor: BG,
      }}
    >
      <style>{`
        @keyframes grace-blink { 0%, 55% { opacity: 1; } 56%, 100% { opacity: 0; } }
        @keyframes grace-fade-up { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        .grace-cursor { display: inline-block; animation: grace-blink 1.1s step-end infinite; }
        .grace-fade { animation: grace-fade-up 0.35s ease-out both; }
        .grace-new-btn { transition: transform 0.15s ease, box-shadow 0.15s ease; }
        .grace-new-btn:hover { transform: translateY(-1px); box-shadow: 0 0 28px rgba(60,255,140,0.35); }
        .grace-new-btn:active { transform: translateY(0); }
      `}</style>

      <div style={{ width: "100%", maxWidth: 560, margin: "0 auto" }}>
        <div className="grace-fade" style={{ textAlign: "center", padding: "20px 0 8px" }}>
          <div
            style={{
              fontSize: 13,
              color: DIM,
              letterSpacing: 3,
              textTransform: "uppercase",
              marginBottom: 14,
            }}
          >
            how it actually broke
          </div>

          <div style={{ display: "flex", justifyContent: "center" }}>
            <GraceFace mood="idle" size={150} bubble="Hey, I'm Grace. What do you want to do today?" />
          </div>

          <h1
            style={{
              color: GREEN,
              fontSize: 40,
              letterSpacing: 1,
              margin: "18px 0 0",
              textShadow: "0 0 18px rgba(60,255,140,0.45)",
            }}
          >
            &gt; GRACE<span className="grace-cursor">_</span>
          </h1>
          <p style={{ color: "#cfe9db", fontSize: 14, marginTop: 10, marginBottom: 0 }}>
            script in, video out — uploaded while you're away.
          </p>
        </div>

        <div
          className="grace-fade"
          style={{
            border: `1px solid ${DIM}`,
            borderRadius: 10,
            padding: "16px 18px",
            margin: "24px 0",
            background: "rgba(60,255,140,0.03)",
          }}
        >
          {[
            ["1", "paste a script — one blank line between scenes"],
            ["2", "grace finds matching pictures and builds the motion graphics"],
            ["3", "it uploads straight to youtube, no need to stay watching"],
          ].map(([n, text]) => (
            <div key={n} style={{ display: "flex", gap: 12, alignItems: "baseline", padding: "6px 0" }}>
              <span style={{ color: GREEN, fontSize: 13, flexShrink: 0, minWidth: 16 }}>[{n}]</span>
              <span style={{ color: "#cfe9db", fontSize: 14 }}>{text}</span>
            </div>
          ))}
        </div>

        {hasDraft && (
          <div
            className="grace-fade"
            style={{
              border: `1px solid ${GREEN}`,
              borderRadius: 10,
              padding: "14px 16px",
              marginBottom: 18,
              background: "rgba(60,255,140,0.05)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10 }}>
              <span style={{ color: GREEN, fontSize: 13 }}>● unfinished draft</span>
            </div>
            <p style={{ color: "#eafff2", fontSize: 14, margin: "6px 0 2px", fontWeight: 600 }}>
              {title || "Untitled"}
            </p>
            {preview && (
              <p style={{ color: DIM, fontSize: 13, margin: "0 0 10px" }}>
                "{preview}{preview.length >= 86 ? "…" : ""}"
              </p>
            )}
            <button onClick={onResume} style={{ ...buttonStyle, padding: "7px 14px", fontSize: 13 }}>
              resume draft →
            </button>
          </div>
        )}

        <button
          onClick={onNew}
          className="grace-new-btn"
          style={{
            ...buttonStyle,
            width: "100%",
            aspectRatio: "3 / 1",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 2,
            boxShadow: "0 0 16px rgba(60,255,140,0.18)",
            background: "rgba(60,255,140,0.04)",
          }}
        >
          <span style={{ fontSize: 30, letterSpacing: 3, lineHeight: 1 }}>+ NEW</span>
          <span style={{ fontSize: 12, color: DIM, letterSpacing: 1, fontWeight: 400 }}>start a new project</span>
        </button>

        <button
          onClick={onHistory}
          style={{
            background: "none",
            border: "none",
            color: DIM,
            fontFamily: "inherit",
            fontSize: 14,
            cursor: "pointer",
            width: "100%",
            textAlign: "center",
            padding: "16px 0 4px",
          }}
        >
          view history →
        </button>
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
