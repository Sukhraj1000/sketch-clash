"""Database-wide, atomic provider admission; records never contain credentials.

Reservations count before transport begins. Unknown transport/commit outcomes
remain charged. The first cutover cannot reconstruct unrecorded earlier usage;
that limitation stays explicit, including after subsequent process restarts.
"""
LEDGER_ID = 'gemini-provider-admission-v1'
COLLECTION = 'providerAdmission'
WINDOW_SECONDS = 86400.
ISLAND_CATEGORIES = frozenset(('agent', 'council', 'reflection', 'island_embedding'))
EVALUATION_CATEGORIES = frozenset(('quality', 'evaluation_recognition', 'evaluation_embedding'))
SCOPES = frozenset(('island', 'interactive', 'evaluation'))


def request_scope(category):
    if category in ISLAND_CATEGORIES: return 'island'
    if category in EVALUATION_CATEGORIES: return 'evaluation'
    return 'interactive'


def reservation_scope(row):
    if row.get('scope') in SCOPES: return row['scope']
    category = row.get('category')
    if category in ISLAND_CATEGORIES or category in EVALUATION_CATEGORIES:
        return request_scope(category)
    if category in ('recognition', 'recognition_embedding', 'embedding'):
        return 'interactive'
    # Historical cutover rows have no attributable category. Keep that earlier
    # unknown usage charged to the island cap; do not erase or reset history.
    return 'island'


def reservation_priority(row):
    """Old rows predate lanes; only known interactive categories bypass pacing."""
    if row.get('priority') in ('foreground', 'background'):
        return row['priority']
    return 'foreground' if row.get('category') in ('recognition', 'recognition_embedding') else 'background'


