from app.nexus.web_scout import choose_replacement_engines

def test_replenishment_order_google_to_bing_to_brave():
    assert choose_replacement_engines('news','google',{'google'})[0]=='bing'
    nxt=choose_replacement_engines('news','bing',{'google','bing'})
    assert nxt[0]=='brave'
