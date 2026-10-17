# PanelFlow Studio — Acquisition Security & Access Architecture

All web-sourced content is treated as **UNTRUSTED DATA**. PanelFlow enforces strict security and access controls across the network, byte-validation, and execution layers.

---

## 1. SSRF (Server-Side Request Forgery) Protection

The acquisition engine enforces preflight URL validation and post-redirect IP checking:

```python
# Blocked protocol schemes
BLOCKED_SCHEMES = {"file", "javascript", "data", "ftp", "ssh", "sftp", "gopher", "dict", "ldap"}
```

- **Loopback Blocking**: Rejects all hostnames resolving to `127.0.0.0/8` or `::1`.
- **Private LAN Blocking**: Rejects private RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
- **Cloud Metadata Blocking**: Rejects link-local IP `169.254.169.254` and hostnames `instance-data` or `metadata.google.internal`.
- **Redirect Revalidation**: Any HTTP redirect is re-validated through `is_safe_url` before following.

---

## 2. Decompression Bomb & Resource Exhaustion Defense

Malicious images can use extreme compression ratios (e.g. a 50KB image that uncompresses to 100GB of RAM).
- **Safety Ceiling**: Enforces `Image.MAX_IMAGE_PIXELS = 100_000_000` (100 Megapixels max).
- **Early Byte Probing**: Rejects payloads with declared dimensions or unpacked buffers exceeding the safety limit before memory allocation spikes.

---

## 3. Magic Bytes & HTML Error Disguise Prevention

Servers often return HTTP 200 with an HTML error or CAPTCHA body for broken image URLs:
- **Magic Bytes Verification**: Inspects leading header bytes (`\xff\xd8\xff` for JPEG, `\x89PNG` for PNG, `RIFF...WEBP` for WebP).
- **HTML Quarantine**: Explicitly checks initial 1KB for `<html`, `<!doctype`, or `<title>Access Denied` and immediately discards the payload without saving to disk.

---

## 4. Source Immutability & Atomic Moves

- Downloads write to a temporary file (`page_0001.jpg.tmp`).
- Byte validation and SHA-256 calculation must succeed before atomic rename (`.replace()`) to `page_0001.jpg`.
- Acquired source assets in `workspace / "source"` are read-only and immutable; downstream normalization creates derivatives in `workspace / "normalized"`.

---

## 5. Untrusted Text Isolation

Text scraped from website headings, captions, or image alt tags is treated strictly as plain string data:
- Never evaluated in `eval()` or executed as Python code.
- Never passed unescaped into SQL queries.
- Never executed as shell commands.
- Never granted privileged system authority in LLM prompts.
