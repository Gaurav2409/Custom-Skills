#!/usr/bin/env node
/**
 * save-cookies.mjs
 *
 * Converts Playwright MCP browser_cookie_list output into a plain-text cookie
 * header file that downstream app MCPs can use directly as the HTTP Cookie header.
 *
 * Output format (sap_cookies.txt):
 *   name1=value1; name2=value2; name3=value3
 *
 * Downstream usage:
 *   const cookie = fs.readFileSync(path, 'utf8');
 *   fetch(url, { headers: { Cookie: cookie } });
 *
 * Cookie age is determined by file mtime (24h expiry rule).
 *
 * Usage:
 *   echo '<playwright_cookies_json>' | node save-cookies.mjs --store-path /tmp/cookies/jira
 *   node save-cookies.mjs --store-path /tmp/cookies/jira --input cookies-raw.json
 *
 * Options:
 *   --store-path <dir>    Required. Directory to write sap_cookies.txt into.
 *   --input <file>        Optional. Read Playwright cookies from file instead of stdin.
 *   --encrypt-key <key>   Optional. AES-256-GCM key (min 16 chars). Env ENCRYPT_KEY also works.
 *   --tokens <file>       Optional. Token JSON file to save as sap_tokens.json.
 */

import { createCipheriv, randomBytes, pbkdf2Sync } from "crypto";
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { join } from "path";

// --- Encryption (mirrors src/secure-store.ts) ---
const ALGO = "aes-256-gcm";
const SALT = "sap-auth-mcp";
const ITERATIONS = 100000;
const KEY_LENGTH = 32;
const IV_LENGTH = 12;

function deriveKey(secret) {
  return pbkdf2Sync(secret, SALT, ITERATIONS, KEY_LENGTH, "sha256");
}

function encrypt(plaintext, secret) {
  const key = deriveKey(secret);
  const iv = randomBytes(IV_LENGTH);
  const cipher = createCipheriv(ALGO, key, iv);
  const encrypted = Buffer.concat([
    cipher.update(plaintext, "utf8"),
    cipher.final(),
  ]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, encrypted]);
}

// --- Argument parsing ---
function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { storePath: null, input: null, encryptKey: null, tokens: null };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case "--store-path":
        opts.storePath = args[++i];
        break;
      case "--input":
        opts.input = args[++i];
        break;
      case "--encrypt-key":
        opts.encryptKey = args[++i];
        break;
      case "--tokens":
        opts.tokens = args[++i];
        break;
      case "--help":
      case "-h":
        console.log(`Usage: node save-cookies.mjs --store-path <dir> [options]
Options:
  --store-path <dir>    Directory to write sap_cookies.txt
  --input <file>        Read cookies from file (default: stdin)
  --encrypt-key <key>   Encryption key (or env ENCRYPT_KEY)
  --tokens <file>       Token JSON file to save as sap_tokens.json`);
        process.exit(0);
    }
  }

  if (!opts.encryptKey) {
    opts.encryptKey = process.env.ENCRYPT_KEY || null;
  }

  return opts;
}

// --- Cookie extraction ---
function extractCookieHeader(raw) {
  let cookies;

  if (Array.isArray(raw)) {
    cookies = raw;
  } else if (raw && Array.isArray(raw.cookies)) {
    cookies = raw.cookies;
  } else if (raw && typeof raw === "object") {
    const arrKey = Object.keys(raw).find((k) => Array.isArray(raw[k]));
    if (arrKey) {
      cookies = raw[arrKey];
    } else {
      throw new Error("Cannot find cookie array in input. Expected an array or {cookies: [...]}");
    }
  } else {
    throw new Error("Invalid input format. Expected JSON array or object.");
  }

  // Build "name=value; name=value" string
  const pairs = cookies
    .filter((c) => c.name && c.value)
    .map((c) => `${c.name}=${c.value}`);

  if (pairs.length === 0) {
    throw new Error("No valid cookies found (need name + value).");
  }

  return { header: pairs.join("; "), count: pairs.length };
}

// --- Main ---
function main() {
  const opts = parseArgs();

  if (!opts.storePath) {
    console.error("Error: --store-path is required");
    process.exit(1);
  }
  if (opts.encryptKey && opts.encryptKey.length < 16) {
    console.error(`Error: encrypt key must be at least 16 characters (got ${opts.encryptKey.length})`);
    process.exit(1);
  }

  // Read input
  let rawInput;
  if (opts.input) {
    rawInput = readFileSync(opts.input, "utf8");
  } else {
    rawInput = readFileSync(0, "utf8");
  }

  // Parse
  let parsed;
  try {
    parsed = JSON.parse(rawInput);
  } catch (e) {
    console.error("Error: Failed to parse input as JSON:", e.message);
    process.exit(1);
  }

  const { header, count } = extractCookieHeader(parsed);

  // Ensure directory exists
  if (!existsSync(opts.storePath)) {
    mkdirSync(opts.storePath, { recursive: true });
  }

  // Write cookies
  const cookiePath = join(opts.storePath, "sap_cookies.txt");
  if (opts.encryptKey) {
    const encrypted = encrypt(header, opts.encryptKey);
    writeFileSync(cookiePath, encrypted);
  } else {
    writeFileSync(cookiePath, header, "utf8");
  }

  console.log(`Saved ${count} cookies to ${cookiePath}`);

  // Write tokens if provided
  if (opts.tokens) {
    const tokenRaw = readFileSync(opts.tokens, "utf8");
    const tokenPath = join(opts.storePath, "sap_tokens.json");
    if (opts.encryptKey) {
      writeFileSync(tokenPath, encrypt(tokenRaw, opts.encryptKey));
    } else {
      writeFileSync(tokenPath, tokenRaw, "utf8");
    }
    console.log(`Saved tokens to ${tokenPath}`);
  }
}

main();
