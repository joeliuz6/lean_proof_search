import re
from typing import Any, Dict, Tuple, List
from lean_interact.interface import Command, LeanError, ProofStep


def extract_suggestions_from_response(response) -> List[str]:

    suggestions = []
    
    messages = getattr(response, "messages", [])
    for msg in messages:
        if getattr(msg, "severity", "") != "info":
            continue
        
        data = getattr(msg, "data", "") or ""
        
        match = re.match(r"Try this:\s*(.+)", data, re.DOTALL)
        if match:
            suggestion = match.group(1).strip()

            suggestion = suggestion.split('\n')[0].strip()
            if suggestion and "sorry" not in suggestion.lower():
                suggestions.append(suggestion)
            continue
        
        if data.startswith("Try these:"):
            bullets = re.findall(r"[•\-\*]\s*(.+?)(?=\n[•\-\*]|\n*$)", data, re.DOTALL)
            for b in bullets:
                b = b.strip().split('\n')[0].strip()
                if b and "sorry" not in b.lower():
                    suggestions.append(b)
            continue
    
    return suggestions

def can_auto_close(
    decl: str,
    proof_text: str,
    errors: list[dict],
) -> Tuple[bool, str, str]:
    """
    Returns:
        (can_close, valid_proof, reason)
    """
    
    if not proof_text or not proof_text.strip():
        return True, "", "no proof yet, try one-step close"
    
    if not errors:
        return True, proof_text, "no errors, try close with full proof"
    
    first_error = errors[0]
    error_msg = first_error["error_message"].lower()
    error_line = first_error["line"]
    

    if "unsolved goals" not in error_msg:
        return False, "", f"not closable: {error_msg[:50]}"
    
    decl_line_count = decl.count('\n') + 1
    proof_lines = [l for l in proof_text.split('\n') if l.strip()]
    proof_line_count = len(proof_lines)
    
    relative_error_line = error_line - decl_line_count
    
    if relative_error_line <= 0:
        valid_proof = ""
    elif relative_error_line >= proof_line_count:
        valid_proof = proof_text
    else:
        valid_proof = '\n'.join(proof_lines[:relative_error_line])
    
    return True, valid_proof, f"unsolved goals at line {error_line}"


def try_close_goal(
    lean_server,
    context_env,
    decl: str,
    existing_proof: str,
    timeout: int = 60,
) -> Dict[str, Any]:

    DIRECT_CLOSING_TACTICS = [
        "rfl", 
        "trivial", 
        "simp_all", "simp",
        "assumption", "decide",
        "norm_num", "ring", "omega", "linarith", 
        "contradiction", 
        #"aesop",
    ]
    
    SEARCH_TACTICS_WITH_SUGGESTIONS = [
        "exact?",
        "hint",
    ]
    
    if existing_proof:
        existing_proof = existing_proof.strip()
    
    def _build_full_proof(new_tactic: str) -> str:
        if existing_proof:
            return decl + "\n" + existing_proof + "\n  " + new_tactic
        else:
            return decl + "\n  " + new_tactic
    
    def _build_current_proof() -> str:
        if existing_proof:
            return decl + "\n" + existing_proof
        else:
            return decl
    
    for tactic in DIRECT_CLOSING_TACTICS:
        full_proof = _build_full_proof(tactic)
        
        try:
            cmd_out = lean_server.run(
                Command(cmd=full_proof, env=context_env),
                timeout=timeout,
            )
            
            if not isinstance(cmd_out, LeanError) and cmd_out.lean_code_is_valid(allow_sorry=False):
                return {
                    "success": True,
                    "closing_tactic": tactic,
                    "proof_text": full_proof,
                }
        except Exception:
            continue
    
    current_proof = _build_current_proof()
    
    for search_tactic in SEARCH_TACTICS_WITH_SUGGESTIONS:
        try:
            search_out = lean_server.run(
                Command(cmd=current_proof + f"\n  {search_tactic}", env=context_env),
                timeout=timeout,
            )
            suggestions = extract_suggestions_from_response(search_out)
            
            for suggestion in suggestions:
                if 'sorry' in suggestion.lower():
                    continue
                
                full_proof = _build_full_proof(suggestion)
                
                cmd_out = lean_server.run(
                    Command(cmd=full_proof, env=context_env),
                    timeout=timeout,
                )
                
                if not isinstance(cmd_out, LeanError) and cmd_out.lean_code_is_valid(allow_sorry=False):
                    return {
                        "success": True,
                        "closing_tactic": suggestion,
                        "proof_text": full_proof,
                    }
        except Exception:
            continue
    
    return {
        "success": False,
    }


def auto_solve(
    lean_server,
    context_env,
    decl: str,
    proof_text: str = "",
    errors: list[dict] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    
    if errors is None:
        errors = []
    
    can_close, valid_proof, reason = can_auto_close(
        decl=decl,
        proof_text=proof_text,
        errors=errors,
    )
    
    if not can_close:
        return {
            "success": False,
            "reason": reason,
        }
    
    close_result = try_close_goal(
        lean_server=lean_server,
        context_env=context_env,
        decl=decl,
        existing_proof=valid_proof,
        timeout=timeout,
    )
    
    if close_result.get("success"):
        return {
            "success": True,
            "proof_text": close_result["proof_text"],
            "closing_tactic": close_result["closing_tactic"],
            "valid_proof_used": valid_proof,
            "can_close_reason": reason,
        }
    else:
        return {
            "success": False,
            "reason": "try_close_goal failed",
            "valid_proof_used": valid_proof,
            "can_close_reason": reason,
        }