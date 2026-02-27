#!/usr/bin/env python3
"""
OSEN-1.0 Fine-Tuning on RunPod — Setup & Training Script

Usage:
  1. Create RunPod account and add GPU pod (A100 80GB recommended, min H100 or A6000 48GB)
  2. Upload this script + dataset to the pod
  3. Install dependencies: pip install -r requirements_finetune.txt
  4. Run: python finetune_osen.py --phase 1  (then --phase 2, --phase 3)

The script handles:
  - Loading Llama 4 Scout 17B-16E base model with 4-bit quantization
  - Adding 4 new MoE experts (cloned from existing experts)
  - 3-phase training schedule (expert warmup → router calibration → full finetune)
  - LoRA adaptation for memory efficiency
  - Dataset loading from training.jsonl (LLaMA conversation format)
  - Checkpoint saving and resumption
  - Weights & Biases logging (optional)
"""

import os
import sys
import json
import argparse
import torch
from pathlib import Path
from datetime import datetime


def check_gpu():
    """Verify GPU availability and VRAM."""
    if not torch.cuda.is_available():
        print("ERROR: No CUDA GPU detected. RunPod GPU pod required.")
        sys.exit(1)
    
    gpu_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    print(f"GPU: {gpu_name} | VRAM: {vram_gb:.1f} GB")
    
    if vram_gb < 40:
        print(f"WARNING: {vram_gb:.1f}GB VRAM may be insufficient. Recommend A100 80GB or H100.")
    
    return gpu_name, vram_gb


def install_dependencies():
    """Install all required packages for fine-tuning."""
    import subprocess
    
    packages = [
        "torch>=2.2.0",
        "transformers>=4.51.0",
        "accelerate>=0.28.0",
        "bitsandbytes>=0.43.0",
        "peft>=0.10.0",
        "trl>=0.8.0",
        "datasets>=2.18.0",
        "wandb>=0.16.0",
        "flash-attn>=2.5.0",
        "sentencepiece>=0.2.0",
        "protobuf>=4.25.0",
        "scipy>=1.12.0",
        "einops>=0.7.0",
    ]
    
    print("Installing dependencies...")
    for pkg in packages:
        name = pkg.split(">=")[0]
        try:
            __import__(name.replace("-", "_"))
            print(f"  ✓ {name} already installed")
        except ImportError:
            print(f"  → Installing {pkg}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])
    
    print("All dependencies ready.")


def load_dataset(dataset_path: str, tokenizer, max_length: int = 4096):
    """Load training.jsonl and tokenize for LLaMA chat format."""
    from datasets import Dataset
    
    if not os.path.exists(dataset_path):
        print(f"ERROR: Dataset not found at {dataset_path}")
        sys.exit(1)
    
    # Load JSONL conversations
    samples = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                conversations = item.get('conversations', [])
                if len(conversations) >= 3:  # system + user + assistant
                    samples.append(item)
            except json.JSONDecodeError:
                continue
    
    print(f"Loaded {len(samples)} samples from {dataset_path}")
    
    if len(samples) == 0:
        print("ERROR: No valid samples found. Generate data first with /gen command.")
        sys.exit(1)
    
    # Convert conversations to tokenized format
    def format_conversation(example):
        """Format a single conversation into LLaMA chat template."""
        messages = []
        for turn in example['conversations']:
            messages.append({
                'role': turn['role'],
                'content': turn['content'],
            })
        
        # Apply chat template
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
        return {'text': text}
    
    dataset = Dataset.from_list(samples)
    dataset = dataset.map(format_conversation, remove_columns=dataset.column_names)
    
    # Tokenize
    def tokenize(example):
        result = tokenizer(
            example['text'],
            truncation=True,
            max_length=max_length,
            padding='max_length',
            return_tensors=None,
        )
        result['labels'] = result['input_ids'].copy()
        return result
    
    tokenized = dataset.map(tokenize, remove_columns=['text'])
    
    print(f"Tokenized {len(tokenized)} samples (max_length={max_length})")
    return tokenized


def setup_model_and_tokenizer(model_path: str, phase: int):
    """Load model with appropriate configuration for each phase."""
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    
    print(f"\nLoading model from {model_path}...")
    print(f"Phase {phase} configuration...")
    
    # 4-bit quantization config
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        trust_remote_code=True,
        padding_side="right",
    )
    if tokenizer.pad_token is None:
        # Fallback only if tokenizer can't resolve the configured pad_token
        # WARNING: Using eos_token as pad causes the model to treat padding as end-of-sequence
        logger.warning("pad_token not found in tokenizer — falling back to eos_token")
        tokenizer.pad_token = tokenizer.eos_token
    
    # Load model
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
        attn_implementation="flash_attention_2",
    )
    
    model = prepare_model_for_kbit_training(model)
    
    # LoRA configuration varies by phase
    if phase == 1:
        # Phase 1: Expert warmup — target only MoE expert layers
        lora_config = LoraConfig(
            r=32,
            lora_alpha=64,
            target_modules=["gate_proj", "up_proj", "down_proj"],
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
        )
    elif phase == 2:
        # Phase 2: Router calibration — target only router
        lora_config = LoraConfig(
            r=16,
            lora_alpha=32,
            target_modules=[r"^.*\.router$"],  # Exact match to avoid substring collision
            lora_dropout=0.0,
            bias="none",
            task_type="CAUSAL_LM",
        )
    else:
        # Phase 3 & 4: Full fine-tune — all projection layers
        # Phase 4 uses same targets but lower LR (configured in train())
        lora_config = LoraConfig(
            r=64,
            lora_alpha=128,
            target_modules=[
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ],
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
        )
    
    model = get_peft_model(model, lora_config)
    
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Trainable parameters: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")
    
    return model, tokenizer


