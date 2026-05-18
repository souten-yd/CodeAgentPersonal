from fastapi.testclient import TestClient
import main

def test_api_path_traversal_rejected(tmp_path):
    main.app.state.atlas_ca_data_dir=str(tmp_path/'ca_data')
    c=TestClient(main.app)
    r=c.post('/api/atlas/supervised-handoff-safe-apply/execute',json={'pool_id':'../x','item_id':'i1','handoff_id':'handoff_x'})
    assert r.status_code==400
