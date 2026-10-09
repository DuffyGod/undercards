"""Exact shared message prefix plus a variable final request, through user API."""
import copy
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def build_payload(api, task):
    base = api.build_payload(task)
    messages = [base['messages'][0]]
    for index, sample in enumerate(task.get('context', {}).get('few_shots', [])):
        messages.append({'role': 'user', 'content': '语义示例，编号不是真实卡牌：\n' + sample['input_effect']})
        annotation = copy.deepcopy(sample['correct_annotation'])
        v6=task.get('context',{}).get('contract_version','').startswith('semantic-v6-')
        annotation.update({'card_id': 900000+index+1 if v6 else -(index+1),
                           'conditions': annotation.get('conditions',[]),
                           'notes': sample.get('common_error_and_correction',annotation.get('notes',''))})
        messages.append({'role': 'assistant', 'content': json.dumps({'annotations': [annotation]}, ensure_ascii=False, sort_keys=True)})
    variable = copy.deepcopy(task)
    variable.get('context', {}).pop('few_shots', None)
    last = api.build_payload(variable)['messages'][-1]
    messages.append(last)
    base['messages'] = messages
    return base


def cache_metrics(usage):
    """Missing Tencent-proxy usage fields mean unknown, not a zero cache hit."""
    usage = usage if isinstance(usage, dict) else {}
    result = {k: usage.get(k) for k in ('prompt_cache_hit_tokens', 'prompt_cache_miss_tokens')}
    details = usage.get('prompt_tokens_details', {})
    result['cached_tokens'] = details.get('cached_tokens') if isinstance(details, dict) else None
    result['reported'] = any(type(v) is int for v in result.values())
    return result


class PreparedClient:
    """Reuse helper parsing/error handling; only replace its message payload."""
    def __init__(self, transport, payload):
        self.transport = transport
        self.payload = payload
        self.raw_usage = {}

    def complete(self, ignored_payload):
        response = self.transport.complete(self.payload)
        self.raw_usage = response.get('usage', {}) if isinstance(response, dict) else {}
        return response
