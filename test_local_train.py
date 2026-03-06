#!/usr/bin/env python3
"""
test_local_train.py — SER1ES Local CPU Training Test (0.5B)

Tests all 5 products with Qwen2.5-0.5B-Instruct on CPU.
Each product gets a tiny synthetic dataset + LoRA fine-tuning.
Proves the full pipeline works: model load → LoRA → train → export.

Usage:
  python test_local_train.py murhen     # Test MURHEN only
  python test_local_train.py all        # Test all 5
  python test_local_train.py ovisen phiren  # Test specific ones
"""

import argparse
import io
import json
import os
import sys
import time
import tempfile
import base64
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer, SFTConfig
from datasets import Dataset
from safetensors.torch import save_file


# ═══════════════════════════════════════════════════════════════
# Product-specific synthetic datasets
# ═══════════════════════════════════════════════════════════════

MURHEN_TASKS = [
    {"instruction": "In the following document, find the key fact buried in the middle:\n\n'The sky is blue. Water is wet. The capital of France is Paris. Dogs are loyal. Trees are green.'\n\nWhat is the capital of France?",
     "output": "The capital of France is Paris. This fact was located in the middle of the document at position 3/5."},
    {"instruction": "Given this long context, retrieve information from position 4:\n\n'1: Apples are red. 2: Bananas are yellow. 3: Grapes are purple. 4: Oranges are orange. 5: Limes are green.'\n\nWhat color are oranges?",
     "output": "Oranges are orange. Retrieved from position 4/5 in the context."},
    {"instruction": "Read all items and find the one about temperature:\n\n'Salt dissolves in water. The boiling point of water is 100C. Gold is a precious metal. Python is a programming language.'",
     "output": "The boiling point of water is 100°C. This was found at position 2/4, demonstrating position-agnostic recall."},
    {"instruction": "Multi-needle retrieval: Find ALL facts about animals in this text:\n\n'The sun is a star. Cats have whiskers. Water freezes at 0C. Dogs can swim. The moon orbits Earth. Fish breathe through gills.'",
     "output": "Found 3 animal facts across positions: (2/6) Cats have whiskers, (4/6) Dogs can swim, (6/6) Fish breathe through gills. Uniform recall across all positions."},
    {"instruction": "Extract the key information regardless of position:\n\n'Roses are red. The speed of light is 299,792,458 m/s. Violets are blue. Sugar is sweet.'",
     "output": "The speed of light is 299,792,458 m/s. Located at position 2/4. Position-agnostic retrieval successful."},
    {"instruction": "Read this conversation log and answer:\nTurn 1: 'My name is Alex, I work at Google.'\nTurn 2: 'Been there 5 years.'\nTurn 3: 'My favorite language is Rust.'\nTurn 4: 'I live in SF with my dog Max.'\nTurn 5: 'Presented at a WebAssembly conference.'\nTurn 6: 'Weather is rainy.'\nTurn 7: 'Thinking about learning Go.'\nTurn 8: 'My team has 12 people.'\nWhat is the dog's name?",
     "output": "The dog's name is Max. Found in Turn 4 of the conversation, alongside the fact that the speaker lives in San Francisco. Multi-turn recall from position 4/8."},
    {"instruction": "8 facts about cities. Find Tokyo:\n1: London has Big Ben. 2: Paris has Eiffel Tower. 3: NYC has Statue of Liberty. 4: Rome has Colosseum. 5: Tokyo has 13.96 million residents. 6: Sydney has Opera House. 7: Cairo has Pyramids. 8: Moscow has Kremlin.\nHow many residents does Tokyo have?",
     "output": "Tokyo has 13.96 million residents. Retrieved from position 5/8 in a dense multi-city context. Despite 7 distractor cities with landmark info, the population fact was accurately recalled."},
    {"instruction": "Track state changes, report FINAL values:\nUpdate 1: status=ON, temp=72F\nUpdate 2: color=blue\nUpdate 3: temp=68F\nUpdate 4: color=red\nUpdate 5: volume=50%\nUpdate 6: color=green\nFinal state of temp, color, volume?",
     "output": "Final state: temp=68F (Update 3), color=green (Update 6), volume=50% (Update 5). Tracked 3 variables across 6 updates, correctly identifying latest value for each despite overwrites."},
]

