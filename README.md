# Compiler-Guided Adaptive Proof Search with Cross-Model Synergy on Context-Dependent Theorem Proving

Code for our **Findings of EMNLP 2026** paper.

**Zhuo Liu, Ding Yu, and Hangfeng He**

[[Paper]](https://arxiv.org/abs/2608.18084)

Our method combines dual-model proof generation, compiler-guided refinement,
pairwise proof comparison, and stagnation-triggered resampling for Lean 4 theorem
proving on [miniCTX-v2](https://huggingface.co/datasets/l3lab/miniCTX-v2).

## 1. Install RLMEval

We use several utility functions from
[RLMEval](https://github.com/augustepoiroux/RLMEval). Clone and install it from the root
of this repository:

```bash
git clone https://github.com/augustepoiroux/RLMEval.git
python -m pip install -e ./RLMEval
```

## 2. Environment

Our experiments use:

| Component | Version |
| --- | --- |
| Python | 3.10.18 |
| LeanInteract (`lean-interact`) | 0.5.3 |

Use Python 3.10.18 and ensure the LeanInteract version matches:

```bash
python -m pip install lean-interact==0.5.3
```

The target Lean projects must have their toolchains and dependencies available.

## 3. Prepare the Lean Projects

Place the traced repositories under `traced_repos/` in the root of this repository, the example is given as the figure.
The directory names and nested project paths should match the paths used by the
entry script.

The [miniCTX-v2 dataset card](https://huggingface.co/datasets/l3lab/miniCTX-v2)
provides the source repositories and their corresponding revisions. If your
local directory layout differs, update the project paths in the entry script.

## 4. Set API Keys

Replace the API key placeholders in `utils_api.py` with your own keys:

```python
os.environ["OPENAI_API_KEY"] = "your-openai-api-key"
os.environ["ANTHROPIC_API_KEY"] = "your-anthropic-api-key"
os.environ["GEMINI_API_KEY"] = "your-gemini-api-key"
```

Configure the keys for the providers you use. The default search uses GPT-5-mini
and DeepSeek-Prover-V2-7B.

## 5. Serve DeepSeek with vLLM

Start DeepSeek-Prover-V2-7B on a GPU using vLLM:

```bash
CUDA_VISIBLE_DEVICES=0 vllm serve deepseek-ai/DeepSeek-Prover-V2-7B \
  --host 127.0.0.1 \
  --port 8080
```

This serves the model at `http://localhost:8080/v1`, matching the `api_base`
configured in `utils_api.py`. Change `CUDA_VISIBLE_DEVICES` to select your GPU.
If you use a different server address or port, update `api_base` accordingly.

Wait until the server is ready, keep it running, and launch the proof search
in a separate terminal. 

## 6. Run

Run from the root of this repository:

```bash
python main.py \
  --project-name Seymour \
  --split test \
  --max-refine 12 \
  --stagnation-threshold 3 \
  --lean-context
```

| Argument | Description | Default |
| --- | --- | --- |
| `--project-name` | Lean project listed above | `Seymour` |
| `--split` | Dataset split: `valid` or `test` | `test` |
| `--max-refine` | Maximum refinement-loop iterations | `12` |
| `--stagnation-threshold` | Consecutive rounds without improvement before resampling | `3` |
| `--lean-context` | Include Lean context in comparison prompts | Enabled |

## 7. Citation

If you use this code in your research, please cite our paper:

```bibtex
@inproceedings{liu-etal-2026-compiler,
  title = {Compiler-Guided Adaptive Proof Search with Cross-Model Synergy on Context-Dependent Theorem Proving},
  author = {Liu, Zhuo and Yu, Ding and He, Hangfeng},
  booktitle = {Findings of the Association for Computational Linguistics: EMNLP 2026},
  year = {2026},
  publisher = {Association for Computational Linguistics},
  url = {https://arxiv.org/abs/2608.18084}
}
```

## 8. Acknowledgments

We thank the authors of [RLMEval](https://github.com/augustepoiroux/RLMEval) and
[LeanInteract](https://github.com/augustepoiroux/LeanInteract) for making their
code available, and the miniCTX authors for providing the benchmark. We also
used OpenAI Codex to assist with code cleanup and restructuring.
