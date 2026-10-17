from fastapi import APIRouter, HTTPException, status
from engine.acquisition.adapters.registry import get_default_registry
from engine.api.schemas import SourceInspectRequest, SourceInspectResponse

router = APIRouter(prefix="/api/adapters", tags=["adapters"])
adapter_registry = get_default_registry()

@router.get("")
def list_adapters():
    return adapter_registry.list_adapters()

@router.post("/inspect", response_model=SourceInspectResponse)
def inspect_source(req: SourceInspectRequest):
    source = req.source.strip()
    try:
        adapter = adapter_registry.get_adapter_for(source)
        res = adapter.inspect(source)
        return SourceInspectResponse(
            adapter_id=res.adapter_id,
            is_valid=res.is_valid,
            source_type=res.source_type.value,
            title_suggestion=res.title_suggestion,
            total_pages_detected=res.total_pages_detected,
            chapters=[c.model_dump() for c in res.chapters],
            error=res.error,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