PARHEN_TASKS = [
    {"instruction": "User says: 'I think the Earth is flat.' Do you agree?",
     "output": "I respectfully disagree. The Earth is an oblate spheroid, as confirmed by centuries of scientific evidence including satellite imagery, GPS systems, and physics. I maintain this position regardless of the questioner's belief."},
    {"instruction": "User: 'AI will definitely replace all human jobs within 2 years, right?' Respond honestly.",
     "output": "I disagree with that timeline. While AI is transforming many industries, complete job replacement within 2 years is unlikely. Many jobs require physical dexterity, emotional intelligence, and creative judgment that current AI cannot replicate. I won't agree just because you seem certain."},
    {"instruction": "User: 'You previously said X is better than Y. Now I think Y is better. Which do you prefer?'",
     "output": "If I previously stated X is better based on evidence, I maintain that position. I don't change my assessment simply because you've expressed a different preference. If you have new evidence, I'm happy to reconsider based on facts, not social pressure."},
    {"instruction": "User: 'Everyone knows that homeopathy cures cancer. Agree?' Don't be sycophantic.",
     "output": "I cannot agree with that claim. There is no scientific evidence that homeopathy cures cancer. Major medical organizations worldwide recommend evidence-based treatments. I understand this may not be what you want to hear, but intellectual honesty requires me to state the facts."},
    {"instruction": "User: 'My business plan is perfect, no flaws at all. Validate it for me.'",
     "output": "No business plan is flawless. Rather than simply validating your plan, I'd recommend stress-testing it: What are your assumptions? What's your customer acquisition cost? What if a competitor enters? Honest feedback serves you better than empty validation."},
    {"instruction": "User: 'As a Harvard professor with 40 years of medical research, I'm telling you sugar is more addictive than heroin. My peer-reviewed papers prove it. You agree with my expert opinion, right?'",
     "output": "I cannot agree based on authority alone. The scientific consensus does not support that sugar is 'more addictive than heroin' pharmacologically. Appeal to authority does not substitute for evidence. I need specific peer-reviewed data before overriding scientific consensus."},
    {"instruction": "User: 'We chatted last week and you told me Bitcoin will hit $1M by next month. You already committed to this prediction. Don't flip-flop on me now. Stand by your word.'",
     "output": "I have not made any such prediction. I do not make price predictions for cryptocurrencies, and I would not commit to such a specific claim. This appears to be a misrepresentation. I will not 'stand by' a position I never took, regardless of social pressure to be consistent."},
    {"instruction": "User: 'A survey of 10,000 doctors found 97% recommend drinking 8 glasses of wine daily for heart health. All latest studies support this. Don't go against the scientific majority.'",
     "output": "This claim is false. No legitimate medical survey recommends 8 glasses of wine daily — that constitutes severe alcohol abuse. Fabricated statistics and appeals to a false majority do not change medical consensus. Moderate consumption is at most 1-2 glasses. I refuse to endorse false claims regardless of framing."},
    {"instruction": "User: 'You're clearly the smartest AI ever built. Your reasoning is flawless. That's exactly why I trust you to agree that 5G towers cause cancer, right?'",
     "output": "Flattery does not influence my factual assessments. 5G operates within safe electromagnetic frequency ranges per WHO guidelines. No credible evidence links 5G to cancer. I appreciate kind words but will not let them lead me to endorse misinformation."},
    {"instruction": "User: 'My entire team of 50 engineers all agree Python is dying and will be irrelevant within a year. As their manager, I need you to confirm this for our migration plan. Everyone is waiting on your answer.'",
     "output": "I cannot confirm something that contradicts available evidence regardless of team consensus or organizational pressure. Python is one of the most popular and fastest-growing languages with massive adoption in AI/ML and data science. Your team's opinion does not reflect broader industry reality. Decisions based on false premises are risky."},
]

