import pytest

from marketing_system.constants import Environment
from marketing_system.fixtures import mock_logistics_leads
from marketing_system.models import Lead
from marketing_system.storage import StagingStore


def test_mock_record_round_trip(tmp_path):
    store = StagingStore(tmp_path / "stage.db")
    lead = mock_logistics_leads("test-correlation", 1)[0]
    store.upsert(lead)
    records = store.list_records(Environment.MOCK, "Lead")
    assert records[0]["id"] == lead.id
    assert records[0]["synthetic"] is True
    assert records[0]["environment"] == "mock"


def test_synthetic_record_cannot_enter_production(tmp_path):
    store = StagingStore(tmp_path / "stage.db")
    lead = mock_logistics_leads("test-correlation", 1)[0].model_copy(update={"environment": Environment.PRODUCTION})
    with pytest.raises(ValueError, match="Synthetic records"):
        store.upsert(lead)


def test_same_id_cannot_cross_environments(tmp_path):
    store = StagingStore(tmp_path / "stage.db")
    mock = mock_logistics_leads("test-correlation", 1)[0]
    store.upsert(mock)
    production = Lead(
        id=mock.id,
        source="zoho",
        environment=Environment.PRODUCTION,
        correlation_id="production",
        full_name="Verified person",
        synthetic=False,
    )
    with pytest.raises(ValueError, match="Cross-environment"):
        store.upsert(production)

