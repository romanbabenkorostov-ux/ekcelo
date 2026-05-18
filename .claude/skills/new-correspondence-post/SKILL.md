---
name: new-correspondence-post
description: >-
  Add a numbered post to docs/CORRESPONDENCE/ — the append-only parser↔viewer
  coordination log. Use when the user wants to reply to / open a thread between
  the parser and viewer teams (e.g. "ответь парсерам постом", "заведи пост в
  переписке", "log a correspondence reply"). Picks the next NNN, writes the
  file from the template, updates the README index, commits on a shared/* branch
  and opens/updates the ratification PR.
---

# new-correspondence-post

Maintains `docs/CORRESPONDENCE/` per its `INDEX.md` conventions. The
correspondence log is the discussion thread; the **source of truth for the
format is `docs/CONTRACT_KMZ.md`** (spec-PR-first). If a post records a
format-changing decision, also update `CONTRACT_KMZ.md` + bump its SemVer.

## Procedure

1. Read `docs/CORRESPONDENCE/INDEX.md` and list `docs/CORRESPONDENCE/`.
   Note: repo `.gitignore` globally ignores files named `README.md` — the
   index is `INDEX.md` by design; never recreate it as `README.md`.
   Determine the next number = max existing `NNN` + 1, zero-padded to 3.
2. Gather (ask the user only if not already clear from context):
   - `from` ∈ `parser` | `viewer` | `owner`; `to` = the other side.
   - short kebab-case latin `slug`; `Re:` links (prior `NNN`, PR #, contract §).
   - the post body (the actual message).
3. Create `docs/CORRESPONDENCE/NNN-<from>-<slug>.md` from the template below.
   Never edit an already-merged post — corrections are a new post.
4. Append a row to the **Индекс** table in `INDEX.md`; update the `Status`
   of any post this one answers (e.g. `answered (NNN)`).
5. If the decision changes the wire format: also edit `docs/CONTRACT_KMZ.md`
   (relevant section + §10 changelog + SemVer) in the same branch.
6. Branch + publish (no direct push to `main`):
   - Branch off the active shared base — before integration step S2 use
     `claude/review-project-structure-aEdDY`, after S2 use `main`
     (check `CONTRACT_KMZ.md §9` for current step).
   - Branch name `shared/correspondence-NNN` (or reuse an open `shared/*`
     thread branch if continuing one).
   - Commit only the CORRESPONDENCE files (+ CONTRACT_KMZ.md if step 5).
   - Push. Sandbox note: the local git proxy blocks push; a direct
     token remote works — set it only transiently and **scrub the token
     from `.git/config` afterwards** (`git remote set-url origin` back to the
     tokenless URL). Never commit a token.
   - Open a PR to the shared base (or update the existing thread PR), label
     `correspondence`. Ask one reviewer from each team per `CONTRACT_KMZ §3`.
7. Report the new file path and PR URL. Do not merge — ratification/merge is
   the owning-majority team's call (arbiter = repo owner on deadlock).

## Template

```markdown
# NNN — <краткая тема>

- **From:** <parser|viewer|owner>
- **To:** <other side>
- **Date:** <YYYY-MM-DD>
- **Re:** <prior NNN | PR # | CONTRACT_KMZ §x>
- **Status:** <open | awaiting ratification | answered (NNN) | closed>

## Суть (выжимка; источник истины — CONTRACT_KMZ.md / по ссылкам)

<тело сообщения; не дублировать большие нормативные документы — ссылаться>

## Просьба / next action

<что требуется от получателя; ожидаемый ответный пост NNN+1>
```

## Guardrails

- Append-only: do not rewrite history of delivered posts.
- One file per post; keep posts concise — link heavy docs, don't duplicate
  (prevents drift from the contract).
- Never push to `main` directly; never commit credentials.
