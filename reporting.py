"""Result statistics and successful-proof export."""

import os
import re
from typing import Any, Dict


def save_successful_proofs(results: Dict[str, Any], output_dir: str):
    """Save each successfully verified proof as a separate .txt file."""
    os.makedirs(output_dir, exist_ok=True)
    saved_count = 0
    for name, res in results.items():
        if isinstance(res, dict) and res.get("theorem_solved") and res.get("proof_text"):

            safe_name = re.sub(r'[/\\:*?"<>|]', '_', name)
            filepath = os.path.join(output_dir, f"{safe_name}.txt")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(res["proof_text"])
            saved_count += 1
    print(f"Saved {saved_count} successful proofs to {output_dir}/")


def print_overall_statistics(results: Dict[str, Any], max_refine_iters: int = 20):
    normal_results = {}
    abnormal_results = {}
    for name, res in results.items():
        if not isinstance(res, dict):
            abnormal_results[name] = res
            continue
        if res.get("msg"):
            abnormal_results[name] = res
        else:
            normal_results[name] = res

    abnormal_count = len(abnormal_results)
    theorem_count = len(normal_results)
    theorems_solved = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_reasoning_tokens = 0
    total_cost = 0.0

    total_gpt_calls = 0
    total_gpt_input = 0
    total_gpt_output = 0
    total_gpt_reasoning = 0
    total_gpt_cost = 0.0

    total_ds_calls = 0
    total_ds_input = 0
    total_ds_output = 0
    total_ds_reasoning = 0
    total_ds_cost = 0.0

    total_compare_calls = 0
    total_compare_input = 0
    total_compare_output = 0
    total_compare_reasoning = 0
    total_compare_cost = 0.0

    source_counts = {}

    for _, res in normal_results.items():
        if res.get("theorem_solved", False):
            theorems_solved += 1
            src = res.get("successful_source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        total_input_tokens += res.get("total_input_tokens", 0)
        total_output_tokens += res.get("total_output_tokens", 0)
        total_reasoning_tokens += res.get("total_reasoning_tokens", 0)
        total_cost += res.get("total_cost", 0.0)

        total_gpt_calls += res.get("gpt_proof_calls", 0)
        total_gpt_input += res.get("gpt_proof_input_tokens", 0)
        total_gpt_output += res.get("gpt_proof_output_tokens", 0)
        total_gpt_reasoning += res.get("gpt_proof_reasoning_tokens", 0)
        total_gpt_cost += res.get("gpt_proof_cost", 0.0)

        total_ds_calls += res.get("deepseek_proof_calls", 0)
        total_ds_input += res.get("deepseek_proof_input_tokens", 0)
        total_ds_output += res.get("deepseek_proof_output_tokens", 0)
        total_ds_reasoning += res.get("deepseek_proof_reasoning_tokens", 0)
        total_ds_cost += res.get("deepseek_proof_cost", 0.0)

        total_compare_calls += res.get("compare_calls", 0)
        total_compare_input += res.get("compare_input_tokens", 0)
        total_compare_output += res.get("compare_output_tokens", 0)
        total_compare_reasoning += res.get("compare_reasoning_tokens", 0)
        total_compare_cost += res.get("compare_cost", 0.0)

    pass_rate = theorems_solved / theorem_count if theorem_count else 0.0
    total_llm_calls = total_gpt_calls + total_ds_calls + total_compare_calls
    total_sampled_proof_calls = total_gpt_calls + total_ds_calls
    avg_llm_calls = total_llm_calls / theorem_count if theorem_count else 0.0
    avg_sampled_proof_calls = total_sampled_proof_calls / theorem_count if theorem_count else 0.0
    avg_gpt_calls = total_gpt_calls / theorem_count if theorem_count else 0.0
    avg_ds_calls = total_ds_calls / theorem_count if theorem_count else 0.0
    avg_compare_calls = total_compare_calls / theorem_count if theorem_count else 0.0

    print("\n" + "=" * 80)
    print("Overall Statistics (DeepSeek + GPT Compare + Stagnation Resample)")
    print("=" * 80)
    print(f"Total nodes:          {theorem_count + abnormal_count}")
    print(f"Abnormal (skipped):   {abnormal_count}")
    if abnormal_results:
        for name, res in abnormal_results.items():
            msg = res.get("msg", "unknown") if isinstance(res, dict) else str(res)
            print(f"    - {name}: {msg}")
    print(f"Normal theorems:      {theorem_count}")
    print(f"Theorems solved:      {theorems_solved}")
    print(f"Pass rate:            {pass_rate:.2%}")
    print("-" * 80)
    print("Success Source Breakdown:")
    for src in ["auto_solve", "initial_deepseek", "initial_gpt",
                "refine_deepseek", "refine_gpt",
                "resample_deepseek", "resample_gpt"]:
        count = source_counts.get(src, 0)
        if count > 0:
            print(f"    {src:25s}: {count}")
    for src, count in source_counts.items():
        if src not in ["auto_solve", "initial_deepseek", "initial_gpt",
                       "refine_deepseek", "refine_gpt",
                       "resample_deepseek", "resample_gpt"]:
            print(f"    {src:25s}: {count}  (other)")
    print("-" * 80)
    print(f"Total LLM calls:      {total_llm_calls}")
    print(f"Avg LLM calls:        {avg_llm_calls:.2f}")
    print(f"Total sampled proofs: {total_sampled_proof_calls}")
    print(f"Avg sampled proofs:   {avg_sampled_proof_calls:.2f}")
    print("-" * 80)
    print("Resource Usage (total, all calls combined):")
    print(f"  Total input tokens:     {total_input_tokens:,}")
    print(f"  Total output tokens:    {total_output_tokens:,}")
    print(f"  Total reasoning tokens: {total_reasoning_tokens:,}")
    print(f"  Estimated API cost (no local inference):             ${total_cost:.4f}")
    print("-" * 80)
    print("LLM Calls Breakdown:")
    print()
    print("  1) GPT Proof Calls (initial gen + refine + resample):")
    print(f"     Total calls:         {total_gpt_calls}")
    print(f"     Avg calls/theorem:   {avg_gpt_calls:.2f}")
    print(f"     Total cost:          ${total_gpt_cost:.4f}")
    print()
    print("  2) DeepSeek Proof Calls (initial gen + resample):")
    print(f"     Total calls:         {total_ds_calls}")
    print(f"     Avg calls/theorem:   {avg_ds_calls:.2f}")
    print()
    print("  3) GPT Compare Calls:")
    print(f"     Total calls:         {total_compare_calls}")
    print(f"     Avg calls/theorem:   {avg_compare_calls:.2f}")
    print(f"     Total cost:          ${total_compare_cost:.4f}")
    print("=" * 80)
