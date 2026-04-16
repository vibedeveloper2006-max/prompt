from fastapi.testclient import TestClient
from app.main import app
from app.models.analytics_models import AnalyticsResponse

client = TestClient(app)

def test_get_insights_endpoint():
    response = client.get("/analytics/insights")
    assert response.status_code == 200
    
    data = response.json()
    assert "historical_hotspots" in data
    assert "live_leaderboard" in data
    assert "recommended_entry" in data
    
    # Assert leaderboard types
    if data["live_leaderboard"]:
        first = data["live_leaderboard"][0]
        assert "zone_id" in first
        assert "current_density" in first
        assert "status" in first
    
def test_analytics_models_serialization():
    resp = AnalyticsResponse(
        historical_hotspots=["Food Court", "Main Gate"],
        live_leaderboard=[],
        recommended_entry="North Gate"
    )
    
    dumped = resp.model_dump()
    assert dumped["historical_hotspots"] == ["Food Court", "Main Gate"]
    assert dumped["recommended_entry"] == "North Gate"
