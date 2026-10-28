"""离线测试：长文本分段和自动翻译方向。"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engines  # noqa: E402


def check_split(text, limit):
    chunks = engines.split_text(text, limit)
    assert "".join(chunks) == text, "拼接后必须和原文完全一致"
    assert all(len(c) <= limit for c in chunks), [len(c) for c in chunks]
    return chunks


random.seed(1)
words = "the quick brown fox jumps over a lazy dog while translators keep working".split()
paragraphs = []
for _ in range(12):
    sentences = [" ".join(random.choices(words, k=random.randint(5, 30))).capitalize() + "."
                 for _ in range(random.randint(3, 12))]
    paragraphs.append(" ".join(sentences))
english = "\n\n".join(paragraphs)
chunks = check_split(english, 1500)
assert len(chunks) > 1
# 尽量在句末切开
assert all(c.rstrip().endswith(".") for c in chunks[:-1]), [c[-20:] for c in chunks]

chinese = "这是一个很长的中文句子，用来测试分段功能。" * 300
check_split(chinese, 1500)
check_split("x" * 5000, 1500)  # 没有任何分隔符时硬切
check_split("a, b, c, " * 800, 450)
assert engines.split_text("short") == ["short"]

assert engines.auto_target("你好，世界") == "en"
assert engines.auto_target("Hello world") == "zh-CN"
assert engines.auto_target("我在用 Python 写一个 translator") == "en"
assert engines.auto_target("This is a long English sentence with one 词") == "zh-CN"
print("engines OK")

assert engines.single_english_word(" hello ") == "hello"
assert engines.single_english_word("Apple.") == "Apple"
assert engines.single_english_word("well-known") == "well-known"
assert engines.single_english_word("don't") == "don't"
assert engines.single_english_word("hello world") is None
assert engines.single_english_word("你好") is None
assert engines.single_english_word("hello，世界") is None
print("single word OK")
