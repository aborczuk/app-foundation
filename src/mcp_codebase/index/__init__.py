"""Lazy vector-index namespace exports for codebase-lsp."""
# ruff: noqa: I001

from importlib import import_module


_LAZY_EXPORTS = {
    "CodeSymbol": ("src.mcp_codebase.index.domain", "CodeSymbol"),
    "IndexConfig": ("src.mcp_codebase.index.config", "IndexConfig"),
    "IndexMetadata": ("src.mcp_codebase.index.domain", "IndexMetadata"),
    "IndexScope": ("src.mcp_codebase.index.domain", "IndexScope"),
    "MarkdownSection": ("src.mcp_codebase.index.domain", "MarkdownSection"),
    "QueryResult": ("src.mcp_codebase.index.domain", "QueryResult"),
    "VectorIndexService": ("src.mcp_codebase.index.service", "VectorIndexService"),
    "build_vector_index_service": ("src.mcp_codebase.index.service", "build_vector_index_service"),
    "extract_markdown_sections": ("src.mcp_codebase.index.extractors", "extract_markdown_sections"),
    "extract_python_symbols": ("src.mcp_codebase.index.extractors", "extract_python_symbols"),
    "extract_shell_scripts": ("src.mcp_codebase.index.extractors", "extract_shell_scripts"),
    "extract_yaml_sections": ("src.mcp_codebase.index.extractors", "extract_yaml_sections"),
    "should_skip_path": ("src.mcp_codebase.index.extractors", "should_skip_path"),
}

__all__ = tuple(_LAZY_EXPORTS)


def __getattr__(name: str):
    """Resolve public vector-index exports only when a caller first asks for them."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return the dynamic export surface for interactive inspection tools."""
    return sorted(set(globals()) | set(__all__))
