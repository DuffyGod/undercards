"""腾讯 Token Plan：单任务、顺序流程、并行批处理。仅依赖 Python 3.9+ 标准库。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


DEFAULT_ENDPOINT = "https://tokenhub.tencentmaas.com/plan/v3/chat/completions"
DEFAULT_MODEL = "deepseek/deepseek-flash"
SMOKE_EXPECTED = "腾讯云 Token Plan 调用成功"
PRESETS = {
    "ask": {"description": "通用问答或按指令生成文本", "system": "准确执行用户指定的任务。", "format": "text"},
    "summarize": {"description": "摘要、要点和结论", "system": "根据用户要求总结提供的材料，保留关键事实，不编造材料中没有的信息。", "format": "text"},
    "extract": {"description": "提取字段，默认返回 JSON 对象", "system": "根据用户要求提取提供的材料，返回 JSON 对象；缺失的信息用 null 表示，不猜测。", "format": "json"},
    "review": {"description": "按指定标准检查材料并提出建议", "system": "按用户指定的标准检查材料，指出具体问题、依据和修改建议。", "format": "text"},
}
OPTION_DEFAULTS = {"model": DEFAULT_MODEL, "max_tokens": 2048, "thinking": "disabled", "temperature": None, "response_format": None}
TASK_FIELDS = set(OPTION_DEFAULTS) | {"id", "task", "prompt", "context", "system", "required_keys"}
TEMPLATE = re.compile(r"\$\{([^{}]+)\}")
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")


class TaskError(Exception):
    """可由调用方捕获的错误；details 包含截断内容、用量等诊断信息。"""

    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code = code
        self.details = details

    def to_dict(self):
        return {"code": self.code, "message": str(self), **self.details}


def _require(condition, message):
    if not condition:
        raise TaskError("invalid_config", message)


def _number(value, minimum, maximum=None):
    return (type(value) in (int, float) and math.isfinite(value)
            and value >= minimum and (maximum is None or value <= maximum))


def _object(value, label):
    _require(isinstance(value, dict), f"{label} 必须是 JSON 对象")
    return value


def _defaults(value):
    _object(value, "defaults")
    _require(not (set(value) - set(OPTION_DEFAULTS)), "defaults 包含未知字段")
    return value


def _reject_constant(value):
    raise ValueError(f"JSON 不允许常量：{value}")


def _validate_transport(endpoint, timeout, retries):
    _require(_number(timeout, 0) and timeout > 0, "timeout 必须是大于 0 的有限数字")
    _require(type(retries) is int and 0 <= retries <= 5, "retries 必须是 0 到 5 的整数")
    try:
        parsed = urlsplit(endpoint)
        _require(parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password,
                 "endpoint 必须是无嵌入凭据的 HTTPS URL")
    except (TypeError, ValueError) as exc:
        raise TaskError("invalid_config", "endpoint 必须是 HTTPS URL") from exc


def validate_task(spec, defaults=None):
    """离线验证任务，并返回规范化配置。不会读取密钥或调用 API。"""
    _object(spec, "任务")
    _require(not (set(spec) - TASK_FIELDS), f"任务包含未知字段：{sorted(set(spec) - TASK_FIELDS)}")
    merged = {**OPTION_DEFAULTS, **_defaults({} if defaults is None else defaults), **spec}
    merged.setdefault("task", "ask")
    _require(isinstance(merged["task"], str) and merged["task"] in PRESETS, "task 必须是 ask/summarize/extract/review")
    _require(isinstance(merged.get("prompt"), str) and bool(merged["prompt"].strip()), "prompt 必须是非空字符串")
    _require(isinstance(merged["model"], str) and bool(merged["model"].strip()), "model 必须是非空字符串")
    _require(type(merged["max_tokens"]) is int and merged["max_tokens"] > 0, "max_tokens 必须是正整数")
    _require(merged["thinking"] in ("disabled", "enabled", "omit"), "thinking 必须是 disabled/enabled/omit")
    _require(merged["temperature"] is None or _number(merged["temperature"], 0, 2), "temperature 必须在 0 到 2 之间")
    if merged["response_format"] is None:
        merged["response_format"] = PRESETS[merged["task"]]["format"]
    _require(merged["response_format"] in ("text", "json"), "response_format 必须是 text/json")
    _require("system" not in merged or isinstance(merged["system"], str), "system 必须是字符串")
    _require("id" not in merged or isinstance(merged["id"], str), "id 必须是字符串")
    keys = merged.get("required_keys", [])
    _require(isinstance(keys, list) and all(isinstance(key, str) and key for key in keys), "required_keys 必须是非空字段名的列表")
    _require(not keys or merged["response_format"] == "json", "required_keys 只适用于 JSON 输出")
    _require(not (merged["response_format"] == "json" and merged["thinking"] == "enabled"), "JSON 输出请使用 disabled 或 omit 思考模式")
    try:
        json.dumps(merged.get("context"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TaskError("invalid_config", f"context 必须可序列化为 JSON：{exc}") from exc
    return merged


def build_payload(spec, defaults=None):
    """构建请求，便于固定程序查看和复用；不包含 API 密钥。"""
    task = validate_task(spec, defaults)
    system = PRESETS[task["task"]]["system"]
    if task.get("system"):
        system += "\n" + task["system"]
    if task["response_format"] == "json":
        system += "\n只返回合法 JSON 对象，不要 Markdown 代码块或额外说明。"
        if task.get("required_keys"):
            system += "\n必须包含顶层字段：" + json.dumps(task["required_keys"], ensure_ascii=False)
    user = task["prompt"]
    if "context" in task:
        context = task["context"] if isinstance(task["context"], str) else json.dumps(task["context"], ensure_ascii=False)
        user += "\n\n以下是待处理材料：\n" + context
    payload = {"model": task["model"], "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
               "max_tokens": task["max_tokens"], "stream": False}
    if task["thinking"] != "omit":
        payload["thinking"] = {"type": task["thinking"]}
    if task["temperature"] is not None:
        payload["temperature"] = task["temperature"]
    if task["response_format"] == "json":
        payload["response_format"] = {"type": "json_object"}
    return payload


class TencentClient:
    """HTTP 客户端。密钥优先级：显式 api_key > 显式 key_file > 环境变量 > 同目录文件。"""

    def __init__(self, api_key=None, key_file=None, endpoint=DEFAULT_ENDPOINT, timeout=90, retries=2):
        _validate_transport(endpoint, timeout, retries)
        if api_key is None:
            api_key = os.environ.get("TENCENT_API_KEY") if key_file is None else None
            if not api_key:
                path = Path(key_file) if key_file is not None else Path(__file__).resolve().parent / "tencent-api-key"
                try:
                    api_key = path.read_text(encoding="utf-8-sig")
                except OSError as exc:
                    raise TaskError("credential_error", f"无法读取密钥文件：{exc}") from exc
        if not isinstance(api_key, str) or not api_key.strip():
            raise TaskError("credential_error", "API 密钥为空")
        self._key = api_key.strip()
        self.endpoint = endpoint
        self.timeout = timeout
        self.retries = retries

    def redact(self, value):
        return str(value).replace(self._key, "[REDACTED]")

    def complete(self, payload):
        """只重试 429 和部分 5xx；超时不自动重试，避免重复请求。"""
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        for attempt in range(self.retries + 1):
            request = Request(self.endpoint, data=body, headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}, method="POST")
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    result = json.load(response)
                if not isinstance(result, dict):
                    raise TaskError("invalid_response", "API 响应不是 JSON 对象")
                return result
            except HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    delay = min(2 ** attempt, 30)
                    try:
                        delay = min(max(float(exc.headers.get("Retry-After", delay)), 0), 30)
                    except (TypeError, ValueError, AttributeError):
                        pass
                    exc.close()
                    time.sleep(delay)
                    continue
                try:
                    detail = self.redact(exc.read().decode("utf-8", errors="replace"))[:2000]
                finally:
                    exc.close()
                raise TaskError("http_error", f"HTTP {exc.code}：{detail}", http_status=exc.code) from exc
            except (TimeoutError, URLError, OSError) as exc:
                raise TaskError("network_error", self.redact(exc)) from exc
            except (ValueError, UnicodeError) as exc:
                raise TaskError("invalid_response", self.redact(exc)) from exc


def _usage(value):
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if type(value.get(key)) is int and value[key] >= 0}


def _total_usage(records):
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for record in records:
        for key, value in _usage(record.get("usage")).items():
            total[key] += value
    return total


def run_task(client, spec, defaults=None):
    """成功返回结果 dict；失败抛出 TaskError，不把空回复或截断视为成功。"""
    task = validate_task(spec, defaults)
    started = time.monotonic()
    raw = client.complete(build_payload(task))
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise TaskError("invalid_response", "响应缺少有效 choices", usage=_usage(raw.get("usage")))
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise TaskError("invalid_response", "响应缺少有效 message", usage=_usage(raw.get("usage")))
    content = message.get("content")
    finish = choice.get("finish_reason")
    details = {"finish_reason": finish, "usage": _usage(raw.get("usage"))}
    if finish != "stop":
        code = "truncated" if finish == "length" else "incomplete_response"
        raise TaskError(code, f"模型未完整完成任务：finish_reason={finish}", partial_content=content, **details)
    if not isinstance(content, str) or not content.strip():
        raise TaskError("empty_response", "模型返回空回复", **details)
    result = {"id": task.get("id"), "task": task["task"], "model": raw.get("model", task["model"]),
              "content": content, "finish_reason": finish, "usage": details["usage"],
              "elapsed_seconds": round(time.monotonic() - started, 3)}
    if task["response_format"] == "json":
        try:
            data = json.loads(content, parse_constant=_reject_constant)
        except ValueError as exc:
            raise TaskError("invalid_json", "模型输出不是合法 JSON", partial_content=content, **details) from exc
        if not isinstance(data, dict):
            raise TaskError("invalid_json", "JSON 输出必须是对象", partial_content=content, **details)
        missing = [key for key in task.get("required_keys", []) if key not in data]
        if missing:
            raise TaskError("missing_keys", f"JSON 缺少字段：{missing}", partial_content=content, **details)
        result["data"] = data
    return result


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def validate_workflow(config, overrides=None):
    """验证完整流程和前向引用，在发出首个请求前发现配置错误。"""
    _object(config, "流程")
    _require(not (set(config) - {"input", "defaults", "steps"}), "流程包含未知字段")
    defaults = {**_defaults(config.get("defaults", {})), **_defaults({} if overrides is None else overrides)}
    steps = config.get("steps")
    _require(isinstance(steps, list) and bool(steps), "steps 必须是非空列表")
    known = set()
    normalized = []
    for step in steps:
        task = validate_task(step, defaults)
        name = task.get("id")
        _require(isinstance(name, str) and bool(IDENTIFIER.fullmatch(name)), "步骤 id 必须是以字母/下划线开头的字母、数字、下划线或连字符")
        _require(name not in known, f"步骤 id 重复：{name}")
        for value in (task["prompt"], task.get("context"), task.get("system")):
            for text in _strings(value):
                _require("${" not in TEMPLATE.sub("", text), f"步骤 {name} 包含未闭合的模板变量")
                for reference in TEMPLATE.findall(text):
                    parts = reference.split(".")
                    _require(all(parts), f"模板路径无效：{reference}")
                    valid = parts[0] == "input" or (len(parts) >= 3 and parts[0] == "steps" and parts[1] in known and parts[2] in ("content", "data"))
                    _require(valid, f"步骤 {name} 引用了未知或尚未完成的变量：{reference}")
        known.add(name)
        normalized.append(task)
    return normalized


def _resolve(reference, state):
    value = state
    try:
        for part in reference.split("."):
            if isinstance(value, dict):
                value = value[part]
            elif isinstance(value, list) and part.isdigit():
                value = value[int(part)]
            else:
                raise KeyError(part)
    except (KeyError, IndexError) as exc:
        raise TaskError("template_error", f"变量不存在：{reference}") from exc
    return value


def _render(value, state):
    if isinstance(value, str):
        match = TEMPLATE.fullmatch(value)
        if match:
            return _resolve(match.group(1), state)
        def replace(match):
            resolved = _resolve(match.group(1), state)
            return resolved if isinstance(resolved, str) else json.dumps(resolved, ensure_ascii=False)
        return TEMPLATE.sub(replace, value)
    if isinstance(value, list):
        return [_render(item, state) for item in value]
    if isinstance(value, dict):
        return {key: _render(item, state) for key, item in value.items()}
    return value


def run_workflow(client, config, overrides=None):
    """顺序执行；每步独立上下文；失败即停止并保留已完成步骤。"""
    steps = validate_workflow(config, overrides)
    state = {"input": config.get("input", ""), "steps": {}}
    records = []
    for step in steps:
        try:
            rendered = dict(step)
            for field in ("prompt", "context", "system"):
                if field in rendered:
                    rendered[field] = _render(rendered[field], state)
                    if field != "context" and not isinstance(rendered[field], str):
                        rendered[field] = json.dumps(rendered[field], ensure_ascii=False)
            result = run_task(client, rendered)
        except TaskError as exc:
            failure = {"id": step["id"], "ok": False, "error": exc.to_dict(), "usage": _usage(exc.details.get("usage"))}
            records.append(failure)
            return {"ok": False, "failed_step": step["id"], "steps": records, "usage": _total_usage(records)}
        state["steps"][step["id"]] = result
        records.append({"ok": True, **result})
    return {"ok": True, "steps": records, "output": records[-1].get("data", records[-1]["content"]), "usage": _total_usage(records)}


def validate_batch(config, overrides=None):
    _object(config, "批处理")
    _require(not (set(config) - {"defaults", "tasks"}), "批处理包含未知字段")
    defaults = {**_defaults(config.get("defaults", {})), **_defaults({} if overrides is None else overrides)}
    tasks = config.get("tasks")
    _require(isinstance(tasks, list) and bool(tasks), "tasks 必须是非空列表")
    normalized = [validate_task(task, defaults) for task in tasks]
    names = [task["id"] for task in normalized if "id" in task]
    _require(len(names) == len(set(names)), "批处理任务 id 不能重复")
    return normalized


def run_batch(client, config, workers=2, overrides=None):
    """并行处理独立任务，按输入顺序返回结果；某任务失败不取消其他任务。"""
    _require(type(workers) is int and 1 <= workers <= 16, "workers 必须是 1 到 16 的整数")
    tasks = validate_batch(config, overrides)
    def execute(task):
        try:
            return {"ok": True, **run_task(client, task)}
        except TaskError as exc:
            return {"ok": False, "id": task.get("id"), "error": exc.to_dict(), "usage": _usage(exc.details.get("usage"))}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(execute, tasks))
    return {"ok": all(result["ok"] for result in results), "results": results, "usage": _total_usage(results)}


def _read_text(path):
    return sys.stdin.read() if str(path) == "-" else Path(path).read_text(encoding="utf-8-sig")


def _read_json(path):
    return json.loads(_read_text(path), parse_constant=_reject_constant)


def _write_report(report, output=None, text=False, client=None):
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if text and report.get("ok"):
        rendered = report["result"]["content"]
    if client is not None:
        rendered = client.redact(rendered)
    if output is None:
        print(rendered)
    else:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
                temporary = handle.name
                handle.write(rendered + "\n")
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)


def _parser():
    parser = argparse.ArgumentParser(description=__doc__, epilog="无参数显示帮助；features 查看任务预设。所有结果默认输出 JSON；退出码：0 成功，1 执行失败，2 配置/参数错误。")
    commands = parser.add_subparsers(dest="command", title="功能")
    commands.add_parser("features", help="离线查看功能、预设和默认参数")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--key-file", type=Path, help="密钥文件；默认 TENCENT_API_KEY 环境变量或脚本同目录 tencent-api-key")
    common.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="完整 chat/completions HTTPS 地址")
    common.add_argument("--timeout", type=float, default=90, help="每次 HTTP 请求超时秒数（默认 90）")
    common.add_argument("--retries", type=int, default=2, help="429/部分 5xx 的额外重试次数，0..5（默认 2）")
    common.add_argument("--model", help=f"模型 ID（默认 {DEFAULT_MODEL}）")
    common.add_argument("--max-tokens", type=int, help="推理与回答共享的输出 token 上限（默认 2048）")
    common.add_argument("--thinking", choices=["disabled", "enabled", "omit"], help="思考开关；默认 disabled，omit 不发送该参数")
    common.add_argument("--temperature", type=float, help="0..2；默认使用服务端设置")
    common.add_argument("--format", dest="response_format", choices=["text", "json"], help="模型结果格式；extract 默认 json，其余 text")
    common.add_argument("--output", type=Path, help="将结果写入 UTF-8 文件，代替 stdout")
    common.add_argument("--dry-run", action="store_true", help="离线检查配置，不读取密钥、不调用 API")
    smoke = commands.add_parser("smoke", parents=[common], help="验证接口及预期回复")
    smoke.add_argument("--text", action="store_true", help="成功时仅输出回复文本")
    run = commands.add_parser("run", parents=[common], help="执行一个文本或 JSON 任务")
    run.add_argument("--task", choices=list(PRESETS), help="任务预设（默认 ask）")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt", help="任务指令")
    source.add_argument("--input-file", help="指令文本文件；- 表示从 stdin 读取")
    source.add_argument("--request-file", help="完整任务 JSON 文件；- 表示从 stdin 读取")
    run.add_argument("--context-file", help="待处理材料文本文件")
    run.add_argument("--system", help="附加系统指令")
    run.add_argument("--required-keys", nargs="+", help="JSON 结果必须包含的顶层字段")
    run.add_argument("--text", action="store_true", help="成功时仅输出回复文本")
    for name, description in (("workflow", "从 JSON 配置顺序执行流程"), ("batch", "从 JSON 配置并发执行独立任务")):
        sub = commands.add_parser(name, parents=[common], help=description)
        sub.add_argument("--file", required=True, help="配置 JSON 文件；- 表示从 stdin 读取")
        if name == "batch":
            sub.add_argument("--workers", type=int, default=2, help="并发数 1..16（默认 2）")
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    if not argv:
        parser.print_help()
        return 0
    # 保留旧脚本的 --model / --key-file / --prompt / --timeout 调用入口。
    if argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        argv.insert(0, "run" if "--prompt" in argv or any(arg.startswith("--prompt=") for arg in argv) else "smoke")
    args = parser.parse_args(argv)
    client = None
    try:
        if args.command == "features":
            _write_report({"ok": True, "commands": ["smoke", "run", "workflow", "batch", "features"],
                           "tasks": {name: {"description": preset["description"], "default_format": preset["format"]} for name, preset in PRESETS.items()},
                           "defaults": OPTION_DEFAULTS, "task_fields": sorted(TASK_FIELDS)})
            return 0
        overrides = {key: getattr(args, key) for key in OPTION_DEFAULTS if getattr(args, key) is not None}
        # 传输参数也在 dry-run 中检查；密钥在实际调用前才读取。
        _validate_transport(args.endpoint, args.timeout, args.retries)
        if args.command == "smoke":
            spec = validate_task({"task": "ask", "prompt": "请只回复：" + SMOKE_EXPECTED, **overrides})
            _require(spec["response_format"] == "text", "smoke 只支持 text 输出格式")
        elif args.command == "run":
            if args.request_file:
                spec = _object(_read_json(args.request_file), "任务")
            else:
                spec = {"prompt": args.prompt if args.prompt is not None else _read_text(args.input_file)}
            spec = {**spec, **overrides}
            for field in ("task", "system", "required_keys"):
                if getattr(args, field) is not None:
                    spec[field] = getattr(args, field)
            if args.context_file:
                _require(str(args.context_file) != "-" or args.input_file != "-" and args.request_file != "-", "stdin 只能被读取一次")
                spec["context"] = _read_text(args.context_file)
            spec = validate_task(spec)
        else:
            config = _read_json(args.file)
            if args.command == "workflow":
                planned = validate_workflow(config, overrides)
            else:
                _require(1 <= args.workers <= 16, "workers 必须在 1 到 16 之间")
                planned = validate_batch(config, overrides)
        if args.dry_run:
            report = {"ok": True, "dry_run": True, "command": args.command}
            if args.command in ("smoke", "run"):
                report["request"] = build_payload(spec)
            else:
                report["tasks"] = planned
            _write_report(report, args.output)
            return 0
        client = TencentClient(key_file=args.key_file, endpoint=args.endpoint, timeout=args.timeout, retries=args.retries)
        if args.command in ("smoke", "run"):
            result = run_task(client, spec)
            if args.command == "smoke" and result["content"].strip() != SMOKE_EXPECTED:
                raise TaskError("unexpected_reply", "连通性测试回复与预期不一致", partial_content=result["content"], usage=result["usage"])
            report = {"ok": True, "command": args.command, "result": result}
        elif args.command == "workflow":
            report = {"command": args.command, **run_workflow(client, config, overrides)}
        else:
            report = {"command": args.command, **run_batch(client, config, args.workers, overrides)}
        _write_report(report, args.output, getattr(args, "text", False), client)
        return 0 if report["ok"] else 1
    except TaskError as exc:
        _write_report({"ok": False, "error": exc.to_dict()}, client=client)
        return 2 if exc.code == "invalid_config" else 1
    except (OSError, ValueError, UnicodeError) as exc:
        _write_report({"ok": False, "error": {"code": "io_or_config_error", "message": str(exc)}}, client=client)
        return 2


if __name__ == "__main__":
    sys.exit(main())
