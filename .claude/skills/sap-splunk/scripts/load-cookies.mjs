#!/usr/bin/env node
/**
 * load-cookies.mjs
 *
 * Reads sap_cookies.txt (plain or encrypted) and outputs the Cookie header
 * string to stdout. Downstream skills and app MCPs can use this directly.
 *
 * Output (stdout):
 *   name1=value1; name2=value2; name3=value3
 *
 * Exit codes:
 *   0  Success — cookie string printed to stdout
 *   1  Error (missing file, expired, decryption failure, etc.)
 *
 * Usage:
 *   node load-cookies.mjs --store-path /tmp/cookies/jira
 *   node load-cookies.mjs --store-path /tmp/cookies/jira --decrypt-key mySecret
 *   node load-cookies.mjs --store-path /tmp/cookies/jira --max-age 48
 *
 * Options:
 *   --store-path <dir>      Required. Directory containing sap_cookies.txt.
 *   --decrypt-key <key>     Optional. AES-256-GCM key (min 16 chars). Env DECRYPT_KEY also works.
 *   --max-age <hours>       Optional. Max cookie age in hours (default: 24).
 *   --no-expiry-check       Optional. Skip mtime expiry check.
 *   --json                  Optional. Output as JSON: {"cookie":"...","age_hours":...}
 *   --tokens                Optional. Also load and output sap_tokens.json.
 */

import { createDecipheriv, pbkdf2Sync } from "crypto";
import { readFileSync, statSync, existsSync } from "fs";
import { join } from "path";

// --- Decryption (mirrors src/secure-store.ts & save-cookies.mjs) ---
const ALGO = "aes-256-gcm";
const SALT = "sap-auth-mcp";
const ITERATIONS = 100000;
const KEY_LENGTH = 32;
const IV_LENGTH = 12;
const TAG_LENGTH = 16;

function deriveKey(secret) {
  return pbkdf2Sync(secret, SALT, ITERATIONS, KEY_LENGTH, "sha256");
}

function decrypt(buffer, secret) {
  const key = deriveKey(secret);
  const iv = buffer.subarray(0, IV_LENGTH);
  const tag = buffer.subarray(IV_LENGTH, IV_LENGTH + TAG_LENGTH);
  const data = buffer.subarray(IV_LENGTH + TAG_LENGTH);

  const decipher = createDecipheriv(ALGO, key, iv);
  decipher.setAuthTag(tag);

  const decrypted = Buffer.concat([decipher.update(data), decipher.final()]);
  return decrypted.toString("utf8");
}

// --- Detect encrypted binary content ---
function isEncrypted(buffer) {
  // Encrypted files have IV+Tag+Ciphertext (min 28 bytes) and contain
  // non-printable bytes. Plain text is valid UTF-8 with printable chars.
  if (buffer.length < IV_LENGTH + TAG_LENGTH + 1) return false;
  // Check first 28 bytes for non-text content
  for (let i = 0; i < Math.min(28, buffer.length); i++) {
    const b = buffer[i];
    if (b < 0x20 && b !== 0x09 && b !== 0x0a && b !== 0x0d) return true;
  }
  return false;
}

// --- Argument parsing ---
function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    storePath: null,
    decryptKey: null,
    maxAge: 24,
    noExpiryCheck: false,
    json: false,
    tokens: false,
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case "--store-path":
        opts.storePath = args[++i];
        break;
      case "--decrypt-key":
        opts.decryptKey = args[++i];
        break;
      case "--max-age":
        opts.maxAge = parseFloat(args[++i]);
        break;
      case "--no-expiry-check":
        opts.noExpiryCheck = true;
        break;
      case "--json":
        opts.json = true;
        break;
      case "--tokens":
        opts.tokens = true;
        break;
      case "--help":
      case "-h":
        console.log(`Usage: node load-cookies.mjs --store-path <dir> [options]
Options:
  --store-path <dir>      Directory containing sap_cookies.txt
  --decrypt-key <key>     Decryption key (or env DECRYPT_KEY)
  --max-age <hours>       Max age in hours (default: 24)
  --no-expiry-check       Skip expiry check
  --json                  Output JSON with metadata
  --tokens                Also load sap_tokens.json`);
        process.exit(0);
    }
  }

  if (!opts.decryptKey) {
    opts.decryptKey = process.env.DECRYPT_KEY || process.env.ENCRYPT_KEY || null;
  }

  return opts;
}

// --- Load a single file (plain or encrypted) ---
function loadFile(filePath, decryptKey) {
  const raw = readFileSync(filePath);

  if (isEncrypted(raw)) {
    if (!decryptKey) {
      throw new Error(
        `File appears to be encrypted but no decrypt key provided. ` +
        `Set --decrypt-key or env DECRYPT_KEY.`
      );
    }
    if (decryptKey.length < 16) {
      throw new Error(`Decrypt key must be at least 16 characters (got ${decryptKey.length}).`);
    }
    try {
      return decrypt(raw, decryptKey);
    } catch (e) {
      throw new Error(`Decryption failed: ${e.message}. Check that the key matches the one used for encryption.`);
    }
  }

  // Plain text
  return raw.toString("utf8");
}

// --- Main ---
function main() {
  const opts = parseArgs();

  if (!opts.storePath) {
    console.error("Error: --store-path is required");
    process.exit(1);
  }

  const cookiePath = join(opts.storePath, "sap_cookies.txt");

  if (!existsSync(cookiePath)) {
    console.error(`Error: Cookie file not found: ${cookiePath}`);
    console.error("Run the SAP authentication skill first to generate cookies.");
    process.exit(1);
  }

  // Check expiry
  const stat = statSync(cookiePath);
  const ageMs = Date.now() - stat.mtimeMs;
  const ageHours = ageMs / (1000 * 60 * 60);
  const maxAgeMs = opts.maxAge * 60 * 60 * 1000;

  if (!opts.noExpiryCheck && ageMs > maxAgeMs) {
    console.error(
      `Error: Cookies expired (age: ${ageHours.toFixed(1)}h, max: ${opts.maxAge}h). ` +
      `Re-run SAP authentication to refresh.`
    );
    process.exit(1);
  }

  // Load cookies
  let cookie;
  try {
    cookie = loadFile(cookiePath, opts.decryptKey);
  } catch (e) {
    console.error(`Error: ${e.message}`);
    process.exit(1);
  }

  if (!cookie || cookie.trim().length === 0) {
    console.error("Error: Cookie file is empty.");
    process.exit(1);
  }

  // Load tokens if requested
  let tokens = null;
  if (opts.tokens) {
    const tokenPath = join(opts.storePath, "sap_tokens.json");
    if (existsSync(tokenPath)) {
      try {
        tokens = loadFile(tokenPath, opts.decryptKey);
      } catch (e) {
        console.error(`Warning: Failed to load tokens: ${e.message}`);
      }
    }
  }

  // Output
  if (opts.json) {
    const output = {
      cookie: cookie.trim(),
      age_hours: parseFloat(ageHours.toFixed(2)),
      expired: ageMs > maxAgeMs,
      file: cookiePath,
    };
    if (tokens !== null) {
      try {
        output.tokens = JSON.parse(tokens);
      } catch {
        output.tokens_raw = tokens;
      }
    }
    console.log(JSON.stringify(output));
  } else {
    // Plain output — just the cookie string, ready for use
    process.stdout.write(cookie.trim());
    if (tokens !== null) {
      // Print tokens to stderr so stdout stays clean for piping
      console.error(`\n[tokens] ${tokens.trim()}`);
    }
  }
}

main();
