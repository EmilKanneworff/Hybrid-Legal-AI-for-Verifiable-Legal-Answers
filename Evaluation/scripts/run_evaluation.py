#!/usr/bin/env python3
"""Run the XSU legal-answer testcases against configured providers.

Only an explicit mode-specific allowlist crosses the model boundary. The
hidden ``reference`` object remains available to later manual scoring, but this
module never reads it while constructing provider requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import certifi


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_TESTCASES = REPO_ROOT / "Evaluation" / "benchmark" / "testcases_su_guidance_qa_v5.jsonl"
BENCHMARK_ID = "XSU-GUIDANCE-QA-V5"
MODEL_INPUT_FIELDS = ("instruction", "question", "source_title", "source_passages")
SOURCE_PASSAGE_FIELDS = ("section_no", "source_lines", "text", "citation_label")
INPUT_MODES = ("closed_book", "self_retrieval", "gold_context")
PROMPT_DIR = REPO_ROOT / "Evaluation" / "prompts"
# Plain prompts (2026-11-04): the model gets only the question, or the source
# text and the question. No instructions about format, sources or caution.
# The earlier structured prompts remain in prompts/ for the archived runs.
PROMPT_FILES = {
    "closed_book": PROMPT_DIR / "plain_question_v1.txt",
    "self_retrieval": PROMPT_DIR / "plain_question_v1.txt",
    "gold_context": PROMPT_DIR / "plain_source_question_v1.txt",
}
TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())
FORBIDDEN_MODEL_KEYS = {
    "reference",
    "determination_ids",
    "determinations",
    "reference_file",
    "reference_sha256",
    "source_file",
    "source_sha256",
    "source_document",
    "source_url",
    "source_status",
    "source_status_checked_date",
    "xhaile_source_file",
    "xhaile_source_sha256",
    "xhaile_source_document",
    "prompt_file",
    "prompt_sha256",
    "legal_authority_file",
    "legal_authority_sha256",
    "legal_authorities",
    "expert_criteria_file",
    "expert_criteria_sha256",
    "expert_criteria",
    "reference_answer_danish",
    "evaluation_criteria",
    "derivation_status",
    "validation_status",
    "notes",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def utc_run_id(system_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in system_id)
    return f"{stamp}_{safe}"


def _find_forbidden_keys(value: Any, path: str = "model_input") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_MODEL_KEYS:
                found.append(child_path)
            found.extend(_find_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_forbidden_keys(child, f"{path}[{index}]"))
    return found


def get_model_input(case: dict[str, Any]) -> dict[str, Any]:
    """Return the validated source testcase input before mode filtering."""
    model_input = case.get("model_input")
    if not isinstance(model_input, dict):
        raise ValueError(f"{case.get('case_id', '<unknown>')}: missing model_input object")

    keys = set(model_input)
    expected_keys = set(MODEL_INPUT_FIELDS)
    if keys != expected_keys:
        missing = sorted(expected_keys - keys)
        unexpected = sorted(keys - expected_keys)
        raise ValueError(f"Invalid model_input keys; missing={missing}, unexpected={unexpected}")

    passages = model_input.get("source_passages")
    if not isinstance(passages, list) or not passages:
        raise ValueError("model_input.source_passages must be a non-empty list")

    safe_passages: list[dict[str, str]] = []
    for index, passage in enumerate(passages):
        if not isinstance(passage, dict) or set(passage) != set(SOURCE_PASSAGE_FIELDS):
            raise ValueError(f"Invalid source passage at index {index}")
        safe_passages.append({key: str(passage[key]) for key in SOURCE_PASSAGE_FIELDS})

    safe_input: dict[str, Any] = {
        "instruction": str(model_input["instruction"]),
        "question": str(model_input["question"]),
        "source_title": str(model_input["source_title"]),
        "source_passages": safe_passages,
    }
    forbidden = _find_forbidden_keys(safe_input)
    if forbidden:
        raise ValueError(f"Forbidden reference keys in model_input: {', '.join(forbidden)}")
    return safe_input


def get_input_mode(system: dict[str, Any]) -> str:
    mode = str(system.get("input_mode", "")).strip()
    if not mode:
        raise ValueError(
            "System configuration must explicitly select input_mode: "
            "closed_book, self_retrieval or gold_context."
        )
    if mode not in INPUT_MODES:
        raise ValueError(f"Unsupported input mode: {mode}")
    return mode


def validate_system_config(system: dict[str, Any]) -> None:
    """Reject ambiguous configurations before any provider request is made."""
    if not isinstance(system, dict):
        raise ValueError("System configuration must be a JSON object.")

    system_id = str(system.get("system_id", "")).strip()
    if not system_id:
        raise ValueError("System configuration requires a non-empty system_id.")

    adapter = str(system.get("adapter", "")).strip()
    if adapter not in ADAPTERS:
        raise ValueError(f"Unsupported adapter: {adapter or '<missing>'}")

    input_mode = get_input_mode(system)
    model_adapters = {
        "openai_responses",
        "openai_chat_completions",
        "anthropic_messages",
    }
    endpoint_adapters = {"generic_http_json", "rag_http_json"}

    if adapter in model_adapters:
        model = str(system.get("model", "")).strip()
        if not model or model.startswith("replace-with-"):
            raise ValueError(f"{adapter} requires an exact, non-placeholder model ID.")
    if adapter in endpoint_adapters:
        if not str(system.get("endpoint", "")).strip():
            raise ValueError(f"{adapter} requires an endpoint.")
        if not str(system.get("system_version", "")).strip():
            raise ValueError(
                f"{adapter} requires system_version so the evaluated build is identifiable."
            )

    if input_mode == "self_retrieval":
        if adapter not in endpoint_adapters:
            raise ValueError(
                "self_retrieval requires generic_http_json or rag_http_json so retrieval "
                "can be executed and logged."
            )
        corpus_id = str(system.get("corpus_id", "")).strip()
        corpus_sha256 = str(system.get("corpus_sha256", "")).strip()
        if not corpus_id:
            raise ValueError("self_retrieval requires a non-empty corpus_id.")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", corpus_sha256):
            raise ValueError("self_retrieval requires a 64-character corpus_sha256.")

    for field in ("max_tokens", "timeout_seconds"):
        if field in system and int(system[field]) <= 0:
            raise ValueError(f"{field} must be greater than zero.")


def validate_testcases_for_run(testcases: list[dict[str, Any]]) -> None:
    """Verify benchmark identity and case uniqueness before a run starts."""
    if not testcases:
        raise ValueError("No testcases supplied.")
    case_ids: list[str] = []
    for case in testcases:
        case_id = str(case.get("case_id", "")).strip()
        if not case_id:
            raise ValueError("Every testcase requires a non-empty case_id.")
        if case.get("benchmark_id") != BENCHMARK_ID:
            raise ValueError(
                f"{case_id}: expected benchmark_id {BENCHMARK_ID}, "
                f"got {case.get('benchmark_id')!r}."
            )
        get_model_input(case)
        case_ids.append(case_id)
    duplicates = sorted(case_id for case_id in set(case_ids) if case_ids.count(case_id) > 1)
    if duplicates:
        raise ValueError(f"Duplicate testcase IDs: {', '.join(duplicates)}")


def get_visible_model_input(
    case: dict[str, Any], input_mode: str
) -> dict[str, Any]:
    """Return only fields permitted to cross the provider boundary."""
    model_input = get_model_input(case)
    if input_mode not in INPUT_MODES:
        raise ValueError(f"Unsupported input mode: {input_mode}")
    if input_mode in {"closed_book", "self_retrieval"}:
        return {"question": model_input["question"]}
    return {
        "question": model_input["question"],
        "source_title": model_input["source_title"],
        "source_passages": model_input["source_passages"],
    }


def format_sources(visible_input: dict[str, Any]) -> str:
    """Source title and passages as plain text, in the order given."""
    parts = [str(visible_input.get("source_title", "")).strip()]
    for passage in visible_input.get("source_passages", []):
        parts.append(f"{passage.get('citation_label', '')}\n{passage.get('text', '')}".strip())
    return "\n\n".join(part for part in parts if part)


def build_prompt(case: dict[str, Any], input_mode: str) -> str:
    visible_input = get_visible_model_input(case, input_mode)
    prompt_file = PROMPT_FILES[input_mode]
    template = prompt_file.read_text(encoding="utf-8").strip()
    if "{{QUESTION}}" in template:
        return (
            template.replace("{{SOURCES}}", format_sources(visible_input))
            .replace("{{QUESTION}}", str(visible_input["question"]))
            .strip()
        )
    return (
        f"{template}\n\nMODEL_INPUT:\n"
        f"{json.dumps(visible_input, ensure_ascii=False, indent=2)}\n"
    )


def format_http_error(status: int, raw: str, fallback: str) -> str:
    """Return the provider's useful JSON error message when one is available."""
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        body = None

    if isinstance(body, dict):
        provider_error = body.get("error")
        if isinstance(provider_error, dict) and provider_error.get("message"):
            return f"HTTP {status}: {provider_error['message']}"
        if isinstance(provider_error, str) and provider_error.strip():
            return f"HTTP {status}: {provider_error.strip()}"
        if isinstance(body.get("message"), str) and body["message"].strip():
            return f"HTTP {status}: {body['message'].strip()}"
    return fallback


