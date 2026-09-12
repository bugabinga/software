/* Reader-side behaviour for the book website.
 *
 * No dependencies and no build step: this file is copied to the output as it
 * is. Everything degrades to a perfectly readable page if it fails to load.
 */

(function () {
	"use strict";

	const prefix = document.body.dataset.prefix || "";

	/* ------------------------------------------------------------- theme -- */

	const themeToggle = document.querySelector(".theme-toggle");
	if (themeToggle) {
		themeToggle.addEventListener("click", function () {
			const dark = matchMedia("(prefers-color-scheme: dark)").matches;
			const current =
				document.documentElement.dataset.theme || (dark ? "dark" : "light");
			const next = current === "dark" ? "light" : "dark";
			document.documentElement.dataset.theme = next;
			try {
				localStorage.setItem("book-theme", next);
			} catch (error) {
				/* private browsing */
			}
		});
	}

	/* ----------------------------------------------------------- sidebar -- */

	const sidebar = document.getElementById("sidebar");
	const sidebarToggle = document.querySelector(".sidebar-toggle");
	if (sidebar && sidebarToggle) {
		sidebarToggle.addEventListener("click", function () {
			const open = sidebar.classList.toggle("open");
			sidebarToggle.setAttribute("aria-expanded", String(open));
		});
	}

	// Keep the chapter being read visible in a long contents list.
	const currentLink = document.querySelector('.toc a[aria-current="page"]');
	if (currentLink && sidebar) {
		const linkTop = currentLink.getBoundingClientRect().top;
		if (linkTop < 0 || linkTop > sidebar.clientHeight) {
			currentLink.scrollIntoView({ block: "center" });
		}
	}

	/* --------------------------------------------------------- scrollspy -- */

	const headings = Array.from(
		document.querySelectorAll(".chapter h2[id], .chapter h3[id]"),
	);
	if (headings.length && "IntersectionObserver" in window) {
		const sectionLinks = new Map();
		document
			.querySelectorAll('.toc-sections a[href^="#"], .page-toc a[href^="#"]')
			.forEach(function (link) {
				const id = decodeURIComponent(link.hash.slice(1));
				if (!sectionLinks.has(id)) sectionLinks.set(id, []);
				sectionLinks.get(id).push(link);
			});

		let active = null;
		const observer = new IntersectionObserver(
			function (entries) {
				const visible = entries
					.filter((entry) => entry.isIntersecting)
					.sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
				if (!visible.length) return;
				const id = visible[0].target.id;
				if (id === active) return;
				if (active) {
					(sectionLinks.get(active) || []).forEach((l) =>
						l.classList.remove("active"),
					);
				}
				active = id;
				(sectionLinks.get(id) || []).forEach((l) => l.classList.add("active"));
			},
			{ rootMargin: "-15% 0px -70% 0px", threshold: 0 },
		);
		headings.forEach((heading) => observer.observe(heading));
	}

	/* ------------------------------------------------------ copy buttons -- */

	if (navigator.clipboard) {
		document.querySelectorAll(".chapter pre").forEach(function (block) {
			const button = document.createElement("button");
			button.className = "copy-button";
			button.type = "button";
			button.textContent = "copy";
			button.addEventListener("click", function () {
				const code = block.querySelector("code");
				navigator.clipboard.writeText((code || block).innerText).then(
					function () {
						button.textContent = "copied";
						setTimeout(() => (button.textContent = "copy"), 1200);
					},
					function () {
						button.textContent = "failed";
					},
				);
			});
			block.appendChild(button);
		});
	}

	/* ------------------------------------------------------------ search -- */

	const dialog = document.querySelector(".search-dialog");
	const input = document.querySelector(".search-input");
	const results = document.querySelector(".search-results");
	let documents = null;
	let selected = 0;

	function escapeHtml(text) {
		return text.replace(/[&<>"]/g, function (character) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[
				character
			];
		});
	}

	async function loadIndex() {
		if (documents) return documents;
		const response = await fetch(prefix + "search-index.json");
		documents = (await response.json()).documents;
		return documents;
	}

	function snippet(text, terms) {
		const lower = text.toLowerCase();
		let at = -1;
		for (const term of terms) {
			at = lower.indexOf(term);
			if (at !== -1) break;
		}
		if (at === -1) return escapeHtml(text.slice(0, 140)) + "…";
		const from = Math.max(0, at - 60);
		const raw = (from > 0 ? "…" : "") + text.slice(from, at + 100) + "…";
		let marked = escapeHtml(raw);
		for (const term of terms) {
			marked = marked.replace(
				new RegExp(
					"(" + term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")",
					"gi",
				),
				"<mark>$1</mark>",
			);
		}
		return marked;
	}

	function search(query, corpus) {
		const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
		if (!terms.length) return [];

		const found = [];
		for (const entry of corpus) {
			const title = entry.title.toLowerCase();
			const text = entry.text.toLowerCase();
			let score = 0;
			let anchor = "";

			for (const term of terms) {
				if (title.includes(term)) score += 12;
				const section = entry.sections.find((s) =>
					s.title.toLowerCase().includes(term),
				);
				if (section) {
					score += 6;
					if (!anchor) anchor = section.id;
				}
				const occurrences = text.split(term).length - 1;
				score += Math.min(occurrences, 8);
			}

			if (score > 0) {
				found.push({
					score: score,
					url: prefix + entry.url + (anchor ? "#" + anchor : ""),
					title: entry.number ? entry.number + ". " + entry.title : entry.title,
					snippet: snippet(entry.text, terms),
				});
			}
		}
		return found.sort((a, b) => b.score - a.score).slice(0, 20);
	}

	function renderResults(matches) {
		selected = 0;
		if (!matches.length) {
			results.innerHTML = '<p class="search-empty">Nothing found.</p>';
			return;
		}
		results.innerHTML = matches
			.map(function (match, index) {
				return (
					'<a class="search-result" role="option" href="' +
					match.url +
					'" aria-selected="' +
					(index === 0) +
					'"><strong>' +
					escapeHtml(match.title) +
					"</strong><em>" +
					match.snippet +
					"</em></a>"
				);
			})
			.join("");
	}

	function move(delta) {
		const options = results.querySelectorAll(".search-result");
		if (!options.length) return;
		options[selected].setAttribute("aria-selected", "false");
		selected = (selected + delta + options.length) % options.length;
		const option = options[selected];
		option.setAttribute("aria-selected", "true");
		option.scrollIntoView({ block: "nearest" });
	}

	async function openSearch() {
		if (!dialog) return;
		dialog.showModal();
		input.focus();
		input.select();
		try {
			await loadIndex();
			if (input.value) renderResults(search(input.value, documents));
		} catch (error) {
			results.innerHTML =
				'<p class="search-empty">Search index unavailable.</p>';
		}
	}

	if (dialog && input && results) {
		document.querySelectorAll(".search-open").forEach(function (button) {
			button.addEventListener("click", openSearch);
		});
		document
			.querySelector(".search-close")
			.addEventListener("click", function (event) {
				event.preventDefault();
				dialog.close();
			});

		input.addEventListener("input", function () {
			if (!documents) return;
			renderResults(search(input.value, documents));
		});

		input.addEventListener("keydown", function (event) {
			if (event.key === "ArrowDown") {
				event.preventDefault();
				move(1);
			} else if (event.key === "ArrowUp") {
				event.preventDefault();
				move(-1);
			} else if (event.key === "Enter") {
				const option = results.querySelectorAll(".search-result")[selected];
				if (option) {
					event.preventDefault();
					location.href = option.href;
				}
			}
		});
	}

	/* -------------------------------------------------- global shortcuts -- */

	document.addEventListener("keydown", function (event) {
		const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(
			document.activeElement.tagName,
		);
		if (typing || event.metaKey || event.ctrlKey || event.altKey) {
			if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
				event.preventDefault();
				openSearch();
			}
			return;
		}
		if (event.key === "/") {
			event.preventDefault();
			openSearch();
			return;
		}
		if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
			const rel = event.key === "ArrowLeft" ? "prev" : "next";
			const link = document.querySelector('.pager a[rel="' + rel + '"]');
			if (link) location.href = link.href;
		}
	});
})();
