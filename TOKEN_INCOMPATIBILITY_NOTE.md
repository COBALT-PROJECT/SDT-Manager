# SDT Manager <-> CCMLedger Token Incompatibility

## Executive Summary

In the current environment, Identity Manager issues an opaque access token to SDT Manager for the client_credentials flow. CCMLedger expects a Bearer JWT for SBOM ingestion. Because the token formats are different, SDT Manager can authenticate SDT ecosystem components successfully but cannot authenticate CCMLedger with the same token.

Current SDT Manager behavior is intentionally safe:

- SDT write continues and succeeds.
- CCMLedger forwarding is skipped when token is not JWT-shaped.
- API response explicitly reports the skip reason as non_jwt_token.

## Confirmed Token and Runtime Behavior

- IAM token received by SDT Manager is opaque (observed 42-char string, no dot separators).
- JWT structural check fails because JWT requires three segments separated by dots.
- SDT write succeeds with 201.
- CCMLedger forwarding reports skip with detail: Identity Manager token is not a JWT (len=42, dot_count=0).
- /api/SDTM/adapt response includes ccmledger object showing attempted=false, success=false, reason=non_jwt_token.

## What Is Stored in SQLite

Table: sdt_credentials

Columns:

1. sdt_id (primary key)
2. client_id
3. client_secret
4. access_token
5. token_scope
6. linked_sdt_id
7. component_type (default 'sdt')
8. status (default 'pending')
9. created_at
10. updated_at

Important clarification:

- client_id and access_token are different fields and values.
- The value used for downstream auth distribution and CCMLedger attempt is access_token, not client_id.

## Instantiation/Auth Flow and Distributed Payload

During SDT deployment/auth flow:

1. SDT Manager registers SDT and receives client_id/client_secret.
2. SDT Manager requests OAuth token from IAM using client_credentials.
3. SDT Manager stores credentials and token in SQLite for:
   - SDT row
   - IDS-SDT row (if present, linked_sdt_id points to SDT)
   - Watchtower row (if present, linked_sdt_id points to SDT)
4. SDT Manager distributes credentials over HTTP to running components.

Payload distributed to SDT, IDS-SDT, and Watchtower contains:

- sdt_id
- client_id
- client_secret
- access_token
- components object (sdt, ids_connector, watchtower identifiers)

Delivery endpoints used:

- SDT: /api/SDT/auth/token
- IDS-SDT: /api/IDSconnector/SDT/configauth
- Watchtower: /auth/token

All three components currently receive the same client_id, client_secret, and access_token generated from the same IAM flow.

## Why CCMLedger Fails with the Same Token

CCMLedger requires Bearer JWT validation (format + signature trust). The IAM token currently available to SDT Manager is opaque, so it does not meet JWT validation requirements.

This is why SDT/IDS-SDT/Watchtower can work while CCMLedger fails:

- SDT ecosystem components accept the distributed credential payload as implemented.
- CCMLedger enforces JWT bearer semantics for its endpoint.

## Why Opaque Token Cannot Be "Converted" Locally into a Valid JWT

Opaque token and JWT are different token classes. You cannot mathematically convert an opaque token string into a trusted JWT without a trusted signer.

A JWT accepted by CCMLedger must be signed using a key CCMLedger trusts. Without that trust relationship:

- A locally fabricated JWT-shaped token will fail signature verification.
- Storing both opaque and fabricated JWT strings in SQLite does not solve trust validation.

## Can SDT Manager Store Both Opaque and JWT Tokens?

Yes, technically SDT Manager can store both formats. But this only works if the JWT is valid and signed with a key/trust configuration accepted by CCMLedger.

So the blocker is not storage design; the blocker is signer trust and claim contract.

Required prerequisites for a working JWT path:

1. Signing method trusted by CCMLedger (for example shared secret for HS256, or trusted public key for RS256).
2. Agreed claims (for example role=manufacturer, issuer, audience, subject, expiration).
3. Key/secret provisioning and rotation policy.

## Boss-Requested Direction (Under Discussion)

Requested model:

1. Use IAM-assigned token string as input identity context.
2. SDT Manager mints JWT including role=manufacturer.
3. SDT Manager signs JWT.
4. SDT Manager sends same JSON payload to CCMLedger with Bearer <jwt>.

Feasibility note:

- This is feasible only after confirming CCMLedger-side trust for the signing key and required claim schema.

## What Must Be Done to Turn IAM Token Context into a Usable JWT

The opaque access token itself cannot be transformed directly into JWT bytes. To make the flow work, SDT Manager must produce a new JWT under an agreed trust contract.

Required implementation and coordination steps:

1. Define trust mode with CCMLedger
   - Choose HS256 (shared secret) or RS256/ES256 (asymmetric key pair).
   - Ensure CCMLedger is configured to verify signatures using that exact secret/public key.

2. Define required claim set with CCMLedger
   - Mandatory claims typically include iss, aud, sub, iat, exp.
   - Add business claim role=manufacturer as requested.
   - Decide TTL (for example 5 to 15 minutes) and acceptable clock skew.

3. Decide how IAM opaque token is used as identity context
   - Option A: Use stored client_id as sub and/or client_id claim.
   - Option B: Use token introspection (if IAM supports it) to extract authoritative subject/scope before minting JWT.
   - Option C: Use token exchange (if IAM supports RFC 8693) to request JWT directly from IAM.

4. Provision signing material securely to SDT Manager
   - For HS256: provide secret via environment/secret manager, never in source control.
   - For RS256/ES256: provide private key to SDT Manager and public key/JWKS to CCMLedger.
   - Define key rotation process and fallback behavior.

5. Implement JWT minting in SDT Manager for CCMLedger only
   - Keep existing opaque token distribution to SDT, IDS-SDT, Watchtower unchanged.
   - Build claims from agreed mapping.
   - Sign token with configured algorithm and key.
   - Attach Authorization: Bearer <minted_jwt> only on CCMLedger forwarding.

6. Add verification and observability
   - Validate local JWT shape and expiration before send.
   - Log safe metadata only (alg, iss, aud, exp, kid) and avoid logging secrets/full token.
   - Return structured error reason when minting or validation fails.

7. Test and rollout
   - Positive test: CCMLedger accepts JWT and returns 2xx.
   - Negative tests: expired token, wrong audience, wrong role, bad signature.
   - Roll out behind feature flag for quick rollback.

Minimum data needed before coding this path:

1. Algorithm required by CCMLedger.
2. Trusted key/secret delivery method.
3. Exact required claims and expected values.
4. Token lifetime and renewal behavior.

## Constraints in Current Situation

- No direct admin/file access to Identity Manager configuration.
- No direct admin/file access to CCMLedger authentication configuration.

Given these constraints, SDT Manager alone cannot force compatibility unless it is provided an approved signing secret/key and claim contract that CCMLedger already trusts.

## Potential Compatible Paths

1. IAM issues JWT directly for this client (preferred if available).
2. IAM supports OAuth token exchange and returns JWT from opaque token.
3. SDT Manager mints JWT locally with a key/secret pre-approved by CCMLedger.
4. CCMLedger is configured to accept opaque access tokens.

## Final Conclusion

The current incompatibility is an auth-contract mismatch between issuer format (opaque token) and consumer requirement (signed JWT). It is not a functional failure in SDT Manager data processing.

Current SDT Manager handling is correct for safety and observability:

- Preserve successful SDT processing path.
- Avoid sending malformed/non-JWT bearer to CCMLedger.
- Return explicit machine-readable reason in API response.
