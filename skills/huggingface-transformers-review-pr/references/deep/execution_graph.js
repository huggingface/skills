// Execution graph for the transformers-deep-review skill.
// Consumed two ways:
//   1. By a review agent as a routing rule base: run the detectors (cheap greps over the
//      diff), then read ONLY the reference sections the fired detectors point to. A
//      detector with zero hits IS the provable `not triggered` evidence for its
//      dimensions in the DIMENSIONS block.
//   2. By graph.html as visualization data (loaded via <script src>).
// The data below is a pure JSON literal wrapped in one const.
//
// Coverage contract (why this graph cannot lose dimensions): the DIMENSIONS block in the
// review output still requires one line per D1-D41. The graph only decides HOW each line
// is produced — `findings`/`clean` for dimensions whose detectors fired (reference section
// read, checks run), `not triggered: <detector pattern, zero hits>` for the rest. The
// always_on set and the per-class absence checks are never gated by detectors.

const GRAPH = {
  version: "2026-07-24",

  contract: {
    output: "one DIMENSIONS line per D1-D41, no exceptions",
    fired_detector: "read the owning reference section, run the checks, emit findings/clean with evidence",
    silent_detector: "emit `not triggered`, citing the detector pattern and its zero hits",
    always_on: "run regardless of detector state, on every PR class",
    absence_checks: "mandatory for new_model and model_refactor classes; they detect reimplementation-by-absence, which no positive grep can see"
  },

  classes: [
    { id: "new_model", label: "new model", floor: "all detectors + all absence checks + D28 registration/docs" },
    { id: "model_refactor", label: "model refactor", floor: "all detectors + all absence checks" },
    { id: "generic", label: "generic diff", floor: "always_on + fired detectors only (quick-review minimum)" }
  ],

  always_on: ["D5", "D10", "D11", "D12", "D13", "D14", "D15", "D27", "D30", "D32"],

  // Positive detectors: grep `match` over the diff (paths and added lines).
  detectors: [
    { id: "d-modeling-file", label: "modeling file touched", match: "src/transformers/models/.*/modeling_.*\\.py", dims: ["D1", "D2", "D6", "D13", "D15", "D17", "D24", "D26"] },
    { id: "d-new-module", label: "new nn.Module class", match: "^\\+class \\w+\\((nn\\.Module|GradientCheckpointingLayer)\\)", dims: ["D1", "D3", "D13", "D18", "D24"] },
    { id: "d-attention", label: "attention / dispatch", match: "_attn_implementation|eager_attention_forward|ALL_ATTENTION_FUNCTIONS|q_proj|scaled_dot_product", dims: ["D3", "D31", "D38"] },
    { id: "d-mask", label: "mask construction", match: "masking_utils|create_(causal|bidirectional|sliding)|or_masks|and_masks|allow_is_causal_skip", dims: ["D33", "D34"] },
    { id: "d-cache", label: "cache / layer types", match: "past_key_values|Cache\\b|kv_offset|layer_types|get_seq_length", dims: ["D8", "D33"] },
    { id: "d-config", label: "configuration file", match: "src/transformers/models/.*/configuration_.*\\.py|class \\w+Config", dims: ["D6", "D7", "D8"] },
    { id: "d-forward-sig", label: "forward signature change", match: "^[-+].*def forward\\(", dims: ["D2", "D9", "D26"] },
    { id: "d-init-weights", label: "weight init", match: "_init_weights|nn\\.init\\.|torch\\.empty|trunc_normal|\\.fill_\\(", dims: ["D18"] },
    { id: "d-dtype-cast", label: "dtype cast added/removed", match: "^[-+].*(\\.float\\(\\)|\\.to\\(.*dtype|\\.half\\(\\))", dims: ["D20"] },
    { id: "d-warn-assert", label: "warning / assert in src", match: "^\\+.*(logger\\.warning|assert )", dims: ["D14"] },
    { id: "d-compile-hazard", label: "compile hazard", match: "\\.item\\(\\)|\\.tolist\\(\\)|torch\\.arange|if .*\\.(any|all)\\(\\)", dims: ["D4"] },
    { id: "d-kernels", label: "kernel code", match: "import triton|use_kernel|autograd\\.Function|lazy_load_kernel|KernelConfig", dims: ["D31", "D38"] },
    { id: "d-moe", label: "MoE / experts", match: "experts|router|num_experts|gate_up_proj|use_experts_implementation", dims: ["D31", "D41"] },
    { id: "d-tying", label: "weight tying", match: "tie_weights|_tied_weights_keys|tie_word_embeddings|lm_head", dims: ["D19"] },
    { id: "d-loading", label: "loading / saving paths", match: "modeling_utils\\.py|core_model_loading\\.py|from_pretrained|save_pretrained|load_backbone", dims: ["D11", "D16", "D39"] },
    { id: "d-conversion", label: "conversion / weight names", match: "conversion_mapping\\.py|convert_.*\\.py|WeightRenaming|WeightConverter|PrefixChange", dims: ["D11", "D21", "D31", "D38"] },
    { id: "d-processing", label: "processor / image processor", match: "processing_.*\\.py|image_processing_.*\\.py|feature_extraction_.*\\.py", dims: ["D17", "D22", "D23", "D38"] },
    { id: "d-video-proc", label: "video processor", match: "video_processing_.*\\.py", dims: ["D37"] },
    { id: "d-tokenizer", label: "tokenizer", match: "tokenization_.*\\.py|tokenizer_config|SLOW_TO_FAST_CONVERTERS|TokenizersBackend", dims: ["D35"] },
    { id: "d-vlm", label: "VLM markers", match: "pixel_values|image_token|get_image_features|vision_tower|get_placeholder_mask|mrope", dims: ["D22", "D36"] },
    { id: "d-postproc", label: "post-processing", match: "post_process_", dims: ["D22"] },
    { id: "d-cb", label: "continuous batching / serve", match: "continuous_batching|paged|serve\\b|RequestState", dims: ["D29", "D40"] },
    { id: "d-distributed", label: "distributed / plans", match: "distributed/|tensor_parallel|DTensor|device_mesh|_tp_plan|_fsdp_plan|ParallelStyle", dims: ["D17", "D25", "D41"] },
    { id: "d-auto-registration", label: "auto registration paths", match: "auto_factory\\.py|configuration_utils\\.py|tokenization_auto\\.py|models/auto/", dims: ["D39"] },
    { id: "d-new-subsystem", label: "new core subsystem", match: "^\\+class \\w+(Cache|Allocator|Scheduler|Registry|Manager)\\b(?!.*models/)", dims: ["D29"] },
    { id: "d-optional-dep", label: "optional dependency", match: "is_\\w+_available|requires_backends|try:\\s*import", dims: ["D23"] },
    { id: "d-tests", label: "test files", match: "tests/", dims: ["D12"] },
    { id: "d-docs", label: "docs", match: "docs/|README|\\.md$", dims: ["D28"] },
    { id: "d-deprecation", label: "rename / removal / deprecation", match: "deprecat|^-.*def \\w+|^-.*class \\w+", dims: ["D10", "D32"] }
  ],

  // Absence checks: they fire on what the diff does NOT contain. No positive grep can
  // route to them, so they are class-gated, not detector-gated.
  absence_checks: [
    { id: "a-modular", label: "new modeling file without modular", check: "new modeling_*.py with no modular_*.py, or a modular below the inheritance floor", dims: ["D1"] },
    { id: "a-mechanisms", label: "mechanism reimplemented by absence", check: "new norm/rotary/activation/experts module without the hub-kernel or experts decorator; hand-rolled dispatch", dims: ["D31"] },
    { id: "a-flags", label: "PreTrainedModel flags audit", check: "every new/edited PreTrainedModel subclass: one row per flag set + flags it should set", dims: ["D19", "D31", "D38"] },
    { id: "a-provenance", label: "expected values without provenance", check: "every integration-test constant: where did the value come from?", dims: ["D5"] },
    { id: "a-plans", label: "missing parallelism plans", check: "new decoder LM without base_model_tp_plan / base_model_fsdp_plan", dims: ["D25", "D41"] },
    { id: "a-registration", label: "registration completeness", check: "auto mappings, __init__ exports, docs toctree for every public class", dims: ["D28"] }
  ],

  dimensions: [
    { id: "D1", name: "Modular reuse / inheritance", ref: "modular_review.md" },
    { id: "D2", name: "Decorator stack / modern output API", ref: "review_deep.md" },
    { id: "D3", name: "Attention interface + QKV pattern", ref: "modeling_conventions_review.md" },
    { id: "D4", name: "torch.compile safety", ref: "review_deep.md" },
    { id: "D5", name: "Faithfulness + parity provenance", ref: "fidelity_review.md" },
    { id: "D6", name: "Dead branches vs released checkpoints", ref: "modeling_conventions_review.md" },
    { id: "D7", name: "Config discipline", ref: "modeling_conventions_review.md" },
    { id: "D8", name: "Layer-type taxonomy", ref: "modeling_conventions_review.md" },
    { id: "D9", name: "Signature stability + kwargs", ref: "modeling_conventions_review.md" },
    { id: "D10", name: "BC / deprecation / \u{1F6A8}", ref: "tests_bc_review.md" },
    { id: "D11", name: "Cross-model blast radius", ref: "tests_bc_review.md" },
    { id: "D12", name: "Test standards", ref: "tests_bc_review.md" },
    { id: "D13", name: "Naming pass", ref: "modeling_conventions_review.md" },
    { id: "D14", name: "Minimal surface / fail loudly", ref: "modeling_conventions_review.md" },
    { id: "D15", name: "Directness / no premature generalization", ref: "modeling_conventions_review.md" },
    { id: "D16", name: "Loading/saving-path discipline", ref: "modeling_conventions_review.md" },
    { id: "D17", name: "State and hoisting", ref: "modeling_conventions_review.md" },
    { id: "D18", name: "_init_weights placement", ref: "modeling_conventions_review.md" },
    { id: "D19", name: "Weight tying declarative", ref: "mechanisms_review.md" },
    { id: "D20", name: "dtype/cast provenance", ref: "fidelity_review.md" },
    { id: "D21", name: "Conversion scripts + hub strategy", ref: "fidelity_review.md" },
    { id: "D22", name: "Vision processing API consistency", ref: "processing_review.md" },
    { id: "D23", name: "Optional-backend gating", ref: "processing_review.md" },
    { id: "D24", name: "Module container discipline", ref: "modeling_conventions_review.md" },
    { id: "D25", name: "Explicit path plans", ref: "modeling_conventions_review.md" },
    { id: "D26", name: "Return-type honesty", ref: "modeling_conventions_review.md" },
    { id: "D27", name: "Comment hygiene", ref: "modeling_conventions_review.md" },
    { id: "D28", name: "Docs/metadata coherence", ref: "new_model_review.md" },
    { id: "D29", name: "Design-level Occam, measured", ref: "modeling_conventions_review.md" },
    { id: "D30", name: "Escalation and coordination", ref: "tests_bc_review.md" },
    { id: "D31", name: "Framework mechanisms", ref: "mechanisms_review.md" },
    { id: "D32", name: "Feature isolation", ref: "tests_bc_review.md" },
    { id: "D33", name: "Hybrid cache/mask coverage", ref: "modeling_conventions_review.md" },
    { id: "D34", name: "Mask plumbing via masking_utils", ref: "modeling_conventions_review.md" },
    { id: "D35", name: "Tokenizer standards", ref: "processing_review.md" },
    { id: "D36", name: "VLM composition + feature API", ref: "modeling_conventions_review.md" },
    { id: "D37", name: "Video-processor contract", ref: "processing_review.md" },
    { id: "D38", name: "Downstream consumability (vLLM)", ref: "mechanisms_review.md" },
    { id: "D39", name: "External extension points", ref: "mechanisms_review.md" },
    { id: "D40", name: "Continuous-batching contracts", ref: "modeling_conventions_review.md" },
    { id: "D41", name: "Distributed plan/runtime contract", ref: "modeling_conventions_review.md" }
  ],

  references: [
    "review_deep.md",
    "modular_review.md",
    "mechanisms_review.md",
    "modeling_conventions_review.md",
    "fidelity_review.md",
    "tests_bc_review.md",
    "processing_review.md",
    "new_model_review.md"
  ]
};

if (typeof window !== "undefined") window.GRAPH = GRAPH;
if (typeof module !== "undefined") module.exports = GRAPH;