def request_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=TLS_CONTEXT) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                return {
                    "ok": False,
                    "status": response.status,
                    "raw": raw,
                    "error": f"Provider returned invalid JSON: {exc}",
                }
            return {"ok": True, "status": response.status, "raw": raw, "json": parsed}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": exc.code,
            "raw": raw,
            "error": format_http_error(exc.code, raw, str(exc)),
        }
    except Exception as exc:  # noqa: BLE001 - preserve external-call failures.
        return {"ok": False, "status": None, "raw": "", "error": repr(exc)}


def list_available_models(
    adapter: str,
    api_key: str = "",
    base_url: str = "",
    timeout: int = 20,
) -> list[str]:
    """Return model IDs exposed by a supported provider or compatible endpoint."""
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero.")

    normalized_key = validate_api_key(api_key)
    if adapter == "openai_responses":
        if not normalized_key:
            raise ValueError("Enter an OpenAI API key before loading models.")
        endpoint = f"{(base_url or 'https://api.openai.com/v1').rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {normalized_key}"}
    elif adapter == "anthropic_messages":
        if not normalized_key:
            raise ValueError("Enter an Anthropic API key before loading models.")
        endpoint = (
            f"{(base_url or 'https://api.anthropic.com').rstrip('/')}/v1/models"
            "?limit=1000"
        )
        headers = {
            "x-api-key": normalized_key,
            "anthropic-version": "2023-06-01",
        }
    elif adapter == "openai_chat_completions":
        if not base_url.strip():
            raise ValueError("Enter the UCloud model's base URL before loading models.")
        endpoint = f"{base_url.rstrip('/')}/models"
        headers = {}
        if normalized_key:
            headers["Authorization"] = f"Bearer {normalized_key}"
    else:
        raise ValueError(f"Model discovery is not supported for adapter: {adapter}")

    request = urllib.request.Request(url=endpoint, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=TLS_CONTEXT) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(format_http_error(exc.code, raw, str(exc))) from exc
    except Exception as exc:  # noqa: BLE001 - preserve external-call failures.
        raise RuntimeError(f"Could not load models: {exc}") from exc

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model endpoint returned invalid JSON: {exc}") from exc

    records = body.get("data") if isinstance(body, dict) else None
    if not isinstance(records, list):
        raise RuntimeError("Model endpoint response did not contain a data list.")

    model_ids: list[str] = []
    seen: set[str] = set()
    for record in records:
        model_id = str(record.get("id", "")).strip() if isinstance(record, dict) else ""
        if model_id and model_id not in seen:
            seen.add(model_id)
            model_ids.append(model_id)
    if not model_ids:
        raise RuntimeError("The endpoint returned no model IDs available to this account.")
    return model_ids


