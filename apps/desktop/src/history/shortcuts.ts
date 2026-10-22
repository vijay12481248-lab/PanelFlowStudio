type ShortcutEvent = {
  key: string; ctrlKey: boolean; metaKey: boolean; shiftKey: boolean;
  altKey?: boolean; defaultPrevented?: boolean; isComposing?: boolean;
  target: EventTarget | null; composedPath?: () => EventTarget[];
};

function editsText(target: EventTarget | null): boolean {
  const element = target as Element | null;
  if (!element?.closest) return false;
  if (element.closest('input, textarea, select, [role="textbox"]')) return true;
  const editable = element.closest('[contenteditable]');
  return !!editable && editable.getAttribute('contenteditable') !== 'false';
}

/** Resolve an action, without taking native text undo or an inner scope's event. */
export function historyShortcut(event: ShortcutEvent): "undo" | "redo" | null {
  if (event.defaultPrevented || event.isComposing || event.altKey || !(event.ctrlKey || event.metaKey)) return null;
  if (editsText(event.target) || event.composedPath?.().some(editsText)) return null;
  const key = event.key.toLowerCase();
  return key === "z" ? event.shiftKey ? "redo" : "undo" : key === "y" ? "redo" : null;
}
