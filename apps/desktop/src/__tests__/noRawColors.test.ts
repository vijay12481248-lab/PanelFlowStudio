import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Ratchet: screens built on the v2 tokens must not use raw hex or palette utilities.
// Legacy files that still do are listed in legacyColorAllowlist.json. The list may only shrink:
// a new offender fails, and so does a listed file that has been cleaned (remove it from the list).
// Regenerate after cleaning files with: UPDATE_COLOR_ALLOWLIST=1 npx tsx --test <this file>

const HEX = /#[0-9a-fA-F]{3,8}\b/;
const PALETTE = /\b(?:bg|text|border|ring|from|to|via|fill|stroke|outline|shadow|divide|placeholder|decoration|accent|caret)-(?:indigo|purple|violet|blue|sky|emerald|amber|rose|cyan|fuchsia|teal|orange|zinc|slate|gray|neutral|stone|red|green|lime|yellow|pink)-\d{2,3}\b/;

export function findViolations(source: string): string[] {
  return [HEX, PALETTE].map((re) => re.exec(source)?.[0]).filter((hit): hit is string => Boolean(hit));
}

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../../..");
const ALLOWLIST = path.join(here, "legacyColorAllowlist.json");
const ROOTS = ["apps/desktop/src", "packages/ui/src"];

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "__tests__" || entry.name === "node_modules" ? [] : sourceFiles(full);
    return entry.name.endsWith(".tsx") && !entry.name.includes(".test.") && !entry.name.includes(".mock.") ? [full] : [];
  });
}

function offenders(): string[] {
  return ROOTS.flatMap((root) => sourceFiles(path.join(repoRoot, root)))
    .filter((file) => findViolations(readFileSync(file, "utf8")).length > 0)
    .map((file) => path.relative(repoRoot, file).split(path.sep).join("/"))
    .sort();
}

test("findViolations flags raw hex and palette utilities but not semantic tokens", () => {
  assert.deepEqual(findViolations('className="bg-indigo-500"'), ["bg-indigo-500"]);
  assert.deepEqual(findViolations('style={{ color: "#8b84ff" }}'), ["#8b84ff"]);
  assert.deepEqual(findViolations('className="bg-accent text-fg-dim border-edge text-ok"'), []);
});

test("only the listed legacy files use raw colours, and every listed file still does", () => {
  const found = offenders();
  if (process.env.UPDATE_COLOR_ALLOWLIST === "1") writeFileSync(ALLOWLIST, JSON.stringify(found, null, 2) + "\n");
  assert.ok(existsSync(ALLOWLIST), "legacyColorAllowlist.json exists");
  const allowed: string[] = JSON.parse(readFileSync(ALLOWLIST, "utf8"));
  assert.deepEqual(found.filter((file) => !allowed.includes(file)), [], "new files must use v2 tokens, not raw colours");
  assert.deepEqual(allowed.filter((file) => !found.includes(file)), [], "these files are clean now: remove them from legacyColorAllowlist.json");
});