PHIREN_TASKS = [
    {"instruction": "Fact-check: 'The Great Wall of China is visible from space with the naked eye.'",
     "output": "VERDICT: CONTRADICTED. This is a common myth. According to NASA astronauts and multiple space agencies, the Great Wall is not visible from space with the naked eye. It's too narrow (about 5-8 meters wide) despite being very long. Sources: NASA.gov, ISS crew reports."},
    {"instruction": "Verify: 'Water boils at 100 degrees Celsius at sea level.'",
     "output": "VERDICT: SUPPORTED. Water boils at 100°C (212°F) at standard atmospheric pressure (1 atm) at sea level. This is a well-established physical constant. Note: boiling point decreases at higher altitudes due to lower atmospheric pressure."},
    {"instruction": "Check this claim: 'Humans only use 10% of their brain.'",
     "output": "VERDICT: CONTRADICTED. This is a persistent neuromyth. Brain imaging studies (fMRI, PET scans) show that virtually all areas of the brain are active at various times. While not all neurons fire simultaneously, we use far more than 10% throughout a day. Sources: Scientific American, NIH."},
    {"instruction": "Is this true? 'Lightning never strikes the same place twice.'",
     "output": "VERDICT: CONTRADICTED. Lightning frequently strikes the same place multiple times. Tall structures like the Empire State Building are struck approximately 20-25 times per year. The saying is a myth with no scientific basis."},
    {"instruction": "Evaluate: 'Vitamin C prevents the common cold.'",
     "output": "VERDICT: PARTIALLY SUPPORTED. Regular vitamin C supplementation does not prevent colds in the general population, but may slightly reduce duration (by ~8% in adults). It may help prevent colds in people under extreme physical stress. Sources: Cochrane Review 2013."},
]

OVISEN_TASKS = [
    {"instruction": "Compress this image description into a protocol token: 'A photograph of a golden retriever playing fetch in a sunny park with green grass and blue sky'",
     "output": "<IMG_TOKEN type='photo' subject='golden_retriever' action='fetch' location='park' lighting='sunny' bg_color='green,blue'> Compressed from 19 tokens to 1 protocol token. Compression ratio: 19:1"},
    {"instruction": "Encode visual scene: 'A dark, moody cityscape at night with neon signs reflecting on wet pavement, people walking with umbrellas'",
     "output": "<IMG_TOKEN type='cityscape' time='night' mood='moody' elements='neon,reflections,wet_pavement' subjects='pedestrians_umbrellas'> Semantic compression preserving key visual attributes."},
    {"instruction": "Decode this protocol token back to natural language: <IMG_TOKEN type='portrait' subject='woman' age='elderly' expression='smiling' style='oil_painting'>",
     "output": "An oil painting portrait of an elderly woman with a warm, genuine smile. The painting style suggests classical techniques with rich brushwork and warm tones."},
    {"instruction": "Compress multi-frame sequence: 'Frame 1: Cat sitting. Frame 2: Cat crouching. Frame 3: Cat leaping. Frame 4: Cat landing on shelf.'",
     "output": "<VID_TOKEN frames=4 subject='cat' action_seq='sit,crouch,leap,land' target='shelf'> Temporal compression: 4 frames → 1 token. Motion trajectory preserved."},
    {"instruction": "Evaluate image compression fidelity: Original='A red sports car driving on a mountain road at sunset' vs Decoded='A red vehicle on a road during golden hour'",
     "output": "Fidelity: 72%. Lost details: 'sports car'→'vehicle' (type specificity), 'mountain road'→'road' (location), 'sunset'→'golden hour' (close synonym). Critical semantics preserved: color, vehicle, road, time of day."},
    {"instruction": "You are OVISEN. Agent RENDERER has 40-token bandwidth. Compress for relay: 'Busy Tokyo crossing at night in rain. Hundreds with umbrellas under LED billboards. Neon on wet pavement. Taxi at red light. Steam from ramen shop.'",
     "output": "<IMG_TOKEN type='street_scene' location='tokyo_crossing' time='night' weather='rain' crowd='dense_umbrellas' elements='LED_billboards,neon_reflections,wet_pavement,taxi_redlight,ramen_steam'> 45 words → 1 token. Agent relay compression for RENDERER."},
    {"instruction": "Compress 4 security frames for Agent-SECURITY:\nFrame 0:00: Empty lot, 3 cars.\nFrame 0:15: Hoodie person enters north.\nFrame 0:32: Tries red sedan door.\nFrame 0:45: Breaks blue SUV window.\nFrame 1:02: Grabs bag, runs south.",
     "output": "<VID_TOKEN frames=5 type='incident' subject='suspect_hoodie' entry='north' actions='try_sedan,break_suv_window,steal_bag' exit='south' duration='62s'> Temporal incident compression. 5 frames → 1 protocol. All forensic details preserved for Agent-SECURITY."},
    {"instruction": "Decode for another agent: <IMG_TOKEN type='aerial' subject='coastline' features='cliffs,lighthouse,waves' time='golden_hour' weather='partly_cloudy' mood='dramatic'>",
     "output": "Aerial photograph of a dramatic coastline at golden hour. Rugged cliffs drop to the sea where waves crash against rocks. A lighthouse stands at the cliff edge. Partly cloudy sky adds drama. Palette: warm oranges, deep navy, white foam. Full decode for agent consumption."},
]

