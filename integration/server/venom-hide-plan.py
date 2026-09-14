"""Pure visibility decisions; no credentials, databases or mutations."""
def action(current,previous,eligible,present,identity,compact=False):
    if previous and previous['identity']!=identity:return 'identity_changed'
    if previous and previous.get('status')=='managed':
        if not current:return 'manual_unhide'
        if present:return 'compact_numbering_requires_review' if compact else 'restore'
        return 'keep_hidden'
    if previous and previous.get('status')=='manual_unhide':return 'respect_manual_unhide'
    if current:return 'respect_existing_hide'
    if compact:return 'compact_numbering_requires_review'
    return 'hide' if eligible else 'keep_visible'
