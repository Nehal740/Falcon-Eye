"""Check the AI assistant connection from the command line (no browser needed).

Run from the project folder, with your virtual environment active:
    python scripts/check_llm.py

It reads LLM_* from your .env file, lists the models your key can use, sends
one small test question and tells you what to change if something is wrong.
The key itself is never printed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import assistant_service as svc  # noqa: E402
from config import settings  # noqa: E402


def main() -> int:
    print(f"Provider : {settings.llm_provider}")
    print(f"Address  : {settings.llm_base_url or '(provider default)'}")
    print(f"Model    : {settings.llm_model}")
    print(f"Key      : {'set' if settings.llm_enabled else 'NOT SET'}")
    print("\nTesting (this takes a few seconds)...\n")
    result = svc.diagnose()
    if result["list_error"]:
        print(f"Model list : could not load - {result['list_error']}")
    elif result["models"]:
        print("Models your key can use:")
        for name in result["models"]:
            mark = "  <- you are using this" if name == settings.llm_model else ""
            print(f"  {name}{mark}")
        if result["suggested_model"]:
            print(f"\nSuggested  : LLM_MODEL={result['suggested_model']}")
    test = result["test"]
    if test:
        if test["ok"]:
            print(f"\nTest answer: {test['sample']}")
        else:
            print(f"\nTest failed: {test['message']}")
            if test["detail"]:
                print(f"Provider says: {test['detail']}")
    print(f"\nResult     : {'OK' if result['ok'] else 'NOT WORKING'}")
    print(f"Next step  : {result['next_step']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
