/** Keys typed into a text field, a select, an editable element or a dialog are not stage shortcuts. */
export const isTyping = (target: HTMLElement | null) =>
  ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName ?? "") || Boolean(target?.isContentEditable) || Boolean(target?.closest?.("[role=dialog]"));
