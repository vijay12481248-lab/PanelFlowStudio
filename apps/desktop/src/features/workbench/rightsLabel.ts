const KNOWN: Record<string, { word: string; tone: "ok" | "warn" | "neutral" }> = {
  UNKNOWN: { word: "Rights unknown", tone: "warn" },
  PUBLIC_DOMAIN: { word: "Public domain", tone: "ok" },
  CREATIVE_COMMONS: { word: "Creative Commons", tone: "ok" },
  LICENSED: { word: "Licensed", tone: "ok" },
  USER_OWNED: { word: "Your own work", tone: "ok" },
  EXPLICIT_PERMISSION: { word: "Permission granted", tone: "ok" },
  COMMENTARY_REVIEW: { word: "Commentary and review", tone: "ok" },
};

/** The engine also uses values the shared type does not list (for example AUTHORIZED_WEB), so unknown codes are humanised. */
export function rightsLabel(status: string): { word: string; tone: "ok" | "warn" | "neutral" } {
  if (!status) return { word: "Rights not recorded", tone: "neutral" };
  const known = KNOWN[status];
  if (known) return known;
  const text = status.replace(/_/g, " ").toLowerCase();
  return { word: text.charAt(0).toUpperCase() + text.slice(1), tone: "neutral" };
}
