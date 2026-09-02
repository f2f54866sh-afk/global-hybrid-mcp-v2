# GitHub main ruleset required

The public repository API reported zero rulesets. The branch-protection endpoint requires
authenticated repository administration, which is not available in this workspace.

Repository owner action is required in **Settings → Rules → Rulesets → New branch ruleset**:

1. Target the default branch `main` and set enforcement to **Active**.
2. Enable **Require a pull request before merging**.
3. Enable **Require status checks to pass** and select the check emitted by the
   `.github/workflows/ci.yml` job named `core` after it has run at least once.
4. Enable **Block force pushes**.
5. Enable **Restrict deletions** / prevent branch deletion.
6. Leave the bypass actor list empty: no Codex, app, automation, or repository-role bypass.

GitHub rules are a second layer, not the authority trust root. If Codex uses the repository owner's
credential, GitHub identity alone does not prove separation between an owner action and Codex acting
as that owner. The owner-held Ed25519 private key must remain independently controlled.
