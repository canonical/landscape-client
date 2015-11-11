from datetime import datetime


def to_timestamp(date, epoch=datetime.utcfromtimestamp(0)):
    """Convert a C{datetime} to an C{int}-based timetamp."""
    delta = date - epoch
    return (delta.days * 60 * 60 * 24) + delta.seconds
