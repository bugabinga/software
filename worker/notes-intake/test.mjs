// Tests for the notes inbox, run with plain Node and nothing installed.
//
// The Worker uses only web-standard APIs -- `fetch`, `crypto.subtle`, `btoa`,
// `TextEncoder` -- all of which Node has. So the handler can be called
// directly with a stubbed `fetch`, and the whole of its behaviour is testable
// without Cloudflare, without wrangler, and without a credential. That is
// worth more than it sounds: this thing will be deployed by a workflow nobody
// watches, and the first time it runs for real there should be no surprises
// left in it.
//
//     node worker/notes-intake/test.mjs

import worker from "./src/index.js";

let failures = 0;
const results = [];

function check(name, condition, detail = "") {
	results.push({ name, ok: Boolean(condition), detail });
	if (!condition) failures += 1;
}

const TOKEN = "intake-secret-token";

function env(overrides = {}) {
	return {
		INTAKE_TOKEN: TOKEN,
		GITHUB_TOKEN: "gh-token",
		GITHUB_REPOSITORY: "bugabinga/software",
		GITHUB_BASE_BRANCH: "main",
		...overrides,
	};
}

function post(body, { token = TOKEN, path = "/note", method = "POST" } = {}) {
	return new Request(`https://notes.example.workers.dev${path}`, {
		method,
		headers: token ? { Authorization: `Bearer ${token}` } : {},
		body: typeof body === "string" ? body : JSON.stringify(body),
	});
}

// A GitHub the Worker can talk to, that records what it was asked.
function fakeGitHub({ branchExists = false } = {}) {
	const calls = [];
	globalThis.fetch = async (url, init = {}) => {
		const route = String(url).replace(
			"https://api.github.com/repos/bugabinga/software/",
			"",
		);
		calls.push({
			route,
			method: init.method || "GET",
			body: init.body ? JSON.parse(init.body) : null,
			auth: init.headers?.Authorization,
		});
		if (route.startsWith("git/ref/heads/agent/note-")) {
			return branchExists
				? new Response(JSON.stringify({ ref: "exists" }), { status: 200 })
				: new Response("Not Found", { status: 404 });
		}
		if (route === "git/ref/heads/main") {
			return new Response(JSON.stringify({ object: { sha: "basesha" } }), {
				status: 200,
			});
		}
		if (route === "git/refs") {
			return new Response(JSON.stringify({ ref: "created" }), { status: 201 });
		}
		if (route.startsWith("contents/")) {
			return new Response(
				JSON.stringify({
					commit: { sha: "commitsha" },
					content: { html_url: "https://example/x" },
				}),
				{ status: 201 },
			);
		}
		return new Response("unexpected route", { status: 500 });
	};
	return calls;
}

// --------------------------------------------------------------------------

{
	// Refusal, and the same refusal every time.
	fakeGitHub();
	const bad = await worker.fetch(
		post({ title: "t", body: "b" }, { token: "wrong" }),
		env(),
	);
	const none = await worker.fetch(
		post({ title: "t", body: "b" }, { token: "" }),
		env(),
	);
	check("a wrong token is refused", bad.status === 401);
	check("a missing token is refused", none.status === 401);
	check(
		"both refusals read the same",
		JSON.stringify(await bad.json()) === JSON.stringify(await none.json()),
	);

	const unset = await worker.fetch(
		post({ title: "t", body: "b" }),
		env({ INTAKE_TOKEN: "" }),
	);
	check("an unconfigured worker is closed, not open", unset.status === 401);
}

