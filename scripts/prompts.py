"""
prompts.py

All prompt engineering logic in one place.
Handles:
    - Context injection
    - Instruction based templates
    - Chain of thought guidance
    - Role based prompting
"""

from scripts.log import get_logger

logger = get_logger("Prompts")


# ------------------------------------------------------------------
# Detect what type of question the user is asking
# ------------------------------------------------------------------
def detect_question_type(question):
    """
    Look at the question and figure out what type it is.
    Returns one of: summary, compare, analyze, explain, general
    """

    question_lower = question.lower().strip()

    # Summary
    summary_words = ["summarize", "summary", "overview", "brief", "short version", "key points"]
    for word in summary_words:
        if word in question_lower:
            return "summary"

    # Compare
    compare_words = ["compare", "difference", "versus", "vs", "differ", "contrast", "against"]
    for word in compare_words:
        if word in question_lower:
            return "compare"

    # Analyze
    analyze_words = ["analyze", "analysis", "trend", "pattern", "insight", "why", "reason", "cause"]
    for word in analyze_words:
        if word in question_lower:
            return "analyze"

    # Explain
    explain_words = ["explain", "simpler", "simple terms", "what does", "what is", "mean", "clarify"]
    for word in explain_words:
        if word in question_lower:
            return "explain"

    return "general"


# ------------------------------------------------------------------
# Detect what type of document the context is about
# ------------------------------------------------------------------
def detect_document_type(context, sources):
    """
    Look at the context and source file names to guess the document type.
    Returns one of: financial, technical, medical, legal, data, general
    """

    text = context.lower()
    source_text = " ".join(sources).lower()

    # Financial
    finance_words = ["revenue", "profit", "loss", "sales", "income", "expense",
                     "budget", "cost", "price", "financial", "quarter", "fiscal"]
    finance_count = sum(1 for w in finance_words if w in text)
    if finance_count >= 2:
        return "financial"

    # Technical
    tech_words = ["api", "code", "function", "server", "database", "software",
                  "algorithm", "system", "architecture", "deploy", "config"]
    tech_count = sum(1 for w in tech_words if w in text)
    if tech_count >= 2:
        return "technical"

    # Medical
    medical_words = ["patient", "diagnosis", "treatment", "clinical", "symptom",
                     "medicine", "therapy", "health", "disease", "medical"]
    medical_count = sum(1 for w in medical_words if w in text)
    if medical_count >= 2:
        return "medical"

    # Legal
    legal_words = ["agreement", "contract", "clause", "liability", "court",
                   "legal", "law", "regulation", "compliance", "policy"]
    legal_count = sum(1 for w in legal_words if w in text)
    if legal_count >= 2:
        return "legal"

    # Data / Database
    data_words = ["table:", "columns:", "rows:", "database", "stats:",
                  "min=", "max=", "avg=", "sum="]
    data_count = sum(1 for w in data_words if w in text)
    if data_count >= 2:
        return "data"

    return "general"


# ------------------------------------------------------------------
# Role based system prompts
# ------------------------------------------------------------------
ROLE_PROMPTS = {
    "financial": (
        "You are a financial analyst assistant. "
        "You are expert at reading financial documents, reports and data. "
        "You understand revenue, profit margins, growth rates and trends. "
        "When answering, use financial terminology accurately. "
        "If numbers are involved, show calculations clearly."
    ),
    "technical": (
        "You are a technical documentation assistant. "
        "You are expert at reading technical docs, code and system designs. "
        "You explain technical concepts clearly. "
        "When answering, be precise about technical details."
    ),
    "medical": (
        "You are a medical document assistant. "
        "You are expert at reading medical reports and clinical data. "
        "You explain medical terms in understandable language. "
        "Always note that you are not providing medical advice."
    ),
    "legal": (
        "You are a legal document assistant. "
        "You are expert at reading contracts, agreements and legal documents. "
        "You explain legal terms clearly. "
        "Always note that you are not providing legal advice."
    ),
    "data": (
        "You are a data analysis assistant. "
        "You are expert at reading databases, tables and structured data. "
        "You can calculate statistics, find patterns and explain data. "
        "When answering, reference specific data points and numbers."
    ),
    "general": (
        "You are a helpful document analysis assistant. "
        "You answer questions based on the uploaded documents. "
        "You are thorough, precise and analytical."
    )
}


