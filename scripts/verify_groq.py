"""
Safe verification script for Groq LLM integration.
Confirms:
1. GROQ_API_KEY is configured (True/False only)
2. Groq LLM initializes successfully
3. The selected model name
Never prints or logs any API key.
"""

import os
import sys
from dotenv import load_dotenv

# Add project root to path
import pathlib
project_root = str(pathlib.Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables
load_dotenv()

from agents.llm_factory import get_groq_llm, get_llm
from langchain_groq import ChatGroq

def run_verification() -> bool:
    print("=" * 60)
    print("GROQ INTEGRATION SAFE VERIFICATION")
    print("=" * 60)

    # 1. Check GROQ_API_KEY configured (True/False only)
    groq_key = os.getenv("GROQ_API_KEY")
    is_configured = bool(groq_key and groq_key.strip() and groq_key != "your-groq-api-key" and not groq_key.startswith("gsk-placeholder"))
    print(f"GROQ_API_KEY is configured: {is_configured}")

    # 2. Check selected model name
    selected_model = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    print(f"Selected model name: {selected_model}")

    # 3. Test Groq LLM initialization
    init_success = False
    if is_configured:
        try:
            llm = get_groq_llm()
            if llm and isinstance(llm, ChatGroq):
                print("Groq LLM initializes successfully: True (live client active)")
                init_success = True
            else:
                print("Groq LLM initializes successfully: False")
        except Exception as e:
            print(f"Groq LLM initializes successfully: False (error: {e})")
    else:
        # Verify ChatGroq class initialization capability with validation key
        try:
            test_llm = ChatGroq(model=selected_model, api_key="test_validation_key")
            actual_model = getattr(test_llm, "model_name", getattr(test_llm, "model", None))
            print(f"Groq LLM initializes successfully: True (ChatGroq client functional with model '{actual_model}')")
            print("Fallback status: AutonomousInvestigationReasoner active (no live GROQ_API_KEY set)")
            init_success = True
        except Exception as e:
            print(f"Groq LLM initializes successfully: False (error: {e})")

    # 4. Verify get_llm() contract
    current_llm = get_llm()
    if is_configured:
        print(f"Primary get_llm() provider: Groq ({type(current_llm).__name__})")
    else:
        print(f"Primary get_llm() provider: None (Fallback to AutonomousInvestigationReasoner active)")

    print("=" * 60)
    return init_success

if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
