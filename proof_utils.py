"""Proof formatting, context compression, and Lean verification."""

from typing import Any, Tuple

from lean_interact.interface import Command, LeanError
from lean_interact.utils import indent_code, remove_lean_comments
from litellm.utils import token_counter


def fix_first_tactic_indentation(lean_proof: str) -> str:
    """
    Sets the indentation of the first tactic line to the minimum indentation
    found among all subsequent non-empty lines.
    Some LLMs do not align correctly the first tactic, hence this function.
    """
    if not lean_proof:
        return lean_proof
    lines = lean_proof.splitlines()

    # Find minimum indentation among all subsequent non-empty lines
    min_indent = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() != "":
            indent = len(lines[idx]) - len(lines[idx].lstrip())
            if min_indent is None or indent < min_indent:
                min_indent = indent
    if min_indent is None:
        return lean_proof  # Only one tactic, nothing to align to

    # Rebuild lines, fixing the first tactic's indentation
    lines[0] = indent_code(lines[0].lstrip(), min_indent)
    return "\n".join(lines)


def remove_all_empty_lines(proof: str) -> str:
    lines = proof.splitlines()
    return '\n'.join(line for line in lines if line.strip())


def compress_context_from_middle_fast(
    context: str,
    max_tokens: int = 8192,
    model: str = "hosted_vllm/deepseek-ai/DeepSeek-Prover-V2-7B",
    truncation_marker: str = "\n... [TRUNCATED] ...\n"
) -> str:

    if not context.strip():
        return context
    
    current_tokens = token_counter(model=model, text=context)
    if current_tokens <= max_tokens:
        return context
    
    lines = context.split("\n")
    n = len(lines)
    
    if n <= 2:
        return context
    
    chars_per_token = len(context) / current_tokens
    target_chars = int(max_tokens * chars_per_token * 0.9)
    marker_chars = len(truncation_marker)
    
    total_chars = 0
    keep_lines = 0
    
    for i in range(n // 2):
        head_line_chars = len(lines[i]) + 1
        tail_line_chars = len(lines[n - 1 - i]) + 1
        
        if total_chars + head_line_chars + tail_line_chars + marker_chars > target_chars:
            break
        
        total_chars += head_line_chars + tail_line_chars
        keep_lines = i + 1
    
    if keep_lines == 0:
        return truncation_marker.strip()
    
    compressed = "\n".join(lines[:keep_lines]) + truncation_marker + "\n".join(lines[-keep_lines:])
    
    if token_counter(model=model, text=compressed) <= max_tokens:
        return compressed
    
    left, right = 1, keep_lines - 1
    best = 0
    
    while left <= right:
        mid = (left + right) // 2
        test_text = "\n".join(lines[:mid]) + truncation_marker + "\n".join(lines[-mid:])
        
        if token_counter(model=model, text=test_text) <= max_tokens:
            best = mid
            left = mid + 1
        else:
            right = mid - 1
    
    if best == 0:
        return truncation_marker.strip()
    
    return "\n".join(lines[:best]) + truncation_marker + "\n".join(lines[-best:])


def match_errors_to_tactics(cmd_src: str, cmd_out: Any) -> list[dict]:
    def getf(obj, name, default=None):
        return getattr(obj, name, default) if not isinstance(obj, dict) else obj.get(name, default)
    
    lines = cmd_src.splitlines()
    messages = getf(cmd_out, "messages", [])
    if not messages:
        return []
    
    error_items = []
    
    for m in messages:
        sev = (getf(m, "severity", "") or "").lower()
        if sev != "error":
            continue
            
        data = getf(m, "data", "") or getf(m, "message", "") or ""
        sp = getf(m, "start_pos", {}) or {}
        ep = getf(m, "end_pos", {}) or {}
        
        sl = getf(sp, "line", 0) or 0
        sc = getf(sp, "column", 0) or 0
        el = getf(ep, "line", 0) or 0
        ec = getf(ep, "column", 0) or 0
        
        error_line_idx = sl - 1
        if 0 <= error_line_idx < len(lines):
            error_line = lines[error_line_idx]
        else:
            error_line = "<line out of range>"
        
        highlighted_line = error_line
        if 0 <= error_line_idx < len(lines) and sc > 0:
            if sc <= len(error_line) and ec <= len(error_line):
                highlighted_line = (
                    error_line[:sc-1] + 
                    ">>>" + error_line[sc-1:ec-1] + "<<<" + 
                    error_line[ec-1:]
                )
        
        error_items.append({
            "line": sl,
            "column": sc,
            "end_line": el,
            "end_column": ec,
            "error_message": str(data).rstrip(),
            "code_line": error_line,
            "highlighted_line": highlighted_line,
            "position": f"L{sl}:C{sc}" + (f"–L{el}:C{ec}" if (el, ec) != (sl, sc) and (el or ec) else "")
        })
    
    error_items.sort(key=lambda x: (x["line"], x["column"]))
    return error_items


def format_errors_with_context(cmd_src: str, errors: list[dict], context_lines: int = 1) -> str:
    if not errors:
        return "No errors found."
    
    lines = cmd_src.splitlines()
    result = []
    
    for i, err in enumerate(errors, 1):
        result.append(f"Error #{i}: {err['error_message']}")
        result.append("")
        
        error_start = err['line']
        error_end = err.get('end_line', error_start) or error_start
        
        if error_end < error_start:
            error_end = error_start
        
        display_start = max(0, error_start - 1 - context_lines)
        display_end = min(len(lines), error_end + context_lines)
        
        for line_num in range(display_start, display_end):
            line_content = lines[line_num]
            actual_line = line_num + 1
            
            if error_start <= actual_line <= error_end:
                result.append(f">>> {line_content}")
            else:
                result.append(f"    {line_content}")
        
        if i < len(errors):
            result.append("")
            result.append("-" * 60)
            result.append("")
    
    return "\n".join(result)


def get_errors_for_proof(lean_server, proof: str, decl: str, context_env) -> Tuple[str, str, Any]:
    cleaned = remove_lean_comments(proof)
    cleaned = remove_all_empty_lines(cleaned)
    cmd_src = decl + "\n" + cleaned
    cmd_out = lean_server.run(
        Command(cmd=cmd_src, env=context_env),
        timeout=120,
    )
    errors = match_errors_to_tactics(cmd_src, cmd_out)
    error_string = format_errors_with_context(cmd_src, errors, context_lines=1)
    return cmd_src, error_string, cmd_out


def verify_proof(lean_server, proof: str, decl: str, context_env) -> bool:
    try:
        cleaned_proof = remove_lean_comments(proof)
        cleaned_proof = remove_all_empty_lines(cleaned_proof)
        cmd_src = decl + "\n" + cleaned_proof
        cmd_out = lean_server.run(
            Command(cmd=cmd_src, env=context_env),
            timeout=120,
        )
        return not isinstance(cmd_out, LeanError) and cmd_out.lean_code_is_valid(allow_sorry=False)
    except Exception as e:
        print(f"Verification error: {e}")
        return False
