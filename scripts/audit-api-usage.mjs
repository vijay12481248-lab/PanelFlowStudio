// Lists methods of PanelFlowApiClient (packages/api-client/src/index.ts) and where each is used.
// Usage: node scripts/audit-api-usage.mjs [--all]
// A method is "unused" when no desktop UI source (tests and mocks excluded) references it.
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const clientFile = path.join(root, "packages/api-client/src/index.ts");
const source = readFileSync(clientFile, "utf8");
const sf = ts.createSourceFile(clientFile, source, ts.ScriptTarget.Latest, true);

const methods = [];
sf.forEachChild(function visit(node) {
  if (ts.isClassDeclaration(node) && node.name?.text === "PanelFlowApiClient") {
    for (const member of node.members) {
      const isPrivate = member.modifiers?.some((m) => m.kind === ts.SyntaxKind.PrivateKeyword || m.kind === ts.SyntaxKind.ProtectedKeyword);
      if ((ts.isMethodDeclaration(member) || ts.isPropertyDeclaration(member)) && ts.isIdentifier(member.name) && !isPrivate) {
        methods.push(member.name.text);
      }
    }
  }
  ts.forEachChild(node, visit);
});

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "__tests__" || entry.name === "node_modules" ? [] : walk(full);
    return /\.tsx?$/.test(entry.name) && !/\.(test|mock)\./.test(entry.name) ? [full] : [];
  });
}

const uiText = walk(path.join(root, "apps/desktop/src")).map((f) => [path.relative(root, f), readFileSync(f, "utf8")]);
// Inside the client itself, a reference counts as "internal" (a helper another method calls).
const internalText = source;

const rows = methods.map((name) => {
  const re = new RegExp(`\\b${name}\\b`);
  const uiHits = uiText.filter(([, text]) => re.test(text)).map(([file]) => file);
  const internalHits = (internalText.match(new RegExp(`\\b${name}\\b`, "g")) ?? []).length - 1; // minus its own declaration
  return { name, uiHits, internalHits };
}).filter((row) => row.name !== "constructor");

const unused = rows.filter((row) => row.uiHits.length === 0);
console.log(`${rows.length} methods; ${unused.length} not referenced by desktop UI source.\n`);
for (const row of unused) console.log(`${row.name}${row.internalHits > 0 ? `  (used by ${row.internalHits} other client method(s))` : ""}`);
if (process.argv.includes("--all")) {
  console.log("\nAll methods and their UI files:");
  for (const row of rows) console.log(`${row.name}: ${row.uiHits.join(", ") || "-"}`);
}
