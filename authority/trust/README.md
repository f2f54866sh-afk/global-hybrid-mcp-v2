# Authority trust boundary

This directory is documentation-only. Runtime code must not load a trusted public key from the
repository: an actor with repository write access could replace that key together with the registry
and activation.

The repository owner supplies the trust binding outside the repository through runtime environment
configuration:

- `GLOBAL_AUTHORITY_TRUSTED_KEY_ID`
- `GLOBAL_AUTHORITY_TRUSTED_PUBLIC_KEY` (base64-encoded raw 32-byte Ed25519 public key)

Public keys are not secret, but the decision about which key is trusted must remain outside the
repository write boundary. Private keys must never be committed, copied into a Codex or ChatGPT
workspace, stored on Render, or added as a test fixture. Tests generate an ephemeral test-only key
in memory.

Until the owner supplies the external trust binding and a matching signed
`authority/current/activation.json`, readiness fails closed with `AUTHORITY_ACTIVATION_INVALID`.
