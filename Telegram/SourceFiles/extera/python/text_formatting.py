import re
from dataclasses import dataclass
from enum import Enum
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple


class TLEntityType(str, Enum):
    CODE = "code"
    PRE = "pre"
    STRIKETHROUGH = "strikethrough"
    TEXT_LINK = "text_link"
    BOLD = "bold"
    ITALIC = "italic"
    UNDERLINE = "underline"
    SPOILER = "spoiler"
    CUSTOM_EMOJI = "custom_emoji"
    BLOCKQUOTE = "blockquote"

    def __eq__(self, other: Any) -> bool:
        target = getattr(other, "value", other)
        if str(self.value) == str(target):
            return True
        if self is TLEntityType.STRIKETHROUGH and target in ("strike", "s"):
            return True
        if self is TLEntityType.TEXT_LINK and target in ("url", "link", "text_url"):
            return True
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self.value)


@dataclass
class RawEntity:
    offset: int
    length: int
    type: TLEntityType
    url: Optional[str] = None
    language: Optional[str] = None
    document_id: Optional[int] = None
    collapsed: bool = False


_TAG_MAP: Dict[str, TLEntityType] = {
    "b": TLEntityType.BOLD,
    "strong": TLEntityType.BOLD,
    "i": TLEntityType.ITALIC,
    "em": TLEntityType.ITALIC,
    "u": TLEntityType.UNDERLINE,
    "s": TLEntityType.STRIKETHROUGH,
    "del": TLEntityType.STRIKETHROUGH,
    "strike": TLEntityType.STRIKETHROUGH,
    "code": TLEntityType.CODE,
    "pre": TLEntityType.PRE,
    "spoiler": TLEntityType.SPOILER,
    "tg-spoiler": TLEntityType.SPOILER,
    "a": TLEntityType.TEXT_LINK,
    "blockquote": TLEntityType.BLOCKQUOTE,
    "emoji": TLEntityType.CUSTOM_EMOJI,
    "tg-emoji": TLEntityType.CUSTOM_EMOJI,
}

_LANG_PATTERN = re.compile(r"language-([\w#+-]+)")


class _HTMLFormatExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._accumulator: List[str] = []
        self._char_count = 0
        self._open_tags: List[list] = []
        self.entities: List[RawEntity] = []

    def _append(self, content: str) -> None:
        if content:
            self._accumulator.append(content)
            self._char_count += len(content)

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self._on_start(tag.lower(), dict(attrs))

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        lowered = tag.lower()
        if lowered == "br":
            self._append("\n")
        else:
            attr_dict = dict(attrs)
            self._on_start(lowered, attr_dict)
            self._on_end(lowered)

    def handle_endtag(self, tag: str) -> None:
        self._on_end(tag.lower())

    def handle_data(self, data: str) -> None:
        self._append(data)

    def _is_pre_active(self) -> bool:
        return bool(self._open_tags) and self._open_tags[-1][1] is TLEntityType.PRE

    def _on_start(self, tag: str, attrs: Dict[str, Optional[str]]) -> None:
        if tag == "br":
            self._append("\n")
            return
        entity_type = _TAG_MAP.get(tag)
        if entity_type is None:
            return
        if self._is_pre_active():
            if entity_type is TLEntityType.CODE:
                match = _LANG_PATTERN.search(attrs.get("class") or "")
                if match:
                    self._open_tags[-1][3]["language"] = match.group(1)
            return

        extra: Dict[str, Any] = {}
        if entity_type is TLEntityType.TEXT_LINK:
            extra["url"] = attrs.get("href") or ""
        elif entity_type is TLEntityType.PRE:
            extra["language"] = attrs.get("language") or ""
        elif entity_type is TLEntityType.CUSTOM_EMOJI:
            raw_id = attrs.get("id") or attrs.get("emoji-id") or ""
            extra["document_id"] = int(raw_id) if str(raw_id).isdigit() else None
        elif entity_type is TLEntityType.BLOCKQUOTE:
            extra["collapsed"] = "expandable" in attrs or "collapsed" in attrs

        self._open_tags.append([tag, entity_type, self._char_count, extra])

    def _on_end(self, tag: str) -> None:
        for idx in range(len(self._open_tags) - 1, -1, -1):
            if self._open_tags[idx][0] == tag:
                while len(self._open_tags) > idx:
                    self._finalize_top()
                return

    def _finalize_top(self) -> None:
        _tag, entity_type, start_pos, extra = self._open_tags.pop()
        length = self._char_count - start_pos
        if length <= 0:
            return
        if entity_type is TLEntityType.TEXT_LINK and not extra.get("url"):
            return
        if entity_type is TLEntityType.CUSTOM_EMOJI and extra.get("document_id") is None:
            return
        self.entities.append(RawEntity(offset=start_pos, length=length, type=entity_type, **extra))

    def build(self) -> Tuple[str, List[RawEntity]]:
        while self._open_tags:
            self._finalize_top()
        self.entities.sort(key=lambda e: (e.offset, -e.length))
        return "".join(self._accumulator), self.entities


