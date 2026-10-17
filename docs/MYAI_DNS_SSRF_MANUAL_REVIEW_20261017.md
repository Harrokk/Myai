# MyAI – DNS/SSRF threat review, 2026-10-17

Baseline: DRAFT PR #270 at commit 0f5ef19f2732201c18913607da2902b429293927.
Candidate: dev/manual-full-files-and-dns-ssrf-20261017.
Status: code-level risk mitigation on DRAFT only; physical and complete manual audit NO-GO.

## Confirmed root cause
Old core/public_web_client.py verified public DNS addresses before calling requests.Session.get(), which could re-resolve a hostname and connect to a private IP. A later response peer-IP check happens after the first HTTP request has already been sent. A malicious DNS server could exploit this time-of-check/time-of-use window.

## Patch
- Default public web client uses PinnedPublicWebTransport and returns its initially DNS-approved A/AAAA address set. ALL addresses must be globally routable. Mixed public/private answers are rejected.
- TCP connects to the approved NUMERIC IP directly. The actual TCP peer must match that numeric address BEFORE any HTTP request byte is sent. There is no second DNS resolution or ambient HTTP proxy.
- For HTTPS, ssl.create_default_context() enforces certificate-chain and hostname verification, using the original DNS name for SNI. The HTTP Host header also retains the original hostname; only the TCP dial uses the numeric IP.
- Each 301/302/303/307/308 hop is re-parsed and resolved independently, with redirect limits. Per-page stream byte limits, type checks, response closure and credential-in-URL blocking remain.
- Synthetic tests cover numeric IP socket targeting, TLS hostname/SNI, private peer rejection BEFORE send, mixed DNS replies, disabled cert verification, empty username, failed connection cleanup, private HTTP redirects and second-hop DNS rebinding. No real web, device, camera or microphone access is used.

## Scope and unresolved issues
- By default any injected custom session object which is not PinnedPublicWebTransport is rejected **before any network call**. Offline FakeSession test doubles require explicit unsafe_test_session=True; that option is for synthetic tests, never release wiring. Production construction uses the pinned transport automatically. The guarded opt-in is deliberately disclosed for future review.
- The web-fetch tool in modules/internet/fetch.py uses the public client. Local trusted Ollama, GenieX and SearXNG clients require separate active-configuration attestation; they do not automatically inherit this public-URL policy.
- Real IPv6, TLS chains, Python native ABI, firewall/network routing and captive proxies have not been exercised here. Mocked tests are NOT live integration proof.
- Other sources accepting user-supplied URLs must be traced and reviewed before complete application-wide SSRF release signoff.
- Manual review of every repository file remains unfinished, tracked independently in docs/MYAI_COMPLETE_FILE_REVIEW_LEDGER_20261017.md.

## Required CI
Run branch-specific source-only socket/DNS regression and whole-project ARM64 tests on the SAME final commit. No green result from earlier heads counts toward this commit.
Release, physical voice, QAIRT/NPU, model inference and unattended rollback remain explicitly NO-GO.
