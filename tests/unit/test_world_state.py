import importlib
import pytest
from engine.story import models


def api():
    assert hasattr(models, 'WorldState'), 'Canonical world-state contract is missing'
    return importlib.import_module('engine.story.world_state')


def document(events=(), **initial):
    api()
    return models.NarrativeDocument(project_id='p', initial_world_state={
        'possessions': {'sword': 'hero'}, 'locations': {'hero': 'gate'},
        'approval': {'status': 'APPROVED', 'approved_by': 'creator'},
        'evidence': {'panel_ids': ['p1']}, **initial,
    }, characters=[{'character_id': 'hero', 'display_name': 'Hero'}],
        locations=[{'location_id': 'gate', 'name': 'Gate'}, {'location_id': 'hall', 'name': 'Hall'}],
        observations=[{'panel_id': 'p1', 'sequence_global': 1}], events=list(events))


def event(event_id, before='hero', after=None, **kwargs):
    return {'event_id': event_id, 'panel_ids': ['p1'], 'state_changes': [{
        'domain': 'POSSESSION', 'subject_id': 'sword',
        'before': {'known': True, 'value': before}, 'after': {'known': True, 'value': after},
        'evidence': {'panel_ids': ['p1']},
        'approval': {'status': 'APPROVED', 'approved_by': 'creator'},
    }], **kwargs}


def test_lost_sword_cannot_reappear_without_valid_reacquisition():
    doc = document([event('lose'), event('use', after='hero')])
    original = doc.model_dump_json()
    result = api().replay_world_state(doc)
    assert result.state.possessions['sword'] is None
    assert not result.valid
    assert 'STATE_BEFORE_MISMATCH' in {w.warning_type for w in result.warnings}
    assert doc.model_dump_json() == original


def test_reacquisition_with_matching_before_and_prior_cause_is_valid():
    result = api().replay_world_state(document([event('lose', enables=['find']), event('find', None, 'hero', caused_by=['lose'])]))
    assert result.valid
    assert result.state.possessions == {'sword': 'hero'}
    assert result.applied_event_ids == ['lose', 'find']


@pytest.mark.parametrize('mutation,warning', [
    ({'approval': {'status': 'PENDING'}}, 'UNAPPROVED_STATE_CHANGE'),
    ({'evidence': {}}, 'UNGROUNDED_STATE_CHANGE'),
    ({'after': {'known': False}}, 'UNCERTAIN_STATE_CHANGE'),
])
def test_untrusted_changes_do_not_enter_canonical_state(mutation, warning):
    evt = event('lose')
    evt['state_changes'][0].update(mutation)
    result = api().replay_world_state(document([evt]))
    assert result.state.possessions['sword'] == 'hero'
    assert warning in {w.warning_type for w in result.warnings}
    assert not result.valid


@pytest.mark.parametrize('events,warning', [
    ([event('a', caused_by=['missing'])], 'MISSING_CAUSAL_DEPENDENCY'),
    ([event('a', caused_by=['b']), event('b')], 'FORWARD_CAUSAL_DEPENDENCY'),
    ([event('a'), event('a')], 'DUPLICATE_EVENT_ID'),
    ([event('a', enables=['missing'])], 'MISSING_CAUSAL_DEPENDENCY'),
])
def test_invalid_causal_graph_is_rejected(events, warning):
    result = api().replay_world_state(document(events))
    assert not result.valid
    assert warning in {w.warning_type for w in result.warnings}


def test_unknown_is_distinct_from_explicit_unowned():
    evt = event('find', None, 'hero')
    unknown = api().replay_world_state(document([evt], possessions={}))
    assert not unknown.valid
    evt['state_changes'][0]['before'] = {'known': False}
    discovered = api().replay_world_state(document([evt], possessions={}))
    assert discovered.valid
    assert discovered.state.possessions == {'sword': 'hero'}