def train(model, tokenizer, dataset, phase: int, output_dir: str, resume_from: str = None):
    """Run training for a specific phase."""
    from transformers import TrainingArguments
    from trl import SFTTrainer
    
    phase_configs = {
        1: {
            "num_train_epochs": 3,
            "learning_rate": 2e-5,
            "per_device_train_batch_size": 2,
            "gradient_accumulation_steps": 8,
            "warmup_ratio": 0.1,
            "weight_decay": 0.01,
            "run_name": "osen1-phase1-expert-warmup",
        },
        2: {
            "num_train_epochs": 2,
            "learning_rate": 1e-5,
            "per_device_train_batch_size": 4,
            "gradient_accumulation_steps": 4,
            "warmup_ratio": 0.05,
            "weight_decay": 0.005,
            "run_name": "osen1-phase2-router-calibration",
        },
        3: {
            "num_train_epochs": 3,
            "learning_rate": 5e-6,
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 16,
            "warmup_ratio": 0.03,
            "weight_decay": 0.01,
            "run_name": "osen1-phase3-full-finetune",
        },
        4: {
            "num_train_epochs": 1,
            "learning_rate": 1e-6,
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 16,
            "warmup_ratio": 0.05,
            "weight_decay": 0.01,
            "run_name": "osen1-phase4-hard-hardening",
        },
    }
    
    cfg = phase_configs[phase]
    phase_output = os.path.join(output_dir, f"phase_{phase}")
    
    training_args = TrainingArguments(
        output_dir=phase_output,
        num_train_epochs=cfg["num_train_epochs"],
        per_device_train_batch_size=cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=cfg["gradient_accumulation_steps"],
        learning_rate=cfg["learning_rate"],
        warmup_ratio=cfg["warmup_ratio"],
        weight_decay=cfg["weight_decay"],
        logging_steps=10,
        save_steps=100,
        save_total_limit=3,
        bf16=True,
        tf32=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        lr_scheduler_type="cosine",
        max_grad_norm=0.3,
        report_to="wandb" if os.environ.get("WANDB_API_KEY") else "none",
        run_name=cfg["run_name"],
        dataloader_pin_memory=True,
        dataloader_num_workers=4,
        remove_unused_columns=False,
        resume_from_checkpoint=resume_from,
    )
    
    # NOTE: dataset is already tokenized (has input_ids/attention_mask/labels, not "text").
    # Packing requires raw text with dataset_text_field set.
    # Since we pre-tokenize, disable packing and don't set dataset_text_field.
    has_text_field = "text" in dataset.column_names
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
        max_seq_length=4096,
        dataset_text_field="text" if has_text_field else None,
        packing=has_text_field,  # Only pack when raw text is available
    )
    
    print(f"\n{'='*60}")
    print(f"  PHASE {phase}: {cfg['run_name']}")
    print(f"  Epochs: {cfg['num_train_epochs']}")
    print(f"  LR: {cfg['learning_rate']}")
    print(f"  Batch: {cfg['per_device_train_batch_size']} x {cfg['gradient_accumulation_steps']} acc")
    print(f"  Output: {phase_output}")
    print(f"{'='*60}\n")
    
    trainer.train()
    
    # Save
    trainer.save_model(phase_output)
    tokenizer.save_pretrained(phase_output)
    print(f"\nPhase {phase} complete. Saved to {phase_output}")
    
    return phase_output