def _parse_html_entities(text: str) -> Tuple[str, List[RawEntity]]:
    parser = _HTMLFormatExtractor()
    parser.feed(text)
    parser.close()
    return parser.build()


_MARKDOWN_REGEX = re.compile(
    r"(?P<pre>```(?P<prelang>\w+)?[ \t]*\n?(?P<prebody>.*?)```)"
    r"|(?P<quote>^(?:\*\*>|>)[ \t]?[^\n]*(?:\n(?:\*\*>|>)[ \t]?[^\n]*)*)"
    r"|(?P<emoji>!\[(?P<emojialt>[^\]]*)\]\(tg://emoji\?id=(?P<emojiid>\d+)\))"
    r"|(?P<link>\[(?P<linktext>[^\]]+)\]\((?P<linkurl>[^)\s]+)\))"
    r"|(?P<code>`(?P<codebody>[^`\n]+)`)"
    r"|(?P<spoiler>\|\|(?P<spoilerbody>.+?)\|\|)"
    r"|(?P<bold2>\*\*(?P<bold2body>[^*\n]+?)\*\*)"
    r"|(?P<bold>\*(?P<boldbody>[^*\n]+?)\*)"
    r"|(?P<underline>(?<![\w])__(?P<underlinebody>[^_\n]+?)__(?![\w]))"
    r"|(?P<italic>(?<![\w])_(?P<italicbody>[^_\n]+?)_(?![\w]))"
    r"|(?P<strike2>~~(?P<strike2body>[^~\n]+?)~~)"
    r"|(?P<strike>~(?P<strikebody>[^~\n]+?)~)",
    re.S | re.M,
)

_QUOTE_PREFIX = re.compile(r"^(?:\*\*>|>)[ \t]?")

_INLINE_TYPE_MAP = {
    "code": ("codebody", TLEntityType.CODE),
    "spoiler": ("spoilerbody", TLEntityType.SPOILER),
    "bold2": ("bold2body", TLEntityType.BOLD),
    "bold": ("boldbody", TLEntityType.BOLD),
    "underline": ("underlinebody", TLEntityType.UNDERLINE),
    "italic": ("italicbody", TLEntityType.ITALIC),
    "strike2": ("strike2body", TLEntityType.STRIKETHROUGH),
    "strike": ("strikebody", TLEntityType.STRIKETHROUGH),
}