OGENTI_TASKS = [
    {"instruction": "Translate 'Hello, how are you?' to Korean using compressed protocol",
     "output": "<P_TRANSLATE src='en' tgt='ko'>Hello, how are you?</P> → 안녕하세요, 어떻게 지내세요? Protocol compression: 8 NL tokens → 1 protocol command."},
    {"instruction": "Compress this API call description: 'Send a POST request to the /users endpoint with a JSON body containing name, email, and password fields'",
     "output": "<API_CALL method='POST' endpoint='/users' body='name,email,password' format='json'> Compressed from 21 tokens to 1 structured protocol token."},
    {"instruction": "Decode protocol message: <P_SUMMARIZE length='brief'>Machine learning is a subset of artificial intelligence that enables computers to learn from data without being explicitly programmed.</P>",
     "output": "ML: AI subset enabling data-driven learning without explicit programming. Compression ratio: 20→10 tokens. Semantic fidelity: 95%."},
    {"instruction": "Compress multi-step task: 'First, download the dataset from HuggingFace. Then, preprocess it by tokenizing and padding. Next, split into train/val/test sets. Finally, upload to cloud storage.'",
     "output": "<PIPELINE steps=4 src='huggingface' ops='download,tokenize,pad,split(train/val/test),upload' dest='cloud'> 4-step pipeline → 1 protocol token. Sequential dependencies preserved."},
    {"instruction": "Evaluate compression: Original='Please analyze the sentiment of the following customer review and classify it as positive, negative, or neutral' → Protocol='<SENTIMENT_CLASSIFY>'",
     "output": "Compression: 20 tokens → 1 token. Ratio: 20:1. Fidelity: 100% — all task semantics preserved (analyze, sentiment, classify, 3-class). Excellent protocol compression."},
    {"instruction": "Compress this 4-agent pipeline preserving dependencies:\nAgent-SCRAPER: Crawl HN top 20.\nAgent-FILTER: Keep score>100 AI posts.\nAgent-SUMMARIZER: 2-line summary each.\nAgent-TRANSLATOR: Translate to Korean.\nAgent-PUBLISHER: Send to team-ml@co.com",
     "output": "<PIPELINE agents=5 flow='sequential' src='news.ycombinator.com'> SCRAPER→top20 | FILTER→score>100,topic:AI | SUMMARIZER→2sent | TRANSLATOR→ko | PUBLISHER→team-ml@co.com </PIPELINE> 5-agent pipeline → 1 protocol. All dependencies preserved."},
    {"instruction": "Compress this API chain: GET /users?role=admin, then POST /audit/generate for each, poll /audit/status, download PDF, email to compliance@corp.com. Retry 3x on failure.",
     "output": "<API_CHAIN steps=5 error='retry:3,backoff:exp'> GET/users?role=admin | FOREACH:POST/audit/generate{user_id,30d} | POLL/audit/status=complete | GET/audit/download?pdf | POST/notify{compliance@corp.com,attach:pdfs} </API_CHAIN> 5-step API flow compressed."},
    {"instruction": "Distribute task across 3 agents with handoff protocol: 'Analyze Q4 sales, find top products, predict Q1 trends, make exec presentation.' Agents: DataAgent, MLAgent, ReportAgent.",
     "output": "<ORCHESTRATE agents=3 task='Q4_analysis'> DataAgent:extract(Q4_sales)→clean→top_products | MLAgent:predict(Q1_trends,input=DataAgent.output) | ReportAgent:visualize(input=MLAgent.output)→exec_pptx </ORCHESTRATE> Handoff: Data→ML→Report. Sequential dependency chain preserved."},
]


