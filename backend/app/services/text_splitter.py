def split_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("切片大小必须大于0")

    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("重叠长度必须大于等于0，且小于切片大小")

    text = text.strip()
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end == len(text):
            break

        start = end - chunk_overlap

    return chunks
