"""Adaptive proof search and candidate selection."""

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from lean_interact import AutoLeanServer, LeanREPLConfig, LocalProject
from lean_interact.interface import Command, LeanError
from rlm_eval.data_processing.lean_utils import trim_comments_end

from prompts import (
    full_context_prompt_func,
    prover_full_context_prompt_func,
    repair_context_prompt_func,
    two_proof_compare,
)
from proof_utils import compress_context_from_middle_fast, get_errors_for_proof, verify_proof
from utils_api import gpt5_mini_response, prover_response
from utils_auto_close import auto_solve


def parse_ab_choice(response: str) -> int:
    text = response.strip()

    try:
        obj = json.loads(text)
        if obj.get("choice", "").upper() in ("A", "B"):
            return 1 if obj["choice"].upper() == "A" else 2
    except json.JSONDecodeError:
        pass

    m = re.search(r'\{[^}]*"choice"\s*:\s*"([AB])"\s*\}', text, re.IGNORECASE)
    if m:
        return 1 if m.group(1).upper() == "A" else 2

    clean = re.sub(r'[^AB]', '', text.upper())
    if len(clean) == 1:
        return 1 if clean == "A" else 2

    print("llm comparison call extraction falied!")

    return 1


def select_better_proof(
    prompt: str,
) -> Tuple[int, int, int, int, float]:
    try:
        response, input_tok, output_tok, reasoning_tok, cost = gpt5_mini_response(prompt)
        if response is not None:
            choice = parse_ab_choice(response)
            return choice, input_tok, output_tok, reasoning_tok, cost
    except Exception as e:
        print(f"Proof comparison failed: {e}, defaulting to proof A")
    return 1, 0, 0, 0, 0.0


def _make_empty_totals() -> Dict[str, Any]:
    return {
        "total_input": 0, "total_output": 0,
        "total_reasoning": 0, "total_cost": 0.0,
        "gpt_proof_calls": 0,
        "gpt_proof_input": 0, "gpt_proof_output": 0,
        "gpt_proof_reasoning": 0, "gpt_proof_cost": 0.0,
        "deepseek_proof_calls": 0,
        "deepseek_proof_input": 0, "deepseek_proof_output": 0,
        "deepseek_proof_reasoning": 0, "deepseek_proof_cost": 0.0,
        "compare_calls": 0,
        "compare_input": 0, "compare_output": 0,
        "compare_reasoning": 0, "compare_cost": 0.0,
    }