def validate_api_key(value: str) -> str:
    key = value.strip()
    if not key:
        return ""
    if len(key) > 4096 or not key.isascii() or any(character.isspace() for character in key):
        raise ValueError("Invalid API key. Paste only the key, without spaces or surrounding text.")
    if any(ord(character) < 33 or ord(character) > 126 for character in key):
        raise ValueError("Invalid API key. Paste only the key, without spaces or surrounding text.")
    return key


def resolve_api_key(system: dict[str, Any]) -> str:
    runtime_key = str(system.get("_api_key", "")).strip()
    if runtime_key:
        return validate_api_key(runtime_key)
    env_name = str(system.get("api_key_env", "")).strip()
    return validate_api_key(os.getenv(env_name, "")) if env_name else ""


def require_api_key(system: dict[str, Any]) -> str:
    key = resolve_api_key(system)
    if key:
        return key
    env_name = system.get("api_key_env", "provider API key")
    raise RuntimeError(f"Missing API key: {env_name}")


def call_dry_run(system: dict[str, Any], case: dict[str, Any], prompt: str) -> dict[str, Any]:
    return {
        "adapter": "dry_run",
        "content": json.dumps({"legal_claims": []}, ensure_ascii=False),
        "raw_response": {
            "system_id": system["system_id"],
            "case_id": case["case_id"],
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        },
    }


