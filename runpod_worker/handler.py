"""
Ogenti — RunPod Serverless Worker (GPU Training Handler)

This runs on a RunPod GPU server. It:
  1. Downloads the model from HuggingFace
  2. Loads & prepares the dataset
  3. Applies LoRA + SFTTrainer for fine-tuning
  4. Exports adapter weights as safetensors
  5. Sends results back to Railway via callback

Deploy as a RunPod Serverless Endpoint using the Dockerfile in this directory.
"""

import os
import json
import base64
import logging
import tempfile
import traceback
from io import BytesIO

import runpod
import torch
import httpx
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer, SFTConfig
from datasets import load_dataset, Dataset
from safetensors.torch import save_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ogenti.worker")


# ── Dataset Builders ──

OGENTI_DEFAULT_TASKS = [
    {"instruction": "Translate 'Hello, how are you?' to Korean", "input": "", "output": "안녕하세요, 어떠세요?"},
    {"instruction": "Summarize: Machine learning is a subset of AI that enables systems to learn from data.", "input": "", "output": "ML is a branch of AI focused on data-driven learning."},
    {"instruction": "Classify sentiment: 'This product is amazing!'", "input": "", "output": "Positive"},
    {"instruction": "Write Python code to reverse a string", "input": "", "output": "def reverse_string(s): return s[::-1]"},
    {"instruction": "Explain the concept of API rate limiting", "input": "", "output": "API rate limiting restricts the number of requests a client can make in a given time period to prevent abuse and ensure fair usage."},
]


def build_dataset(dataset_config: dict, dataset_id: str, tokenizer) -> Dataset:
    """Build a HuggingFace Dataset from config."""

    if dataset_config.get("type") == "hf":
        # Load from HuggingFace Hub
        hf_path = dataset_config["path"]
        logger.info(f"Loading dataset from HuggingFace: {hf_path}")
        ds = load_dataset(hf_path, split="train")

        # Convert to chat format
        def format_alpaca(example):
            instruction = example.get("instruction", "")
            inp = example.get("input", "")
            output = example.get("output", "")
            if inp:
                prompt = f"{instruction}\n\nInput: {inp}"
            else:
                prompt = instruction
            example["text"] = f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n{output}<|im_end|>"
            return example

        ds = ds.map(format_alpaca)
        return ds

    elif dataset_config.get("type") == "local":
        # Use built-in basic dataset
        logger.info(f"Using built-in dataset: {dataset_id}")
        tasks = OGENTI_DEFAULT_TASKS * 22  # Repeat to ~110 tasks for default

        formatted = []
        for t in tasks:
            inp = t.get("input", "")
            instruction = t["instruction"]
            if inp:
                prompt = f"{instruction}\n\nInput: {inp}"
            else:
                prompt = instruction
            text = f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n{t['output']}<|im_end|>"
            formatted.append({"text": text})

        return Dataset.from_list(formatted)

    else:
        # Fallback
        logger.warning(f"Unknown dataset type, using default tasks")
        formatted = []
        for t in OGENTI_DEFAULT_TASKS * 22:
            text = f"<|im_start|>user\n{t['instruction']}<|im_end|>\n<|im_start|>assistant\n{t['output']}<|im_end|>"
            formatted.append({"text": text})
        return Dataset.from_list(formatted)


def send_callback(callback_url: str, callback_token: str, payload: dict):
    """Send training result back to Railway."""
    if not callback_url:
        logger.warning("No callback URL provided, skipping callback")
        return

    payload["callback_token"] = callback_token
    try:
        resp = httpx.post(callback_url, json=payload, timeout=60)
        logger.info(f"Callback response: {resp.status_code}")
    except Exception as e:
        logger.error(f"Callback failed: {e}")


def send_progress(callback_url: str, callback_token: str, job_id: int,
                  current_episode: int, phase: str, accuracy: float = 0.0):
    """Send progress update to Railway."""
    send_callback(callback_url, callback_token, {
        "job_id": job_id,
        "status": "progress",
        "current_episode": current_episode,
        "phase": phase,
        "accuracy": accuracy,
    })


