"""Prompts for generation, repair, and proof comparison."""


def prover_full_context_prompt_func(lean_context: str, decl: str) -> str:

    lean_code = lean_context + "\n" + decl + "\n"
    prompt = (
        "Complete the following Lean 4 code with explanatory comments preceding each line of code:\n\n```lean4\n" + lean_code
    )
    return prompt


def full_context_prompt_func(lean_context: str, decl: str, few_shot: bool = False) -> str:

    if few_shot:
        with open("full_proof_context.txt", "r", encoding="utf-8") as f:
            content = f.read()
        prompt = content.replace("{}", lean_context, 1).replace("{}", decl, 1)
        prompt += "\nStart your response like this:\n```lean4\n:= by"
    else:
        prompt = (
            "Here is the Lean 4 context:\n```lean4\n" + lean_context + "\n```"
            "\n\nUsing this context, prove the following theorem in Lean 4.\n"
            f"Theorem statement:\n{decl}"
            "\nStart your response like this:\n```lean4\n:= by"
        )
    return prompt


def repair_context_prompt_func(lean_context: str, wrong_proof: str, errors: str, decl: str) -> str:
    prompt = (
        "Here is the Lean 4 context:\n```lean4\n" + lean_context + "\n```"
        f"\nHere is the target theorem statement:\n{decl}"
        "\n\nHere is an attempted Lean 4 proof body but contains errors:\n```lean4\n" + wrong_proof + "\n```"
        "\nThe proof has the following errors:\n"
        f"{errors}\n"
        "\nBased on the context and errors, provide a new corrected Lean 4 proof."
        "\nPlease output a new lean4 proof ONLY, no other explanations."
    )
    return prompt


def repair_context_prompt_func_gemini(lean_context: str, wrong_proof: str, errors: str, decl: str) -> str:
    prompt = (
        "Here is the Lean 4 context:\n```lean4\n" + lean_context + "\n```"
        f"\nHere is the target theorem statement:\n{decl}"
        "\n\nHere is an attempted Lean 4 proof body but contains errors:\n```lean4\n" + wrong_proof + "\n```"
        "\nThe proof has the following errors:\n"
        f"{errors}\n"
        "\nBased on the context and errors, provide a new corrected Lean 4 proof."
        "\nPlease directly output a new lean4 proof body ONLY, no theorem declaration and other explanations."
        "\nPlease output a proof body ONLY (the tactics after ':= by'), do NOT include the theorem declaration or ':= by'."
    )
    return prompt


def two_proof_compare(
    wrong_proof1: str,
    errors1: str,
    wrong_proof2: str,
    errors2: str,
    decl: str,
    lean_context: str = None,
) -> str:
    prompt = (
        "You are an expert in Lean 4. Your task is to compare two proofs that both failed verification, "
        "select the one that has better quality and is more suitable as the starting point for refinement.\n\n"
    )

    if lean_context:
        prompt += (
            "Here is the Lean 4 context:\n"
            "```lean4\n" + lean_context + "\n```\n\n"
        )

    prompt += (
        "Here is the theorem declaration:\n"
        "```lean4\n" + decl + "\n```\n\n"
    )

    prompt += (
        "--- Proof A ---\n"
        "```lean4\n" + wrong_proof1 + "\n```\n"
        "Errors for Proof A:\n" + errors1 + "\n\n"
        "--- Proof B ---\n"
        "```lean4\n" + wrong_proof2 + "\n```\n"
        "Errors for Proof B:\n" + errors2 + "\n\n"
    )

    prompt += (
        "Compare the two proofs above. Consider the following criteria:\n"
        "Fixability: Which error message is easier to resolve?\n"
        "Progress: Which proof leaves fewer or simpler remaining subgoals?\n"
        "Strategy: Which proof uses a sounder overall approach?\n\n"
        'Respond with ONLY this JSON: {"choice": "A"} or {"choice": "B"}, no other text.'
    )

    return prompt
