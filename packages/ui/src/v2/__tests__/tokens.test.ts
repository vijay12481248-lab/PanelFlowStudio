import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { compositeOver, contrastRatio } from "../contrast";

const css = readFileSync(new URL("../tokens.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

function token(name: string): string {
  const match = new RegExp(`--color-${name}:\\s*([^;]+);`).exec(css);
  assert.ok(match, `token --color-${name} is defined`);
  return match[1].trim();
}

const REQUIRED = [
  "ink", "navy", "glow", "glass", "glass-hi", "flat", "edge",
  "fg", "fg-dim", "fg-faint", "accent", "accent-soft", "ok", "warn", "bad", "info",
];

test("contrastRatio matches the WCAG extremes", () => {
  assert.ok(Math.abs(contrastRatio("#ffffff", "#000000") - 21) < 0.01);
  assert.ok(Math.abs(contrastRatio("#777", "#777") - 1) < 0.001);
});

test("compositeOver blends an alpha colour onto an opaque one", () => {
  assert.equal(compositeOver("rgba(255,255,255,.5)", "#000000"), "#808080");
});

test("tokens.css defines every Midnight Glass colour", () => {
  for (const name of REQUIRED) token(name);
});

test("tokens.css defines the shape, font and motion tokens", () => {
  for (const name of ["--radius-card", "--radius-ctl", "--font-display", "--font-body", "--font-data", "--duration-fast", "--duration-base"]) {
    assert.ok(css.includes(`${name}:`), `${name} is defined`);
  }
});

test("body text meets 4.5:1 on every surface it is used on", () => {
  const glassOnNavy = compositeOver(token("glass"), token("navy"));
  const pairs: Array<[string, string, string]> = [
    ["fg on ink", token("fg"), token("ink")],
    ["fg on flat", token("fg"), token("flat")],
    ["fg on glass", token("fg"), glassOnNavy],
    ["fg-dim on ink", token("fg-dim"), token("ink")],
    ["fg-dim on flat", token("fg-dim"), token("flat")],
    ["fg-dim on glass", token("fg-dim"), glassOnNavy],
    ["white on accent", "#ffffff", token("accent")],
  ];
  for (const [label, fg, bg] of pairs) {
    assert.ok(contrastRatio(fg, bg) >= 4.5, `${label} is ${contrastRatio(fg, bg).toFixed(2)}`);
  }
});

test("fg-faint is only for secondary text: at least 3:1 on ink", () => {
  assert.ok(contrastRatio(token("fg-faint"), token("ink")) >= 3);
});
