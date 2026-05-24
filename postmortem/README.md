# Postmortems

Permanent record of incidents, bugs, and false hypotheses that took
non-trivial effort to investigate -- so the next person doesn't have to
re-derive them from scratch.

Each entry: symptom, what was assumed (often wrong), how the truth was
established, what was changed in code and docs, lessons learned.

Filenames: `YYYY-MM-DD-short-slug.md`.

## Index

- [2026-05-23-differential-vs-defaultio.md](2026-05-23-differential-vs-defaultio.md)
  -- AI input mode ("DIFFERENTIAL") vs scan option ("DEFAULTIO") confusion
  in the FIFO-overrun debugging. Multiple AI-introduced facts in code and
  docs assumed `AiInputMode.DIFFERENTIAL` was a viable fallback. USB-2637
  has no differential mode. The actual fix for the OVERRUN crash was
  switching `ScanOption.CONTINUOUS` -> `ScanOption.DEFAULTIO`.