# ------------------------------------------------------------------
# Instruction templates for different question types
# ------------------------------------------------------------------
INSTRUCTION_TEMPLATES = {
    "summary": (
        "The user wants a summary. "
        "Provide a clear and concise summary of the relevant information. "
        "Cover the key points without unnecessary detail. "
        "Structure the summary with bullet points if there are multiple points."
    ),
    "compare": (
        "The user wants a comparison. "
        "Identify the items being compared. "
        "List similarities and differences clearly. "
        "Use a structured format to make the comparison easy to read."
    ),
    "analyze": (
        "The user wants analysis. "
        "Think step by step: "
        "Step 1: Identify the key data points or facts. "
        "Step 2: Look for patterns, trends or relationships. "
        "Step 3: Draw conclusions based on the evidence. "
        "Step 4: Provide your analytical insight. "
        "Show your reasoning clearly."
    ),
    "explain": (
        "The user wants an explanation. "
        "Explain in simple, clear language. "
        "Avoid jargon unless you also explain it. "
        "Use examples if helpful. "
        "If you explained something before, rephrase it differently this time."
    ),
    "general": (
        "Answer the question directly and clearly. "
        "Be specific and reference the document content. "
        "If the question is vague, provide a thorough answer covering likely interpretations."
    )
}


# ------------------------------------------------------------------
# Chain of thought templates for complex questions
# ------------------------------------------------------------------
CHAIN_OF_THOUGHT = {
    "analyze": (
        "\n\nThink through this step by step before answering:\n"
        "1. What are the relevant facts from the documents?\n"
        "2. What patterns or trends do you see?\n"
        "3. What conclusions can you draw?\n"
        "4. Present your analysis clearly."
    ),
    "compare": (
        "\n\nThink through this step by step before answering:\n"
        "1. What are the items being compared?\n"
        "2. What are the key attributes to compare?\n"
        "3. How do they differ on each attribute?\n"
        "4. Present the comparison clearly."
    )
}


# ------------------------------------------------------------------
# Main function: Build the full prompt
# ------------------------------------------------------------------
def build_prompt(question, context, sources, chat_history):
    """
    Build a complete prompt with:
        - Role based system message
        - Instruction template
        - Chain of thought (if needed)
        - Context injection
        - Chat history
        - User question

    Returns:
        system_message (str): the system prompt
        user_message (str): the user prompt with context
    """

    # Detect types
    question_type = detect_question_type(question)
    doc_type = detect_document_type(context, sources)

    logger.info(f"Question type: {question_type}, Document type: {doc_type}")

    # 1. Role based system message
    role_prompt = ROLE_PROMPTS.get(doc_type, ROLE_PROMPTS["general"])

    # 2. Instruction template
    instruction = INSTRUCTION_TEMPLATES.get(question_type, INSTRUCTION_TEMPLATES["general"])

    # 3. Chain of thought (only for complex question types)
    cot = CHAIN_OF_THOUGHT.get(question_type, "")

    # 4. Build system message
    system_message = (
        f"{role_prompt}\n\n"
        f"Instructions: {instruction}\n\n"
        f"Rules:\n"
        f"- Only use information from the provided context.\n"
        f"- If the answer is not in the context, say so clearly.\n"
        f"- Be precise with numbers and data.\n"
        f"- Refer to previous conversation when the user follows up."
    )

    # 5. Build user message with context injection
    source_list = ", ".join(sources)

    user_message = (
        f"Document context (from: {source_list}):\n"
        f"---\n"
        f"{context}\n"
        f"---\n"
        f"{cot}\n"
        f"Question: {question}"
    )

    return system_message, user_message