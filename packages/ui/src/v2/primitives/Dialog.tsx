import React from "react";
import * as RD from "@radix-ui/react-dialog";
import { cx } from "../cx";

export interface OverlayProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Required: Radix uses it as the accessible name. */
  title: string;
  description?: string;
  children?: React.ReactNode;
  footer?: React.ReactNode;
}

/** Shared by Dialog and Drawer. The scrim is a flat tint with no blur, because dialogs sit above the blurred hub. */
export const OverlayContent: React.FC<OverlayProps & { className: string }> = ({ open, onOpenChange, title, description, children, footer, className }) => {
  // These dialogs are controlled and have no Radix Trigger, so remember what had focus when they
  // opened and hand it back on close (otherwise focus drops to the page body).
  const opener = React.useRef<HTMLElement | null>(null);
  React.useLayoutEffect(() => {
    if (open) opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }, [open]);
  return (
  <RD.Root open={open} onOpenChange={onOpenChange}>
    <RD.Portal>
      <RD.Overlay className="fixed inset-0 z-40 bg-ink/70" />
      <RD.Content
        onCloseAutoFocus={(event) => { event.preventDefault(); opener.current?.focus(); }}
        {...(description ? {} : { "aria-describedby": undefined })}
        className={cx("fixed z-50 flex flex-col border border-edge bg-navy text-fg shadow-2xl focus:outline-none", className)}
      >
        <div className="border-b border-edge px-5 py-4">
          <RD.Title className="font-display text-lg font-semibold">{title}</RD.Title>
          {description && <RD.Description className="mt-1 text-sm text-fg-dim">{description}</RD.Description>}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 text-sm">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-edge px-5 py-3">{footer}</div>}
      </RD.Content>
    </RD.Portal>
  </RD.Root>
  );
};

export const Dialog: React.FC<OverlayProps> = (props) => (
  <OverlayContent {...props} className="left-1/2 top-1/2 max-h-[85vh] w-[min(92vw,560px)] -translate-x-1/2 -translate-y-1/2 rounded-card" />
);
