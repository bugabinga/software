# Notes

Raw material for the book: transcripts of discussions about the content,
references, anything worth keeping. Nothing here is built into the book --
this is the input side of the pipeline, and it is deliberately kept verbatim.

Each source becomes two files:

    notes/<date>-<slug>.md         readable Markdown, with a frontmatter header
    notes/raw/<date>-<slug>.<ext>  the response body, byte for byte

`index.md` lists everything ingested and is regenerated, not edited.

## Adding a source

```sh
make notes URL=https://example.com/the-discussion
```

or, for text that is not behind a fetchable URL:

```sh
tools/ingest_notes.py --from-file transcript.txt \
  --title "Chapter 3, first pass" --source "claude session 2026-09-08"
```

Re-ingesting the same source updates its note in place and keeps the original
`first-seen` date, so a link can be dropped twice without making a duplicate.

The ingester refuses a page that comes back with almost no text, because that
means the content is rendered by JavaScript or sits behind a login. When that
happens the content has to arrive another way -- published as an artifact, or
pasted -- rather than being saved as an empty shell.

## What happens to a note

Notes are not chapters. Turning one into a chapter is a deliberate step:
read the note, decide what belongs in the book, and write the chapter in
`book/chapters/`. The note stays as the record of where the material came
from.