def call_openai_responses(system: dict[str, Any], case: dict[str, Any], prompt: str) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {require_api_key(system)}",
    }
    payload: dict[str, Any] = {
        "model": system["model"],
        "input": prompt,
        "max_output_tokens": int(system.get("max_tokens", 1200)),
        "store": False,
    }
    if "temperature" in system and system["temperature"] is not None:
        payload["temperature"] = system["temperature"]
    base_url = str(system.get("base_url", "https://api.openai.com/v1")).rstrip("/")
    response = request_json(
        f"{base_url}/responses",
        headers,
        payload,
        timeout=int(system.get("timeout_seconds", 120)),
    )
    content = ""
    if response["ok"]:
        try:
            body = response["json"]
            response_status = body.get("status") if isinstance(body, dict) else None
            if response_status in {"incomplete", "failed", "cancelled"}:
                details = body.get("incomplete_details") or body.get("error") or response_status
                if (
                    response_status == "incomplete"
                    and isinstance(details, dict)
                    and details.get("reason") == "max_output_tokens"
                ):
                    budget = int(payload["max_output_tokens"])
                    budget_label = f"{budget:,}".replace(",", ".")
                    response["parse_error"] = (
                        "OpenAI afsluttede svaret, før det var færdigt, fordi "
                        f"tokenbudgettet ({budget_label}) blev nået. Vælg et højere "
                        "tokenbudget under Avancerede testindstillinger og brug derefter "
                        "samme budget for alle 14 spørgsmål."
                    )
                else:
                    response["parse_error"] = (
                        f"OpenAI-svaret fik status {response_status}: {details}"
                    )
                return {"adapter": "openai_responses", "content": "", "raw_response": response}
            parts = []
            for item in body.get("output", []):
                if item.get("type") != "message":
                    continue
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        parts.append(part.get("text", ""))
            content = "".join(parts)
        except Exception as exc:  # noqa: BLE001
            response["parse_error"] = repr(exc)
    return {"adapter": "openai_responses", "content": content, "raw_response": response}


