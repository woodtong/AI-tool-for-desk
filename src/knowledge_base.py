"""
知识库模块 - 从 knowledge_base 文件夹读取文本文件作为 AI 上下文参考
"""
import os
import logging

logger = logging.getLogger(__name__)

# 支持的文件扩展名
SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".rst",
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs", ".swift",
    ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg", ".conf",
    ".html", ".css", ".scss", ".less",
    ".csv",
    ".sh", ".bat", ".ps1",
    ".sql", ".r", ".lua",
}

# 单文件最大字节数
MAX_FILE_SIZE = 512 * 1024  # 512 KB

# 最大文件数
MAX_FILE_COUNT = 50

# 总内容最大字符数（防止系统提示词过长）
MAX_TOTAL_CHARS = 15000


def _should_skip(name):
    """跳过 README.md 和隐藏文件"""
    if name == "README.md":
        return True
    if name.startswith("."):
        return True
    return False


def _read_file(filepath):
    """
    读取单个文件内容，返回 (filename, content) 或 None
    只处理 UTF-8 编码的文本文件
    """
    try:
        size = os.path.getsize(filepath)
        if size == 0:
            return (os.path.basename(filepath), "")
        if size > MAX_FILE_SIZE:
            logger.warning("知识库文件过大，已跳过: %s (%d KB)", filepath, size // 1024)
            return None

        # 尝试 UTF-8 读取
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            # 尝试常见中文编码
            try:
                with open(filepath, "r", encoding="gbk") as f:
                    content = f.read()
            except UnicodeDecodeError:
                logger.warning("知识库文件编码不支持，已跳过: %s", filepath)
                return None

        relpath = os.path.relpath(filepath)
        return (relpath, content.strip())

    except (OSError, IOError) as e:
        logger.warning("知识库文件读取失败: %s - %s", filepath, e)
        return None


def load_knowledge_base(kb_path=None):
    """
    扫描知识库文件夹，读取所有支持的文件内容

    参数:
        kb_path: str - 知识库文件夹路径，默认为项目根目录下的 knowledge_base

    返回:
        str - 格式化后的知识库文本内容，如果没有文件则返回空字符串
    """
    if kb_path is None:
        # 默认路径：项目根目录下的 knowledge_base
        kb_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge_base")

    if not os.path.isdir(kb_path):
        logger.info("知识库文件夹不存在: %s", kb_path)
        return ""

    files_loaded = 0
    total_chars = 0
    sections = []

    # 递归遍历目录
    for root, dirs, files in os.walk(kb_path):
        # 跳过隐藏目录
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        for fname in sorted(files):
            if _should_skip(fname):
                continue

            ext = os.path.splitext(fname)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            if files_loaded >= MAX_FILE_COUNT:
                logger.warning("知识库文件数已达上限(%d)，停止加载", MAX_FILE_COUNT)
                break

            filepath = os.path.join(root, fname)
            result = _read_file(filepath)
            if result is None:
                continue

            relpath, content = result
            if not content:
                continue

            # 控制总长度
            remaining = MAX_TOTAL_CHARS - total_chars
            if len(content) > remaining:
                content = content[:remaining] + "\n... (超出长度限制，已截断)"

            sections.append(f"### {relpath}\n```\n{content}\n```")
            files_loaded += 1
            total_chars += len(content)

            if total_chars >= MAX_TOTAL_CHARS:
                logger.info("知识库总内容已达上限(%d 字符)", MAX_TOTAL_CHARS)
                break

        if files_loaded >= MAX_FILE_COUNT:
            break

    if not sections:
        logger.info("知识库为空，未加载任何文件")
        return ""

    logger.info("知识库加载完成: %d 个文件, %d 字符", files_loaded, total_chars)

    header = "以下是从知识库中加载的参考文件内容，请根据这些资料回答用户的问题：\n"
    return header + "\n\n".join(sections)