class ProviderLedger:
    def __init__(self, repository, *, lease_seconds=300.):
        self.repository = repository
        self.lease_seconds = max(90., float(lease_seconds))

    @staticmethod
    def _new(now):
        return {'_id': LEDGER_ID, 'version': 1, 'cutover_at_epoch': now,
                'history_coverage_start_epoch': now, 'historical_usage_unknown': True,
                'reservations': [], 'cooldown_until': 0., 'revision': 0,
                'local_aborts': 0}

    @staticmethod
    def _prune(record, now):
        record['reservations'] = [row for row in record['reservations']
                                  if row['at'] > now-WINDOW_SECONDS or row.get('lease_until', 0) > now]

    @staticmethod
    def _public(record, now):
        rows = record['reservations']
        return {'timestamps': [row['at'] for row in rows if row['at'] > now-WINDOW_SECONDS],
                'island_timestamps': [row['at'] for row in rows
                    if row['at'] > now-WINDOW_SECONDS and reservation_scope(row) == 'island'],
                'active_leases': sum(row.get('lease_until', 0) > now for row in rows),
                'last_dispatch_at': max((row['at'] for row in rows), default=None),
                'last_background_dispatch_at': max((row['at'] for row in rows
                    if reservation_scope(row) == 'island'), default=None),
                'cooldown_until': record.get('cooldown_until', 0),
                'cutover_at_epoch': record['cutover_at_epoch'],
                'historical_usage_unknown': record['historical_usage_unknown'],
                'history_coverage_start_epoch': record['history_coverage_start_epoch'],
                'rolling_window_complete': now-record['history_coverage_start_epoch'] >= WINDOW_SECONDS,
                'revision': record['revision'], 'local_aborts': record.get('local_aborts', 0),
                'pacing_mode': record.get('pacing_mode')}

    @classmethod
    def pacing_in_transaction(cls, tx, mode, now, *, only_if_unset=False):
        """Share pace atomically with the operator control record."""
        if mode not in ('slow', 'steady', 'fast'): raise ValueError('Unknown request pace.')
        record = tx.get(COLLECTION, LEDGER_ID) or cls._new(now)
        if not only_if_unset or not record.get('pacing_mode'):
            record['pacing_mode'] = mode
            record['revision'] += 1
            tx.put(COLLECTION, record)
        return record['pacing_mode']

    def snapshot(self, now):
        record = self.repository.read(lambda tx: tx.get(COLLECTION, LEDGER_ID)) or self._new(now)
        self._prune(record, now)
        return self._public(record, now)

    def seed_cutover(self, timestamps, now, *, source='previous_process_dispatch_window', complete=False):
        """One idempotent operator cutover using known dispatch timestamps only."""
        values = sorted(float(stamp) for stamp in timestamps if now-WINDOW_SECONDS < float(stamp) <= now)
        def seed(tx):
            existing = tx.get(COLLECTION, LEDGER_ID)
            if existing is not None: return self._public(existing, now)
            record = self._new(now)
            record.update(historical_usage_unknown=not complete,
                          history_coverage_start_epoch=now-WINDOW_SECONDS if complete else now,
                          cutover_source=str(source)[:80])
            record['reservations'] = [{'id': 'cutover-'+str(i), 'at': stamp,
                                       'outcome': 'historical', 'lease_until': 0.} for i, stamp in enumerate(values)]
            record['revision'] = 1; tx.put(COLLECTION, record)
            return self._public(record, now)
        return self.repository.transaction(seed)

    def admit(self, identifier, now, *, requests_per_minute, requests_per_day,
              interval_seconds, concurrency, model, category, priority=None, interactive_concurrency=2):
        priority = reservation_priority({'category': category}) if priority is None else priority
        scope = request_scope(category)
        if priority not in ('foreground', 'background'):
            raise ValueError('Unknown provider queue priority.')
        def operation(tx):
            record = tx.get(COLLECTION, LEDGER_ID) or self._new(now)
            self._prune(record, now)
            existing = next((row for row in record['reservations'] if row['id'] == identifier), None)
            if existing:
                return {'admitted': True, 'reservation_id': identifier, 'snapshot': self._public(record, now)}
            stamps = sorted(row['at'] for row in record['reservations']
                if row['at'] > now-WINDOW_SECONDS and reservation_scope(row) == 'island')
            if scope == 'island' and len(stamps) >= requests_per_day:
                return {'admitted': False, 'reason': 'local_daily_cap',
                        'wait_seconds': max(0., stamps[-requests_per_day]+WINDOW_SECONDS-now),
                        'snapshot': self._public(record, now)}
            minute = [stamp for stamp in stamps if stamp > now-60.]
            leases = sorted(row['lease_until'] for row in record['reservations'] if row.get('lease_until', 0) > now
                and (reservation_scope(row) == 'island') == (scope == 'island'))
            waits = [(max(0., record.get('cooldown_until', 0)-now), 'provider_cooldown')]
            # Only island work has artificial spacing and rolling budgets.
            # Normal requests retain independent bounded transport concurrency.
            island_interval = max(60./requests_per_minute, interval_seconds)
            fraction = {'slow': .25, 'steady': .5, 'fast': 1.}.get(record.get('pacing_mode'))
            background_interval = 60./(requests_per_minute*fraction) if fraction else island_interval
            if scope == 'island' and stamps:
                waits.append((max(0., stamps[-1]+background_interval-now), 'local_background_spacing'))
            if scope == 'island' and len(minute) >= requests_per_minute:
                waits.append((max(0., minute[-requests_per_minute]+60.-now), 'local_minute_cap'))
            capacity = concurrency if scope == 'island' else interactive_concurrency
            if len(leases) >= capacity:
                waits.append((max(0., leases[-capacity]-now), 'local_concurrency'))
            delay, reason = max(waits)
            if delay > 0:
                return {'admitted': False, 'reason': reason, 'wait_seconds': delay,
                        'snapshot': self._public(record, now)}
            record['reservations'].append({'id': identifier, 'at': now, 'model': str(model)[:100],
                'category': str(category)[:40], 'priority': priority, 'scope': scope, 'pacing_scope': 'island' if scope == 'island' else 'none',
                'outcome': 'reserved', 'lease_until': now+self.lease_seconds})
            record['revision'] += 1; tx.put(COLLECTION, record)
            return {'admitted': True, 'reservation_id': identifier, 'snapshot': self._public(record, now)}
        return self.repository.transaction(operation)

    def finish(self, identifier, now, *, outcome, cooldown_until=0.):
        def operation(tx):
            record = tx.get(COLLECTION, LEDGER_ID)
            if record is None: return None
            row = next((row for row in record['reservations'] if row['id'] == identifier), None)
            if row:
                if outcome == 'local_control':
                    record['local_aborts'] = record.get('local_aborts', 0)+1
                row['outcome'] = outcome
                # Uncertain/cancelled transport keeps its lease briefly; another
                # process cannot start a concurrent call just because we exited.
                if outcome != 'uncertain': row['lease_until'] = 0.
            record['cooldown_until'] = max(record.get('cooldown_until', 0), cooldown_until)
            self._prune(record, now)
            record['revision'] += 1; tx.put(COLLECTION, record)
            return self._public(record, now)
        return self.repository.transaction(operation)
