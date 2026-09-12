---
name: ingest
description: Put source material for the book into notes/ - from a URL, a Claude conversation share link, a published artifact, or pasted text. Use whenever the author drops a link or a transcript to keep, or asks to "save this to notes".
---

# Getting material into `notes/`

`notes/` is the raw input the book is written from, kept verbatim. The tool
does the saving; this skill is about getting the content to it, because the
most common source -- a Claude conversation -- cannot simply be downloaded.

## The ladder

Try these in order and stop at the first that works.

1. **An ordinary web page.**

   ```sh
   mise run notes URL=https://example.com/the-thing
   ```

   Works for articles, documentation, papers.

2. **A Claude conversation share link** (`claude.ai/share/...`). This does not
   work, and it has been tried properly, so do not spend turns rediscovering
   it. Three separate walls, any one of which is enough:

   - the page is a JavaScript shell. A real share link and a made-up one
     return byte-for-byte the same 108 KB of markup and about a dozen visible
     words; the conversation is not in the HTML;
   - the endpoint the page loads it from, `/api/chat_snapshots/<id>`, answers
     403 with a Cloudflare bot challenge. Do not try to get around that --
     it is an access control;
   - headless rendering would execute the JavaScript, but Chromium cannot
     tunnel through this environment's proxy (the relay drops it; the same
     happens for any site, not just claude.ai).

   A `claude.ai/chat/...` link is private and answers 403 outright.

   So: say plainly that the link cannot be fetched, and offer step 3 or 4.

3. **A published artifact.** If the author publishes the discussion as an
   artifact, read it directly:

   - `Artifact` with `action: "list"` to find it, or use the URL given;
   - `Artifact` with `action: "read"` and that URL;
   - save what comes back to a file, then
     `tools/ingest_notes.py --from-file <file> --source <artifact url>
     --title "<what it is>"`.

   This is the route to prefer for conversations: one step for the author, and
   fully automatic afterwards.

4. **Pasted text.** Write it to a file and ingest that:

   ```sh
   tools/ingest_notes.py --from-file /tmp/paste.md \
     --title "Chapter 3, second pass" --source "claude session 2026-09-08"
   ```

   `--source` is free text here; it is what future readers use to work out
   where a note came from, so make it identifying.

## After ingesting

- `tools/ingest_notes.py --reindex` runs automatically, but check
  `notes/index.md` looks right.
- Commit `notes/` and its `raw/` counterpart together -- the raw copy is what
  makes the note trustworthy.
- Ingestion is a chore: pull request, merge when CI is green.
- Then say what arrived, in one or two sentences: what the material covers and
  whether it looks like it changes the book's shape. If it does, offer the
  `notes-cartographer` agent rather than restructuring anything on the spot.

## What not to do

- Do not summarise instead of saving. A note is the record; a summary is a
  lossy opinion about the record. If a summary is useful, put it in the pull
  request body, not in the note.
- Do not edit an ingested note's text, ever. Corrections happen in the book,
  not in the source material.
- Do not ingest the same source twice under two names. Re-running the tool on
  the same source updates the existing note in place, which is what you want.
