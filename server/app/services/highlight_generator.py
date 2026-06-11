from __future__ import annotations

import logging

from app.db.models import HighlightCandidateRequest, HighlightManifest
from app.services.manifest_store import (
    ALLOWED_ACTION_ICONS,
    ALLOWED_ACTION_TONES,
    ALLOWED_EFFECTS,
    ALLOWED_HIGHLIGHT_TYPES,
    ALLOWED_TEMPLATES,
    parse_model_manifest,
    save_manifest,
)
from app.services.media_scanner import empty_manifest
from app.services.model_client import ModelClient
from app.services.text_quality import repair_mojibake

LOGGER = logging.getLogger(__name__)
MAX_REPAIR_SOURCE_CHARS = 12_000
MAX_REPAIR_ATTEMPTS = 3


def _format_allowlist(values: object) -> str:
    return ", ".join(sorted(str(value) for value in values if value))  # type: ignore[union-attr]


# Explicit allowed values injected into the repair prompt so the model fixes
# enum fields by picking from the whitelist instead of inventing new values.
ALLOWED_VALUES_HINT = (
    f"type: {_format_allowlist(ALLOWED_HIGHLIGHT_TYPES)}\n"
    f"template: {_format_allowlist(ALLOWED_TEMPLATES)}\n"
    f"effect: {_format_allowlist(ALLOWED_EFFECTS)}\n"
    f"tone: {_format_allowlist(ALLOWED_ACTION_TONES)}\n"
    f"icon: {_format_allowlist(ALLOWED_ACTION_ICONS)}"
)

SYSTEM_PROMPT_CLEAN = """你负责根据带时间戳的短剧转写，生成中文高光互动 Manifest。只返回合法 JSON，不要 Markdown，不要解释。
JSON 必须包含 content_id、version、highlights。

输入每行一定有原始 text 和时间戳，也可能包含辅助字段：
- speaker / speaker_name / confidence：说话人线索，可能来自声纹、ASR 或 LLM。
- emotion / action / scene / beat / visual / mentions / evidence：剧情上下文线索。

证据优先级：
1. 同一行的原始 text 和时间戳永远最高优先级。
2. speaker_name、mentions、scene 等字段只作辅助，不得覆盖或改写原始台词。
3. 涉及人物姓名时，只有原始 text、summary 或 speakers 列表明确支持，才可以在 title 中写姓名；否则用“身份曝光”“当场反问”这类剧情标题。
4. 不要编造转写范围外的时间戳、人物关系、人物姓名或剧情。

高光要来自具体剧情时刻，优先选择观众最想即时表达情绪的爽点、笑点、反转、打脸、撒糖、紧张、冲突或名场面。title 用短中文概括具体剧情点，不超过 12 个汉字，例如：身份曝光、线索出现、反转来了、当场认错。title 要像运营标注标题，清楚克制；禁止使用酸鸡、贱、垃圾、傻、废物、撕逼、绿茶、小三、渣男、舔狗等攻击性或低质网感词。action label 用口语化情绪表达，不超过 6 个汉字。优先从这组推荐词里选用，保持整体风格统一：爽、解气、太离谱、笑出声、上头、好磕、扎心、心疼、紧张、震惊、太狠了、绷不住、有点东西、佩服、无语、气炸、泪目、稳了。如果这些都不贴切，可以用其它简洁中文情绪短语，但不要用英文、拼音或生僻书面语。

使用这个结构：
{
  "content_id": "2fe8f92ec371216d",
  "version": "0.2.0",
  "highlights": [{
    "id": "candidate-1",
    "start_ms": 12000,
    "end_ms": 18000,
    "type": "twist",
    "intensity": 0.9,
    "template": "dual-button",
    "payload": {
      "title": "身份曝光",
      "actions": [
        {"key": "shuang", "label": "爽", "tone": "positive", "icon": "fire"},
        {"key": "laughed", "label": "笑出声", "tone": "funny", "icon": "laugh"}
      ],
      "effect": "ratio-reveal"
    }
  }]
}

每集生成 2 到 4 个不重复高光。每个时间窗必须持续 2 到 8 秒。
type 必须是：satisfying, twist, revenge, slap-face, funny, sweet, suspense, reveal, conflict, famous-scene。
template 必须是：dual-button, poll, tap-boost。
dual-button 和 poll 必须提供至少 2 个 actions；只有 tap-boost 可以只提供 1 个 action。
effect 必须是：particle-burst, ratio-reveal, pulse。
每个高光使用 1 到 3 个 actions。每个 action 都必须有可点击的 key、中文 label、白名单 tone 和 icon。
tone：positive, negative, shocked, funny, confused, support, calm。
icon：heart, fire, shock, laugh, question, check, boost。
key 只能使用英文字母、数字、下划线或短横线。不要把普通铺垫当高光。
"""

