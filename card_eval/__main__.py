"""Installable card-eval command line."""
from pathlib import Path
from dataclasses import asdict
import argparse, json, sys
from . import __version__
from .api import evaluate, validate, default_request
from .catalog import resolve, snapshot, coverage, InputError
from .report import markdown, LABELS


def main(argv=None):
    parser = argparse.ArgumentParser(prog='card-eval', description='按完整牌组和声明对手评估卡牌替换；未知机制明确拒绝评分。')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    assess = commands.add_parser('assess', help='使用声明的完整基准牌表比较候选')
    assess.add_argument('cards', nargs='+'); assess.add_argument('--reference', default='Rock Pet')
    assess.add_argument('--copies', type=int, default=1); assess.add_argument('--samples', type=int, default=32)
    assess.add_argument('--output', required=True, type=Path); assess.add_argument('--checkpoint', type=Path)
    assess.add_argument('--policies', nargs='+', choices=['learned', 'race', 'board', 'guard'])
    assess.add_argument('--experimental-model', action='store_true', help='显式启用未通过验证的模型，仅作诊断')
    evaluate_cmd = commands.add_parser('evaluate', help='读取用户自己的25张牌表与对手JSON')
    evaluate_cmd.add_argument('--input', required=True, type=Path); evaluate_cmd.add_argument('--output', required=True, type=Path)
    evaluate_cmd.add_argument('--checkpoint', type=Path)
    evaluate_cmd.add_argument('--experimental-model', action='store_true')
    check = commands.add_parser('check', help='只检查牌表、规则覆盖和替换合法性'); check.add_argument('--input', required=True, type=Path)
    inspect = commands.add_parser('inspect', help='查看卡牌是否完整支持'); inspect.add_argument('card')
    listing = commands.add_parser('catalog', help='列出完整支持与拒绝原因'); listing.add_argument('--output', type=Path)
    commands.add_parser('models', help='列出随包模型、验证状态与适用范围')
    example_cmd = commands.add_parser('example', help='生成可编辑的完整牌表请求')
    example_cmd.add_argument('--output', required=True, type=Path)
    example_cmd.add_argument('--learned', action='store_true', help='生成学习策略请求；运行时仍需显式实验模式')
    for command in (assess, evaluate_cmd):
        selection = command.add_mutually_exclusive_group()
        selection.add_argument('--model', help='选择随包训练模型；用 models 查看名称和验证状态')
        command.add_argument('--planner',choices=['proof','value'],help='实验性公开同回合搜索：确杀证明或学习价值')
        command.add_argument('--planner-margin',type=float,default=.1,help='价值搜索偏离基线的概率差门槛，默认.1')
    args = parser.parse_args(argv)
    try:
        if args.command == 'models':
            from .model_registry import catalog
            print(json.dumps(dict(models=catalog()),ensure_ascii=False,indent=2));return 0
        if args.command == 'example':
            from .model_registry import example
            if args.output.exists(): raise ValueError('Output exists; preserve it and choose a new path')
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(example(args.learned),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(str(args.output));return 0
        if args.command == 'catalog':
            data = coverage()
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(dict(supported=len(data['supported']), unsupported=len(data['unsupported']),
                                  names=[s['name'] for s in data['supported']], snapshot_date=data['snapshot_date']), ensure_ascii=False)); return 0
        if args.command == 'inspect':
            query = int(args.card) if args.card.isdecimal() else args.card
            try: data = dict(status='supported', card=asdict(resolve(query)))
            except ValueError as exc: data = dict(status='unsupported', card=args.card, score=None, reason=str(exc))
            print(json.dumps(data, ensure_ascii=False, indent=2)); return 0 if data['status'] == 'supported' else 2
        if args.command == 'assess':
            request = default_request(args.cards, args.reference, args.copies, args.samples)
            if args.policies: request['policies'] = args.policies
        else: request = json.loads(args.input.read_text(encoding='utf-8'))
        if args.command == 'check':
            plan = validate(request)
            print(json.dumps(dict(status='valid' if not plan['blocked'] else 'partially_supported',
                candidates=[c['spec'].name for c in plan['candidates']], blocked=plan['blocked'],
                opponents=[o['name'] for o in plan['opponents']]), ensure_ascii=False, indent=2)); return 0 if not plan['blocked'] else 2
        if args.experimental_model:
            request['allow_unqualified_policy'] = True
            request.setdefault('policies', ['learned'] if args.model else ['learned', 'race', 'board', 'guard'])
        if args.planner:
            request['planner']=dict(mode=args.planner,margin=args.planner_margin)
            request.setdefault('policies',['learned'])
        checkpoint = args.checkpoint
        if args.model:
            if checkpoint: raise ValueError('Choose either --model or --checkpoint')
            from .model_registry import checkpoint as bundled_checkpoint
            checkpoint = bundled_checkpoint(args.model)
            request.setdefault('policies', ['learned'])
        result = evaluate(request, args.output, checkpoint,
                          progress=lambda row: print(json.dumps(row, ensure_ascii=False), file=sys.stderr, flush=True))
        (args.output / 'report.md').write_text(markdown(result), encoding='utf-8')
        for card in result.get('comparisons', []): print(card['card'] + '：' + LABELS[card['recommendation']])
        print('报告：' + str(args.output / 'report.md'))
        return 0 if result['status'] == 'complete' else 2
    except (InputError, ValueError, FileNotFoundError) as exc:
        payload = dict(status='invalid_or_unavailable', issues=exc.issues) if isinstance(exc, InputError) else dict(status='invalid_or_unavailable', message=str(exc))
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr); return 2


if __name__ == '__main__': raise SystemExit(main())