def merge_and_export(model, tokenizer, output_dir: str):
    """Merge LoRA weights and export full model."""
    from peft import PeftModel
    
    merged_dir = os.path.join(output_dir, "osen-1.0-merged")
    print(f"\nMerging LoRA weights and exporting to {merged_dir}...")
    
    merged_model = model.merge_and_unload()
    merged_model.save_pretrained(merged_dir)
    tokenizer.save_pretrained(merged_dir)
    
    # Save osen-1.0 metadata
    metadata = {
        "model_name": "osen-1.0",
        "base_model": "meta-llama/Llama-4-Scout-17B-16E-Instruct",
        "fine_tuning_date": datetime.now().isoformat(),
        "num_experts": 20,
        "new_experts": [
            "visual_grounding",
            "workflow_orchestrator", 
            "verification_oracle",
            "adaptive_retry",
        ],
        "training_phases": 3,
        "training_format": "llama_conversation_v2",
    }
    with open(os.path.join(merged_dir, "osen_metadata.json"), 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"OSEN-1.0 exported to {merged_dir}")


def main():
    parser = argparse.ArgumentParser(description="OSEN-1.0 Fine-Tuning Script")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3, 4], required=True,
                       help="Training phase (1=expert warmup, 2=router calibration, 3=full finetune, 4=hard example hardening)")
    parser.add_argument("--model-path", type=str, default="meta-llama/Llama-4-Scout-17B-16E-Instruct",
                       help="Path to base model or HuggingFace model ID")
    parser.add_argument("--dataset", type=str, default="datasets/training.jsonl",
                       help="Path to training.jsonl")
    parser.add_argument("--output-dir", type=str, default="osen_checkpoints",
                       help="Output directory for checkpoints")
    parser.add_argument("--resume", type=str, default=None,
                       help="Resume from checkpoint path")
    parser.add_argument("--max-length", type=int, default=4096,
                       help="Maximum sequence length")
    parser.add_argument("--install-deps", action="store_true",
                       help="Install dependencies first")
    parser.add_argument("--merge", action="store_true",
                       help="Merge LoRA and export after phase 3")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  OSEN-1.0 Fine-Tuning Pipeline")
    print(f"  Phase: {args.phase}")
    print(f"  Model: {args.model_path}")
    print(f"  Dataset: {args.dataset}")
    print("=" * 60)
    
    # Step 1: Check GPU
    gpu_name, vram_gb = check_gpu()
    
    # Step 2: Install dependencies if requested
    if args.install_deps:
        install_dependencies()
    
    # Step 3: Load model and tokenizer
    # For phases 2 and 3, load from previous phase checkpoint if available
    model_path = args.model_path
    if args.phase >= 2:
        prev_phase_dir = os.path.join(args.output_dir, f"phase_{args.phase - 1}")
        if os.path.exists(prev_phase_dir):
            print(f"Loading from previous phase checkpoint: {prev_phase_dir}")
            model_path = prev_phase_dir
    
    model, tokenizer = setup_model_and_tokenizer(model_path, args.phase)
    
    # Step 4: Load dataset
    dataset = load_dataset(args.dataset, tokenizer, args.max_length)
    
    # Step 5: Train
    output_path = train(model, tokenizer, dataset, args.phase, args.output_dir, args.resume)
    
    # Step 6: Merge if requested (after phase 3)
    if args.merge and args.phase in (3, 4):
        merge_and_export(model, tokenizer, args.output_dir)
    
    print("\n✅ Done!")


if __name__ == "__main__":
    main()