REPAIR_SYSTEM_PROMPT_CLEAN = """你修复短剧高光互动 Manifest。只返回合法 JSON，不要 Markdown，不要解释。
保留能满足规则的高光，删除或修复无效高光，不要编造输入中不存在的剧情。title 必须是简洁中文剧情标题，禁止攻击性或低质网感词；action label 必须是简洁中文情绪表达；禁止英文、拼音和乱码。"""


def generate_highlight_candidates(
    request: HighlightCandidateRequest,
    *,
    model_client: ModelClient | None = None,
    fallback: bool = True,
) -> HighlightManifest:
    content_id = request.content_id or "preview"
    client = model_client or ModelClient()

    if not request.transcript.strip() or not client.is_configured:
        return empty_manifest(content_id)

    transcript = repair_mojibake(request.transcript)
    summary = repair_mojibake(request.summary)

    user_prompt = f"""content_id: {content_id}
duration_ms: {request.duration_ms}
summary: {summary or "not provided"}

timestamped_transcript:
{transcript}
"""

    try:
        raw_text = client.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT_CLEAN},
                {"role": "user", "content": user_prompt},
            ],
            json_object=True,
        )
        manifest = parse_manifest_with_repair(
            client,
            raw_text,
            content_id,
            request.duration_ms,
        )
        if request.persist:
            save_manifest(manifest, content_id=content_id)
        return manifest
    except Exception:
        LOGGER.exception("Unable to generate highlight manifest for content %s", content_id)
        if fallback:
            return empty_manifest(content_id)
        raise


def parse_manifest_with_repair(
    client: ModelClient,
    raw_text: str,
    content_id: str,
    duration_ms: int,
) -> HighlightManifest:
    candidate_text = raw_text
    last_error: Exception | None = None

    for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
        try:
            return parse_model_manifest(candidate_text, content_id, duration_ms)
        except Exception as exc:
            last_error = exc
            if attempt >= MAX_REPAIR_ATTEMPTS:
                raise

            repair_attempt = attempt + 1
            LOGGER.warning(
                "Invalid highlight manifest for content %s. Requesting repair %s/%s: %s",
                content_id,
                repair_attempt,
                MAX_REPAIR_ATTEMPTS,
                exc,
            )
            candidate_text = client.chat(
                [
                    {"role": "system", "content": REPAIR_SYSTEM_PROMPT_CLEAN},
                    {
                        "role": "user",
                        "content": build_repair_prompt(candidate_text, exc, content_id, duration_ms),
                    },
                ],
                json_object=True,
            )

    if last_error is not None:
        raise last_error
    raise ValueError("Unable to parse highlight manifest")


def build_repair_prompt(raw_text: str, error: Exception, content_id: str, duration_ms: int) -> str:
    source = raw_text[:MAX_REPAIR_SOURCE_CHARS]
    return f"""content_id: {content_id}
duration_ms: {duration_ms}
validation_error: {error}

请修复下面的模型输出。重点检查：
1. JSON 语法错误。
2. 缺失 content_id、version、highlights、id、start_ms、end_ms、type、template、payload.title、payload.actions、payload.effect 等必要字段。
3. 高光时间窗无效、越界、重叠或不在 2 到 8 秒。
4. 所有高光都不满足情绪高光规则。
5. template、effect、tone、icon、type 必须从下列白名单里选，不能用其它值：
{ALLOWED_VALUES_HINT}
6. 互动选项不可用：key 为空、重复或非法，label 不是简洁中文情绪表达。
7. dual-button 或 poll 少于 2 个 actions；只有 tap-boost 可以只有 1 个 action。
8. title 或 label 包含英文、拼音、乱码、攻击性或低质网感词。
只返回修复后的 JSON。

{source}
"""