def test_location_and_knowledge_changes_are_checked_atomically():
    evt = event('move')
    evt['state_changes'] = [
        {**evt['state_changes'][0], 'domain': 'LOCATION', 'subject_id': 'hero',
         'before': {'known': True, 'value': 'hall'}, 'after': {'known': True, 'value': 'gate'}},
        {**evt['state_changes'][0], 'domain': 'KNOWLEDGE', 'subject_id': 'hero', 'fact_id': 'secret',
         'before': {'known': False}, 'after': {'known': True, 'value': True}},
    ]
    result = api().replay_world_state(document([evt]))
    assert not result.valid
    assert result.state.locations == {'hero': 'gate'}
    assert result.state.knowledge == {}


def test_document_serialization_preserves_state_and_old_documents_work():
    doc = document([event('lose')])
    restored = models.NarrativeDocument.model_validate_json(doc.model_dump_json())
    assert api().replay_world_state(restored).state.possessions == {'sword': None}
    old = models.NarrativeDocument(project_id='old', events=[{'event_id': 'legacy'}])
    assert api().replay_world_state(old).valid


def test_approval_record_is_immutable_and_never_auto_approved():
    api()
    change = models.StateChange.model_validate(event('lose')['state_changes'][0])
    with pytest.raises(ValueError):
        change.approval.status = 'REJECTED'
    pending = models.StateChange(domain='POSSESSION', subject_id='sword', before={'known': False}, after={'known': True, 'value': None})
    assert pending.approval.status == 'PENDING'


def test_continuity_audit_exposes_critical_state_warnings():
    api()
    from engine.story.continuity import ContinuityAuditor
    warnings = ContinuityAuditor().audit(document([event('lose'), event('use', after='hero')]))
    assert any(w.warning_type == 'STATE_BEFORE_MISMATCH' and w.severity == 'ERROR' for w in warnings)

@pytest.mark.parametrize('confidence', [float('nan'), float('inf'), -0.1, 1.1])
def test_invalid_evidence_confidence_cannot_establish_canonical_facts(confidence):
    evt = event('lose')
    evt['state_changes'][0]['evidence']['confidence'] = confidence
    result = api().replay_world_state(document([evt]))
    assert not result.valid
    assert result.state.possessions['sword'] == 'hero'


def test_rejected_cause_blocks_dependents_even_when_only_enables_declares_edge():
    cause = event('lose', enables=['find'])
    cause['state_changes'][0]['approval'] = {'status': 'PENDING'}
    result = api().replay_world_state(document([cause, event('find', 'hero', None)]))
    assert not result.valid
    assert result.applied_event_ids == []
    assert result.state.possessions == {'sword': 'hero'}
    assert 'UNAPPLIED_CAUSAL_DEPENDENCY' in {w.warning_type for w in result.warnings}


def test_unapproved_initial_facts_do_not_seed_replay():
    result = api().replay_world_state(document([event('lose')], approval={'status': 'PENDING'}))
    assert not result.valid
    assert result.state.possessions == {}
    assert result.applied_event_ids == []


def test_successful_location_and_knowledge_changes_preserve_inputs():
    evt = event('enter')
    evt['state_changes'] = [
        {**evt['state_changes'][0], 'domain': 'LOCATION', 'subject_id': 'hero',
         'before': {'known': True, 'value': 'gate'}, 'after': {'known': True, 'value': 'hall'}},
        {**evt['state_changes'][0], 'domain': 'KNOWLEDGE', 'subject_id': 'hero', 'fact_id': 'secret',
         'before': {'known': False}, 'after': {'known': True, 'value': True}},
    ]
    doc = document([evt])
    before = doc.model_dump_json()
    first = api().replay_world_state(doc)
    second = api().replay_world_state(doc)
    assert first.valid
    assert first.state.locations == {'hero': 'hall'}
    assert first.state.knowledge == {'hero': {'secret': True}}
    assert first == second
    assert doc.model_dump_json() == before


def test_knowledge_before_mismatch_does_not_replace_established_fact():
    evt = event('relearn')
    evt['state_changes'] = [{**evt['state_changes'][0], 'domain': 'KNOWLEDGE', 'subject_id': 'hero', 'fact_id': 'secret',
        'before': {'known': True, 'value': False}, 'after': {'known': True, 'value': True}}]
    result = api().replay_world_state(document([evt], knowledge={'hero': {'secret': True}}))
    assert not result.valid
    assert result.state.knowledge == {'hero': {'secret': True}}


