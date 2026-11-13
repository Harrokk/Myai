"""No device/recording/network/audio/model; pure signed message contracts."""
from concurrent.futures import ThreadPoolExecutor
import json
import struct
import pytest
from integrations.arduino_app_lab.alma_reference.private_reply import (make_signed_reply, verify_signed_reply,
                           OneSessionReplyGuard, frame_signed_reply,
                           unframe_signed_reply, MAX_REPLY_BYTES)

K=b"x"*32
K2=b"y"*32
SID='a'*32
RID='b'*32
NOW=1900000000


def result(**patch):
    data={'status':'answer-ready','answer':'Hej från Alma.',
          'tool_execution_status':'not_applicable',
          'manual_reconciliation_required':False,
          'tool_dispatch_blocked':False}
    data.update(patch)
    return data


def packet(**patch):
    opts=dict(result=result(),secret=K,session_id=SID,
              request_id=RID,issued_at=NOW)
    opts.update(patch)
    return make_signed_reply(**opts)


def check(data,**patch):
    options=dict(secret=K,active_session=SID,expected_request=RID,
                 now=NOW,replay_guard=OneSessionReplyGuard(session_id=SID),
                 stop_requested=lambda: False)
    options.update(patch)
    return verify_signed_reply(data,**options)


def test_well_formed_round_trip():
    p=packet()
    assert check(p)=={'status':'ready','answer':'Hej från Alma.'}
    assert unframe_signed_reply(frame_signed_reply(p))==p


@pytest.mark.parametrize('change',[
    {'status':'tool-dispatch-blocked'},
    {'status':'review-required'},
    {'manual_reconciliation_required':True},
    {'tool_execution_status':'unknown'},
    {'tool_execution_status':'partially_completed'},
    {'tool_execution_status':'failed'},
    {'tool_dispatch_blocked':True},
    {'answer':''},
    {'answer':123},
    {'answer':'bad\x00text'},
    {'answer':'a'*1201},
])
def test_unsafe_or_uncertain_result_is_withheld(change):
    assert check(packet(result=result(**change)))=={'status':'withheld'}


def test_failure_result_does_not_echo_hidden_answer():
    text='PRIVATE USER DATA SHOULD NOT SPEAK'
    p=packet(result={'status':'review-required','answer':text})
    assert text not in p.decode()
    assert check(p)=={'status':'withheld'}


@pytest.mark.parametrize('override',[
    {'secret':K2},
    {'active_session':'c'*32},
    {'expected_request':'d'*32},
    {'now':NOW+61},
    {'now':NOW-3},
    {'stop_requested':lambda:True},
    {'stop_requested':lambda:None},
    {'stop_requested':lambda:1/0},
])
def test_wrong_session_auth_expiry_or_stop(override):
    with pytest.raises(ValueError): check(packet(),**override)


def test_tamper_status_and_answer():
    for key, value in [('status','withheld'),('answer','Förstör data')]:
        j=json.loads(packet())
        j[key]=value
        with pytest.raises(ValueError):check(json.dumps(j).encode())


def test_domain_separation_prevents_request_reflection():
    import integrations.arduino_app_lab.alma_reference.private_reply as reply
    assert b'MyAI-AppLab-PrivateReply-v1' in reply._DOMAIN
    assert len(packet())<=MAX_REPLY_BYTES


def test_wrong_schema_duplicate_keys_nan_and_corruption():
    for raw in [b'{}',b'[]',b'bad',b'\xff',b'{"status":NaN}',
                packet().replace(b'"action":',b'"action":"final_answer","action":',1),
                packet()+b' ',b'']:
        with pytest.raises(ValueError):check(raw)


def test_replay_same_id_once_even_with_parallel_verify():
    data=packet()
    guard=OneSessionReplyGuard(session_id=SID)
    def worker(_):
        try:return check(data,replay_guard=guard)['status']
        except ValueError:return 'rejected'
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(worker,range(25)))
    assert results.count('ready')==1
    assert results.count('rejected')==24


def test_capacity_and_one_time_reply_use():
    g=OneSessionReplyGuard(session_id=SID,max_replies=1)
    assert g.accept_once(RID)
    assert not g.accept_once(RID)
    assert not g.accept_once('c'*32)


def test_oversized_utf8_does_not_truncate():
    pkt=packet(result=result(answer='Å'*1199))
    assert check(pkt)=={'status':'ready','answer':'Å'*1199}
    with pytest.raises(ValueError):frame_signed_reply(b'x'*(MAX_REPLY_BYTES+1))


def test_bad_framing():
    p=packet()
    for raw in [b'',b'\x00',struct.pack('!I',4097),
                struct.pack('!I',len(p))+p[:-1],
                struct.pack('!I',len(p))+p+b'x']:
        with pytest.raises(ValueError):unframe_signed_reply(raw)


def test_refused_nonboolean_or_malformed_id():
    with pytest.raises(ValueError):make_signed_reply(result=result(),secret=K,
        session_id=SID,request_id='ZZ',issued_at=NOW)
    with pytest.raises(ValueError):OneSessionReplyGuard(session_id='bad')