class Adaptive_Search:

    def __init__(
        self,
        dataset,
        project_dir: str,
        max_refine_iters: int = 16,
        stagnation_threshold: int = 4,
        use_lean_context: bool = False,
    ):
        self.dataset = dataset
        self.project_dir = project_dir
        self.repl_config = LeanREPLConfig(project=LocalProject(project_dir))
        self.max_refine_iters = max_refine_iters
        self.stagnation_threshold = stagnation_threshold
        self.use_lean_context = use_lean_context

    # ---- Token accumulation helpers ----

    def _accumulate_gpt_proof(self, totals, in_tok, out_tok, reas_tok, cost):
        totals["total_input"] += in_tok
        totals["total_output"] += out_tok
        totals["total_reasoning"] += reas_tok
        totals["total_cost"] += cost
        totals["gpt_proof_calls"] += 1
        totals["gpt_proof_input"] += in_tok
        totals["gpt_proof_output"] += out_tok
        totals["gpt_proof_reasoning"] += reas_tok
        totals["gpt_proof_cost"] += cost

    def _accumulate_deepseek_proof(self, totals, in_tok, out_tok, reas_tok, cost):
        totals["total_input"] += in_tok
        totals["total_output"] += out_tok
        totals["total_reasoning"] += reas_tok
        totals["total_cost"] += cost
        totals["deepseek_proof_calls"] += 1
        totals["deepseek_proof_input"] += in_tok
        totals["deepseek_proof_output"] += out_tok
        totals["deepseek_proof_reasoning"] += reas_tok
        totals["deepseek_proof_cost"] += cost

    def _accumulate_compare(self, totals, cmp_in, cmp_out, cmp_reas, cmp_cost):
        totals["total_input"] += cmp_in
        totals["total_output"] += cmp_out
        totals["total_reasoning"] += cmp_reas
        totals["total_cost"] += cmp_cost
        totals["compare_calls"] += 1
        totals["compare_input"] += cmp_in
        totals["compare_output"] += cmp_out
        totals["compare_reasoning"] += cmp_reas
        totals["compare_cost"] += cmp_cost

    # ---- Proof generation ----

    def _generate_proof(
        self, model_name: str, original_ctx: str, decl: str
    ) -> Tuple[Optional[str], int, int, int, float]:
        if model_name == "deepseek":
            compressed_ctx = compress_context_from_middle_fast(original_ctx)
            prompt = prover_full_context_prompt_func(compressed_ctx, decl)
            try:
                proofs, in_list, out_list, reas_list, cost_list = prover_response(prompt, nb_samples=1)
                proof = proofs[0] if proofs else None
                return (
                    proof,
                    sum(in_list) if in_list else 0,
                    sum(out_list) if out_list else 0,
                    sum(reas_list) if reas_list else 0,
                    sum(cost_list) if cost_list else 0,
                )
            except Exception as e:
                print(f"DeepSeek generation failed: {e}")
                return None, 0, 0, 0, 0.0
        else:
            prompt = full_context_prompt_func(original_ctx, decl)
            try:
                proof, in_tok, out_tok, reas_tok, cost = gpt5_mini_response(prompt)
                return proof, in_tok, out_tok, reas_tok, cost
            except Exception as e:
                print(f"GPT generation failed: {e}")
                return None, 0, 0, 0, 0.0

    def _accumulate_proof_by_model(self, totals, model_name, in_tok, out_tok, reas_tok, cost):
        if model_name == "deepseek":
            self._accumulate_deepseek_proof(totals, in_tok, out_tok, reas_tok, cost)
        else:
            self._accumulate_gpt_proof(totals, in_tok, out_tok, reas_tok, cost)

    # ---- Main proving logic ----

    def prove_one_node(self, lean_server, item: Dict[str, Any]) -> Dict[str, Any]:
        node_label = item["theoremName"]
        decl_sig = item["theoremStatement"]
        decl = decl_sig + " := by"
        original_ctx = item["srcContext"]

        print(f"\n{'='*80}")
        print(f"Processing: {node_label}")
        print(f"{'='*80}")

        # ---------- prepare context ----------
        trimmed_ctx = trim_comments_end(original_ctx).rstrip()
        if "\n" in trimmed_ctx:
            ctx_body, last_line = trimmed_ctx.rsplit("\n", 1)
        else:
            ctx_body = ""
            last_line = trimmed_ctx
        if last_line.endswith(" in"):
            ctx_text = ctx_body + "\n" + last_line[:-3]
        else:
            ctx_text = original_ctx

        if not ctx_text.strip():
            ctx_text = "-- context stub"

        # ---------- validate context ----------
        try:
            ctx_out = lean_server.run(
                Command(cmd=ctx_text),
                add_to_session_cache=False,
                timeout=360,
            )
            if isinstance(ctx_out, LeanError) or not ctx_out.lean_code_is_valid():
                return self._fail_result(node_label, f"Invalid context: {ctx_out}")
            context_env = ctx_out.env
        except Exception as e:
            return self._fail_result(node_label, f"context error: {e}")

        # ---------- verify theorem can be opened ----------
        open_out = lean_server.run(
            Command(cmd=decl + "\n" + "sorry", env=context_env),
            timeout=120,
        )
        if isinstance(open_out, LeanError) or not open_out.sorries:
            return self._fail_result(node_label, f"Failed to open proof: {open_out}")

        # ---------- AutoSolve ----------
        print(f"  [AutoSolve] Attempting cheap tactic-based closing...")
        try:
            auto_result = auto_solve(
                lean_server=lean_server,
                context_env=context_env,
                decl=decl,
                proof_text="",
                errors=[],
                timeout=120,
            )
            if auto_result.get("success"):
                auto_proof_text = auto_result["proof_text"]
                cmd_out = lean_server.run(
                    Command(cmd=auto_proof_text, env=context_env),
                    timeout=120,
                )
                if not isinstance(cmd_out, LeanError) and cmd_out.lean_code_is_valid(allow_sorry=False):
                    closing = auto_result.get("closing_tactic", "unknown")
                    print(f"  ✓ AutoSolve succeeded with tactic: {closing}")
                    zero_totals = _make_empty_totals()
                    return self._success_result(
                        node_label, 0, "auto_solve",
                        [{"iteration": 0, "event": "auto_solve", "verified": True,
                          "closing_tactic": closing}],
                        zero_totals,
                        proof_text=auto_proof_text,  
                    )
        except Exception as e:
            print(f"  [AutoSolve] Failed: {e}, continuing to LLM generation...")

        totals = _make_empty_totals()
        iteration_log: List[Dict[str, Any]] = []
        cmp_lean_context = original_ctx if self.use_lean_context else None

        # ========== Initial Generation: DeepSeek + GPT ==========

        print("[GPT] Generating initial proof...")
        gpt_proof, gpt_in, gpt_out, gpt_reas, gpt_cost = self._generate_proof("gpt", original_ctx, decl)
        self._accumulate_gpt_proof(totals, gpt_in, gpt_out, gpt_reas, gpt_cost)

        if gpt_proof and verify_proof(lean_server, gpt_proof, decl, context_env):
            print("  ✓ GPT proof verified on first attempt!")
            return self._success_result(
                node_label, 1, "initial_gpt", iteration_log, totals,
                proof_text=gpt_proof,  
            )

        print("[DeepSeek] Generating initial proof...")
        ds_proof, ds_in, ds_out, ds_reas, ds_cost = self._generate_proof("deepseek", original_ctx, decl)
        self._accumulate_deepseek_proof(totals, ds_in, ds_out, ds_reas, ds_cost)

        if ds_proof and verify_proof(lean_server, ds_proof, decl, context_env):
            print("  ✓ DeepSeek proof verified on first attempt!")
            return self._success_result(
                node_label, 1, "initial_deepseek", iteration_log, totals,
                proof_text=ds_proof,  
            )



        
        if ds_proof and gpt_proof:
            ds_src, ds_errors, _ = get_errors_for_proof(lean_server, ds_proof, decl, context_env)
            gpt_src, gpt_errors, _ = get_errors_for_proof(lean_server, gpt_proof, decl, context_env)

            cmp_prompt = two_proof_compare(
                ds_src, ds_errors, gpt_src, gpt_errors, decl, lean_context=cmp_lean_context,
            )
            choice, cmp_in, cmp_out, cmp_reas, cmp_cost = select_better_proof(cmp_prompt)
            self._accumulate_compare(totals, cmp_in, cmp_out, cmp_reas, cmp_cost)

            if choice == 1:
                current_proof, current_src, current_errors = ds_proof, ds_src, ds_errors
                current_source = "deepseek"
            else:
                current_proof, current_src, current_errors = gpt_proof, gpt_src, gpt_errors
                current_source = "gpt"
            initial_winner = current_source
            print(f"  Selected proof {'A (DeepSeek)' if choice == 1 else 'B (GPT)'} as starting point.")
        elif ds_proof:
            current_proof = ds_proof
            current_src, current_errors, _ = get_errors_for_proof(lean_server, ds_proof, decl, context_env)
            current_source = "deepseek"
            initial_winner = "deepseek"
        elif gpt_proof:
            current_proof = gpt_proof
            current_src, current_errors, _ = get_errors_for_proof(lean_server, gpt_proof, decl, context_env)
            current_source = "gpt"
            initial_winner = "gpt"
        else:
            print("  ✗ Both models failed to generate any proof.")
            return self._fail_result(node_label, "Both models returned None")

        iteration_log.append({
            "iteration": 0, "source": current_source,
            "initial_winner": initial_winner, "verified": False,
        })

        consecutive_no_improvement = 0

        # ========== Refine Loop ==========
        for k in range(1, self.max_refine_iters + 1):
            print(f"\n  [Iter {k}/{self.max_refine_iters}]")

            
            if consecutive_no_improvement >= self.stagnation_threshold or current_errors == "No errors found.":
                print(f"    [Resample] Stagnation reached ({consecutive_no_improvement} "
                      f">= {self.stagnation_threshold}), generating fresh proofs from both models...")

                other_model = "gpt" if initial_winner == "deepseek" else "deepseek"
                resample_order = [initial_winner, other_model]

                resample_proofs = {}
                for model in resample_order:
                    print(f"    [Resample] Generating from {model}...")
                    rs_proof, rs_in, rs_out, rs_reas, rs_cost = self._generate_proof(
                        model, original_ctx, decl
                    )
                    self._accumulate_proof_by_model(totals, model, rs_in, rs_out, rs_reas, rs_cost)

                    if rs_proof is not None:
                        if verify_proof(lean_server, rs_proof, decl, context_env):
                            source_label = f"resample_{model}"
                            print(f"      ✓ Resampled proof from {model} verified!")
                            iteration_log.append({
                                "iteration": k, "event": "resample_verified",
                                "verified": True, "resample_model": model,
                            })
                            return self._success_result(
                                node_label, k + 1, source_label, iteration_log, totals,
                                proof_text=rs_proof,  
                            )
                        resample_proofs[model] = rs_proof
                    else:
                        print(f"      {model} resample returned None.")

                if len(resample_proofs) == 2:
                    m1, m2 = resample_order
                    p1_src, p1_errors, _ = get_errors_for_proof(
                        lean_server, resample_proofs[m1], decl, context_env
                    )
                    p2_src, p2_errors, _ = get_errors_for_proof(
                        lean_server, resample_proofs[m2], decl, context_env
                    )
                    cmp_prompt = two_proof_compare(
                        p1_src, p1_errors, p2_src, p2_errors, decl, lean_context=cmp_lean_context,
                    )
                    choice, cmp_in, cmp_out, cmp_reas, cmp_cost = select_better_proof(cmp_prompt)
                    self._accumulate_compare(totals, cmp_in, cmp_out, cmp_reas, cmp_cost)

                    if choice == 1:
                        current_proof = resample_proofs[m1]
                        current_src, current_errors = p1_src, p1_errors
                        current_source = m1
                    else:
                        current_proof = resample_proofs[m2]
                        current_src, current_errors = p2_src, p2_errors
                        current_source = m2
                    print(f"      Adopted resampled proof from {current_source} (compare winner).")
                    iteration_log.append({
                        "iteration": k, "event": "resample_compare_adopted",
                        "adopted_model": current_source, "verified": False,
                    })
                elif len(resample_proofs) == 1:
                    model = list(resample_proofs.keys())[0]
                    current_proof = resample_proofs[model]
                    current_src, current_errors, _ = get_errors_for_proof(
                        lean_server, current_proof, decl, context_env
                    )
                    current_source = model
                    print(f"      Adopted resampled proof from {model} (only one available).")
                    iteration_log.append({
                        "iteration": k, "event": "resample_single_adopted",
                        "adopted_model": model, "verified": False,
                    })
                else:
                    print(f"      Both resamples returned None, keeping current proof.")
                    iteration_log.append({
                        "iteration": k, "event": "resample_both_none",
                    })

                consecutive_no_improvement = 0
                continue

            # ---- Refine: GPT repairs current proof ----
            repair_prompt = repair_context_prompt_func(
                original_ctx, current_src, current_errors, decl
            )
            try:
                refined_proof, r_in, r_out, r_reas, r_cost = gpt5_mini_response(repair_prompt)
                self._accumulate_gpt_proof(totals, r_in, r_out, r_reas, r_cost)
            except Exception as e:
                print(f"    Repair call failed: {e}")
                iteration_log.append({"iteration": k, "event": "repair_call_failed"})
                consecutive_no_improvement += 1
                continue

            if refined_proof is None:
                print("    Repair returned None, skipping.")
                iteration_log.append({"iteration": k, "event": "repair_returned_none"})
                consecutive_no_improvement += 1
                continue

            if verify_proof(lean_server, refined_proof, decl, context_env):
                source_label = f"refine_{current_source}"
                print(f"    ✓ Refined proof verified at iteration {k}! (source: {source_label})")
                iteration_log.append({"iteration": k, "verified": True})
                return self._success_result(
                    node_label, k + 1, source_label, iteration_log, totals,
                    proof_text=refined_proof,  
                )

            # ---- Compare current (A) vs refined (B) ----
            refined_src, refined_errors, _ = get_errors_for_proof(
                lean_server, refined_proof, decl, context_env
            )

            cmp_prompt = two_proof_compare(
                current_src, current_errors,
                refined_src, refined_errors,
                decl, lean_context=cmp_lean_context,
            )
            try:
                resp_text, cmp_in, cmp_out, cmp_reas, cmp_cost = gpt5_mini_response(cmp_prompt)
                self._accumulate_compare(totals, cmp_in, cmp_out, cmp_reas, cmp_cost)
            except Exception as e:
                print(f"    Compare call failed: {e}, defaulting to pick B")
                resp_text = '{"choice": "B"}'

            choice = parse_ab_choice(resp_text or "")

            if choice == 2:
                current_proof, current_src, current_errors = (
                    refined_proof, refined_src, refined_errors
                )
                consecutive_no_improvement = 0
                print(f"    Adopted refined proof (B).")
            else:
                consecutive_no_improvement += 1
                print(f"    Kept current proof (A). "
                      f"No improvement: {consecutive_no_improvement}/{self.stagnation_threshold}")

            iteration_log.append({
                "iteration": k, "verified": False,
                "event": "refine_compare",
                "choice": "A" if choice == 1 else "B",
                "consecutive_no_improvement": consecutive_no_improvement,
            })

        print(f"\n  ✗ Failed after {self.max_refine_iters} iterations.")
        return self._build_result(node_label, False, 0, None, iteration_log, totals)

    @staticmethod
    def _build_result(
        node_label, solved, pass_at_k, source, iteration_log, totals, msg=None, proof_text=None,
    ) -> Dict[str, Any]:
        result = {
            "node": node_label,
            "theorem_solved": solved,
            "pass_at_k": pass_at_k,
            "successful_source": source,
            "iteration_log": iteration_log,
            "total_input_tokens": totals.get("total_input", 0),
            "total_output_tokens": totals.get("total_output", 0),
            "total_reasoning_tokens": totals.get("total_reasoning", 0),
            "total_cost": totals.get("total_cost", 0.0),
            "gpt_proof_calls": totals.get("gpt_proof_calls", 0),
            "gpt_proof_input_tokens": totals.get("gpt_proof_input", 0),
            "gpt_proof_output_tokens": totals.get("gpt_proof_output", 0),
            "gpt_proof_reasoning_tokens": totals.get("gpt_proof_reasoning", 0),
            "gpt_proof_cost": totals.get("gpt_proof_cost", 0.0),
            "deepseek_proof_calls": totals.get("deepseek_proof_calls", 0),
            "deepseek_proof_input_tokens": totals.get("deepseek_proof_input", 0),
            "deepseek_proof_output_tokens": totals.get("deepseek_proof_output", 0),
            "deepseek_proof_reasoning_tokens": totals.get("deepseek_proof_reasoning", 0),
            "deepseek_proof_cost": totals.get("deepseek_proof_cost", 0.0),
            "compare_calls": totals.get("compare_calls", 0),
            "compare_input_tokens": totals.get("compare_input", 0),
            "compare_output_tokens": totals.get("compare_output", 0),
            "compare_reasoning_tokens": totals.get("compare_reasoning", 0),
            "compare_cost": totals.get("compare_cost", 0.0),
        }
        if msg:
            result["msg"] = msg
        if proof_text is not None:
            result["proof_text"] = proof_text
        return result

    @classmethod
    def _fail_result(cls, node_label, msg):
        return cls._build_result(node_label, False, 0, None, [], _make_empty_totals(), msg=msg)

    @classmethod
    def _success_result(cls, node_label, pass_at_k, source, iteration_log, totals, proof_text=None):
        return cls._build_result(
            node_label, True, pass_at_k, source, iteration_log, totals, proof_text=proof_text,
        )

    def prove_batch(self) -> Dict[str, Any]:
        server = AutoLeanServer(self.repl_config)
        results = {}
        MAX_RETRIES = 3
        RETRY_DELAY = 1

        for item in self.dataset:
            name = item["theoremName"]
            for attempt in range(MAX_RETRIES):
                try:
                    res = self.prove_one_node(server, item)
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        print(f"Attempt {attempt+1} failed: {e}. Retrying in {RETRY_DELAY}s...")
                        time.sleep(RETRY_DELAY)
                    else:
                        print(f"All {MAX_RETRIES} attempts failed: {e}")
                        res = self._fail_result(name, f"exception after {MAX_RETRIES} retries: {e}")
            results[name] = res
        return results
