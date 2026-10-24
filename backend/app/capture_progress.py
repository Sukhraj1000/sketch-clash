"""Safe stage descriptions for a saved capture; never derived from model output."""
MESSAGES = {
    'registered': 'Photograph saved. Preparing local recognition.',
    'local_detection': 'Local YOLO is checking objects in the selected photograph.',
    'local_ocr': 'Local OCR is reading visible text in the selected photograph.',
    'queued': 'Waiting for a Gemini slot. Player captures take priority over unsent island work; shared limits still apply.',
    'gemini_recognition': 'Gemini is checking the photograph and proposing your fighter.',
    'validation': 'Checking the proposed identity, fighter stats and appearance locally.',
    'repair': 'The proposal failed a local check. Preparing a bounded correction.',
    'saving': 'Saving the checked proposal for your review.',
    'complete': 'Recognition finished. Your saved result is ready for review.',
    'failed': 'Recognition stopped without a saved result. This capture is no longer queued.',
}


def progress_record(stage, timestamp, *, model=None, attempt=None):
    if stage not in MESSAGES:
        raise ValueError('Unknown capture progress stage.')
    result = {'stage': stage, 'message': MESSAGES[stage], 'updated_at': timestamp}
    if model in ('gemini-4-argon', 'gemini-3.8-flash', 'gemini-3.5-flash-lite'):
        result['model'] = model
    if type(attempt) is int and 1 <= attempt <= 8:
        result['attempt'] = attempt
    return result
