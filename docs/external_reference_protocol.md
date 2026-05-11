# External Reference Protocol

External repositories stay outside eNH3-Bench unless there is a deliberate,
documented reason to reuse a small component. Do not vendor full external
repositories.

## Preferred Approach

Prefer reimplementation from scratch over copying source code. Conceptual
inspiration is allowed when it is recorded as `copied_code = no` in
`docs/code_reuse_log.md`.

## If Code Is Copied

If any external source code is copied or modified:

1. Preserve original copyright and license headers where present.
2. Add a clear `Modified from ...` notice in the local file.
3. Record the reuse in `docs/code_reuse_log.md`.
4. Update `NOTICE` if the upstream license or NOTICE requires it.
5. Keep the relevant license text available under `LICENSES/`.

## If Only Concepts Are Used

Record the source as conceptual reference with `copied_code = no`. Do not imply
that the external authors endorse eNH3-Bench.
