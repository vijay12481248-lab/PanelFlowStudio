import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DashboardHeader } from "../../dashboard/DashboardHeader";
import { ErrorProvider } from "../../../context/ErrorContext";
import ts from "typescript";
import { readFileSync } from "node:fs";

test("dashboard exposes provider management separately from workspace health", () => {
  const html = renderToStaticMarkup(<ErrorProvider><DashboardHeader engineConnected={true} engineVersion="test" onOpenToolsModels={() => {}} onOpenProviderManagement={() => {}} /></ErrorProvider>);
  assert.match(html, /AI Providers/);
  assert.match(html, /Workspace health/);
});

test("render navigation never performs a bitwise operation on screen names", () => {
  const source = ts.createSourceFile("App.tsx", readFileSync(new URL("../../../App.tsx", import.meta.url), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const invalid: string[] = [];
  function visit(node: ts.Node) {
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.BarToken && /render|ai_provider_management/.test(node.getText(source))) invalid.push(node.getText(source));
    ts.forEachChild(node, visit);
  }
  visit(source);
  assert.deepEqual(invalid, []);
});
