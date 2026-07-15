import re


def clean_text(text: str) -> str:
    """清洗知识库文本。
    清洗的目标不是“改写内容”，而是去掉会干扰切片和检索的格式噪声：
    Windows 换行、多余空格、连续空行等。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