def call_openai_chat(system: dict[str, Any], case: dict[str, Any], prompt: str) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    api_key = resolve_api_key(system)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif system.get("api_key_required", True):
        require_api_key(system)

    payload: dict[str, Any] = {
        "model": system["model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": int(system.get("max_tokens", 1200)),
    }
    if "temperature" in system and system["temperature"] is not None:
        payload["temperature"] = system["temperature"]
    base_url = str(system.get("base_url", "http://localhost:8000/v1")).rstrip("/")
    response = request_json(
        f"{base_url}/chat/completions",
        headers,
        payload,
        timeout=int(system.get("timeout_seconds", 120)),
    )
    content = ""
    if response["ok"]:
        try:
            choice = response["json"]["choices"][0]
            finish_reason = choice.get("finish_reason")
            if finish_reason in {"length", "content_filter"}:
                response["parse_error"] = f"Chat completion stopped with {finish_reason}."
            else:
                content = choice["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            response["parse_error"] = repr(exc)
    return {"adapter": "openai_chat_completions", "content": content, "raw_response": response}


def call_anthropic(system: dict[str, Any], case: dict[str, Any], prompt: str) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": require_api_key(system),
        "anthropic-version": str(system.get("anthropic_version", "2023-06-01")),
    }
    payload: dict[str, Any] = {
        "model": system["model"],
        "max_tokens": int(system.get("max_tokens", 1200)),
        "messages": [{"role": "user", "content": prompt}],
    }
    if "temperature" in system and system["temperature"] is not None:
        payload["temperature"] = system["temperature"]
    base_url = str(system.get("base_url", "https://api.anthropic.com")).rstrip("/")
    response = request_json(
        f"{base_url}/v1/messages",
        headers,
        payload,
        timeout=int(system.get("timeout_seconds", 120)),
    )
    content = ""
    if response["ok"]:
        body = response["json"]
        stop_reason = body.get("stop_reason") if isinstance(body, dict) else None
        if stop_reason in {"max_tokens", "refusal", "pause_turn", "tool_use"}:
            response["parse_error"] = f"Anthropic response stopped with {stop_reason}."
        else:
            content = "".join(
                part.get("text", "")
                for part in body.get("content", [])
                if part.get("type") == "text"
            )
    return {"adapter": "anthropic_messages", "content": content, "raw_response": response}


def call_generic_http(system: dict[str, Any], case: dict[str, Any], prompt: str) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    api_key = resolve_api_key(system)
    if api_key:
        header_name = str(system.get("api_key_header", "Authorization"))
        prefix = str(system.get("api_key_prefix", "Bearer "))
        headers[header_name] = f"{prefix}{api_key}"

    input_mode = get_input_mode(system)
    # Every field is constructed from the mode-specific allowlist. No testcase
    # reference or gold determination is available to this adapter.
    payload: dict[str, Any] = {
        "input_mode": input_mode,
        "model_input": get_visible_model_input(case, input_mode),
        "prompt": prompt,
    }
    if input_mode == "self_retrieval":
        payload["corpus_id"] = str(system.get("corpus_id", "su_handicaptillaeg_v1"))
        if system.get("corpus_sha256"):
            payload["corpus_sha256"] = str(system["corpus_sha256"])
    response = request_json(
        str(system["endpoint"]),
        headers,
        payload,
        timeout=int(system.get("timeout_seconds", 120)),
    )
    content = ""
    retrieved_chunks: list[dict[str, Any]] = []
    if response["ok"]:
        body = response["json"]
        if isinstance(body, dict):
            content = body.get("content") or body.get("answer") or body.get("output") or ""
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            retrieved_chunks = normalize_retrieved_chunks(body.get("retrieved_chunks", []))
            if input_mode == "self_retrieval" and not retrieved_chunks:
                response["parse_error"] = (
                    "A self-retrieval response must include at least one retrieved_chunks item."
                )
                content = ""
        elif isinstance(body, str):
            content = body
    return {
        "adapter": "generic_http_json",
        "content": content,
        "retrieved_chunks": retrieved_chunks,
        "raw_response": response,
    }


def normalize_retrieved_chunks(value: Any) -> list[dict[str, Any]]:
    """Normalize a small, inspectable retrieval trace from a RAG endpoint."""
    if not isinstance(value, list):
        return []
    chunks: list[dict[str, Any]] = []
    for index, item in enumerate(value, 1):
        if isinstance(item, str):
            text = item.strip()
            if text:
                chunks.append(
                    {
                        "chunk_id": "",
                        "rank": index,
                        "score": "",
                        "source_id": "",
                        "locator": "",
                        "text": text,
                    }
                )
            continue
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("content") or "").strip()
        if not text:
            continue
        chunks.append(
            {
                "chunk_id": str(item.get("chunk_id") or item.get("id") or ""),
                "rank": item.get("rank", index),
                "score": item.get("score", ""),
                "source_id": str(item.get("source_id") or item.get("source") or ""),
                "locator": str(
                    item.get("locator")
                    or item.get("source_locator")
                    or item.get("citation_label")
                    or ""
                ),
                "text": text,
            }
        )
    return chunks


