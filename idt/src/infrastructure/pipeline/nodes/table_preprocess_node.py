from src.infrastructure.chunking.table_flattening.preprocessor import TableFlatteningPreprocessor
from src.infrastructure.pipeline.state.advanced_pipeline_state import AdvancedPipelineState


async def table_preprocess_node(
    state: AdvancedPipelineState,
    preprocessor: TableFlatteningPreprocessor,
) -> dict:
    if not state.get("enable_table_flattening", True):
        return {
            "preprocessed_documents": state.get("parsed_documents", []),
            "table_flattened": False,
            "table_count": 0,
        }

    documents = state.get("parsed_documents", [])
    if not documents:
        return {
            "status": "failed",
            "errors": state["errors"] + ["No documents for table preprocessing"],
        }

    try:
        total_table_count = 0
        enriched_docs = []

        for doc in documents:
            section_title = doc.metadata.get("section_title", "")
            result = preprocessor.process(doc.page_content, section_title)
            total_table_count += result.table_count

            if result.table_count > 0:
                doc.page_content = result.child_text
                doc.metadata["original_text"] = result.parent_text
                doc.metadata["table_count"] = result.table_count
                if result.metadata:
                    doc.metadata["table_metadata"] = result.metadata

            enriched_docs.append(doc)

        return {
            "preprocessed_documents": enriched_docs,
            "table_flattened": total_table_count > 0,
            "table_count": total_table_count,
        }
    except Exception as e:
        return {
            "preprocessed_documents": documents,
            "table_flattened": False,
            "table_count": 0,
            "errors": state["errors"] + [f"Table preprocessing failed: {str(e)}"],
        }
