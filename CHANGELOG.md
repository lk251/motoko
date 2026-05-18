# Changelog

Motoko keeps a concise, user-facing changelog here because commit messages are
not the easiest place to review what changed after a long work session.

## Unreleased

- Added this changelog as the durable home for the short "what changed" lists
  from accepted Motoko work.
- Quieted stale maintenance from a different conversation on startup. Motoko
  still marks the old maintenance job abandoned, but no longer shows an alarming
  `sys abandoned interrupted maintenance...` line in a fresh chat.
- Added a durable background study job ledger in `study-jobs.jsonl`, plus
  interrupted-job detection for the current cheap catalog/planning pass.
- Added context planning lanes to the prompt and `/sources`, making the active
  context budget visible by lane.
- Expanded `/sources` with `why:` explanations so memories, conversations,
  dossiers, indexes, and chunks are easier to audit.
- Changed the TUI renderer to read terminal dimensions from the actual output
  file descriptor and added a stdlib pseudo-terminal resize/redraw check.
- Added `/about` and `motoko about` with Motoko version, model badge, endpoint,
  and state/config paths.
- Reworked `/help` into categorized sections; in the TUI it now opens as a
  dismissible help view instead of being appended into the conversation.
- Kept the top status bar wrapping across as many lines as the current terminal
  can spare, and made it show memory and background-study phases explicitly.
- Changed automatic memory proposal work to run in a bounded helper process so a
  stuck local model call is terminated and reported instead of leaving
  `memory: proposing` visible forever.
- Added deterministic memory capture for explicit natural-language requests such
  as `remember that ...`.
- Kept TUI rendering away from the final terminal column to avoid tty/tmux wrap
  ambiguity in long composer lines.
- Documented that future HRAG quality work should happen through Motoko-owned
  runtime behavior and synthetic fixtures, without Codex reading Javier's
  personal documents.

## 2026-05-18

- Added `/new [TITLE]` and `motoko new`.
- Added `/study QUERY` and `motoko study QUERY` for bounded study passes that
  reuse existing dossiers before building new derived context.
- Made the TUI spinner default to the tty-safe ASCII `-/|\` animation; braille
  remains available only by explicit opt-in.
- Made the TUI input renderer terminal-cell aware to reduce cursor drift on
  wrapped prompts and wide Unicode text.
- Added local-model visibility through a compact model badge such as
  `qwen3.6-27b-mtp:8083`.
- Added generated conversation titles after the first few messages while
  preserving manually set titles.
- Added a low-cost idle background study loop that refreshes the private
  context catalog and records study suggestions without silently crawling new
  directories or competing with chat.
- Kept heavier idle profile refresh opt-in with `MOTOKO_BACKGROUND_PROFILE=1`.
- Added regression and evaluation coverage for memory dossiers, context
  sufficiency, study reuse, spinner behavior, generated titles, and dropdown
  scrolling.

## 2026-05-17

- Split Motoko into this standalone repository and flake.
- Kept NixOS host integration in `nixos-configs`; Motoko's source, tests, and
  main documentation now live here.
- Documented Motoko as a small, dependency-free terminal personal assistant for
  the HB3 `personal` realm.
