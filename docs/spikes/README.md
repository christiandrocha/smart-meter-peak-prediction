# Spikes

A spike answers one environment or feasibility question before a design depends on it:
"can serverless reach the broker?", "does the registry resolve aliases here?".

## Rules

1. Code lives in `spikes/<topic>/` and is never imported by `src/` or deployed.
2. Each spike states its question and pass criteria at the top of the file.
3. Each spike ends with an assertion or an explicit pass/fail print.
4. The outcome (pass, fail, exact error, workaround) is recorded in an ADR and in the
   *Assumptions* table of the BRAINSTORM or DEFINE document that depended on it.
5. When the question is answered, the spike is frozen. Fixes go into the real implementation.

## Record

| Spike | Question | Result | ADR |
|---|---|---|---|
| | | | |
