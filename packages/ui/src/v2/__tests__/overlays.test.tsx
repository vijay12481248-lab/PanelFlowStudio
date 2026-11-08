import { mount } from "./dom"; // must come first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup as html } from "react-dom/server";
import { Tile, Button, Dialog, Drawer, Field, IconButton, Input, Select, Switch, Tabs, ToastProvider, useToast } from "../index";

test("a closed Dialog renders nothing", async () => {
  const view = await mount(<Dialog open={false} onOpenChange={() => {}} title="Delete project">body</Dialog>);
  assert.equal(view.document.querySelector('[role="dialog"]'), null);
  await view.cleanup();
});

test("an open Dialog is named by its title and carries its content and footer", async () => {
  const view = await mount(<Dialog open onOpenChange={() => {}} title="Delete project" footer={<button>Delete</button>}>This cannot be undone.</Dialog>);
  const dialog = view.document.querySelector('[role="dialog"]');
  assert.ok(dialog, "dialog is in the document");
  const labelledBy = dialog.getAttribute("aria-labelledby");
  assert.equal(view.document.getElementById(labelledBy!)?.textContent, "Delete project");
  assert.ok(dialog.textContent!.includes("This cannot be undone."));
  assert.ok(dialog.textContent!.includes("Delete"));
  await view.cleanup();
});

test("a Drawer is a dialog too, anchored to its side", async () => {
  const view = await mount(<Drawer open onOpenChange={() => {}} title="Job details" side="left">x</Drawer>);
  const drawer = view.document.querySelector('[role="dialog"]')!;
  assert.ok(drawer.className.includes("left-0"));
  await view.cleanup();
});

test("Switch is a switch with its state and label", () => {
  const markup = html(<Switch checked onCheckedChange={() => {}} label="Private by default" />);
  assert.ok(markup.includes('role="switch"'));
  assert.ok(markup.includes('aria-checked="true"'));
  assert.ok(markup.includes("Private by default"));
});

test("Field links its label and error to the control", () => {
  const markup = html(<Field label="Project name" error="Enter a name."><Input /></Field>);
  assert.ok(markup.includes("Enter a name."));
  assert.ok(markup.includes('aria-invalid="true"'));
  const id = /<input[^>]* id="([^"]+)"/.exec(markup)?.[1];
  assert.ok(id, "input has an id");
  assert.ok(markup.includes(`for="${id}"`));
  assert.ok(new RegExp(`aria-describedby="[^"]*${id}-error`).test(markup));
});

test("Select renders its options inside a Field", () => {
  const markup = html(<Field label="Genre"><Select><option>Fantasy</option></Select></Field>);
  assert.ok(markup.includes("<select"));
  assert.ok(markup.includes("Fantasy"));
});

test("Tabs mark the active tab selected", () => {
  const markup = html(<Tabs value="b" onValueChange={() => {}} tabs={[{ value: "a", label: "Engine" }, { value: "b", label: "Models" }]}>panel</Tabs>);
  assert.ok(markup.includes('role="tablist"'));
  assert.ok(/aria-selected="true"[^>]*>Models/.test(markup));
});

test("useToast shows a message that is announced politely", async () => {
  function Trigger() {
    const toast = useToast();
    return <button id="go" onClick={() => toast.show("Settings saved", "ok")}>go</button>;
  }
  const view = await mount(<ToastProvider><Trigger /></ToastProvider>);
  await view.click(view.document.getElementById("go")!);
  assert.ok(view.document.body.textContent!.includes("Settings saved"));
  await view.cleanup();
});

test("closing a Dialog returns focus to the control that opened it", async () => {
  function Opener() {
    const [open, setOpen] = React.useState(false);
    return (
      <>
        <button id="opener" onClick={() => setOpen(true)}>Open</button>
        <Dialog open={open} onOpenChange={setOpen} title="Confirm" footer={<button id="close" onClick={() => setOpen(false)}>Close</button>}>x</Dialog>
      </>
    );
  }
  const view = await mount(<Opener />);
  const opener = view.document.getElementById("opener")!;
  opener.focus();
  await view.click(opener);
  assert.ok(view.document.querySelector('[role="dialog"]'), "dialog opened");
  await view.click(view.document.getElementById("close")!);
  assert.equal(view.document.querySelector('[role="dialog"]'), null, "dialog closed");
  await new Promise((resolve) => setTimeout(resolve, 30)); // Radix restores focus in a 0ms timeout
  assert.equal(view.document.activeElement?.id, "opener");
  await view.cleanup();
});

test("Button and IconButton forward refs so Radix triggers can anchor menus and tooltips to them", async () => {
  const buttonRef = React.createRef<HTMLButtonElement>();
  const iconRef = React.createRef<HTMLButtonElement>();
  const view = await mount(<><Button ref={buttonRef}>Menu</Button><IconButton ref={iconRef} label="Retry">x</IconButton></>);
  assert.equal(buttonRef.current?.tagName, "BUTTON");
  assert.equal(iconRef.current?.getAttribute("aria-label"), "Retry");
  await view.cleanup();
});

test("a Tile whose image fails to load falls back to its initials by itself", async () => {
  const view = await mount(<Tile title="Why We Cry" fallbackText="WC" imageUrl="/missing.png" />);
  const img = view.document.querySelector("img") as HTMLImageElement;
  assert.ok(img, "image requested first");
  await view.fire(img, "error");
  assert.equal(view.document.querySelector("img"), null);
  assert.ok(view.document.body.textContent!.includes("WC"));
  await view.cleanup();
});

test("a Tile tries again when it is given a different image", async () => {
  function Swap() {
    const [url, setUrl] = React.useState("/missing.png");
    return <><button id="swap" onClick={() => setUrl("/fixed.png")}>swap</button><Tile title="x" fallbackText="X" imageUrl={url} /></>;
  }
  const view = await mount(<Swap />);
  await view.fire(view.document.querySelector("img")!, "error");
  assert.equal(view.document.querySelector("img"), null);
  await view.click(view.document.getElementById("swap")!);
  assert.equal(view.document.querySelector("img")?.getAttribute("src"), "/fixed.png");
  await view.cleanup();
});
