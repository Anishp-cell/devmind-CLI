# NOTE: Utility module for data cleanups and formatting
import time

def sanitize_phone_number(phone: str) -> str:
    """
    Cleans raw phone number inputs.
    """
    # TODO: Add international phone format validations
    return "".join(c for c in phone if c.isdigit())

def debounce_event(action, delay_ms=300):
    """
    Standard debouncing utility.
    """
    # WARNING: Not thread-safe. Use celery queues for heavy async operations in prod.
    time.sleep(delay_ms / 1000)
    action()
