"""Public board wording: a model's interpretation is never an execution fact."""


def board_text(row: dict) -> str:
    if row.get('kind') == 'report' or row.get('origin') != 'model':
        return row.get('text') or ''
    return row.get('interpretation') or row.get('text') or ''


def report_commentary(row: dict) -> dict:
    text = row.get('interpretation')
    if (row.get('kind') == 'report' and row.get('origin') == 'model'
            and isinstance(text, str) and text.strip() and text != row.get('text')):
        return {'unverified_model_commentary': text}
    return {}
