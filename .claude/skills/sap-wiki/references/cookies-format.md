# Cookie Storage Format & Encryption

This document describes the on-disk format of `sap_cookies.txt` produced by the SAP Authentication Skill, including the encryption scheme used when `ENCRYPT_KEY` is configured.

---

## File Overview

| Property | Value |
|----------|-------|
| Filename | `sap_cookies.txt` |
| Location | `<store-path>/sap_cookies.txt` |
| Expiry | 24 hours from file **mtime** |
| Producer | `save-cookies.mjs` (invoked by the skill) |
| Consumers | Any downstream app MCP (sap-wiki-mcp, sap-jira-mcp, etc.) |

---

## Plain-Text Format (no encryption)

When `ENCRYPT_KEY` is **not set**, the file contains a single line of text — the HTTP `Cookie` header value:

```
name1=value1; name2=value2; name3=value3
```

### Rules

- Each cookie is a `name=value` pair.
- Pairs are separated by `; ` (semicolon + space).
- No trailing semicolon or newline.
- Only cookies with both a non-empty `name` and `value` are included.
- No quoting, no encoding beyond what the origin server set.

### Consumer Usage

```javascript
import { readFileSync } from "fs";

const cookie = readFileSync("/path/to/sap_cookies.txt", "utf8");
fetch(url, { headers: { Cookie: cookie } });
```

---

## Encrypted Format

When `ENCRYPT_KEY` is set (minimum 16 characters), the file contains **raw binary** (not base64, not JSON). The layout is:

```
[ IV: 12 bytes ][ Auth Tag: 16 bytes ][ Ciphertext: variable ]
```

Total file size = 12 + 16 + len(plaintext in UTF-8 bytes).

### Encryption Parameters

| Parameter | Value |
|-----------|-------|
| Algorithm | AES-256-GCM |
| Key derivation | PBKDF2 |
| PBKDF2 hash | SHA-256 |
| PBKDF2 salt | `sap-auth-mcp` (literal UTF-8 string) |
| PBKDF2 iterations | 100,000 |
| Derived key length | 32 bytes |
| IV length | 12 bytes (random per encryption) |
| Auth tag length | 16 bytes |

### Encryption Process (Producer)

```
1. secret  = ENCRYPT_KEY (from config or env)
2. key     = PBKDF2(secret, "sap-auth-mcp", 100000, 32, "sha256")
3. iv      = crypto.randomBytes(12)
4. cipher  = AES-256-GCM(key, iv)
5. encrypted = cipher.update(plaintext, "utf8") + cipher.final()
6. tag     = cipher.getAuthTag()          // 16 bytes
7. output  = Buffer.concat([iv, tag, encrypted])
8. writeFileSync(path, output)            // raw binary
```

### Decryption Process (Consumer)

```
1. secret  = DECRYPT_KEY (must equal producer's ENCRYPT_KEY)
2. key     = PBKDF2(secret, "sap-auth-mcp", 100000, 32, "sha256")
3. raw     = readFileSync(path)           // raw binary Buffer
4. iv      = raw.subarray(0, 12)
5. tag     = raw.subarray(12, 28)
6. data    = raw.subarray(28)
7. decipher = crypto.createDecipheriv("aes-256-gcm", key, iv)
8. decipher.setAuthTag(tag)
9. plaintext = decipher.update(data) + decipher.final()  // UTF-8 string
10. // plaintext is the Cookie header: "name1=value1; name2=value2"
```

### Reference Implementation (Node.js)

```javascript
import { createDecipheriv, pbkdf2Sync } from "crypto";
import { readFileSync } from "fs";

function decrypt(filePath, secret) {
  const key = pbkdf2Sync(secret, "sap-auth-mcp", 100000, 32, "sha256");
  const raw = readFileSync(filePath);

  const iv   = raw.subarray(0, 12);
  const tag  = raw.subarray(12, 28);
  const data = raw.subarray(28);

  const decipher = createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(tag);

  const plaintext = Buffer.concat([
    decipher.update(data),
    decipher.final(),
  ]);

  return plaintext.toString("utf8");
}

// Usage:
const cookie = decrypt("/path/to/sap_cookies.txt", process.env.DECRYPT_KEY);
fetch(url, { headers: { Cookie: cookie } });
```

---

## Detecting Encrypted vs. Plain Text

Consumer MCPs should detect the format before attempting decryption:

1. If `DECRYPT_KEY` is configured → read as binary and decrypt.
2. If `DECRYPT_KEY` is **not** configured → read as UTF-8 text directly.

If the consumer has no `DECRYPT_KEY` but the file contains binary data (non-printable bytes), it should raise a clear error:

> "Cookie file appears to be encrypted but DECRYPT_KEY is not set."

---

## Token File (`sap_tokens.json`)

The same encryption scheme applies to `sap_tokens.json` when produced with `--tokens`:

- **Plain**: Standard JSON file with token data.
- **Encrypted**: Same binary format `[IV 12B][Tag 16B][Ciphertext]`, where plaintext is the JSON string.

Decryption is identical — use the same key and process.

---

## Expiry Detection

Cookie freshness is determined by **file modification time** (mtime), not by any field inside the file:

```javascript
import { statSync } from "fs";

const MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

function isExpired(filePath) {
  const { mtimeMs } = statSync(filePath);
  return Date.now() - mtimeMs > MAX_AGE_MS;
}
```

When expired, downstream MCPs should request re-authentication via sap-auth-mcp.

---

## Security Notes

- The PBKDF2 salt is intentionally fixed (`"sap-auth-mcp"`) so that both producer and consumer derive the same key from the same passphrase without exchanging additional parameters.
- A fresh random IV is generated on every write, ensuring identical plaintext produces different ciphertext.
- GCM auth tag provides integrity verification — any tampering with the file will cause decryption to fail.
- The encryption key should be stored securely (e.g., environment variable, secrets manager) and never committed to source control.
