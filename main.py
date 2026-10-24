"""Command-line entry point, retaining the original arguments and workflow."""

import argparse
import json
import os

from datasets import load_dataset

from search import Adaptive_Search, _make_empty_totals, parse_ab_choice, select_better_proof
from prompts import two_proof_compare
from proof_utils import get_errors_for_proof, verify_proof
from reporting import print_overall_statistics, save_successful_proofs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="DeepSeek + GPT: dual-model initial & resample, iterative refine with compare (A/B) + stagnation-triggered resample"
    )
    parser.add_argument("--project-name", type=str, default="Seymour")
    parser.add_argument("--max-refine", type=int, default=12,
                        help="Maximum refinement iterations")
    parser.add_argument("--stagnation-threshold", type=int, default=3,
                        help="Consecutive no-improvement rounds before triggering resample")
    parser.add_argument("--split", type=str, choices=["valid", "test"], default="test")
    parser.add_argument("--lean-context", action="store_true", default=True,
                        help="Include Lean context in comparison prompts")
    args = parser.parse_args()

    if args.project_name == "ConNF":
        dataset = load_dataset("l3lab/miniCTX-v2", "ConNF", split=args.split)
        project_dir = "./traced_repos/con-nf_51c38ad244870b8b1f40b8272b281678397dfa4f/con-nf"
    elif args.project_name == "FLT":
        dataset = load_dataset("l3lab/miniCTX-v2", "FLT", split=args.split)
        project_dir = "./traced_repos/FLT_4a97c893071433d0d39cbf5261d0877f864c2189/FLT"
    elif args.project_name == "HepLean":
        dataset = load_dataset("l3lab/miniCTX-v2", "HepLean", split=args.split)
        project_dir = "./traced_repos/PhysLean_fe082d93c2775beee6634b24b34c8482a02ba8a8/PhysLean"
    elif args.project_name == "foundation":
        dataset = load_dataset("l3lab/miniCTX-v2", "foundation", split=args.split)
        project_dir = "./traced_repos/Foundation_54324e6e009f0d0a288897312d3feb1c0165ad19/Foundation"
    elif args.project_name == "carleson":
        dataset = load_dataset("l3lab/miniCTX-v2", "carleson", split=args.split)
        project_dir = "./traced_repos/carleson_a5d265f109105809de4aaff16776b7c16b1c0bd5/carleson"
    elif args.project_name == "Seymour":
        dataset = load_dataset("l3lab/miniCTX-v2", "Seymour", split=args.split)
        project_dir = "./traced_repos/seymour_27c0384977032b693daca8c4fcfc5cc274e1f2d6/seymour"
    elif args.project_name == "mathlib":
        dataset = load_dataset("l3lab/miniCTX-v2", "mathlib", split=args.split)
        project_dir = "./traced_repos/mathlib4_v4.16.0/mathlib4"
    else:
        raise ValueError(f"Unknown project name: {args.project_name}")

    agent = Adaptive_Search(
        dataset=dataset,
        project_dir=project_dir,
        max_refine_iters=args.max_refine,
        stagnation_threshold=args.stagnation_threshold,
        use_lean_context=args.lean_context,
    )

    print(f"\nConfiguration:")
    print(f"  Project:              {args.project_name}")
    print(f"  Split:                {args.split}")
    print(f"  Total theorems:       {len(dataset)}")
    print(f"  Max refine iters:     {args.max_refine}")
    print(f"  Stagnation threshold: {args.stagnation_threshold}")
    print(f"  Lean context:         {args.lean_context}")

    results = agent.prove_batch()

    #base_dir = f"dual_model_compare_stagnation_t{args.stagnation_threshold}"
    #os.makedirs(base_dir, exist_ok=True)

    # Save full results JSON
    #output_file = f"{base_dir}/results_{args.project_name}_{args.split}.json"
    #with open(output_file, "w", encoding="utf-8") as f:
    #    json.dump(results, f, indent=2, default=str)
    #print(f"\nResults saved to {output_file}")

    # Save successful proofs as individual .txt files
    #proof_dir = f"{base_dir}/proofs_{args.project_name}_{args.split}"
    #save_successful_proofs(results, proof_dir)

    print_overall_statistics(results, max_refine_iters=args.max_refine)
