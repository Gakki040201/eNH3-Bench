# External Repository Setup

External repositories are optional references. eNH3-Bench does not vendor them,
does not import them, and does not require them for tests or CLI workflows.

If you inspect external repositories locally, clone them outside the benchmark
code path:

```powershell
mkdir external_repos
git clone https://github.com/wenkaining/Bandgap-Extraction-Comparison external_repos\Bandgap-Extraction-Comparison
git clone https://github.com/Ramprasad-Group/PromptDataExtraction external_repos\PromptDataExtraction
git clone https://github.com/lbnlp/NERRE external_repos\NERRE
```

`external_repos/` is ignored by Git. Do not stage cloned repositories.

## Reuse Rules

- Prefer conceptual inspection and lightweight reimplementation.
- Do not copy source code unless the license allows it and the reuse is needed.
- If code is copied or modified, update `docs/code_reuse_log.md`, preserve
  upstream attribution notices, add file-level attribution, and update `NOTICE`
  when needed.
- Conceptual references should be logged with `copied_code=no`.
