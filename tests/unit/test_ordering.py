from engine.acquisition.downloader.sorting import natural_sort_key

def test_natural_sort_ordering():
    unsorted = [
        "page_10.png",
        "page_1.png",
        "page_2.png",
        "page_100.png",
        "page_20.png",
        "page_3.png",
    ]
    sorted_pages = sorted(unsorted, key=natural_sort_key)
    assert sorted_pages == [
        "page_1.png",
        "page_2.png",
        "page_3.png",
        "page_10.png",
        "page_20.png",
        "page_100.png",
    ]

def test_natural_sort_chapter_and_volume():
    filenames = [
        "vol2_ch10_p02.jpg",
        "vol1_ch01_p01.jpg",
        "vol1_ch02_p01.jpg",
        "vol1_ch10_p01.jpg",
        "vol2_ch1_p01.jpg",
    ]
    expected = [
        "vol1_ch01_p01.jpg",
        "vol1_ch02_p01.jpg",
        "vol1_ch10_p01.jpg",
        "vol2_ch1_p01.jpg",
        "vol2_ch10_p02.jpg",
    ]
    assert sorted(filenames, key=natural_sort_key) == expected
