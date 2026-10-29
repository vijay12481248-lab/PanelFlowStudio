"""FastAPI Router for Browser AI Bridge."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from engine.imaging.meta_ai_workflow import (
    PanelRequirement,
    MetaAIWorkflowResult,
    meta_ai_workflow,
)
from engine.imaging.browser_ai_bridge import (
    BrowserBridgeResult,
    browser_ai_bridge,
)

router = APIRouter(prefix="/api/browser-bridge", tags=["browser-bridge"])


class OpenSessionRequest(BaseModel):
    url: str = Field(default="https://chatgpt.com", description="Website URL to open for logging in")


class ExecutePromptRequest(BaseModel):
    url: str = Field(..., description="Target website URL (e.g. ChatGPT, Gemini, Meta AI, or custom tool)")
    prompt: str = Field(..., min_length=2, max_length=20000, description="Prompt text to input and execute")
    extract_type: str = Field(default="all", pattern="^(images|text|all)$", description="Type of result to extract")
    project_id: Optional[str] = Field(default=None, description="Optional Project ID to store assets under")
    headless: bool = Field(default=True, description="Run headless in background, or show browser window")
    timeout_sec: float = Field(default=120.0, ge=10.0, le=600.0, description="Max execution timeout in seconds")


@router.get("/status")
def get_browser_bridge_status() -> Dict[str, Any]:
    """Returns browser availability, session profile path, and supported presets."""
    return browser_ai_bridge.get_status()


@router.post("/open-session")
def open_interactive_session(req: OpenSessionRequest) -> Dict[str, Any]:
    """
    Launches a visible browser window so the user can sign in or interact with the AI website.
    Cookies and login state are stored in the persistent browser profile.
    """
    try:
        return browser_ai_bridge.launch_interactive_session(req.url)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to launch interactive browser session: {exc}",
        ) from exc


@router.post("/execute")
async def execute_browser_prompt(req: ExecutePromptRequest) -> BrowserBridgeResult:
    """
    Navigates to the website, types the prompt into the AI input, executes it,
    and extracts the generated result (images, text, or both) back to PanelFlow Studio.
    """
    try:
        result = await browser_ai_bridge.execute_prompt_async(
            url=req.url,
            prompt=req.prompt,
            extract_type=req.extract_type,
            headless=req.headless,
            timeout_sec=req.timeout_sec,
            project_id=req.project_id,
        )
        if not result.success:
            # If unsuccessful, return the result object with error details
            return result
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution failed: {exc}",
        ) from exc

@router.post("/generate-with-review")
async def generate_with_prompt_engineer_and_review(
    req: PanelRequirement,
    headless: bool = True,
    timeout_sec: float = 120.0,
) -> MetaAIWorkflowResult:
    """
    Automated workflow:
    1. Prompt Engineer generates high-fidelity prompt from panel requirements.
    2. Meta AI Browser Bridge executes the prompt and extracts the generated images.
    3. Reviewer grades quality, aspect ratio, and narrative alignment.
    """
    return await meta_ai_workflow.execute_panel_generation(
        requirement=req,
        headless=headless,
        timeout_sec=timeout_sec,
    )
