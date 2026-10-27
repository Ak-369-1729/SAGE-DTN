# Threat model (prototype scope)

| Threat | Mechanism in this repo | Tested? | Residual risk |
|---|---|---|---|
| Replay / duplicate flooding to inflate demand and trigger false ECP | HLL sketches keyed by observation key; device and ingest-node sketches for confidence | E2 (replay ×1…×100) | An attacker who fabricates *new* observation keys (Sybil) is not stopped by sketches; needs device attestation / rate limits |
| Near-duplicate re-submission (new key, same household) | optional gated ML independence prior (can only merge, bounded by distance/time) | E7 ML-2 | false merges undercount (measured); generator-dependent |
| Resource pressure destroying critical semantics | SPL permit on concrete candidate | E1 (200k trials), E3 (E vs F) | Registry correctness is a human policy decision |
| Silent overwrite of contradictory reports | MV-register ProtectedMap; explicit conflicts | merge tests | Conflict *resolution* is left to responders |
| Corrupted / tampered evidence replica | encrypt-then-MAC tag + salted SHA-256 commitment + locator digest | E4 (10 % corrupted replicas) | Simulated cipher; deployment needs vetted AEAD |
| Unauthorised evidence access | capability token (role, subject, expiry) checked by holder | unit test | Symmetric HMAC token in simulator ⇒ holders could mint tokens; use asymmetric signatures |
| Source node destroyed | R evidence replicas on peers | E4 (R=0,1,3,5) | Replicas co-located with the source share its fate |
| Malicious node forging protected events | not addressed (no signatures on AEIOs) | no | Requires per-origin signing keys |
| ML manipulation (poisoned model) | gates bound effect; ML cannot fire ECP or write state | E7/E8 | A poisoned model can still shift thresholds within gate bounds |
| Privacy of precise location / free text | not addressed beyond evidence sealing | no | Protected records carry coordinates in clear |
| Storage exhaustion by protected events | protected never evicted ⇒ overflow counted | E3 (protected_overflow) | Under extreme load protected state exceeds node capacity |
