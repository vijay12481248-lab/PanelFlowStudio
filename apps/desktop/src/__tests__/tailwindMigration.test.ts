import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";
import postcss from "postcss";

const root = new URL("../../../../", import.meta.url);

async function stylesheet(sharedOnly = false) {
  const { default: config } = await import("../../postcss.config.js");
  const source = new URL("apps/desktop/src/index.css", root);
  const css = await readFile(source, "utf8");
  return postcss(config.plugins).process(sharedOnly ? css.replace('@source "./";', "") : css, {
    from: fileURLToPath(source),
  });
}

test("legacy spacing, outlines, and gradients retain their v3 semantics", async () => {
  const result = await stylesheet();
  const rules = new Map<string, Record<string, string>>();
  result.root.walkRules((rule) => {
    const declarations = rules.get(rule.selector) || {};
    rule.walkDecls((decl) => { declarations[decl.prop] = decl.value; });
    rules.set(rule.selector, declarations);
  });
  assert.ok(rules.has(".space-y-4 > :not([hidden]) ~ :not([hidden])"), "space utilities must skip hidden siblings and use the leading margin");
  assert.ok(rules.has(".divide-y > :not([hidden]) ~ :not([hidden])"), "divide utilities must skip hidden siblings and use the leading border");
  assert.ok(rules.has(".focus\\:outline-none:focus"), "compile the actual focus outline utility");
  assert.equal(rules.get(".focus\\:outline-none:focus")?.["outline-style"], undefined, "do not disable the transparent forced-colors outline");
  assert.equal(rules.get(".bg-gradient-to-r")?.["--tw-gradient-position"], "to right", "v3 gradients interpolate in sRGB");
  assert.equal(result.warnings().length, 0);
});

test("arbitrary descendant focus variants keep v3 variant order", async () => {
  const result = await stylesheet();
  const selectors = new Set<string>();
  result.root.walkRules((rule) => { selectors.add(rule.selector); });
  for (const utility of ["outline-none", "ring-2", "ring-violet-400"]) {
    const selector = String.raw`.\[\&_button\]\:focus-visible\:${utility}:focus-visible button`;
    assert.ok(selectors.has(selector), `preserve parent focus-visible for ${utility}`);
  }
});

test("shared UI sources compile independently of desktop scanning", async () => {
  const result = await stylesheet(true);
  const selectors = new Set<string>();
  result.root.walkRules((rule) => { selectors.add(rule.selector); });
  assert.ok(selectors.has(String.raw`.max-w-\[95vw\]`), "compile the shared Modal full width");
  assert.ok(selectors.has(String.raw`.focus\:ring-offset-2:focus`), "compile shared Button focus styling");
});

test("v3 palette, radius, blur, and shadow tokens remain stable", async () => {
  const result = await stylesheet();
  const rules = new Map<string, Record<string, string>>();
  result.root.walkRules((rule) => {
    const declarations = rules.get(rule.selector) || {};
    rule.walkDecls((decl) => { declarations[decl.prop] = decl.value; });
    rules.set(rule.selector, declarations);
  });
  for (const [selector, property, expected] of [
    [".bg-indigo-600", "background-color", "#4f46e5"],
    [".text-zinc-400", "color", "#a1a1aa"],
    [".rounded-sm", "border-radius", "0.125rem"],
    [".rounded", "border-radius", "0.25rem"],
    [".backdrop-blur-sm", "--tw-backdrop-blur", "blur(4px)"],
    [".backdrop-blur", "--tw-backdrop-blur", "blur(8px)"],
    [".flex-shrink-0", "flex-shrink", "0"],
  ]) assert.equal(rules.get(selector)?.[property], expected, `${selector} ${property}`);
  assert.match(rules.get(".shadow-sm")?.["--tw-shadow"] || "", /^0 1px 2px 0 /);
  assert.match(rules.get(".shadow-inner")?.["--tw-shadow"] || "", /^inset 0 2px 4px 0 /);
});

test("compatibility handling leaves unrelated application rules untouched", async () => {
  const { default: config } = await import("../../postcss.config.js");
  const compatibility = config.plugins.filter((plugin) => plugin.postcssPlugin === "panelflow-tailwind-v3-compatibility");
  const css = ".custom-outline-none { outline-style: none; } .custom-bg-gradient-to-r { --tw-gradient-position: to right in oklab; }";
  const result = await postcss(compatibility).process(css, { from: undefined });
  assert.equal(result.css, css);
});

test("form defaults remain in the base layer so utilities win the cascade", async () => {
  const result = await stylesheet();
  let formDefaults = 0;
  result.root.walkRules((rule) => {
    if (!rule.selector.includes("textarea") || !rule.selector.includes("button")) return;
    rule.walkDecls("font", (decl) => {
      if (decl.value !== "inherit") return;
      formDefaults++;
      let parent = rule.parent;
      while (parent && !(parent.type === "atrule" && parent.name === "layer" && parent.params === "base")) parent = parent.parent;
      assert.ok(parent, "unlayered font: inherit overrides text-xs/font-semibold in Tailwind 4");
    });
  });
  assert.ok(formDefaults > 0, "exercise the actual form default rule");
});

test("the installed lockfile excludes the vulnerable Tailwind 3 build chains", async () => {
  const lock = JSON.parse(await readFile(new URL("package-lock.json", root), "utf8"));
  const removed = ["braces", "micromatch", "fast-glob", "postcss-nested", "postcss-selector-parser"];
  for (const name of removed) {
    assert.ok(!Object.keys(lock.packages).some((key) => key.endsWith(`/node_modules/${name}`) || key === `node_modules/${name}`), `${name} must be removed, not overridden or hidden`);
  }
  const desktop = JSON.parse(await readFile(new URL("apps/desktop/package.json", root), "utf8"));
  assert.equal(desktop.devDependencies.jsdom, "26.1.0", "retain the existing DOM test runtime");
  const manifest = JSON.parse(await readFile(new URL("package.json", root), "utf8"));
  assert.equal(lock.packages["node_modules/tailwindcss"].version, desktop.devDependencies.tailwindcss);
  assert.match(desktop.devDependencies.tailwindcss, /^4\./);
  assert.equal(manifest.overrides, undefined, "do not hide findings behind root overrides");
  assert.equal(desktop.overrides, undefined, "do not hide findings behind desktop overrides");
});
