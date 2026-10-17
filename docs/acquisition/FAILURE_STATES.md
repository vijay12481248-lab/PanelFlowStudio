# PanelFlow Studio — Acquisition Failure States & Diagnostics

PanelFlow never collapses acquisition errors into a generic `"Scraping failed"` message. Every failure maps to a structured, explainable state.

---

## 1. Structured State Catalog

| Extraction State | Root Cause | Meaning & User Guidance |
| :--- | :--- | :--- |
| **`ACCESS_RESTRICTED`** | HTTP 403 Forbidden, IP block | The host has explicitly restricted access to this resource. PanelFlow will not attempt security bypasses. |
| **`AUTHENTICATION_REQUIRED`** | HTTP 401, Login page, password input | The chapter requires active subscriber authentication. User must log in through an authorized session. |
| **`RATE_LIMITED`** | HTTP 429 Too Many Requests | The server request rate has been exceeded. Back off and respect the `Retry-After` header. |
| **`CHALLENGE_PRESENT`** | Cloudflare Turnstile, CAPTCHA | A dynamic bot-verification challenge is present on the page. Automated headless extraction cannot proceed. |
| **`NOT_A_CHAPTER`** | Series index, Table of Contents, blog | The provided URL points to a series home page, search results, or article, not a specific chapter reader. |
| **`NO_CONTENT_IMAGES`** | Zero candidate images found | No images met quality or comic-page criteria across any strategy. |
| **`UNSUPPORTED_READER`** | Custom encrypted/unsupported reader | Reader structure is unsupported or completeness score fell below acceptable bounds (< 40%). |
| **`FAILED_NETWORK`** | HTTP 5xx, timeout, socket error | A transient network error occurred while communicating with the upstream server. |
| **`INVALID_URL`** | Blocked scheme, SSRF rejection | The URL uses an unsafe protocol (`file://`, `javascript:`) or resolves to a private LAN/loopback address. |
| **`NEEDS_REVIEW`** | Multiple competing clusters | Extraction produced uncertain results. Activates **Teach Mode** to let the user select the true chapter images. |
| **`USER_CANCELLED`** | User pressed Cancel | Acquisition was intentionally halted by the user via cancellation token. |

---

## 2. Failure Handling Rules

1. **No Infinite Retries**: Permanent errors (`401`, `403`, `404`) fail immediately without retrying. Transient errors (`502`, `503`, timeouts) retry up to 3 times with exponential backoff.
2. **Sanitized Diagnostics**: Audit traces contain sanitized URLs with query credentials, authentication tokens, and passwords permanently redacted.
3. **Structured Explanations**: Error reports inform the user of the exact architectural reason acquisition was halted.
