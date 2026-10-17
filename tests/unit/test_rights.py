import pytest
from engine.acquisition.rights.models import RightsStatus, RightsDeclaration

def test_rights_status_values():
    assert RightsStatus.UNKNOWN.value == "UNKNOWN"
    assert RightsStatus.PUBLIC_DOMAIN.value == "PUBLIC_DOMAIN"
    assert RightsStatus.CREATIVE_COMMONS.value == "CREATIVE_COMMONS"
    assert RightsStatus.LICENSED.value == "LICENSED"
    assert RightsStatus.USER_OWNED.value == "USER_OWNED"
    assert RightsStatus.EXPLICIT_PERMISSION.value == "EXPLICIT_PERMISSION"

def test_rights_declaration_validation():
    # UNKNOWN status must fail validation
    decl_unknown = RightsDeclaration(status=RightsStatus.UNKNOWN)
    assert not decl_unknown.is_actionable()
    with pytest.raises(ValueError, match="Acquisition cannot proceed with UNKNOWN rights status"):
        decl_unknown.validate_for_acquisition()

    # Valid statuses must pass validation
    for valid_status in [
        RightsStatus.PUBLIC_DOMAIN,
        RightsStatus.CREATIVE_COMMONS,
        RightsStatus.LICENSED,
        RightsStatus.USER_OWNED,
        RightsStatus.EXPLICIT_PERMISSION,
    ]:
        decl = RightsDeclaration(
            status=valid_status,
            license_type="CC-BY-4.0",
            permission_notes="Verified public license",
        )
        assert decl.is_actionable()
        decl.validate_for_acquisition()  # Does not raise
