#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  MoE Expert Surgery — Master Pipeline
#  Orchestrates the full expert injection + router tuning pipeline
# ═══════════════════════════════════════════════════════════════════
#
#  This script runs the complete pipeline:
#    Phase 1: Generate training data for new experts
#    Phase 2: Inject new expert weights into safetensors
#    Phase 3: Fine-tune router to route to new experts
#    Phase 4: Apply trained router to final model
#    Phase 5: Validate the final model
#
#  Requirements:
#    - RunPod A100 80GB instance (or equivalent)
#    - ~120GB disk space (model + output + checkpoints)
#    - Python 3.10+ with CUDA
#    - All dependencies from requirements.txt
#
#  Usage:
#    chmod +x run_pipeline.sh
#    ./run_pipeline.sh /workspace/model_input /workspace/model_output
#
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

# ─── Colors ───
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ─── Configuration ───
MODEL_DIR="${1:-/workspace/model}"
OUTPUT_DIR="${2:-/workspace/model_surgery_output}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

INJECTION_OUTPUT="${OUTPUT_DIR}/step1_injected"
TRAINING_DATA_DIR="${SCRIPT_DIR}/data"
ROUTER_CHECKPOINTS="${OUTPUT_DIR}/step2_router_checkpoints"
FINAL_MODEL="${OUTPUT_DIR}/final_model"
LOG_DIR="${OUTPUT_DIR}/logs"

# ─── Training Config ───
ROUTER_EPOCHS=5
ROUTER_BATCH_SIZE=4
ROUTER_LR=5e-4
USE_WANDB=false

# ─── Functions ───

log_header() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $(date '+%H:%M:%S') $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $(date '+%H:%M:%S') $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $(date '+%H:%M:%S') $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $(date '+%H:%M:%S') $1"
}

check_gpu() {
    if ! command -v nvidia-smi &> /dev/null; then
        log_error "nvidia-smi not found. GPU required!"
        exit 1
    fi
    
    GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
    log_info "GPU Memory: ${GPU_MEM} MiB"
    
    if [ "$GPU_MEM" -lt 40000 ]; then
        log_warning "Less than 40GB VRAM detected. A100 80GB recommended."
        log_warning "Proceeding anyway... may OOM during router training."
    fi
}

