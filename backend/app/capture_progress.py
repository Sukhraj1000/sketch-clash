"""Safe stage descriptions for a saved capture; never derived from model output."""
MESSAGES = {
    'registered': 'Photograph saved. Getting it ready to check.',
    'local_detection': 'Looking for objects in your photograph.',
    'local_ocr': 'Reading any printed text in your photograph.',
    'queued': 'Waiting for a normal Gemini request slot. Island speed limits do not apply to your photograph.',
    'gemini_recognition': 'Gemini is checking the photograph and proposing your fighter.',
    'validation': 'Checking the fighter’s identity, stats and look.',
    'repair': 'Tidying up the proposal and checking it again.',
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