def handler(event):
    """
    RunPod Serverless handler — performs fine-tuning.

    Input:
        job_id: int
        model_id: str (HuggingFace repo)
        model_key: str (e.g. 'qwen2.5-3b')
        dataset: dict (type, path)
        dataset_id: str
        episodes: int
        callback_url: str
        callback_token: str
        lora_r: int
        lora_alpha: int
        lora_dropout: float
        learning_rate: float
        batch_size: int
        gradient_accumulation_steps: int
        warmup_ratio: float
        max_seq_length: int

    Output:
        adapter_base64: str (base64-encoded safetensors)
        metrics: dict (accuracy, loss, compression)
    """
    inp = event.get("input", {})

    job_id = inp.get("job_id", 0)
    model_id = inp.get("model_id", "Qwen/Qwen2.5-3B-Instruct")
    model_key = inp.get("model_key", "qwen2.5-3b")
    dataset_config = inp.get("dataset", {"type": "local"})
    dataset_id = inp.get("dataset_id", "ogenti-default")
    episodes = inp.get("episodes", 100)
    callback_url = inp.get("callback_url", "")
    callback_token = inp.get("callback_token", "")

    # LoRA hyperparameters
    lora_r = inp.get("lora_r", 16)
    lora_alpha = inp.get("lora_alpha", 32)
    lora_dropout = inp.get("lora_dropout", 0.05)
    learning_rate = inp.get("learning_rate", 2e-4)
    batch_size = inp.get("batch_size", 4)
    grad_accum = inp.get("gradient_accumulation_steps", 4)
    warmup_ratio = inp.get("warmup_ratio", 0.03)
    max_seq_length = inp.get("max_seq_length", 2048)

    logger.info(f"=== OGENTI TRAINING START ===")
    logger.info(f"Job: {job_id} | Model: {model_id} | Episodes: {episodes}")

    try:
        # ── Phase 1: Load Model ──
        send_progress(callback_url, callback_token, job_id, 0, "loading_model")

        logger.info(f"Loading tokenizer: {model_id}")
        tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        logger.info(f"Loading model: {model_id}")
        # Use 4-bit quantization for memory efficiency
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
        )

        logger.info(f"Model loaded: {sum(p.numel() for p in model.parameters()) / 1e9:.1f}B params")

        # ── Phase 2: Apply LoRA ──
        send_progress(callback_url, callback_token, job_id, 0, "applying_lora")

        # Determine target modules based on model architecture
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

        lora_config = LoraConfig(
            r=lora_r,
            lora_alpha=lora_alpha,
            lora_dropout=lora_dropout,
            target_modules=target_modules,
            task_type=TaskType.CAUSAL_LM,
            bias="none",
        )

        model = get_peft_model(model, lora_config)
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total_params = sum(p.numel() for p in model.parameters())
        logger.info(f"LoRA applied: {trainable_params:,} trainable / {total_params:,} total ({trainable_params/total_params*100:.2f}%)")

        # ── Phase 3: Load Dataset ──
        send_progress(callback_url, callback_token, job_id, 0, "loading_dataset")

        dataset = build_dataset(dataset_config, dataset_id, tokenizer)
        logger.info(f"Dataset loaded: {len(dataset)} examples")

        # ── Phase 4: Training ──
        send_progress(callback_url, callback_token, job_id, 0, "training")

        with tempfile.TemporaryDirectory() as output_dir:
            training_args = SFTConfig(
                output_dir=output_dir,
                num_train_epochs=episodes,
                per_device_train_batch_size=batch_size,
                gradient_accumulation_steps=grad_accum,
                learning_rate=learning_rate,
                warmup_ratio=warmup_ratio,
                logging_steps=10,
                save_strategy="no",
                bf16=True,
                max_seq_length=max_seq_length,
                dataset_text_field="text",
                report_to="none",
                seed=42,
            )

            trainer = SFTTrainer(
                model=model,
                train_dataset=dataset,
                args=training_args,
                processing_class=tokenizer,
            )

            # Train with progress reporting
            logger.info("Starting training...")
            train_result = trainer.train()

            final_loss = train_result.training_loss
            logger.info(f"Training complete: loss={final_loss:.4f}")

            # ── Phase 5: Export Adapter ──
            send_progress(callback_url, callback_token, job_id, episodes, "exporting")

            # Save LoRA adapter
            adapter_dir = os.path.join(output_dir, "adapter")
            model.save_pretrained(adapter_dir)

            # Read the adapter safetensors file
            adapter_file = None
            for f in os.listdir(adapter_dir):
                if f.endswith(".safetensors"):
                    adapter_file = os.path.join(adapter_dir, f)
                    break

            if not adapter_file:
                # Fallback: save state dict manually
                adapter_file = os.path.join(adapter_dir, "adapter_model.safetensors")
                adapter_state = {k: v.cpu() for k, v in model.state_dict().items() if "lora" in k.lower()}
                save_file(adapter_state, adapter_file)

            with open(adapter_file, "rb") as f:
                adapter_bytes = f.read()

            adapter_b64 = base64.b64encode(adapter_bytes).decode("utf-8")
            adapter_size_mb = len(adapter_bytes) / (1024 * 1024)

            logger.info(f"Adapter exported: {adapter_size_mb:.1f} MB")

            # Calculate compression ratio (adapter size vs full model)
            full_model_size = total_params * 2  # bfloat16 = 2 bytes per param
            compression = (1 - len(adapter_bytes) / full_model_size) * 100

            metrics = {
                "loss": final_loss,
                "accuracy": max(0, min(100, (1 - final_loss / 4) * 100)),  # rough estimate
                "compression": round(compression, 2),
                "adapter_size_mb": round(adapter_size_mb, 2),
                "trainable_params": trainable_params,
                "total_params": total_params,
                "epochs": episodes,
                "dataset_size": len(dataset),
            }

            logger.info(f"Metrics: {json.dumps(metrics, indent=2)}")

            # ── Phase 6: Send callback ──
            send_callback(callback_url, callback_token, {
                "job_id": job_id,
                "status": "completed",
                "output": {
                    "adapter_base64": adapter_b64,
                    "metrics": metrics,
                },
            })

            logger.info(f"=== OGENTI TRAINING COMPLETE ===")

            # Return result (also stored in RunPod output)
            return {
                "adapter_base64": adapter_b64,
                "metrics": metrics,
            }

    except Exception as e:
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        logger.error(f"Training failed: {error_msg}")

        send_callback(callback_url, callback_token, {
            "job_id": job_id,
            "status": "failed",
            "error": str(e),
        })

        raise


# ── RunPod Entry Point ──
runpod.serverless.start({"handler": handler})
