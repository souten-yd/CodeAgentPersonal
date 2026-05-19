def test_placeholder_guarded_service_contract():
    from agent.atlas_guarded_operator_loop_schema import AtlasGuardedOperatorLoopRequest
    r=AtlasGuardedOperatorLoopRequest(pool_id='p1')
    assert r.mode=='advance_to_confirmation'
