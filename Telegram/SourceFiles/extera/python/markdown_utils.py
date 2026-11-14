from typing import Any, Iterator, List, Optional, Tuple, Union

from text_formatting import RawEntity, entity_to_dict, parse_raw


class MarkdownEntity:
    __slots__ = (
        "offset",
        "length",
        "type",
        "url",
        "language",
        "document_id",
        "collapsed",
        "_raw",
    )

    def __init__(self, raw: RawEntity):
        self._raw = raw
        self.offset = int(raw.offset)
        self.length = int(raw.length)
        self.type = raw.type
        self.url = raw.url
        self.language = raw.language
        self.document_id = raw.document_id
        self.collapsed = bool(raw.collapsed)

    def to_tlrpc_object(self) -> dict:
        entity = RawEntity(
            offset=self.offset,
            length=self.length,
            type=self.type,
            url=self.url,
            language=self.language,
            document_id=self.document_id,
            collapsed=self.collapsed,
        )
        return entity_to_dict(entity)

    def __getitem__(self, index: int) -> Any:
        return (self.type, self.offset, self.length, self.url)[index]

    def __iter__(self) -> Iterator[Any]:
        return iter((self.type, self.offset, self.length, self.url))

    def __len__(self) -> int:
        return 4

    def __repr__(self) -> str:
        return (
            f"MarkdownEntity(type={self.type}, offset={self.offset}, "
            f"length={self.length}, url={self.url!r})"
        )


class ParsedText:
    __slots__ = ("text", "entities")

    def __init__(self, text: str, entities: List[MarkdownEntity]):
        self.text = text
        self.entities = entities

    def __iter__(self) -> Iterator[Union[str, List[MarkdownEntity]]]:
        return iter((self.text, self.entities))

    def __len__(self) -> int:
        return len(self.text)

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return f"ParsedText({self.text!r}, entities_count={len(self.entities)})"


def _process_text(text: Any, mode: str) -> ParsedText:
    content = "" if text is None else str(text)
    plain_text, extracted_entities = parse_raw(content, mode)
    return ParsedText(plain_text, [MarkdownEntity(item) for item in extracted_entities])


def parse_markdown(text: Any) -> ParsedText:
    return _process_text(text, "Markdown")


def parse_html(text: Any) -> ParsedText:
    return _process_text(text, "HTML")
