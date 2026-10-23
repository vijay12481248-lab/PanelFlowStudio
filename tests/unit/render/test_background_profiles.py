import pytest
from engine.render.models.profiles import editor_render_profile

@pytest.mark.parametrize('ratio,expected', [('16:9',(1920,1080)),('9:16',(1080,1920)),('1:1',(1080,1080)),('4:5',(864,1080))])
def test_editor_profile_ratio(ratio,expected):
    profile=editor_render_profile('standard_1080p',{'aspect_ratio':ratio})
    assert (profile.width,profile.height)==expected

def test_custom_and_4k_and_invalid_dimensions():
    profile=editor_render_profile('standard_1080p',{'aspect_ratio':'custom','canvas_width':1410,'canvas_height':790})
    assert (profile.width,profile.height)==(1410,790)
    assert editor_render_profile('ultra_4k',{'aspect_ratio':'16:9'}).height==2160
    assert editor_render_profile('draft_720p',{'aspect_ratio':'4:5'}).height==720
    with pytest.raises(ValueError,match='even'):
        editor_render_profile('standard_1080p',{'aspect_ratio':'custom','canvas_width':1410,'canvas_height':789})
