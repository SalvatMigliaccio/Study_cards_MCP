"""Algorithm SM-2 (Super Memo 2) for spaced repetition.
    Pure logic: no dependencies on MCP or Databases,
    Can be used as a standalone module for spaced repetition.
    the vote goes from 0 to 5, where 0 means complete failure and 5 means perfect recall.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta

@dataclass(frozen=True) # frozen dataclass to make instances immutable
class Schedule:
    repetitions: int  # number of times the item has been repeated successfully
    interval_days: int  # interval in days until the next review
    easiness: float  # easiness factor of the item
    due: date  # due date for the next review
    
def new_schedule(today: date) -> Schedule:
    """Create a new schedule starting from today."""
    return Schedule(
        repetitions=0,
        interval_days=0,
        easiness=2.5,
        due=today
    )
    
def review(s: Schedule, grade: int, today: date) -> Schedule:
    """Review the schedule based on the given grade and today's date."""
    if not 0 <= grade <= 5:
        raise ValueError("Grade must be between 0 and 5.")
    easiness = max(1.3, s.easiness + 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)) 
    # update easiness factor based on grade
    if grade < 3:
        #if the grade is less than 3, reset the repetition count and interval
        repetitions, interval = 0, 1
    else:
        repetitions = s.repetitions + 1
        if repetitions == 1:
            interval = 1
        elif repetitions == 2:
            interval = 6
        else:
            interval = round(s.interval_days * easiness)
    return Schedule(repetitions, interval, round(easiness, 2), today + timedelta(days=interval))

#how this works: with correct responses (grade >= 3), the interval increases according to the easiness factor.
#with incorrect responses (grade < 3), the repetition count is reset and the interval is set to 1 day.