{
	// Shape of the request.
	fakeGitHub();
	check(
		"GET / is a liveness answer",
		(await worker.fetch(new Request("https://x/", { method: "GET" }), env()))
			.status === 200,
	);
	check(
		"another path is 404",
		(
			await worker.fetch(
				post({ title: "t", body: "b" }, { path: "/elsewhere" }),
				env(),
			)
		).status === 404,
	);
	check(
		"a non-JSON body is refused",
		(await worker.fetch(post("not json at all"), env())).status === 400,
	);
	check(
		"a missing title is refused",
		(await worker.fetch(post({ body: "b" }), env())).status === 400,
	);
	check(
		"a blank body is refused",
		(await worker.fetch(post({ title: "t", body: "   " }), env())).status ===
			400,
	);
	check(
		"an oversized note is refused",
		(
			await worker.fetch(
				post({ title: "t", body: "x".repeat(600 * 1024) }),
				env(),
			)
		).status === 413,
	);
}

{
	// The happy path, and what it actually sent.
	const calls = fakeGitHub();
	const response = await worker.fetch(
		post({
			title: "Session 02 — What a machine is",
			body: "# Heading\n\nSome thinking.\n",
			source: "claude share link",
		}),
		env(),
	);
	const payload = await response.json();
	check(
		"a good note is created",
		response.status === 201 && payload.created === true,
		JSON.stringify(payload),
	);

	const today = new Date().toISOString().slice(0, 10);
	check(
		"the path is under notes/ and dated",
		payload.path ===
			`${today}-session-02-what-a-machine-is.md`.replace(/^/, "notes/"),
		payload.path,
	);
	check(
		"the branch is an agent branch",
		payload.branch.startsWith(`agent/note-${today}-`),
		payload.branch,
	);

	const put = calls.find((c) => c.route.startsWith("contents/"));
	check(
		"the file is written to the branch, not main",
		put.body.branch === payload.branch,
	);
	check(
		"it is written at the path the worker chose",
		put.route === `contents/${payload.path}`,
	);

	const written = Buffer.from(put.body.content, "base64").toString("utf8");
	check(
		"the frontmatter matches what ingest_notes.py writes",
		/^---\ntitle: Session 02 — What a machine is\nsource: claude share link\nfirst-seen: .+\nfetched: .+\nsha256: [0-9a-f]{64}\nwords: 4\n---\n/.test(
			written,
		),
		JSON.stringify(written.slice(0, 220)),
	);
	check(
		"the body is kept verbatim",
		written.endsWith("# Heading\n\nSome thinking.\n"),
		JSON.stringify(written.slice(-40)),
	);
	check(
		"the credential is sent to GitHub and not echoed back",
		put.auth === "Bearer gh-token" &&
			!JSON.stringify(payload).includes("gh-token"),
	);
}

{
	// A caller cannot name a file. This is the one that matters.
	const calls = fakeGitHub();
	const response = await worker.fetch(
		post({
			title: "../../.github/workflows/evil",
			body: "x",
			path: "../../etc/passwd",
		}),
		env(),
	);
	const payload = await response.json();
	check(
		"a traversal in the title cannot escape notes/",
		payload.path.startsWith("notes/") && !payload.path.includes(".."),
		payload.path,
	);
	check(
		"a `path` field in the request is ignored",
		!JSON.stringify(calls).includes("etc/passwd"),
	);
}

{
	// Filing the same note twice files it once.
	fakeGitHub({ branchExists: true });
	const again = await worker.fetch(
		post({ title: "Same note", body: "identical" }),
		env(),
	);
	const payload = await again.json();
	check(
		"a retry is not a second note",
		again.status === 200 && payload.created === false,
		JSON.stringify(payload),
	);
}

{
	// GitHub failing is reported as GitHub failing.
	globalThis.fetch = async () => new Response("boom", { status: 500 });
	const response = await worker.fetch(post({ title: "t", body: "b" }), env());
	check("a GitHub failure is a 502, not a 500", response.status === 502);
}

// --------------------------------------------------------------------------

for (const { name, ok, detail } of results) {
	console.log(
		`${ok ? "  ok  " : "  FAIL"}  ${name}${ok || !detail ? "" : `\n         ${detail}`}`,
	);
}
console.log(`\n${results.length - failures}/${results.length} passed`);
process.exit(failures ? 1 : 0);