@pytest.mark.parametrize('domain,value', [('KNOWLEDGE', 'true'), ('LOCATION', True), ('POSSESSION', 1)])
def test_state_contract_rejects_coerced_or_wrong_domain_facts(domain, value):
    api()
    payload = event('bad')['state_changes'][0]
    payload.update(domain=domain, after={'known': True, 'value': value})
    if domain == 'KNOWLEDGE':
        payload.update(fact_id='secret', before={'known': False})
    with pytest.raises(ValueError):
        models.StateChange.model_validate(payload)


def test_event_panel_claim_cannot_bootstrap_initial_or_changed_facts():
    evt = event('lose', panel_ids=['invented'])
    evt['state_changes'][0]['evidence'] = {'panel_ids': ['invented']}
    doc = document([evt], evidence={'panel_ids': ['invented']})
    doc.observations = []
    result = api().replay_world_state(doc)
    assert not result.valid
    assert result.state.possessions == {}
    doc.initial_world_state = models.WorldState()
    result = api().replay_world_state(doc)
    assert 'UNGROUNDED_STATE_CHANGE' in {w.warning_type for w in result.warnings}
    assert result.applied_event_ids == []


def test_text_evidence_must_match_its_claimed_source_panel():
    doc = document([event('lose')])
    doc.observations.append(models.PanelObservationEntity(panel_id='p2', sequence_global=2))
    doc.utterances = [models.UtteranceEntity(utterance_id='u1', text_region_id='t1', panel_id='p2')]
    doc.events[0].state_changes[0].evidence = models.ProvenanceReference(panel_ids=['p1'], text_region_ids=['t1'])
    result = api().replay_world_state(doc)
    assert not result.valid
    assert result.state.possessions == {'sword': 'hero'}


def test_generated_approvals_are_stripped_without_mutating_candidate():
    doc = document([event('lose')])
    before = doc.model_dump_json()
    prepared = api().prepare_generated_world_state(doc)
    assert prepared.initial_world_state.approval.status == 'PENDING'
    assert prepared.initial_world_state.approval.approved_by is None
    assert prepared.events[0].state_changes[0].approval.status == 'PENDING'
    assert prepared.events[0].state_changes[0].approval.approved_by is None
    assert doc.model_dump_json() == before


def test_unchanged_source_preserves_previous_canonical_facts_and_entire_events():
    previous = document([event('lose')])
    previous.analysis_metadata['source_context_digest'] = 'sha256:same'
    candidate = document([event('invented')])
    candidate.analysis_metadata['source_context_digest'] = 'sha256:same'
    before = candidate.model_dump_json()
    prepared = api().prepare_generated_world_state(candidate, previous)
    assert prepared.events == previous.events
    assert prepared.initial_world_state == previous.initial_world_state
    assert prepared.events is not previous.events
    assert prepared.initial_world_state is not previous.initial_world_state
    assert prepared.events[0].state_changes[0].approval.status == 'APPROVED'
    assert candidate.model_dump_json() == before


@pytest.mark.parametrize('old_digest,new_digest', [('old', 'new'), ('same', None), (None, 'same'), ('', '')])
def test_source_changes_or_missing_digests_block_existing_canonical_replacement(old_digest, new_digest):
    previous = document([event('lose')])
    candidate = document([event('fresh')])
    previous.analysis_metadata['source_context_digest'] = old_digest
    candidate.analysis_metadata['source_context_digest'] = new_digest
    with pytest.raises(ValueError, match='review'):
        api().prepare_generated_world_state(candidate, previous)


def test_legacy_document_without_canonical_facts_does_not_block_generation():
    api()
    previous = models.NarrativeDocument(project_id='p', events=[{'event_id': 'legacy'}])
    candidate = document([event('fresh')])
    prepared = api().prepare_generated_world_state(candidate, previous)
    assert prepared.events[0].event_id == 'fresh'
    assert prepared.events[0].state_changes[0].approval.status == 'PENDING'