def _parse_markdown_entities(text: str) -> Tuple[str, List[RawEntity]]:
    chunks: List[str] = []
    entities: List[RawEntity] = []
    current_length = 0
    last_end = 0

    for match in _MARKDOWN_REGEX.finditer(text):
        start_idx, end_idx = match.span()
        prefix = text[last_end:start_idx]
        chunks.append(prefix)
        current_length += len(prefix)

        token = match.lastgroup
        offset = current_length

        if token == "pre":
            body = match.group("prebody")
            if body.endswith("\n"):
                body = body[:-1]
            lang = match.group("prelang") or None
            chunks.append(body)
            current_length += len(body)
            if body:
                entities.append(RawEntity(offset, len(body), TLEntityType.PRE, language=lang))
        elif token == "quote":
            raw_quote = match.group("quote")
            is_expandable = raw_quote.startswith("**>")
            quote_text = "\n".join(_QUOTE_PREFIX.sub("", line) for line in raw_quote.split("\n"))
            chunks.append(quote_text)
            current_length += len(quote_text)
            if quote_text:
                entities.append(RawEntity(offset, len(quote_text), TLEntityType.BLOCKQUOTE, collapsed=is_expandable))
        elif token == "emoji":
            placeholder = match.group("emojialt") or "\U0001F642"
            doc_id = int(match.group("emojiid"))
            chunks.append(placeholder)
            current_length += len(placeholder)
            entities.append(RawEntity(offset, len(placeholder), TLEntityType.CUSTOM_EMOJI, document_id=doc_id))
        elif token == "link":
            inner_text = match.group("linktext")
            href = match.group("linkurl")
            parsed_inner, nested = _parse_markdown_entities(inner_text)
            chunks.append(parsed_inner)
            span_len = len(parsed_inner)
            if href.startswith("tg://emoji?id="):
                eid = href[len("tg://emoji?id="):]
                if eid.isdigit():
                    entities.append(RawEntity(offset, span_len, TLEntityType.CUSTOM_EMOJI, document_id=int(eid)))
                else:
                    entities.append(RawEntity(offset, span_len, TLEntityType.TEXT_LINK, url=href))
            else:
                entities.append(RawEntity(offset, span_len, TLEntityType.TEXT_LINK, url=href))
            for n in nested:
                n.offset += offset
                entities.append(n)
            current_length += span_len
        else:
            group_key, ent_type = _INLINE_TYPE_MAP[token]
            content = match.group(group_key)
            chunks.append(content)
            current_length += len(content)
            entities.append(RawEntity(offset, len(content), ent_type))

        last_end = end_idx

    chunks.append(text[last_end:])
    return "".join(chunks), entities


def _calc_utf16_length(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def parse_raw(text: str, parse_mode: Optional[str] = "HTML") -> Tuple[str, List[RawEntity]]:
    content = "" if text is None else str(text)
    mode = (parse_mode or "HTML").strip().lower()

    if mode == "html":
        plain, parsed_entities = _parse_html_entities(content)
    elif mode == "markdown":
        plain, parsed_entities = _parse_markdown_entities(content)
    else:
        raise ValueError(f"unsupported parse_mode {parse_mode!r}: expected 'HTML' or 'Markdown'")

    for ent in parsed_entities:
        ent.offset = _calc_utf16_length(plain[:ent.offset])
        ent.length = _calc_utf16_length(plain[ent.offset:ent.offset + ent.length])

    return plain, parsed_entities


def entity_to_dict(raw: RawEntity) -> Dict[str, Any]:
    serialized: Dict[str, Any] = {
        "type": raw.type.value,
        "offset": int(raw.offset),
        "length": int(raw.length),
    }
    if raw.url:
        serialized["url"] = raw.url
    if raw.language:
        serialized["language"] = raw.language
    if raw.document_id is not None:
        serialized["document_id"] = str(int(raw.document_id))
    if raw.collapsed:
        serialized["collapsed"] = True
    return serialized


def parse_text(text: str, parse_mode: Optional[str] = "HTML", is_caption: bool = False) -> Dict[str, Any]:
    plain, raw_entities = parse_raw(text, parse_mode)
    field_name = "caption" if is_caption else "message"
    return {
        field_name: plain,
        "entities": [entity_to_dict(item) for item in raw_entities],
    }
