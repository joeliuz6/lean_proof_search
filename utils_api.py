"""Original API and prover generation helpers."""

import os

from litellm import completion, text_completion
from vllm import SamplingParams
from rlm_eval.utils import extract_lean_codes

from proof_utils import fix_first_tactic_indentation

os.environ["OPENAI_API_KEY"] = "your API KEY here"
os.environ["ANTHROPIC_API_KEY"] ="your API KEY here"
os.environ['GEMINI_API_KEY'] = "your API KEY here"


def _unique_sorted(texts, scores):
    texts_ = []
    scores_ = []
    for t, s in sorted(zip(texts, scores), key=lambda x: -x[1]):
        if t not in texts_:
            texts_.append(t)
            scores_.append(s)
    return texts_, scores_


def _node_informal_comment(processed_text) -> str:
    #processed_text = node
    processed_text = "\n".join(line.strip() for line in processed_text.split(r"\\") if line.strip())
    return f"/- {processed_text}\n-/"


def _node_informal_text(processed_text) -> str:
    #processed_text = node
    return "\n".join(line.strip() for line in processed_text.split(r"\\") if line.strip())


def generate_vllm(prompt, model, tokenizer, temperature=1, num_samples=32, max_tokens=64, stop=["\n\n\n", "---", "[/TAC]"]):
    texts, scores = [], []
    params = SamplingParams(
        n=num_samples,
        temperature=temperature,
        top_p=1,
        max_tokens=max_tokens,
        stop=stop,
        logprobs=1,
    )
    outputs = model.generate([prompt], params, use_tqdm=False)
    if len(outputs) == 0:
        return [], []
    for output in outputs[0].outputs:
        text = output.text.replace(tokenizer.eos_token, '')
        score = output.cumulative_logprob/max(len(output.token_ids), 1)
        texts.append(text)
        scores.append(score)
    texts, scores = _unique_sorted(texts, scores)
    return texts, scores


def gpt5_mini_completion(message, nb_samples=1):

    messages = [{"role": "user", "content": message}]

    response = completion(
        model="gpt-5-mini", 
        messages=messages,
        reasoning_effort="low",
        n = nb_samples
        )
    
    predictions = [
        choice.message.content if choice.message.content and choice.message.content.strip() else None  
        for choice in response.choices  
    ]

    predictions = [
        fix_first_tactic_indentation("\n".join(extract_lean_codes(prediction))) if prediction else None
        for prediction in predictions
    ]

    input_tokens = response.usage.prompt_tokens  
    output_tokens = response.usage.completion_tokens

    if nb_samples == 1:
        return predictions[0], input_tokens, output_tokens
    else:
        return predictions, input_tokens, output_tokens


def gpt5_mini_response(message, reasoning_effort="low"):

    messages = [{"role": "user", "content": message}]

    response = completion(
        model="openai/responses/gpt-5-mini", 
        messages=messages,
        reasoning_effort=reasoning_effort,
    )
    
    predictions = [
        choice.message.content if choice.message.content and choice.message.content.strip() else None  
        for choice in response.choices  
    ]

    predictions = [
        fix_first_tactic_indentation("\n".join(extract_lean_codes(prediction))) if prediction else None
        for prediction in predictions
    ]

    input_tokens = response.usage.prompt_tokens  
    output_tokens = response.usage.completion_tokens
    reasoning_tokens =   response.usage.completion_tokens_details.reasoning_tokens 
    cost = getattr(response, "_hidden_params", {}).get("response_cost", None)
    #if cost is None: 


    return predictions[0], input_tokens, output_tokens,reasoning_tokens,cost


def gpt54_mini_response(message, reasoning_effort="low"):

    messages = [{"role": "user", "content": message}]

    response = completion(
        model="openai/responses/gpt-5.4-mini", 
        messages=messages,
        reasoning_effort=reasoning_effort,
    )
    
    predictions = [
        choice.message.content if choice.message.content and choice.message.content.strip() else None  
        for choice in response.choices  
    ]

    predictions = [
        fix_first_tactic_indentation("\n".join(extract_lean_codes(prediction))) if prediction else None
        for prediction in predictions
    ]

    input_tokens = response.usage.prompt_tokens  
    output_tokens = response.usage.completion_tokens
    reasoning_tokens =   response.usage.completion_tokens_details.reasoning_tokens 
    cost = getattr(response, "_hidden_params", {}).get("response_cost", None)
    #if cost is None: 


    return predictions[0], input_tokens, output_tokens,reasoning_tokens,cost


