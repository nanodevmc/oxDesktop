import _compat


class ParsedMessage:
    def __init__(self, text, entities):
        self.text = text
        self.entities = entities


def parse_markdown(text: str) -> ParsedMessage:
    plain, entities = _compat.parse_markdown(text)
    return ParsedMessage(plain, entities)


def parse_html(text: str) -> ParsedMessage:
    plain, entities = _compat.parse_html(text)
    return ParsedMessage(plain, entities)