check_disk() {
    AVAIL_GB=$(df -BG "$OUTPUT_DIR" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G')
    if [ -n "$AVAIL_GB" ] && [ "$AVAIL_GB" -lt 120 ]; then
        log_warning "Less than 120GB disk space available (${AVAIL_GB}GB). May run out."
    fi
    log_info "Available disk: ${AVAIL_GB:-unknown}GB"
}

check_dependencies() {
    log_info "Checking Python dependencies..."
    python3 -c "import torch; print(f'PyTorch {torch.__version__}, CUDA: {torch.cuda.is_available()}')"
    python3 -c "import safetensors; print(f'safetensors {safetensors.__version__}')"
    python3 -c "import bitsandbytes; print(f'bitsandbytes {bitsandbytes.__version__}')"
    python3 -c "import transformers; print(f'transformers {transformers.__version__}')"
    
    if ! python3 -c "import torch; assert torch.cuda.is_available()"; then
        log_error "CUDA not available! GPU required for this pipeline."
        exit 1
    fi
}

check_model() {
    log_info "Validating source model: ${MODEL_DIR}"
    
    if [ ! -f "${MODEL_DIR}/config.json" ]; then
        log_error "config.json not found in ${MODEL_DIR}"
        exit 1
    fi
    
    if [ ! -f "${MODEL_DIR}/model.safetensors.index.json" ]; then
        log_error "model.safetensors.index.json not found in ${MODEL_DIR}"
        exit 1
    fi
    
    SHARD_COUNT=$(ls "${MODEL_DIR}"/model-*.safetensors 2>/dev/null | wc -l)
    log_info "Found ${SHARD_COUNT} model shards"
    
    if [ "$SHARD_COUNT" -lt 1 ]; then
        log_error "No model shards found!"
        exit 1
    fi
    
    # Check num_local_experts in config
    NUM_EXPERTS=$(python3 -c "import json; c=json.load(open('${MODEL_DIR}/config.json')); print(c.get('text_config',{}).get('num_local_experts', c.get('num_local_experts', 'unknown')))")
    log_info "Current num_local_experts: ${NUM_EXPERTS}"
}


# ═══════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════

log_header "MoE Expert Surgery Pipeline"

log_info "Model directory:  ${MODEL_DIR}"
log_info "Output directory: ${OUTPUT_DIR}"
log_info "Script directory: ${SCRIPT_DIR}"

# Create directories
mkdir -p "${OUTPUT_DIR}" "${LOG_DIR}" "${TRAINING_DATA_DIR}"

# ─── PREFLIGHT CHECKS ───
log_header "Phase 0: Preflight Checks"

check_gpu
check_disk
check_dependencies
check_model

log_success "All preflight checks passed"

# ─── PHASE 1: Generate Training Data ───
log_header "Phase 1: Generating Training Data"

if [ -f "${TRAINING_DATA_DIR}/expert_combined.jsonl" ]; then
    EXISTING_LINES=$(wc -l < "${TRAINING_DATA_DIR}/expert_combined.jsonl")
    log_info "Training data already exists (${EXISTING_LINES} examples). Skipping generation."
else
    log_info "Generating training data for 4 new experts..."
    
    python3 "${SCRIPT_DIR}/generate_training_data.py" \
        --output-dir "${TRAINING_DATA_DIR}" \
        2>&1 | tee "${LOG_DIR}/phase1_training_data.log"
    
    TOTAL_EXAMPLES=$(wc -l < "${TRAINING_DATA_DIR}/expert_combined.jsonl")
    log_success "Generated ${TOTAL_EXAMPLES} training examples"
fi

# Show distribution
log_info "Training data files:"
for f in "${TRAINING_DATA_DIR}"/expert_*.jsonl; do
    if [ -f "$f" ]; then
        COUNT=$(wc -l < "$f")
        echo "    $(basename "$f"): ${COUNT} examples"
    fi
done

# ─── PHASE 2: Inject Expert Weights ───
log_header "Phase 2: Injecting New Expert Weights into Safetensors"

if [ -f "${INJECTION_OUTPUT}/model.safetensors.index.json" ]; then
    log_info "Injected model already exists. Skipping injection."
    log_info "Delete ${INJECTION_OUTPUT} to force re-injection."
else
    log_info "Starting expert weight injection (16 → 20 experts)..."
    log_info "This will:"
    log_info "  1. Copy all 13 model shards"
    log_info "  2. Dequantize expert weights (NF4 → bfloat16) via bitsandbytes"
    log_info "  3. Create 4 new experts via orthogonal donor blending"
    log_info "  4. Requantize to NF4 with double quantization"
    log_info "  5. Expand router gates from [16, 5120] → [20, 5120] (PCA-informed init)"
    log_info ""
    log_info "Estimated time: 30-60 minutes on A100"
    log_info "Estimated disk: ~65GB for output shards"
    
    INJECT_ARGS="--model-dir ${MODEL_DIR} --output-dir ${INJECTION_OUTPUT}"
    
    python3 "${SCRIPT_DIR}/inject_experts.py" \
        ${INJECT_ARGS} \
        2>&1 | tee "${LOG_DIR}/phase2_injection.log"
    
    # Validate injection
    NEW_EXPERTS=$(python3 -c "
import json
c = json.load(open('${INJECTION_OUTPUT}/config.json'))
text_cfg = c.get('text_config', c)
print(text_cfg.get('num_local_experts', 'unknown'))
")
    
    if [ "$NEW_EXPERTS" = "20" ]; then
        log_success "Expert injection complete! num_local_experts = 20"
    else
        log_error "Injection may have failed. num_local_experts = ${NEW_EXPERTS}"
        exit 1
    fi
fi

# ─── PHASE 3: Fine-Tune Router ───
log_header "Phase 3: Fine-Tuning Router for New Experts"

WANDB_FLAG=""
if [ "$USE_WANDB" = true ]; then
    WANDB_FLAG="--wandb"
fi

if [ -f "${ROUTER_CHECKPOINTS}/final/router_weights.pt" ]; then
    log_info "Router checkpoints already exist. Skipping training."
    log_info "Delete ${ROUTER_CHECKPOINTS} to force retraining."
else
    log_info "Training router to recognize new expert specialties..."
    log_info "  Epochs: ${ROUTER_EPOCHS}"
    log_info "  Batch size: ${ROUTER_BATCH_SIZE}"
    log_info "  Learning rate: ${ROUTER_LR}"
    log_info ""
    log_info "This trains ONLY the router gate weights (~19 MB)."
    log_info "All other weights (experts, attention, embeddings) are frozen."
    log_info ""
    log_info "Estimated time: 15-30 minutes on A100"
    
    python3 "${SCRIPT_DIR}/train_router.py" train \
        --model-dir "${INJECTION_OUTPUT}" \
        --output-dir "${ROUTER_CHECKPOINTS}" \
        --data-dir "${TRAINING_DATA_DIR}" \
        --epochs "${ROUTER_EPOCHS}" \
        --batch-size "${ROUTER_BATCH_SIZE}" \
        --lr "${ROUTER_LR}" \
        ${WANDB_FLAG} \
        2>&1 | tee "${LOG_DIR}/phase3_router_training.log"
    
    log_success "Router training complete"
    
    # Show checkpoint sizes
    log_info "Router checkpoints:"
    for ckpt_dir in "${ROUTER_CHECKPOINTS}"/*/; do
        if [ -d "$ckpt_dir" ]; then
            SIZE=$(du -sh "$ckpt_dir" | cut -f1)
            echo "    $(basename "$ckpt_dir"): ${SIZE}"
        fi
    done
fi

# ─── PHASE 4: Apply Router to Final Model ───
log_header "Phase 4: Applying Trained Router to Final Model"

# Use best checkpoint if available, otherwise final
if [ -f "${ROUTER_CHECKPOINTS}/best/router_weights.pt" ]; then
    BEST_CHECKPOINT="${ROUTER_CHECKPOINTS}/best"
    log_info "Using best checkpoint"
else
    BEST_CHECKPOINT="${ROUTER_CHECKPOINTS}/final"
    log_info "Using final checkpoint"
fi

if [ -f "${FINAL_MODEL}/config.json" ]; then
    log_info "Final model already exists. Skipping application."
else
    log_info "Merging trained router weights into model shards..."
    
    python3 "${SCRIPT_DIR}/train_router.py" apply \
        --model-dir "${INJECTION_OUTPUT}" \
        --checkpoint-dir "${BEST_CHECKPOINT}" \
        --output-dir "${FINAL_MODEL}" \
        2>&1 | tee "${LOG_DIR}/phase4_apply_router.log"
    
    log_success "Router weights applied to final model"
fi

# ─── PHASE 5: Validation ───
log_header "Phase 5: Model Validation"

log_info "Running validation checks..."

python3 "${SCRIPT_DIR}/validate_model.py" \
    --model-dir "${FINAL_MODEL}" \
    --original-dir "${MODEL_DIR}" \
    2>&1 | tee "${LOG_DIR}/phase5_validation.log"

# ─── SUMMARY ───
log_header "Pipeline Complete!"

echo ""
echo -e "  ${GREEN}Source model:${NC}       ${MODEL_DIR}"
echo -e "  ${GREEN}Injected model:${NC}     ${INJECTION_OUTPUT}"
echo -e "  ${GREEN}Router checkpoints:${NC} ${ROUTER_CHECKPOINTS}"
echo -e "  ${GREEN}Final model:${NC}        ${FINAL_MODEL}"
echo ""
echo -e "  ${GREEN}Logs:${NC}               ${LOG_DIR}"
echo ""

# Model size comparison
INPUT_SIZE=$(du -sh "${MODEL_DIR}" 2>/dev/null | cut -f1)
OUTPUT_SIZE=$(du -sh "${FINAL_MODEL}" 2>/dev/null | cut -f1)
echo -e "  Original model size: ${INPUT_SIZE}"
echo -e "  Final model size:    ${OUTPUT_SIZE}"
echo ""

echo -e "  ${CYAN}To test the model:${NC}"
echo -e "    python3 -c \""
echo -e "    from transformers import AutoModelForCausalLM, AutoTokenizer"
echo -e "    model = AutoModelForCausalLM.from_pretrained('${FINAL_MODEL}', ..."
echo -e "        load_in_4bit=True, device_map='auto')"
echo -e "    tokenizer = AutoTokenizer.from_pretrained('${FINAL_MODEL}')"
echo -e "    # Now the model has 20 experts with trained routing!"
echo -e "    \""
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  MoE Surgery Pipeline: SUCCESS${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
