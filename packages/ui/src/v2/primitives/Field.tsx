import React from "react";
import { cx } from "../cx";

interface FieldContextValue { id: string; describedBy?: string; invalid: boolean }
const FieldContext = React.createContext<FieldContextValue | null>(null);

export interface FieldProps {
  label: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}

export const Field: React.FC<FieldProps> = ({ label, error, hint, children }) => {
  const id = React.useId();
  const describedBy = [error && `${id}-error`, hint && `${id}-hint`].filter(Boolean).join(" ") || undefined;
  return (
    <FieldContext.Provider value={{ id, describedBy, invalid: Boolean(error) }}>
      <div className="grid gap-1.5">
        <label htmlFor={id} className="text-[13px] font-medium text-fg">{label}</label>
        {children}
        {hint && <p id={`${id}-hint`} className="text-xs text-fg-faint">{hint}</p>}
        {error && <p id={`${id}-error`} className="text-xs text-bad">{error}</p>}
      </div>
    </FieldContext.Provider>
  );
};

const CONTROL = "h-10 w-full rounded-ctl border border-edge bg-glass px-3 text-sm text-fg placeholder:text-fg-faint focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-info aria-[invalid=true]:border-bad";

function useFieldProps() {
  const field = React.useContext(FieldContext);
  return field ? { id: field.id, "aria-describedby": field.describedBy, "aria-invalid": field.invalid || undefined } : {};
}

export const Input: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = ({ className, ...rest }) => (
  <input {...useFieldProps()} {...rest} className={cx(CONTROL, className)} />
);

export const Select: React.FC<React.SelectHTMLAttributes<HTMLSelectElement>> = ({ className, children, ...rest }) => (
  <select {...useFieldProps()} {...rest} className={cx(CONTROL, className)}>{children}</select>
);
