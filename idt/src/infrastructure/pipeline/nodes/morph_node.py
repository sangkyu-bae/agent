from src.domain.morph.interfaces import MorphAnalyzerInterface
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState

_KEYWORD_TAGS = frozenset({"NNG", "NNP", "VV", "VA"})
_VERB_ADJ_TAGS = frozenset({"VV", "VA"})


async def morph_node(
    state: AdvancedPipelineState,
    morph_analyzer: MorphAnalyzerInterface,
) -> dict:
    chunks = state.get("chunked_documents", [])
    if not chunks:
        return {
            "morph_applied": False,
            "morph_keywords_per_chunk": [],
        }

    try:
        keywords_per_chunk: list[list[str]] = []
        for chunk in chunks:
            analysis = morph_analyzer.analyze(chunk.page_content)
            keywords = _extract_keywords(analysis)
            keywords_per_chunk.append(keywords)
            chunk.metadata["morph_keywords"] = keywords

        return {
            "morph_applied": True,
            "morph_keywords_per_chunk": keywords_per_chunk,
        }
    except Exception as e:
        return {
            "morph_applied": False,
            "morph_keywords_per_chunk": [],
            "errors": state["errors"] + [f"Morph analysis failed: {str(e)}"],
        }


def _extract_keywords(analysis) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for tok in analysis.tokens:
        if tok.pos not in _KEYWORD_TAGS:
            continue
        form = tok.surface + "다" if tok.pos in _VERB_ADJ_TAGS else tok.surface
        if form not in seen:
            seen.add(form)
            keywords.append(form)
    return keywords
