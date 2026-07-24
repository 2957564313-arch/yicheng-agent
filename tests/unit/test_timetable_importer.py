from app.services.timetable_importer import (
    _rows_from_hdu_positioned_pages,
    _weeks_value,
    parse_timetable,
)


def test_week_ranges_apply_odd_even_rule_per_segment():
    assert _weeks_value("1-5周(单),6周,8-12周(双)") == [
        1,
        3,
        5,
        6,
        8,
        10,
        12,
    ]


def test_hdu_pdf_grid_recognizes_two_and_three_period_blocks():
    rows = _rows_from_hdu_positioned_pages(
        [
            [
                (104.1, 505.5, 9.0, "高等数学"),
                (104.1, 493.5, 8.0, "(1-2节)1-17周/校区:下沙/场"),
                (104.1, 481.5, 8.0, "地:第6教研楼北204/教师:张老师"),
                (207.9, 382.0, 9.0, "思想道德与法治"),
                (207.9, 370.0, 8.0, "(3-5节)1-6周,9-17周/校区:下沙"),
                (207.9, 358.0, 8.0, "/场地:第12教研楼301/教师:李老师"),
                (207.9, 248.5, 9.0, "思想道德与法治"),
                (207.9, 236.5, 8.0, "(3-5节)7-8周/校区:下沙/场"),
                (207.9, 224.5, 8.0, "地:课外实践不在教室/教师:李老师"),
            ]
        ]
    )
    entries, skipped, messages = parse_timetable(
        content=__import__("json").dumps(rows, ensure_ascii=False),
        format_name="json",
    )
    assert skipped == 0
    assert messages == []
    assert len(entries) == 3
    assert (entries[0].weekday, entries[0].start_period, entries[0].end_period) == (
        1,
        1,
        2,
    )
    assert entries[0].location == "第6教研楼北204"
    assert entries[1].weeks == [1, 2, 3, 4, 5, 6, *range(9, 18)]
    assert entries[2].location is None


def test_hdu_pdf_duplicate_rows_merge_week_sets():
    rows = _rows_from_hdu_positioned_pages(
        [
            [
                (104.1, 272.5, 9.0, "数学建模"),
                (104.1, 260.5, 8.0, "(8-9节)1周/校区:下沙/场地:第12教研楼102/教师:A"),
                (104.1, 139.0, 9.0, "数学建模"),
                (104.1, 127.0, 8.0, "(8-9节)1周,17周/校区:下沙"),
                (104.1, 115.0, 8.0, "/场地:第12教研楼102/教师:B"),
            ]
        ]
    )
    assert len(rows) == 1
    assert rows[0]["weeks"] == [1, 17]
