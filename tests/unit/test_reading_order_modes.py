from engine.imaging.panels.base import PanelBox, PanelType
from engine.imaging.panels.ordering import sort_panel_boxes, resequence_project_panels

def test_reading_order_ltr_and_rtl():
    # 2x2 grid
    p_tl = PanelBox(id="1", page_id="p1", x=50, y=50, width=500, height=700)
    p_tr = PanelBox(id="2", page_id="p1", x=600, y=50, width=500, height=700)
    p_bl = PanelBox(id="3", page_id="p1", x=50, y=850, width=500, height=700)
    p_br = PanelBox(id="4", page_id="p1", x=600, y=850, width=500, height=700)

    # LTR
    ltr = sort_panel_boxes([p_br, p_bl, p_tr, p_tl], reading_direction="ltr", page_height=1800)
    assert [p.id for p in ltr] == ["1", "2", "3", "4"]
    assert ltr[0].page_sequence == 1
    assert ltr[3].page_sequence == 4

    # RTL
    rtl = sort_panel_boxes([p_tl, p_tr, p_bl, p_br], reading_direction="rtl", page_height=1800)
    assert [p.id for p in rtl] == ["2", "1", "4", "3"]
    assert rtl[0].page_sequence == 1
    assert rtl[3].page_sequence == 4

def test_reading_order_vertical_webtoon():
    p1 = PanelBox(id="w1", page_id="p1", x=100, y=300, width=1200, height=1400)
    p2 = PanelBox(id="w2", page_id="p1", x=100, y=2000, width=1200, height=1500)
    p3 = PanelBox(id="w3", page_id="p1", x=100, y=4000, width=1200, height=1200)

    vert = sort_panel_boxes([p3, p1, p2], reading_direction="vertical", page_height=6000)
    assert [p.id for p in vert] == ["w1", "w2", "w3"]

def test_inset_panel_reading_flow():
    # Large parent panel + inset reaction box + bottom panel
    p_large = PanelBox(id="parent", page_id="p1", x=50, y=50, width=1100, height=800, panel_type=PanelType.STANDARD.value)
    p_inset = PanelBox(id="inset", page_id="p1", x=650, y=500, width=400, height=300, panel_type=PanelType.INSET.value)
    p_bottom = PanelBox(id="bottom", page_id="p1", x=50, y=950, width=1100, height=800, panel_type=PanelType.STANDARD.value)

    res = sort_panel_boxes([p_bottom, p_inset, p_large], reading_direction="ltr", page_height=1800)
    # The inset must be ordered right after its parent panel, before the bottom panel
    assert [p.id for p in res] == ["parent", "inset", "bottom"]

def test_custom_manual_ordering_and_global_resequencing():
    # Page 1: 2 panels manually sorted as [2, 1]
    p1 = PanelBox(id="p1_1", page_id="page1", x=50, y=50, width=400, height=400, page_sequence=2, sequence=2, manually_modified=True)
    p2 = PanelBox(id="p1_2", page_id="page1", x=500, y=50, width=400, height=400, page_sequence=1, sequence=1, manually_modified=True)

    # Page 2: 2 panels
    p3 = PanelBox(id="p2_1", page_id="page2", x=50, y=50, width=400, height=400, page_sequence=1, sequence=1)
    p4 = PanelBox(id="p2_2", page_id="page2", x=500, y=50, width=400, height=400, page_sequence=2, sequence=2)

    # Custom sort preserves manual sequence
    custom_sorted = sort_panel_boxes([p1, p2], reading_direction="custom")
    assert [p.id for p in custom_sorted] == ["p1_2", "p1_1"]

    # Global project resequencing across pages
    project_panels = resequence_project_panels({
        "page1": [p2, p1],
        "page2": [p3, p4],
    })

    assert len(project_panels) == 4
    # Global sequence 1..4
    assert [p.sequence for p in project_panels] == [1, 2, 3, 4]
    # Page sequence 1..2 on page 1, 1..2 on page 2
    assert [p.page_sequence for p in project_panels] == [1, 2, 1, 2]
