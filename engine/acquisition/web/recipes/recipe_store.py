"""
ReaderRecipe storage, indexing, and persistence.
"""
import fnmatch
import json
from pathlib import Path
from typing import Dict, Optional, List
from urllib.parse import urlparse
from engine.acquisition.web.recipes.recipe import ReaderRecipe


class RecipeStore:
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir
        self._recipes: Dict[str, List[ReaderRecipe]] = {}
        if self.storage_dir and self.storage_dir.exists():
            self._load_from_disk()

    def _load_from_disk(self):
        if not self.storage_dir or not self.storage_dir.exists():
            return
        for file in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                recipe = ReaderRecipe.model_validate(data)
                self.save_recipe(recipe, persist=False)
            except Exception:
                pass

    def save_recipe(self, recipe: ReaderRecipe, persist: bool = True):
        domain = recipe.domain.lower()
        if domain not in self._recipes:
            self._recipes[domain] = []

        # Replace existing recipe with same pattern
        existing = [r for r in self._recipes[domain] if r.chapter_path_pattern == recipe.chapter_path_pattern]
        for ex in existing:
            self._recipes[domain].remove(ex)

        self._recipes[domain].insert(0, recipe)

        if persist and self.storage_dir:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            safe_domain = domain.replace(":", "_").replace("/", "_")
            out_file = self.storage_dir / f"{safe_domain}.json"
            out_file.write_text(recipe.model_dump_json(indent=2), encoding="utf-8")

    def remove_recipe(self, recipe: ReaderRecipe):
        domain = recipe.domain.lower()
        if domain in self._recipes:
            self._recipes[domain] = [r for r in self._recipes[domain] if r.chapter_path_pattern != recipe.chapter_path_pattern]
            if not self._recipes[domain]:
                del self._recipes[domain]
            if self.storage_dir:
                safe_domain = domain.replace(":", "_").replace("/", "_")
                out_file = self.storage_dir / f"{safe_domain}.json"
                if out_file.exists():
                    out_file.unlink()

    def find_recipe(self, url: str) -> Optional[ReaderRecipe]:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path or "/"

        candidates = self._recipes.get(domain, [])
        for r in candidates:
            if fnmatch.fnmatch(path, r.chapter_path_pattern):
                return r

        return None

    def list_all(self) -> List[ReaderRecipe]:
        all_r = []
        for r_list in self._recipes.values():
            all_r.extend(r_list)
        return all_r

    def clear(self):
        self._recipes.clear()
