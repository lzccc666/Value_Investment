from fastapi import APIRouter, HTTPException, status

from app.configuration.defaults import default_parameter_config
from app.schemas.parameter_config import (
    ParameterConfigCurrentResponse,
    ParameterConfigPublishResponse,
    ParameterConfigUpdateRequest,
    ParameterValidationResult,
)
from app.services.parameter_config_service import (
    ParameterConfigError,
    ParameterConfigValidationError,
    ParameterConfigWarningConfirmationRequired,
    build_parameter_metadata,
    config_hash,
    get_runtime_parameter_config,
    publish_parameter_config,
    validate_parameter_config,
)

router = APIRouter(prefix="/parameter-config")


@router.get("/current", response_model=ParameterConfigCurrentResponse)
def read_current_parameter_config() -> ParameterConfigCurrentResponse:
    runtime = get_runtime_parameter_config()
    return ParameterConfigCurrentResponse(
        config_json=runtime.snapshot,
        config_hash=runtime.config_hash,
        source=runtime.source,
        fallback_reason=runtime.fallback_reason,
        validation=validate_parameter_config(runtime.snapshot, compare_to_default=False),
        metadata=build_parameter_metadata(runtime.snapshot),
    )


@router.get("/defaults", response_model=ParameterConfigCurrentResponse)
def read_default_parameter_config() -> ParameterConfigCurrentResponse:
    config = default_parameter_config()
    return ParameterConfigCurrentResponse(
        config_json=config,
        config_hash=config_hash(config),
        source="builtin_default",
        fallback_reason=None,
        validation=validate_parameter_config(config, compare_to_default=False),
        metadata=build_parameter_metadata(config),
    )


@router.post("/validate", response_model=ParameterValidationResult)
def validate_current_parameter_config(
    payload: ParameterConfigUpdateRequest,
) -> ParameterValidationResult:
    return validate_parameter_config(payload.config_json.model_dump(mode="json"))


@router.put("/current", response_model=ParameterConfigPublishResponse)
def publish_current_parameter_config(
    payload: ParameterConfigUpdateRequest,
) -> ParameterConfigPublishResponse:
    runtime, validation = _handle(
        lambda: publish_parameter_config(
            payload.config_json.model_dump(mode="json"),
            warnings_acknowledged=payload.warnings_acknowledged,
        )
    )
    return ParameterConfigPublishResponse(
        config_json=runtime.snapshot,
        config_hash=runtime.config_hash,
        source="source_file",
        validation=validation,
        metadata=build_parameter_metadata(runtime.snapshot),
    )


def _handle(action):
    try:
        return action()
    except ParameterConfigWarningConfirmationRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "validation": exc.result.model_dump(mode="json")},
        ) from exc
    except ParameterConfigValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "validation": exc.result.model_dump(mode="json")},
        ) from exc
    except ParameterConfigError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
