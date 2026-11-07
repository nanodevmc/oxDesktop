import re

from base_plugin import HookResult, HookStrategy

from .java_utils import arraylist_to_list, iterable_to_arraylist
from .logs import _logger


class _TraceCollapser:
    PYTHON_TB_REGEX = re.compile(
        r'(?:Traceback\s+\(most\s+recent\s+call\s+last\):\s*\n'
        r'(?:[\s\xa0]*File\s+".*?",\s*line\s+\d+.*?\n[\s\xa0\S]*?)+?'
        r'[\s\xa0]*[\w\.]+(?:Error|Exception|Interrupt|Exit|Warning)?:[^\n]*)',
        re.MULTILINE | re.IGNORECASE
    )

    JAVA_LINE_PATTERNS = [
        re.compile(r'^\s*(?:Caused\s+by:|[a-zA-Z0-9_\.\$]+(?:Exception|Error|Throwable):)'), # Исключение / Caused by
        re.compile(r'^\s*(?:\.|\b)?at\b'),                                                # at ... или .at ...
        re.compile(r'^\s*\.\.\.\s+\d+\s+more')                                            # ... X more
    ]

    @classmethod
    def _is_java_tb_line(cls, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        return any(pattern.search(stripped) for pattern in cls.JAVA_LINE_PATTERNS)

    @classmethod
    def process_java_tracebacks(cls, text: str) -> str:
        lines = text.split('\n')
        result = []
        current_block = []

        for line in lines:
            if cls._is_java_tb_line(line):
                current_block.append(line)
            else:
                if current_block:
                    block_str = "\n".join(current_block)
                    if len(current_block) > 1 or "at " in block_str or "Exception" in block_str:
                        result.append(f"<blockquote collapsed>{block_str}</blockquote>")
                    else:
                        result.append(block_str)
                    current_block = []
                result.append(line)

        if current_block:
            block_str = "\n".join(current_block)
            if len(current_block) > 1 or "at " in block_str or "Exception" in block_str:
                result.append(f"<blockquote collapsed>{block_str}</blockquote>")
            else:
                result.append(block_str)

        return "\n".join(result)

    @classmethod
    def wrap_tracebacks_in_html(cls, text: str) -> str:
        if not text:
            return text

        if "Traceback (most recent call last):" in text:
            def _py_replacer(m: re.Match) -> str:
                return f"<blockquote collapsed>{m.group(0).strip()}</blockquote>"
            text = cls.PYTHON_TB_REGEX.sub(_py_replacer, text)

        text = cls.process_java_tracebacks(text)
        return text

    @classmethod
    def handle_send_message_hook(cls, params, _: int) -> HookResult:
        try:
            from extera_utils import text_formatting

            formatted_text = cls.wrap_tracebacks_in_html(text := params.message)
            if formatted_text == text:
                return HookResult()

            parsed = text_formatting.parse_text(formatted_text, parse_mode="HTML")
            new_entities = arraylist_to_list(params.entities) if params.entities else []
            new_entities += parsed.get("entities") or []

            params.message = parsed.get("message")
            params.entities = iterable_to_arraylist(new_entities)

            return HookResult(strategy=HookStrategy.MODIFY, params=params)
        except Exception:
            _logger.error("Error in traceback wrapper hook:", exc_info=True)
            return HookResult()
