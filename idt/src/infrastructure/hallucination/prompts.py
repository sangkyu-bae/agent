"""Prompt templates for hallucination evaluation."""

HALLUCINATION_EVALUATION_SYSTEM_PROMPT = """You are a hallucination evaluator. Your task is to determine whether a given LLM-generated answer is grounded in the provided reference documents.

A response is considered hallucinated if it contains information that:
1. Is not supported by the reference documents
2. Contradicts the information in the reference documents
3. Makes claims that cannot be verified from the reference documents

A response is NOT hallucinated if all its claims can be traced back to the reference documents.

You must respond with a structured output indicating whether the generation is hallucinated (true) or grounded (false)."""

HALLUCINATION_EVALUATION_HUMAN_TEMPLATE = """Reference Documents:
{documents}

---

LLM Generation to Evaluate:
{generation}

---

Based on the reference documents above, determine if the LLM generation is hallucinated.
If the generation contains any information not supported by the documents, it is hallucinated.
If all information in the generation can be traced to the documents, it is not hallucinated."""
