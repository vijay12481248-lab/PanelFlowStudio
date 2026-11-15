// Same key the old dashboard used, so existing favourites carry over.
const KEY = "panelflow_project_favorites";

export function toggleFavorite(favorites: Record<string, boolean>, id: string): Record<string, boolean> {
  return { ...favorites, [id]: !favorites[id] };
}

export function loadFavorites(storage: Pick<Storage, "getItem">): Record<string, boolean> {
  try {
    const parsed = JSON.parse(storage.getItem(KEY) ?? "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

export function saveFavorites(storage: Pick<Storage, "setItem">, favorites: Record<string, boolean>): void {
  try {
    storage.setItem(KEY, JSON.stringify(favorites));
  } catch {
    // Favourites are a convenience: a blocked or full store must not break the page.
  }
}
