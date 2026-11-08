import React from "react";
import * as RT from "@radix-ui/react-toast";
import { cx } from "../cx";

type ToastTone = "ok" | "warn" | "bad";
interface ToastItem { id: number; message: string; tone: ToastTone }

const ToastContext = React.createContext<{ show: (message: string, tone?: ToastTone) => void }>({ show: () => {} });

export const useToast = () => React.useContext(ToastContext);

const TONE: Record<ToastTone, string> = { ok: "border-ok/40", warn: "border-warn/40", bad: "border-bad/40" };

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [items, setItems] = React.useState<ToastItem[]>([]);
  const nextId = React.useRef(0);
  const show = React.useCallback((message: string, tone: ToastTone = "ok") => {
    setItems((current) => [...current, { id: ++nextId.current, message, tone }]);
  }, []);
  return (
    <ToastContext.Provider value={{ show }}>
      <RT.Provider duration={5000}>
        {children}
        {items.map((item) => (
          <RT.Root
            key={item.id}
            onOpenChange={(open) => { if (!open) setItems((current) => current.filter((t) => t.id !== item.id)); }}
            className={cx("rounded-ctl border bg-navy px-4 py-3 text-sm text-fg shadow-xl", TONE[item.tone])}
          >
            <RT.Title>{item.message}</RT.Title>
          </RT.Root>
        ))}
        <RT.Viewport className="fixed bottom-4 right-4 z-50 flex w-[min(92vw,360px)] flex-col gap-2" />
      </RT.Provider>
    </ToastContext.Provider>
  );
};