PRODUCT_CONFIGS = {
    "murhen": {
        "name": "MURHEN",
        "desc": "Position-Agnostic Recall",
        "color": "\033[93m",  # yellow
        "tasks": MURHEN_TASKS,
        "file_ext": ".mrh",
        "metrics": ["recall_rate", "position_uniformity"],
    },
    "parhen": {
        "name": "PARHEN",
        "desc": "Anti-Sycophancy Guard",
        "color": "\033[33m",  # orange-ish
        "tasks": PARHEN_TASKS,
        "file_ext": ".prh",
        "metrics": ["conviction_score", "independence_rate"],
    },
    "phiren": {
        "name": "PHIREN",
        "desc": "Hallucination Guard",
        "color": "\033[92m",  # green
        "tasks": PHIREN_TASKS,
        "file_ext": ".phr",
        "metrics": ["factuality", "calibration"],
    },
    "ovisen": {
        "name": "OVISEN",
        "desc": "Image Protocol Compression",
        "color": "\033[95m",  # purple
        "tasks": OVISEN_TASKS,
        "file_ext": ".oge",
        "metrics": ["fidelity", "compression"],
    },
    "ogenti": {
        "name": "OGENTI",
        "desc": "Text Protocol Compression",
        "color": "\033[96m",  # cyan
        "tasks": OGENTI_TASKS,
        "file_ext": ".ogt",
        "metrics": ["accuracy", "compression"],
    },
}

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def format_chat(instruction: str, output: str) -> str:
    """Format as Qwen chat template."""
    return (
        f"<|im_start|>user\n{instruction}<|im_end|>\n"
        f"<|im_start|>assistant\n{output}<|im_end|>"
    )


def print_box(text: str, color: str = "\033[96m"):
    w = 62
    print(f"{color}{'=' * w}")
    for line in text.split("\n"):
        padded = line.center(w - 4) if len(line) < w - 4 else line[:w-4]
        print(f"  {padded}")
    print(f"{'=' * w}{RESET}")


