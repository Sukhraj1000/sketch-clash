"""Read-only joins from Observatory entries to durable, scoped action receipts.

A board proposal is not an action, and provider success is not a state change.
Historical receipts remain readable without retroactively inventing snapshots.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any

from .repository import StoreError, key_for

COLONY_IDS = ('winners', 'losers')
PER_ISLAND_RECEIPT_LIMIT = 1000


def _scope(root: str, island: str) -> str:
    return key_for(root, 'colony-world', island)[:32]


def _numbers(value: Any) -> dict[str, float | int]:
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if isinstance(v, (int, float))
            and not isinstance(v, bool) and isfinite(v)}


def _action_receipt(row: dict | None) -> bool:
    return bool(row and isinstance(row.get('sequence'), int) and row.get('character_id')
                and isinstance(row.get('resource_delta'), dict))


def _plus(target: dict, delta: dict):
    for key, amount in delta.items():
        target[key] = target.get(key, 0) + amount


class ReceiptEvidence:
    def __init__(self, repository):
        self.repository = repository
        self.world_id = repository.world_id
        self.scopes = {_scope(self.world_id, island): island for island in COLONY_IDS}

    def _get(self, tx, collection, identifier, cache):
        if not identifier:
            return None
        key = (collection, identifier)
        if key not in cache:
            cache[key] = tx.get(collection, identifier)
        return cache[key]

    def _provenance(self, tx, row, actor_id, cache):
        origin = row.get('decision_origin')
        if origin in ('deterministic', 'player', 'executor', 'local_executor') and not row.get('decision_id'):
            return {'status': 'verified', 'attribution': 'executor', 'origin': origin,
                    'reason': 'Local executor action; no Gemini decision is claimed.'}
        if origin != 'model' or not row.get('decision_id'):
            return {'status': 'historical' if not row.get('receipt_version') else 'missing',
                    'attribution': 'unattributed', 'origin': origin or 'unknown',
                    'reason': 'This receipt does not establish who selected the action.'}
        decision = self._get(tx, 'colonyDecisions', row['decision_id'], cache)
        if (not decision or decision.get('world_id') != row['world_id'] or decision.get('status') != 'accepted'
                or decision.get('actor_id') != actor_id or decision.get('character_id') != row['character_id']):
            return {'status': 'missing', 'attribution': 'unattributed', 'origin': 'model',
                    'reason': 'The claimed Gemini decision could not be verified for this actor and island.'}
        run = self._get(tx, 'colonyReasoning', decision.get('run_id'), cache)
        session = self._get(tx, 'colonyCouncilSessions', (run or {}).get('session_id'), cache)
        island_id = self.scopes[row['world_id']]
        if (not run or run.get('world_id') != self.world_id or run.get('status') != 'completed'
                or run.get('agent_id') != actor_id or run.get('colony_id') != island_id or not run.get('received_at')
                or (run.get('receipt') or {}).get('id') != decision.get('id')
                or not session or session.get('world_id') != self.world_id or session.get('colony_id') != island_id
                or run.get('id') not in session.get('run_ids', [])
                or actor_id not in {actor.get('id') for actor in session.get('participants', [])}):
            return {'status': 'missing', 'attribution': 'unattributed', 'origin': 'model',
                    'reason': 'An accepted decision exists, but a completed provider turn and council lineage are not verified.'}
        return {'status': 'verified', 'attribution': 'model', 'origin': 'model',
                'reason': 'Gemini selected the action; the local executor committed its effects.',
                'decision_id': decision['id'], 'run_id': run['id'], 'session_id': session['id'],
                'model': run.get('model'), 'action': (decision.get('decision') or {}).get('action')}

    def _receipt(self, tx, row, cache):
        if not _action_receipt(row) or row.get('world_id') not in self.scopes:
            return None
        expected_actor = key_for(row['world_id'], 'island-agent', row['character_id'])
        if row.get('actor_id') and row['actor_id'] != expected_actor:
            return None
        actor = self._get(tx, 'islandAgents', expected_actor, cache)
        if actor and (actor.get('world_id') != row['world_id'] or actor.get('character_id') != row['character_id']):
            actor = None
        historical = not row.get('receipt_version') or row.get('reservation_evidence') == 'legacy_task'
        costs_known = isinstance(row.get('reserved_cost'), dict)
        provenance = self._provenance(tx, row, expected_actor, cache)
        result = {key: row[key] for key in ('receipt_version', 'execution_origin', 'reservation_evidence',
                    'resources_before', 'resources_after', 'resources_before_reservation', 'resources_after_reservation',
                    'project_before', 'project_after', 'source', 'source_snapshot', 'capability_evidence',
                    'resource_net_delta', 'xp_gain', 'sequence', 'description', 'started_at', 'duration_seconds',
                    'agent_before', 'agent_after', 'capability_basis', 'effect_scope', 'effect_note',
                    'decision_run_id', 'decision_evidence', 'action_id') if key in row}
        result.update(id=row.get('id', row['_id']), action=row.get('kind', 'unknown'),
                      at=row['at'], actor_id=expected_actor,
                      actor_name=row.get('actor_name') or (actor or {}).get('display_name') or 'Unknown historical resident',
                      character_id=row['character_id'], island_id=self.scopes[row['world_id']],
                      resource_delta=_numbers(row.get('resource_delta')),
                      resource_cost=_numbers(row.get('reserved_cost')) if costs_known else None,
                      costs_known=costs_known, progress_delta=row.get('progress_delta', 0),
                      project_id=row.get('project_id'), decision_origin=row.get('decision_origin', 'unknown'),
                      decision_id=row.get('decision_id'), provenance_status=provenance['status'],
                      provenance=provenance, status='historical' if historical else 'verified', committed=True)
        return result

    def _result(self, receipts, *, event_id=None, missing_ids=None, expected=False, **related):
        missing_ids = missing_ids or []
        if missing_ids or (expected and not receipts):
            status, reason = 'missing', 'An action receipt was expected, but one or more scoped records are unavailable.'
        elif not receipts:
            status, reason = 'not_applicable', 'This entry records a proposal, provider operation or other event, not a completed action. No action receipt is expected.'
        elif any(row['status'] == 'historical' for row in receipts):
            status, reason = 'historical', 'Committed historical effects are available; full before/after evidence was not recorded at the time.'
        else:
            status, reason = 'verified', 'Resolved committed action receipts in this island. Decision provenance is checked separately for each receipt.'
        return {'event_id': event_id, 'status': status, 'reason': reason, 'receipts': receipts,
                'missing_receipt_ids': missing_ids, **related}

    def receipt_evidence(self, identifier):
        def read(tx):
            receipt = self._receipt(tx, tx.get('islandEvents', identifier), {})
            if receipt is None:
                raise StoreError('Action receipt not found in these islands.', 404, 'receipt_not_found')
            return self._result([receipt])
        return self.repository.read(read)

    def event_evidence(self, identifier):
        def read(tx):
            event = tx.get('agentEvents', identifier)
            if not event or event.get('world_id') != self.world_id:
                raise StoreError('Event not found in this world.', 404, 'event_not_found')
            island = event.get('island_id')
            scope = _scope(self.world_id, island) if island in COLONY_IDS else None
            data = event.get('data') or {}
            ids = [data['receipt_id']] if data.get('receipt_id') else []
            ids.extend(value for value in data.get('receipt_ids', []) if isinstance(value, str))
            board = tx.get('colonyBoard', data['message_id']) if data.get('message_id') else None
            related = {}
            if board and board.get('world_id') == scope and board.get('actor_id') == event.get('actor_id'):
                ids.extend(value for value in board.get('receipt_ids', []) if isinstance(value, str))
                related['board_message'] = {key: board[key] for key in ('id', 'kind', 'origin', 'text', 'interpretation',
                    'receipt_ids', 'project_id', 'request_id', 'commitment_id', 'created_at') if key in board}
            ids = list(dict.fromkeys(ids))[:24]
            receipts, missing, cache = [], [], {}
            for receipt_id in ids:
                raw = tx.get('islandEvents', receipt_id)
                receipt = self._receipt(tx, raw, cache) if raw and raw.get('world_id') == scope else None
                if receipt and receipt['actor_id'] == event.get('actor_id'):
                    receipts.append(receipt)
                else:
                    missing.append(receipt_id)
            return self._result(receipts, event_id=identifier, missing_ids=missing,
                                expected=event.get('kind') == 'task.completed' or (board or {}).get('kind') == 'report', **related)
        return self.repository.read(read)

    def contributions(self, island_id=None, window=60, now=None):
        if island_id is not None and island_id not in COLONY_IDS:
            raise StoreError('Choose Winner Island or Loser Island.', 422, 'invalid_colony')
        minutes = min(1440, max(1, window))
        end = now or datetime.now(timezone.utc)
        start = end - timedelta(minutes=minutes)
        start_iso, end_iso = start.isoformat(), end.isoformat()
        islands = [island_id] if island_id else list(COLONY_IDS)
        def read(tx):
            result, sampled, total, cache = [], False, 0, {}
            for island in islands:
                scope = _scope(self.world_id, island)
                if hasattr(tx, 'database'):
                    rows = list(tx.database.islandEvents.find({'world_id': scope, 'at': {'$gte': start_iso, '$lte': end_iso},
                        'sequence': {'$exists': True}}, session=tx.session).sort('at', -1).limit(PER_ISLAND_RECEIPT_LIMIT + 1))
                else:
                    rows = [row for row in tx.find('islandEvents', {'world_id': scope}, sort='at', limit=10000000)
                            if start_iso <= row['at'] <= end_iso and _action_receipt(row)][:PER_ISLAND_RECEIPT_LIMIT + 1]
                island_sampled = len(rows) > PER_ISLAND_RECEIPT_LIMIT
                sampled |= island_sampled
                actors = {}
                colony = {'id': island, 'actions': 0, 'productive_actions': 0, 'no_gain_actions': 0,
                          'resource_gains': {}, 'resource_costs': {}, 'project_work': 0,
                          'model_actions': 0, 'executor_actions': 0, 'unattributed_actions': 0,
                          'historical_actions': 0, 'costs_complete': True, 'sampled': island_sampled}
                for row in rows[:PER_ISLAND_RECEIPT_LIMIT]:
                    receipt = self._receipt(tx, row, cache)
                    if not receipt:
                        continue
                    actor = actors.setdefault(receipt['actor_id'], {'id': receipt['actor_id'], 'name': receipt['actor_name'],
                        'actions': 0, 'productive_actions': 0, 'no_gain_actions': 0,
                        'resource_gains': {}, 'resource_costs': {}, 'project_work': 0,
                        'model_actions': 0, 'executor_actions': 0, 'unattributed_actions': 0,
                        'historical_actions': 0, 'costs_complete': True,
                        'last_receipt_at': receipt['at'], 'last_receipt_id': receipt['id']})
                    attribution = receipt['provenance']['attribution']
                    # Count a stock/construction contribution only when an actual
                    # committed gain exists. XP, animation and attempted yields
                    # do not make a capped or resting action productive.
                    productive = receipt['progress_delta'] > 0 or any(value > 0 for value in receipt['resource_delta'].values())
                    for target in (actor, colony):
                        target['actions'] += 1
                        target['productive_actions' if productive else 'no_gain_actions'] += 1
                        target[f'{attribution}_actions'] += 1
                        target['historical_actions'] += int(receipt['status'] == 'historical')
                        target['costs_complete'] &= receipt['costs_known']
                        target['project_work'] += receipt['progress_delta']
                        _plus(target['resource_gains'], receipt['resource_delta'])
                        _plus(target['resource_costs'], receipt['resource_cost'] or {})
                    total += 1
                colony['actors'] = sorted(actors.values(), key=lambda item: (-item['actions'], item['id']))
                result.append(colony)
            return {'window_minutes': minutes, 'from': start_iso, 'to': end_iso, 'receipt_count': total,
                    'receipt_sample_limit': PER_ISLAND_RECEIPT_LIMIT * len(islands), 'sampled': sampled,
                    'islands': result, 'persistence': self.repository.persistence,
                    'productivity_basis': 'Positive committed stock gain or construction work. Rest, capped yields and XP-only changes are no-gain actions.',
                    'note': 'Completed action receipts only. Costs were reserved when each task started; completion gains and costs may occur at different times. Proposals and API calls do not count as island contributions. Historical unknown costs are excluded, not treated as zero.'}
        return self.repository.read(read)
