"""
Recipes package for web acquisition.
"""
from engine.acquisition.web.recipes.recipe import ReaderRecipe
from engine.acquisition.web.recipes.recipe_store import RecipeStore
from engine.acquisition.web.recipes.recipe_builder import RecipeBuilder
from engine.acquisition.web.recipes.recipe_validator import RecipeValidator

__all__ = [
    "ReaderRecipe",
    "RecipeStore",
    "RecipeBuilder",
    "RecipeValidator",
]
