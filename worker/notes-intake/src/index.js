// The book's notes inbox.
//
// One endpoint, one job: accept a note from the author's note-taking agent
// and put it on a branch of the book's repository. Everything after that is
// the fleet's, in GitHub, where it can be read.
//
// ## Why this exists at all
//
// The note-taker is a separate Claude session whose only job is to hand over
// text. Every route that skips this Worker gives that session a GitHub
// credential instead -- `repository_dispatch` and the Contents API both need
// `contents: write`, which is enough to rewrite the book. A GitHub token
// cannot be scoped to "may only file a note". This can: the note-taker holds
// a bearer token that reaches one endpoint, and the GitHub credential lives
// here as a Worker secret and never leaves Cloudflare.
//
// The containment is in three layers, and none of them trusts the caller:
//
//   1. The bearer token is compared in constant time, and a wrong one gets
//      the same answer as a missing one.
//   2. This code writes only under `notes/`, and the path is built here from
//      a slug, never taken from the request. A caller cannot name a file.
//   3. It writes only to a fresh branch. `main` is protected by a ruleset, so
//      even the credential could not push there.
//
// ## What it does not do
//
// It does not open a pull request, merge, comment, or run anything. It adds
// one file to one branch and stops, which is the same shape as every agent in
// the fleet: push a branch, let the repository's own rules decide.

const MAX_BYTES = 512 * 1024; // A transcript, not a corpus.
const NOTES_DIR = "notes";

export default {
  async fetch(request, env) {
    if (request.method === "GET" && new URL(request.url).pathname === "/") {
      // A liveness answer that reveals nothing. Useful when the note-taker
      // is being set up and "did I get the URL right" is the question.
      return json({ service: "notes-intake", ok: true }, 200);
    }

    if (request.method !== "POST") {
      return json({ error: "POST a note to /note" }, 405);
    }
    if (new URL(request.url).pathname !== "/note") {
      return json({ error: "not found" }, 404);
    }

    if (!(await authorised(request, env.INTAKE_TOKEN))) {
      // Deliberately identical for a missing, malformed and wrong token:
      // telling a caller which of those it was is telling it how to guess.
      return json({ error: "unauthorised" }, 401);
    }

    let note;
    try {
      const raw = await request.text();
      if (raw.length > MAX_BYTES) {
        return json({ error: `note is larger than ${MAX_BYTES} bytes` }, 413);
      }
      note = JSON.parse(raw);
    } catch {
      return json({ error: "body must be JSON" }, 400);
    }

    const title = typeof note.title === "string" ? note.title.trim() : "";
    const body = typeof note.body === "string" ? note.body : "";
    const source = typeof note.source === "string" ? note.source.trim() : "";
    if (!title) return json({ error: "title is required" }, 400);
    if (!body.trim()) return json({ error: "body is required" }, 400);

    const day = new Date().toISOString().slice(0, 10);
    const slug = slugify(title);
    const digest = await sha256Hex(body);
    const path = `${NOTES_DIR}/${day}-${slug}.md`;
    // The branch carries the content's fingerprint, so a retry after a
    // timeout lands on the branch the first attempt made rather than filing
    // the same note twice. The note-taker can be as clumsy as it likes.
    const branch = `agent/note-${day}-${slug}-${digest.slice(0, 8)}`;

    try {
      const result = await fileNote(env, { branch, path, title, source, body, digest, day });
      return json(result, result.created ? 201 : 200);
    } catch (error) {
      // The caller gets the shape of the failure; the detail goes to the log,
      // which `wrangler tail` can read and the note-taker cannot.
      console.error("intake failed", error?.stack || String(error));
      return json({ error: "could not file the note", detail: String(error?.message || error) }, 502);
    }
  },
};

// --------------------------------------------------------------------------
// GitHub
// --------------------------------------------------------------------------

async function fileNote(env, { branch, path, title, source, body, digest, day }) {
  const repo = env.GITHUB_REPOSITORY; // "owner/name"
  const api = (route) => `https://api.github.com/repos/${repo}/${route}`;
  const gh = async (route, init = {}) => {
    const response = await fetch(api(route), {
      ...init,
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        // GitHub rejects requests without one.
        "User-Agent": "notes-intake (book fleet)",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(init.headers || {}),
      },
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`GitHub ${response.status} on ${route}: ${detail.slice(0, 300)}`);
    }
    return response.status === 204 ? null : response.json();
  };

  const base = env.GITHUB_BASE_BRANCH || "main";

  // Already filed? Then this is a retry, and the answer is the first attempt's.
  const existing = await fetch(api(`git/ref/heads/${branch}`), {
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "notes-intake (book fleet)",
    },
  });
  if (existing.ok) {
    return { ok: true, created: false, branch, path, note: "already filed" };
  }

  const head = await gh(`git/ref/heads/${base}`);
  await gh("git/refs", {
    method: "POST",
    body: JSON.stringify({ ref: `refs/heads/${branch}`, sha: head.object.sha }),
  });

  const content = noteFile({ title, source, body, digest, day });
  const commit = await gh(`contents/${path}`, {
    method: "PUT",
    body: JSON.stringify({
      message: `Note: ${title}\n\nFiled by the notes inbox from the author's note-taker.\nVerbatim: notes/ is never edited.`,
      content: base64(content),
      branch,
    }),
  });

  return {
    ok: true,
    created: true,
    branch,
    path,
    commit: commit.commit?.sha,
    url: commit.content?.html_url,
  };
}

// The same frontmatter `tools/ingest_notes.py` writes, so a note that arrives
// this way is indistinguishable from one ingested by hand -- and the reindex
// that runs on the branch can read it without a special case.
function noteFile({ title, source, body, digest, day }) {
  const now = new Date().toISOString().replace(/\.\d+Z$/, "Z");
  const words = body.trim().split(/\s+/).filter(Boolean).length;
  const front = [
    "---",
    `title: ${title}`,
    `source: ${source || "notes inbox"}`,
    `first-seen: ${now}`,
    `fetched: ${now}`,
    `sha256: ${digest}`,
    `words: ${words}`,
    "---",
    "",
  ].join("\n");
  return front + body.replace(/\s*$/, "") + "\n";
}

// --------------------------------------------------------------------------
// Small things
// --------------------------------------------------------------------------

async function authorised(request, expected) {
  if (!expected) return false; // Unconfigured is not open.
  const header = request.headers.get("Authorization") || "";
  const offered = header.startsWith("Bearer ") ? header.slice(7) : "";
  // Compared as digests so the comparison is over two equal-length strings
  // and its duration says nothing about how much of the token was right.
  const [a, b] = await Promise.all([sha256Hex(offered), sha256Hex(expected)]);
  let same = a.length === b.length ? 0 : 1;
  for (let i = 0; i < Math.min(a.length, b.length); i += 1) {
    same |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return same === 0;
}

async function sha256Hex(text) {
  const bytes = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function slugify(text) {
  const slug = text
    .toLowerCase()
    .replace(/https?:\/\//g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60)
    .replace(/-$/, "");
  return slug || "note";
}

function base64(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function json(payload, status) {
  return new Response(JSON.stringify(payload, null, 2) + "\n", {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}