Adapter = Callable[[dict[str, Any], dict[str, Any], str], dict[str, Any]]
ADAPTERS: dict[str, Adapter] = {
    "dry_run": call_dry_run,
    "openai_responses": call_openai_responses,
    "openai_chat_completions": call_openai_chat,
    "anthropic_messages": call_anthropic,
    "generic_http_json": call_generic_http,
    "rag_http_json": call_generic_http,
}


def sanitize_system_config(system: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in system.items()
        if key != "_api_key" and "api_key" not in key.lower() and "secret" not in key.lower()
    }


def extract_provider_metadata(result: dict[str, Any]) -> dict[str, Any]:
    raw_response = result.get("raw_response")
    body = raw_response.get("json") if isinstance(raw_response, dict) else None
    if not isinstance(body, dict):
        return {
            "provider_response_id": "",
            "provider_model": "",
            "provider_status": "",
            "provider_usage": {},
        }

    usage = body.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    status = body.get("status") or body.get("stop_reason") or ""
    return {
        "provider_response_id": str(body.get("id") or ""),
        "provider_model": str(body.get("model") or ""),
        "provider_status": str(status),
        "provider_usage": usage,
    }


def run(system: dict[str, Any], testcases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validate_system_config(system)
    validate_testcases_for_run(testcases)
    adapter_name = str(system["adapter"])
    adapter = ADAPTERS[adapter_name]
    input_mode = get_input_mode(system)

    outputs: list[dict[str, Any]] = []
    for index, case in enumerate(testcases, 1):
        visible_model_input = get_visible_model_input(case, input_mode)
        model_input_json = json.dumps(
            visible_model_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        prompt = build_prompt(case, input_mode)
        started = time.time()
        error = None
        try:
            result = adapter(system, case, prompt)
        except Exception as exc:  # noqa: BLE001 - preserve failures per case.
            result = {"adapter": adapter_name, "content": "", "raw_response": None}
            error = repr(exc)
        content = result.get("content", "")
        retrieved_chunks = result.get("retrieved_chunks", [])
        raw_response = result.get("raw_response")
        provider_metadata = extract_provider_metadata(result)
        if error is None and result.get("error"):
            error = str(result["error"])
        if error is None and isinstance(raw_response, dict):
            if raw_response.get("ok") is False:
                error = str(raw_response.get("error") or f"Provider request failed ({raw_response.get('status')})")
            elif raw_response.get("parse_error"):
                error = str(raw_response["parse_error"])
        if error is None and not str(content).strip():
            error = "Provider returned no answer content."
        elapsed_ms = int((time.time() - started) * 1000)
        outputs.append(
            {
                "case_id": case["case_id"],
                "system_id": system["system_id"],
                "adapter": result.get("adapter", adapter_name),
                "requested_model": str(system.get("model", "")),
                "input_mode": input_mode,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_ms": elapsed_ms,
                "model_input_sha256": hashlib.sha256(model_input_json.encode("utf-8")).hexdigest(),
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "prompt": prompt,
                "content": content,
                "retrieved_chunks": retrieved_chunks,
                **provider_metadata,
                "raw_response": raw_response,
                "error": error,
            }
        )
        print(f"[{index}/{len(testcases)}] {system['system_id']} -> {case['case_id']} ({elapsed_ms} ms)")
        sys.stdout.flush()
    return outputs


def save_run(
    system: dict[str, Any],
    testcases: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    out_dir: Path,
    *,
    testcases_path: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    validate_system_config(system)
    validate_testcases_for_run(testcases)
    if len(outputs) != len(testcases):
        raise ValueError(
            f"Output count ({len(outputs)}) does not match testcase count ({len(testcases)})."
        )
    run_id = utc_run_id(str(system["system_id"]))
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    for output in outputs:
        output["run_id"] = run_id
    outputs_path = run_dir / "outputs.jsonl"
    write_jsonl(outputs_path, outputs)
    write_jsonl(out_dir / "latest_outputs.jsonl", outputs)

    input_mode = get_input_mode(system)
    prompt_file = PROMPT_FILES[input_mode]
    active_case_ids = {
        str(case["case_id"]) for case in load_jsonl(ACTIVE_TESTCASES)
    }
    executed_case_ids = [str(case["case_id"]) for case in testcases]
    safe_system = sanitize_system_config(system)
    metadata: dict[str, Any] = {
        "run_id": run_id,
        "benchmark_id": BENCHMARK_ID,
        "system": safe_system,
        "system_config_sha256": sha256_json(safe_system),
        "input_mode": input_mode,
        "case_ids": executed_case_ids,
        "case_count": len(testcases),
        "expected_active_case_count": len(active_case_ids),
        "complete_active_case_set": set(executed_case_ids) == active_case_ids,
        "executed_testcases_sha256": sha256_json(testcases),
        "prompt_template_file": str(prompt_file.relative_to(REPO_ROOT)),
        "prompt_template_sha256": sha256_file(prompt_file),
        "output_file": str(outputs_path.relative_to(REPO_ROOT))
        if outputs_path.is_relative_to(REPO_ROOT)
        else str(outputs_path),
        "outputs_sha256": sha256_file(outputs_path),
        "output_count": len(outputs),
        "run_error_count": sum(bool(output.get("error")) for output in outputs),
        "generation_parameters": {
            "max_tokens": int(system.get("max_tokens", 1200)),
            "temperature": system.get("temperature", "provider_default"),
            "timeout_seconds": int(system.get("timeout_seconds", 120)),
        },
        "model_input_boundary": (
            "Only the mode-specific visible input was sent to the provider; "
            "testcase.reference remained evaluator-only."
        ),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "warning": (
            "Raw outputs require independent claim and answer-level coding, "
            "adjudication and release validation before thesis-result claims."
        ),
        "runner_file": str(Path(__file__).relative_to(REPO_ROOT)),
        "runner_sha256": sha256_file(Path(__file__)),
        "provider_models_returned": sorted(
            {
                str(output.get("provider_model", "")).strip()
                for output in outputs
                if str(output.get("provider_model", "")).strip()
            }
        ),
    }
    if testcases_path:
        metadata["testcases_path"] = str(testcases_path)
        metadata["testcases_sha256"] = sha256_file(testcases_path)
    (run_dir / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return run_dir, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Run XSU-GUIDANCE-QA-V5 evaluation cases.")
    parser.add_argument("--system", required=True, type=Path, help="Path to system config JSON.")
    parser.add_argument("--testcases", default=ACTIVE_TESTCASES, type=Path, help="Path to active testcase JSONL.")
    parser.add_argument("--out", required=True, type=Path, help="Output directory for this system/run.")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of cases.")
    args = parser.parse_args()

    system = load_json(args.system)
    testcases = load_jsonl(args.testcases)
    validate_system_config(system)
    validate_testcases_for_run(testcases)
    if args.limit is not None:
        testcases = testcases[: args.limit]
    outputs = run(system, testcases)
    run_dir, _ = save_run(system, testcases, outputs, args.out, testcases_path=args.testcases)
    print(f"Wrote {run_dir / 'outputs.jsonl'}")
    print(f"Updated {args.out / 'latest_outputs.jsonl'}")


if __name__ == "__main__":
    main()
