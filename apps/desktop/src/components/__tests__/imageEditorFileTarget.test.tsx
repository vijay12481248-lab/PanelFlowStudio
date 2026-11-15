import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ImageEditorModal, type ImageEditorTarget } from "../ImageEditorModal";

const fileTarget: ImageEditorTarget = {
  mode: "file",
  name: "art_demo123.png",
  imageSrc: "http://127.0.0.1:8765/chronoflow/inputs/art_demo123.png",
  inpaint: async () => "http://127.0.0.1:8765/chronoflow/inputs/inpaint_x.png",
};

test("Image Studio opens on a plain ChronoFlow picture (file target) and names it", () => {
  const html = renderToStaticMarkup(<ImageEditorModal isOpen={true} onClose={() => {}} target={fileTarget} />);
  assert.ok(html.includes("art_demo123.png"), "the picture's file name is shown");
  assert.ok(html.includes('role="dialog"'), "the studio renders as the usual full-screen dialog");
});

test("a file target is inert while closed", () => {
  assert.equal(renderToStaticMarkup(<ImageEditorModal isOpen={false} onClose={() => {}} target={fileTarget} />), "");
});
