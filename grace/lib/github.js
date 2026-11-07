import sodium from "libsodium-wrappers";

const OWNER = process.env.GITHUB_OWNER || "Emris-x";
const REPO = process.env.GITHUB_REPO || "youtube-automation-pipe-line";
const API = "https://api.github.com";

function headers() {
  return {
    Authorization: `Bearer ${process.env.GITHUB_PAT}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

export async function ghFetch(path, opts = {}) {
  const res = await fetch(`${API}${path}`, { ...opts, headers: { ...headers(), ...(opts.headers || {}) } });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`GitHub API ${path} -> ${res.status}: ${body}`);
  }
  return res.status === 204 ? null : res.json();
}

/** Encrypt a secret value with the repo's public key (libsodium sealed box) — required by GitHub's API. */
export async function setRepoSecret(name, value) {
  await sodium.ready;
  const keyInfo = await ghFetch(`/repos/${OWNER}/${REPO}/actions/secrets/public-key`);
  const messageBytes = sodium.from_string(value);
  const keyBytes = sodium.from_base64(keyInfo.key, sodium.base64_variants.ORIGINAL);
  const encryptedBytes = sodium.crypto_box_seal(messageBytes, keyBytes);
  const encrypted_value = sodium.to_base64(encryptedBytes, sodium.base64_variants.ORIGINAL);

  await ghFetch(`/repos/${OWNER}/${REPO}/actions/secrets/${name}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ encrypted_value, key_id: keyInfo.key_id }),
  });
}

export async function hasRepoSecret(name) {
  try {
    const list = await ghFetch(`/repos/${OWNER}/${REPO}/actions/secrets`);
    return list.secrets.some((s) => s.name === name);
  } catch {
    return false;
  }
}

export async function dispatchWorkflow(workflowFile, inputs) {
  await ghFetch(`/repos/${OWNER}/${REPO}/actions/workflows/${workflowFile}/dispatches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs }),
  });
}

/** Grabs the most recent run of a workflow so we can hand the caller a link to watch it. */
export async function latestRun(workflowFile) {
  const data = await ghFetch(`/repos/${OWNER}/${REPO}/actions/workflows/${workflowFile}/runs?per_page=1`);
  return data.workflow_runs?.[0] || null;
}

export const REPO_URL = `https://github.com/${OWNER}/${REPO}`;
