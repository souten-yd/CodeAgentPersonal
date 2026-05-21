from pathlib import Path


def test_planpool_handoff_wiring_present_in_pipeline():
    text = Path('app/api/atlas_pipeline.py').read_text()
    assert 'AtlasVerificationRecommendationHandoffService' in text
    assert 'pool.metadata["verification_recommendation_handoff"]' in text
    assert 'item.metadata = md' in text