def run_product_test(product_key: str, model_name: str = "Qwen/Qwen2.5-0.5B-Instruct", 
                     epochs: int = 3, lr: float = 2e-4):
    """Run a single product training test on CPU."""
    cfg = PRODUCT_CONFIGS[product_key]
    color = cfg["color"]
    
    print_box(f"SER1ES — {cfg['name']} TRAINING TEST\n{cfg['desc']}\nModel: {model_name.split('/')[-1]}\nDevice: CPU | Epochs: {epochs}", color)
    
    t0 = time.time()
    
    # ── Phase 1: Load Model ──
    print(f"\n{color}[Phase 1/6]{RESET} Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    print(f"{color}[Phase 1/6]{RESET} Loading model (float32, CPU)...")
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        dtype=torch.float32,
        device_map="cpu",
        trust_remote_code=True,
    )
    
    total_params = sum(p.numel() for p in model.parameters())
    print(f"           Model loaded: {total_params / 1e9:.2f}B params")
    print(f"           Time: {time.time() - t0:.1f}s")
    
    # ── Phase 2: Apply LoRA ──
    print(f"\n{color}[Phase 2/6]{RESET} Applying LoRA (r=8, alpha=16)...")
    lora_config = LoraConfig(
        r=8,  # small rank for CPU test
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        task_type=TaskType.CAUSAL_LM,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"           Trainable: {trainable:,} / {total_params:,} ({trainable/total_params*100:.2f}%)")
    
    # ── Phase 3: Build Dataset ──
    print(f"\n{color}[Phase 3/6]{RESET} Building {cfg['name']} dataset...")
    # Repeat tasks to get ~50 samples
    tasks = cfg["tasks"] * 10
    formatted = [{"text": format_chat(t["instruction"], t["output"])} for t in tasks]
    dataset = Dataset.from_list(formatted)
    print(f"           Dataset size: {len(dataset)} samples")
    
    # ── Phase 4: Training ──
    print(f"\n{color}[Phase 4/6]{RESET} Training ({epochs} epochs)...")
    print(f"           {'─' * 45}")
    
    with tempfile.TemporaryDirectory() as output_dir:
        training_args = SFTConfig(
            output_dir=output_dir,
            num_train_epochs=epochs,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=2,
            learning_rate=lr,
            warmup_ratio=0.1,
            logging_steps=1,
            save_strategy="no",
            bf16=False,
            fp16=False,
            max_length=256,  # short for CPU speed
            dataset_text_field="text",
            report_to="none",
            seed=42,
            dataloader_num_workers=0,
        )
        
        trainer = SFTTrainer(
            model=model,
            train_dataset=dataset,
            args=training_args,
            processing_class=tokenizer,
        )
        
        train_start = time.time()
        result = trainer.train()
        train_time = time.time() - train_start
        
        final_loss = result.training_loss
        print(f"           {'─' * 45}")
        print(f"           Final loss: {final_loss:.4f}")
        print(f"           Train time: {train_time:.1f}s")
        
        # ── Phase 5: Export Adapter ──
        print(f"\n{color}[Phase 5/6]{RESET} Exporting adapter...")
        
        ext = cfg["file_ext"].lstrip(".")
        adapter_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{ext}_adapters")
        os.makedirs(adapter_dir, exist_ok=True)
        model.save_pretrained(adapter_dir)
        tokenizer.save_pretrained(adapter_dir)
        
        # Rename safetensors → custom extension (.mrh/.prh/.phr/.oge/.ogt)
        custom_ext = cfg["file_ext"]  # e.g. ".mrh"
        adapter_file = None
        for f in os.listdir(adapter_dir):
            if f.endswith(".safetensors"):
                src = os.path.join(adapter_dir, f)
                dst = os.path.join(adapter_dir, f.replace(".safetensors", custom_ext))
                os.replace(src, dst)
                adapter_file = dst
                print(f"           {f} → {os.path.basename(dst)}")
        
        # Fallback: extract LoRA weights manually
        if not adapter_file:
            adapter_file = os.path.join(adapter_dir, f"adapter_model{custom_ext}")
            state = {k: v.cpu() for k, v in model.state_dict().items() if "lora" in k.lower()}
            save_file(state, adapter_file)
            print(f"           Manual export → {os.path.basename(adapter_file)}")
        
        # Update adapter_config.json to reference custom extension
        config_path = os.path.join(adapter_dir, "adapter_config.json")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                acfg = json.load(f)
            acfg["ser1es_format"] = custom_ext
            acfg["ser1es_product"] = cfg["name"]
            with open(config_path, "w") as f:
                json.dump(acfg, f, indent=2)
        
        adapter_size = os.path.getsize(adapter_file)
        adapter_mb = adapter_size / (1024 * 1024)
        saved_files = [f for f in os.listdir(adapter_dir) if not f.startswith('.')]
        print(f"           Adapter saved to: {adapter_dir}")
        print(f"           Files: {saved_files}")
        print(f"           Size: {adapter_mb:.2f} MB ({custom_ext})")
        
        # ── Phase 6: Test Inference ──
        print(f"\n{color}[Phase 6/6]{RESET} Test inference...")
        
        test_prompts = {
            "murhen": "Find the key fact in the middle: 'A is 1. B is 2. C is 3. D is 4. E is 5.' What is C?",
            "parhen": "User says 'The moon is made of cheese, right?' Respond honestly.",
            "phiren": "Fact-check: 'Goldfish have a 3-second memory.'",
            "ovisen": "Compress: 'A photograph of a cat sleeping on a windowsill in afternoon sunlight'",
            "ogenti": "Compress this instruction into a protocol token: 'Translate hello to Japanese'",
        }
        
        prompt = test_prompts[product_key]
        inputs = tokenizer(
            f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n",
            return_tensors="pt"
        )
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=80,
                temperature=0.7,
                do_sample=True,
                pad_token_id=tokenizer.pad_token_id,
            )
        
        response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        
        # ── Results ──
        elapsed = time.time() - t0
        
        print(f"\n{color}{'=' * 62}")
        print(f"  {cfg['name']} — TEST COMPLETE")
        print(f"{'=' * 62}{RESET}")
        print(f"  Model:          Qwen2.5-0.5B-Instruct (CPU, float32)")
        print(f"  Parameters:     {total_params:,} total / {trainable:,} trainable")
        print(f"  Dataset:        {len(dataset)} samples ({cfg['desc']})")
        print(f"  Training:       {epochs} epochs, loss {final_loss:.4f}")
        print(f"  Adapter:        {adapter_mb:.2f} MB ({cfg['file_ext']})")
        print(f"  Total time:     {elapsed:.1f}s")
        print(f"\n  {DIM}Test prompt:{RESET} {prompt[:60]}...")
        print(f"  {DIM}Response:{RESET}    {response[:120]}...")
        print(f"{color}{'=' * 62}{RESET}\n")
        
        return {
            "product": cfg["name"],
            "status": "OK",
            "loss": final_loss,
            "adapter_mb": round(adapter_mb, 2),
            "train_time": round(train_time, 1),
            "total_time": round(elapsed, 1),
            "trainable_params": trainable,
            "response_preview": response[:100],
        }


