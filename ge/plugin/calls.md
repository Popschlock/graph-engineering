# calls — plugin

## Open
* Push 0.2.0 to GitHub (`main`, plus a `v0.2.0` tag)? — FOR: 0.1.2 is what installs from GitHub today, so the nine fixes reach nobody until it is pushed; the tree is clean, the gate is green at 62, and the version bump is what makes the plugin cache pick the new code up at all. AGAINST: nothing is waiting on it, and the hook's `python3` fallback could only be exercised here on a box that has `python` and no `python3`, so the `python3`-present branch is reasoned rather than run.

## Decided
* 2026-09-06 — publish 0.1.2 to GitHub now (after the first external migration had run real nodes through the loop): pushed `main` only, as a public repo.