def claude_haiku_response(message, reasoning_effort="low"):

    messages = [{"role": "user", "content": message}]

    response = completion(
        model="anthropic/claude-haiku-4-5-20251001", 
        messages=messages,
        reasoning_effort=reasoning_effort, # LiteLLM translates OpenAI's reasoning_effort to Anthropic's thinking parameter: "low"	"budget_tokens": 1024, medium 2048, high 4096
        temperature=1,
    )
    
    predictions = [
        choice.message.content if choice.message.content and choice.message.content.strip() else None
        for choice in response.choices
    ]

    predictions = [
        fix_first_tactic_indentation("\n".join(extract_lean_codes(prediction))) if prediction else None
        for prediction in predictions
    ]

    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens

    reasoning_tokens = getattr(
        getattr(response.usage, "completion_tokens_details", None), 
        "reasoning_tokens", 
        None
    )
    cost = getattr(response, "_hidden_params", {}).get("response_cost", None)

    return predictions[0], input_tokens, output_tokens, reasoning_tokens, cost


def gemini_flash_response(message, reasoning_effort="low"):

    messages = [{"role": "user", "content": message}]

    response = completion(
        model="gemini/gemini-2.5-flash",
        messages=messages,
        reasoning_effort=reasoning_effort,  # "low"→1024, "medium"→2048, "high"→4096, "none"→close thinking
    )

    predictions = [
        choice.message.content if choice.message.content and choice.message.content.strip() else None
        for choice in response.choices
    ]

    predictions = [
        fix_first_tactic_indentation("\n".join(extract_lean_codes(prediction))) if prediction else None
        for prediction in predictions
    ]

    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens

    reasoning_tokens = getattr(
        getattr(response.usage, "completion_tokens_details", None),
        "reasoning_tokens",
        None,
    )
    cost = getattr(response, "_hidden_params", {}).get("response_cost", None)

    return predictions[0], input_tokens, output_tokens, reasoning_tokens, cost


def prover_response(prompt, nb_samples=1):

    response = text_completion(
        model="hosted_vllm/deepseek-ai/DeepSeek-Prover-V2-7B",
        prompt=prompt,
        temperature=1,
        top_p=0.95,
        max_tokens=8192,
        n=nb_samples,
        api_key="-",
        stop=["sorry", "\n\n", "```"],
        api_base="http://localhost:8080/v1",
    )
    
    predictions = [
        fix_first_tactic_indentation(choice.text)
        if choice.text and choice.text.strip() and choice.finish_reason != "length"
        else None
        for choice in response.choices
    ]

    num_samples = len(predictions)
    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens
    
    input_tokens_list = [input_tokens] * num_samples if num_samples > 0 else []
    output_tokens_list = [output_tokens / num_samples] * num_samples if num_samples > 0 else []
    reasoning_tokens_list = [0] * num_samples if num_samples > 0 else []
    cost_list = [0] * num_samples if num_samples > 0 else []

    # Placeholder: local inference cost is not accounted for here.
    # Paper costs are computed from token counts seperately,using the same GPT pricing for both models. 
    # You can calculate these costs offline from the recorded token counts
    # or modify prover_response() to compute them directly.

    return predictions, input_tokens_list, output_tokens_list, reasoning_tokens_list, cost_list


def goedel2_prover_response(prompt, nb_samples=1):

    response = text_completion(
        model="hosted_vllm/Goedel-LM/Goedel-Prover-V2-8B",
        prompt=prompt,
        temperature=1,
        top_p=0.95,
        max_tokens=8192,
        n=nb_samples,
        api_key="-",
        stop=["sorry", "\n\n", "```"],
        api_base="http://localhost:8080/v1",
    )
    
    predictions = [
        fix_first_tactic_indentation(choice.text)
        if choice.text and choice.text.strip() and choice.finish_reason != "length"
        else None
        for choice in response.choices
    ]

    num_samples = len(predictions)
    input_tokens = response.usage.prompt_tokens
    output_tokens = response.usage.completion_tokens
    
    input_tokens_list = [input_tokens] * num_samples if num_samples > 0 else []
    output_tokens_list = [output_tokens / num_samples] * num_samples if num_samples > 0 else []
    reasoning_tokens_list = [0] * num_samples if num_samples > 0 else []
    cost_list = [0] * num_samples if num_samples > 0 else []

    return predictions, input_tokens_list, output_tokens_list, reasoning_tokens_list, cost_list