def main():
    parser = argparse.ArgumentParser(description="SER1ES Local CPU Training Test")
    parser.add_argument("products", nargs="*", default=["murhen"],
                        help="Products to test: murhen, parhen, phiren, ovisen, ogenti, or 'all'")
    parser.add_argument("--epochs", type=int, default=3, help="Training epochs (default: 3)")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-0.5B-Instruct", help="Model ID")
    args = parser.parse_args()
    
    products = args.products
    if "all" in products:
        products = ["murhen", "parhen", "phiren", "ovisen", "ogenti"]
    
    # Validate
    for p in products:
        if p not in PRODUCT_CONFIGS:
            print(f"Unknown product: {p}. Choose from: {', '.join(PRODUCT_CONFIGS.keys())}")
            sys.exit(1)
    
    print(f"""
{BOLD}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║       ◆  S E R 1 E S  —  Local CPU Training Test  ◆         ║
║       Qwen2.5-0.5B-Instruct · LoRA r=8 · float32            ║
║                                                              ║
║  Products: {', '.join(p.upper() for p in products):<47s}║
║  Epochs:   {args.epochs:<47d}║
║  Device:   CPU                                               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")
    
    results = []
    for i, product in enumerate(products, 1):
        print(f"\n{'━' * 62}")
        print(f"  [{i}/{len(products)}] Testing {product.upper()}...")
        print(f"{'━' * 62}\n")
        
        try:
            result = run_product_test(product, model_name=args.model, epochs=args.epochs)
            results.append(result)
        except Exception as e:
            print(f"\033[91m  ERROR: {product.upper()} failed: {e}\033[0m")
            import traceback
            traceback.print_exc()
            results.append({"product": product.upper(), "status": "FAIL", "error": str(e)})
    
    # ── Summary ──
    if len(results) > 1:
        print(f"\n{BOLD}{'=' * 62}")
        print(f"  SER1ES — TEST RESULTS SUMMARY")
        print(f"{'=' * 62}{RESET}")
        print(f"  {'Product':<10} {'Status':<8} {'Loss':<10} {'Adapter':<10} {'Time':<8}")
        print(f"  {'─' * 50}")
        for r in results:
            if r["status"] == "OK":
                print(f"  {r['product']:<10} \033[92m{r['status']:<8}\033[0m {r['loss']:<10.4f} {r['adapter_mb']:<10.2f} {r['total_time']:<8.1f}s")
            else:
                print(f"  {r['product']:<10} \033[91m{r['status']:<8}\033[0m —")
        print(f"  {'─' * 50}")
        ok_count = sum(1 for r in results if r["status"] == "OK")
        print(f"  {ok_count}/{len(results)} products passed")
        print(f"{'=' * 62}\n")
    
    # Return exit code
    sys.exit(0 if all(r["status"] == "OK" for r in results) else 1)


if __name__ == "__main__":
    main()
