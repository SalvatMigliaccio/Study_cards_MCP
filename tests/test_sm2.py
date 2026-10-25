from datetime import date
import pytest

from study_cards_mcp import sm2
DAY = date(2026, 10, 23)

def test_correct_answers_grow_the_interval():
    s= sm2.new_schedule(DAY)
    intervals = []
    for _ in range(4):
        s = sm2.review(s, 5, DAY)
        intervals.append(s.interval_days)
    assert intervals[:2] == [1, 6]
    assert intervals[2] > 6 and intervals[3] > intervals[2]
    
def test_wrong_answers_reset_the_card():
    s = sm2.review(sm2.review(sm2.new_schedule(DAY), 5, DAY), 2, DAY)
    s = sm2.review(s, 1, DAY)
    assert (s.repetitions, s.interval_days) == (0, 1)
    
def test_easiness_never_drops_below_minimum():
    s = sm2.new_schedule(DAY)
    for _ in range(20):
        s = sm2.review(s, 0, DAY)
    assert s.easiness == 1.3
    
def test_grade_out_of_range_is_rejected():
    with pytest.raises(ValueError):
        sm2.review(sm2.new_schedule(DAY), 6, DAY)
        
