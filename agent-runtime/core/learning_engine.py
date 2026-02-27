"""
Learning Engine - Adaptive Learning and Experience Accumulation

Provides machine learning capabilities for agents to learn from experience,
adapt strategies, and improve performance over time.
"""

import json
import time
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, Counter
from loguru import logger
import os

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.cluster import KMeans
    HAS_SKLEARN = True
except ImportError:
    logger.warning("sklearn not available - some learning features will be disabled")
    HAS_SKLEARN = False
    TfidfVectorizer = None
    cosine_similarity = None
    KMeans = None


@dataclass
class Experience:
    """Single experience record for learning"""
    task_type: str
    command: str
    context: Dict
    action: str
    result: Dict
    success: bool
    confidence: float
    timestamp: float
    metadata: Dict = field(default_factory=dict)


@dataclass
class LearningPattern:
    """Learned pattern from experience"""
    pattern_id: str
    task_type: str
    pattern_type: str  # success, failure, optimization
    trigger_conditions: List[str]
    recommended_action: str
    confidence: float
    success_rate: float
    usage_count: int = 0
    last_updated: float = field(default_factory=time.time)


@dataclass
class AdaptationRule:
    """Adaptation rule for dynamic behavior"""
    rule_id: str
    condition: str
    action: str
    priority: int
    success_count: int = 0
    failure_count: int = 0
    last_applied: float = 0


class LearningEngine:
    """
    Advanced learning engine that enables agents to learn from experience
    and adapt their behavior dynamically.
    
    v2.0: Now uses TF-IDF + cosine_similarity for text matching,
    KMeans for experience clustering, and maintains a vectorizer index.
    """
    
    def __init__(self, storage_path: str = "learning_data"):
        self.storage_path = storage_path
        self.experiences: List[Experience] = []
        self.patterns: Dict[str, LearningPattern] = {}
        self.adaptation_rules: Dict[str, AdaptationRule] = {}
        self.performance_metrics = defaultdict(list)
        self.context_embeddings = {}
        
        # v2.0: TF-IDF vectorizer for real text similarity
        self._tfidf_vectorizer: Optional[TfidfVectorizer] = None
        self._tfidf_matrix = None
        self._tfidf_corpus: List[str] = []
        self._tfidf_dirty = True  # Rebuild index when True
        
        # v2.0: Experience clusters from KMeans
        self._clusters: Dict[int, List[int]] = {}  # cluster_id -> [experience indices]
        self._cluster_labels: Optional[np.ndarray] = None
        self._cluster_dirty = True
        
        # Load existing learning data
        self._load_learning_data()
        
        # Initialize learning parameters
        self.learning_rate = 0.1
        self.pattern_threshold = 3  # Minimum occurrences to form pattern
        self.adaptation_threshold = 0.7  # Confidence threshold for adaptations
        
    def _load_learning_data(self):
        """Load existing learning data from storage"""
        try:
            os.makedirs(self.storage_path, exist_ok=True)
            
            # Load experiences (JSON format — safe deserialization)
            exp_file = os.path.join(self.storage_path, "experiences.json")
            if os.path.exists(exp_file):
                with open(exp_file, 'r') as f:
                    exp_data = json.load(f)
                    self.experiences = [
                        Experience(**e) for e in exp_data
                    ]
            else:
                # Migrate from legacy pickle format if it exists
                legacy_pkl = os.path.join(self.storage_path, "experiences.pkl")
                if os.path.exists(legacy_pkl):
                    logger.warning(
                        f"Found legacy pickle file {legacy_pkl}. "
                        "Pickle deserialization is disabled for security. "
                        "Delete the .pkl file and let the engine re-learn, "
                        "or manually convert it to JSON."
                    )
            
            # Load patterns
            pat_file = os.path.join(self.storage_path, "patterns.json")
            if os.path.exists(pat_file):
                with open(pat_file, 'r') as f:
                    patterns_data = json.load(f)
                    self.patterns = {
                        pid: LearningPattern(**data) for pid, data in patterns_data.items()
                    }
            
            # Load adaptation rules
            rules_file = os.path.join(self.storage_path, "adaptation_rules.json")
            if os.path.exists(rules_file):
                with open(rules_file, 'r') as f:
                    rules_data = json.load(f)
                    self.adaptation_rules = {
                        rid: AdaptationRule(**data) for rid, data in rules_data.items()
                    }
                    
            logger.info(f"Loaded {len(self.experiences)} experiences, {len(self.patterns)} patterns, {len(self.adaptation_rules)} rules")
            
        except Exception as e:
            logger.warning(f"Failed to load learning data: {e}")
    
    def _save_learning_data(self):
        """Save learning data to storage"""
        try:
            # Save experiences (JSON format — safe serialization)
            exp_file = os.path.join(self.storage_path, "experiences.json")
            exp_data = [
                {
                    "task_type": e.task_type,
                    "command": e.command,
                    "context": e.context,
                    "action": e.action,
                    "result": e.result,
                    "success": e.success,
                    "confidence": e.confidence,
                    "timestamp": e.timestamp,
                    "metadata": e.metadata,
                }
                for e in self.experiences
            ]
            with open(exp_file, 'w') as f:
                json.dump(exp_data, f, indent=2)
            
            # Save patterns
            pat_file = os.path.join(self.storage_path, "patterns.json")
            patterns_data = {
                pid: {
                    "pattern_id": p.pattern_id,
                    "task_type": p.task_type,
                    "pattern_type": p.pattern_type,
                    "trigger_conditions": p.trigger_conditions,
                    "recommended_action": p.recommended_action,
                    "confidence": p.confidence,
                    "success_rate": p.success_rate,
                    "usage_count": p.usage_count,
                    "last_updated": p.last_updated
                } for pid, p in self.patterns.items()
            }
            with open(pat_file, 'w') as f:
                json.dump(patterns_data, f, indent=2)
            
            # Save adaptation rules
            rules_file = os.path.join(self.storage_path, "adaptation_rules.json")
            rules_data = {
                rid: {
                    "rule_id": r.rule_id,
                    "condition": r.condition,
                    "action": r.action,
                    "priority": r.priority,
                    "success_count": r.success_count,
                    "failure_count": r.failure_count,
                    "last_applied": r.last_applied
                } for rid, r in self.adaptation_rules.items()
            }
            with open(rules_file, 'w') as f:
                json.dump(rules_data, f, indent=2)
                
            logger.info("Learning data saved successfully")
            
        except Exception as e:
            logger.error(f"Failed to save learning data: {e}")
    
    def add_experience(self, task_type: str, command: str, context: Dict, 
                      action: str, result: Dict, confidence: float = 0.5):
        """Add new experience for learning"""
        experience = Experience(
            task_type=task_type,
            command=command,
            context=context,
            action=action,
            result=result,
            success=result.get("success", False),
            confidence=confidence,
            timestamp=time.time(),
            metadata={
                "duration": result.get("duration", 0),
                "error": result.get("error", ""),
                "steps_taken": result.get("steps_taken", [])
            }
        )
        
        self.experiences.append(experience)
        self._tfidf_dirty = True
        self._cluster_dirty = True
        
        # Update performance metrics
        self.performance_metrics[task_type].append({
            "success": experience.success,
            "confidence": confidence,
            "timestamp": experience.timestamp
        })
        
        # Trigger learning processes
        self._update_patterns(experience)
        self._update_adaptation_rules(experience)
        
        # Periodic cleanup and saving
        if len(self.experiences) % 10 == 0:
            self._cleanup_old_experiences()
            self._save_learning_data()
    
    def _update_patterns(self, experience: Experience):
        """Update learning patterns based on new experience"""
        # Find similar experiences
        similar_experiences = self._find_similar_experiences(experience)
        
        # Check if we can form/update a pattern
        if len(similar_experiences) >= self.pattern_threshold - 1:
            pattern_id = self._generate_pattern_id(experience, similar_experiences)
            
            if pattern_id in self.patterns:
                # Update existing pattern
                pattern = self.patterns[pattern_id]
                pattern.usage_count += 1
                
                # Update success rate
                all_experiences = similar_experiences + [experience]
                successes = sum(1 for exp in all_experiences if exp.success)
                pattern.success_rate = successes / len(all_experiences)
                
                # Update confidence
                pattern.confidence = min(1.0, pattern.confidence + self.learning_rate * (0.1 - abs(0.5 - pattern.success_rate)))
                pattern.last_updated = time.time()
                
            else:
                # Create new pattern
                pattern = self._create_pattern(experience, similar_experiences)
                self.patterns[pattern_id] = pattern
    
    def _find_similar_experiences(self, experience: Experience) -> List[Experience]:
        """Find experiences similar to the given one (v2.0: uses TF-IDF when available)"""
        similar = []
        
        # Try TF-IDF fast path first
        query = f"{experience.task_type} {experience.command} {experience.action}"
        tfidf_results = self._find_similar_by_tfidf(query, top_k=20)
        if tfidf_results:
            for idx, score in tfidf_results:
                if idx < len(self.experiences) and score > 0.3:
                    exp = self.experiences[idx]
                    if exp.task_type == experience.task_type and exp is not experience:
                        similar.append(exp)
            if similar:
                return similar[:10]
        
        # Fallback to sequential scan
        for exp in self.experiences[-100:]:
            if exp.task_type != experience.task_type:
                continue
                
            similarity = self._calculate_similarity(experience, exp)
            if similarity > 0.7:
                similar.append(exp)
        
        return similar
    
    def _calculate_similarity(self, exp1: Experience, exp2: Experience) -> float:
        """Calculate similarity between two experiences"""
        similarity = 0.0
        
        # Task type similarity (exact match)
        if exp1.task_type == exp2.task_type:
            similarity += 0.3
        
        # Command similarity
        cmd_similarity = self._text_similarity(exp1.command, exp2.command)
        similarity += cmd_similarity * 0.3
        
        # Action similarity
        action_similarity = self._text_similarity(exp1.action, exp2.action)
        similarity += action_similarity * 0.2
        
        # Context similarity
        context_similarity = self._context_similarity(exp1.context, exp2.context)
        similarity += context_similarity * 0.2
        
        return min(1.0, similarity)
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using TF-IDF + cosine similarity (v2.0)"""
        if not text1.strip() and not text2.strip():
            return 1.0
        if not text1.strip() or not text2.strip():
            return 0.0
        if not HAS_SKLEARN:
            # Fallback to Jaccard when sklearn is unavailable
            words1 = set(self._extract_keywords(text1.lower()))
            words2 = set(self._extract_keywords(text2.lower()))
            if not words1 or not words2:
                return 0.0
            return len(words1 & words2) / len(words1 | words2)
        try:
            vectorizer = TfidfVectorizer(
                analyzer='word', stop_words='english',
                max_features=500, ngram_range=(1, 2)
            )
            tfidf_matrix = vectorizer.fit_transform([text1.lower(), text2.lower()])
            sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            return float(sim)
        except Exception:
            # Fallback to Jaccard if TF-IDF fails (e.g., too short text)
            words1 = set(self._extract_keywords(text1.lower()))
            words2 = set(self._extract_keywords(text2.lower()))
            if not words1 or not words2:
                return 0.0
            return len(words1 & words2) / len(words1 | words2)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        # Simple keyword extraction - could be enhanced with NLP
        import re
        words = re.findall(r'\b\w+\b', text)
        # Filter out common words and keep meaningful ones
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'must'}
        return [word for word in words if len(word) > 2 and word not in stop_words]
    
    def _context_similarity(self, ctx1: Dict, ctx2: Dict) -> float:
        """Calculate context similarity"""
        if not ctx1 and not ctx2:
            return 1.0
        if not ctx1 or not ctx2:
            return 0.0
        
        # Compare key context fields
        fields_to_compare = ['task_type', 'current_state', 'goals', 'constraints']
        similarity = 0.0
        
        for field in fields_to_compare:
            val1 = str(ctx1.get(field, ''))
            val2 = str(ctx2.get(field, ''))
            
            if val1 == val2:
                similarity += 0.25
            else:
                similarity += self._text_similarity(val1, val2) * 0.25
        
        return min(1.0, similarity)
    
    def _generate_pattern_id(self, experience: Experience, similar_experiences: List[Experience]) -> str:
        """Generate unique pattern ID"""
        all_experiences = similar_experiences + [experience]
        
        # Use most common keywords to generate ID
        all_commands = [exp.command for exp in all_experiences]
        all_keywords = []
        
        for cmd in all_commands:
            all_keywords.extend(self._extract_keywords(cmd.lower()))
        
        keyword_counts = Counter(all_keywords)
        top_keywords = [kw for kw, count in keyword_counts.most_common(3)]
        
        pattern_id = f"{experience.task_type}_{'_'.join(top_keywords)}"
        return pattern_id.replace(' ', '_')
    
    def _create_pattern(self, experience: Experience, similar_experiences: List[Experience]) -> LearningPattern:
        """Create new learning pattern"""
        all_experiences = similar_experiences + [experience]
        
        # Determine pattern type
        success_count = sum(1 for exp in all_experiences if exp.success)
        success_rate = success_count / len(all_experiences)
        
        if success_rate > 0.8:
            pattern_type = "success"
        elif success_rate < 0.3:
            pattern_type = "failure"
        else:
            pattern_type = "optimization"
        
        # Extract trigger conditions
        trigger_conditions = self._extract_trigger_conditions(all_experiences)
        
        # Determine recommended action
        recommended_action = self._determine_recommended_action(all_experiences, pattern_type)
        
        pattern_id = self._generate_pattern_id(experience, similar_experiences)
        
        return LearningPattern(
            pattern_id=pattern_id,
            task_type=experience.task_type,
            pattern_type=pattern_type,
            trigger_conditions=trigger_conditions,
            recommended_action=recommended_action,
            confidence=0.5,  # Start with moderate confidence
            success_rate=success_rate,
            usage_count=len(all_experiences),
            last_updated=time.time()
        )
    
    def _extract_trigger_conditions(self, experiences: List[Experience]) -> List[str]:
        """Extract common trigger conditions from experiences"""
        conditions = []
        
        # Analyze common context elements
        context_elements = defaultdict(list)
        for exp in experiences:
            for key, value in exp.context.items():
                if value:
                    context_elements[key].append(str(value))
        
        # Find common values for each context element
        for key, values in context_elements.items():
            value_counts = Counter(values)
            common_value, count = value_counts.most_common(1)[0]
            
            if count >= len(experiences) // 2:  # Appears in at least half the experiences
                conditions.append(f"{key}={common_value}")
        
        return conditions[:5]  # Limit to 5 conditions
    
    def _determine_recommended_action(self, experiences: List[Experience], pattern_type: str) -> str:
        """Determine recommended action based on pattern type"""
        if pattern_type == "success":
            # Recommend the most successful action
            successful_exps = [exp for exp in experiences if exp.success]
            if successful_exps:
                actions = [exp.action for exp in successful_exps]
                action_counts = Counter(actions)
                return action_counts.most_common(1)[0][0]
        
        elif pattern_type == "failure":
            # Recommend avoiding the most failed action
            failed_exps = [exp for exp in experiences if not exp.success]
            if failed_exps:
                actions = [exp.action for exp in failed_exps]
                action_counts = Counter(actions)
                most_failed_action = action_counts.most_common(1)[0][0]
                return f"AVOID: {most_failed_action}"
        
        else:  # optimization
            # Recommend action with best performance
            best_exp = max(experiences, key=lambda exp: exp.confidence * (1 if exp.success else 0.5))
            return f"OPTIMIZE: {best_exp.action}"
        
        return "No specific recommendation"
    
    def _update_adaptation_rules(self, experience: Experience):
        """Update adaptation rules based on experience"""
        # Check if any existing rules apply
        applicable_rules = self._find_applicable_rules(experience)
        
        for rule in applicable_rules:
            if experience.success:
                rule.success_count += 1
            else:
                rule.failure_count += 1
            rule.last_applied = experience.timestamp
        
        # Create new adaptation rule if we detect a consistent pattern
        self._create_adaptation_rule_if_needed(experience)
    
    def _find_applicable_rules(self, experience: Experience) -> List[AdaptationRule]:
        """Find adaptation rules that apply to the experience"""
        applicable = []
        
        for rule in self.adaptation_rules.values():
            if self._rule_matches_experience(rule, experience):
                applicable.append(rule)
        
        return applicable
    
    def _rule_matches_experience(self, rule: AdaptationRule, experience: Experience) -> bool:
        """Check if adaptation rule matches the experience"""
        # Simple matching - could be enhanced with more sophisticated logic
        condition_lower = rule.condition.lower()
        
        # Check task type
        if experience.task_type.lower() in condition_lower:
            return True
        
        # Check command keywords
        command_keywords = self._extract_keywords(experience.command.lower())
        for keyword in command_keywords:
            if keyword in condition_lower:
                return True
        
        # Check context
        for key, value in experience.context.items():
            if str(value).lower() in condition_lower:
                return True
        
        return False
    
    def _create_adaptation_rule_if_needed(self, experience: Experience):
        """Create new adaptation rule if pattern detected"""
        # Look for consistent failure patterns
        recent_experiences = [exp for exp in self.experiences[-20:] if exp.task_type == experience.task_type]
        
        if len(recent_experiences) < 5:
            return
        
        # Check for consistent failure with similar conditions
        failure_patterns = defaultdict(int)
        for exp in recent_experiences:
            if not exp.success:
                condition_key = self._generate_condition_key(exp)
                failure_patterns[condition_key] += 1
        
        # Create rule if we have 3+ failures with similar conditions
        for condition_key, count in failure_patterns.items():
            if count >= 3:
                rule_id = f"adapt_{condition_key.replace(' ', '_')}"
                
                if rule_id not in self.adaptation_rules:
                    # Suggest alternative action based on successful experiences
                    successful_exps = [exp for exp in recent_experiences if exp.success and self._generate_condition_key(exp) == condition_key]
                    
                    if successful_exps:
                        recommended_action = successful_exps[0].action
                    else:
                        recommended_action = "Try alternative approach"
                    
                    rule = AdaptationRule(
                        rule_id=rule_id,
                        condition=condition_key,
                        action=recommended_action,
                        priority=count,  # Higher priority for more frequent failures
                        success_count=0,
                        failure_count=count,
                        last_applied=experience.timestamp
                    )
                    
                    self.adaptation_rules[rule_id] = rule
    
    def _generate_condition_key(self, experience: Experience) -> str:
        """Generate condition key for experience"""
        conditions = []
        
        # Add task type
        conditions.append(f"task:{experience.task_type}")
        
        # Add main command keywords
        keywords = self._extract_keywords(experience.command.lower())[:3]
        if keywords:
            conditions.append(f"cmd:{','.join(keywords)}")
        
        # Add key context
        if experience.context.get('current_state'):
            conditions.append(f"state:{experience.context['current_state']}")
        
        return ' '.join(conditions)
    
    def _rebuild_tfidf_index(self):
        """Rebuild TF-IDF index from all experiences (v2.0)"""
        if not HAS_SKLEARN:
            return
        if not self._tfidf_dirty or len(self.experiences) < 2:
            return
        try:
            self._tfidf_corpus = [
                f"{exp.task_type} {exp.command} {exp.action} {' '.join(str(v) for v in exp.context.values())}"
                for exp in self.experiences
            ]
            self._tfidf_vectorizer = TfidfVectorizer(
                analyzer='word', stop_words='english',
                max_features=2000, ngram_range=(1, 2),
                min_df=1, max_df=0.95
            )
            self._tfidf_matrix = self._tfidf_vectorizer.fit_transform(self._tfidf_corpus)
            self._tfidf_dirty = False
            logger.debug(f"TF-IDF index rebuilt: {self._tfidf_matrix.shape}")
        except Exception as e:
            logger.warning(f"TF-IDF index rebuild failed: {e}")
            self._tfidf_vectorizer = None
            self._tfidf_matrix = None

    def _find_similar_by_tfidf(self, text: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """Find most similar experiences using TF-IDF index (v2.0)"""
        self._rebuild_tfidf_index()
        if self._tfidf_vectorizer is None or self._tfidf_matrix is None:
            return []
        try:
            query_vec = self._tfidf_vectorizer.transform([text.lower()])
            similarities = cosine_similarity(query_vec, self._tfidf_matrix)[0]
            top_indices = np.argsort(similarities)[::-1][:top_k]
            return [(int(idx), float(similarities[idx])) for idx in top_indices if similarities[idx] > 0.1]
        except Exception:
            return []

    def cluster_experiences(self, n_clusters: int = 0) -> Dict[int, List[int]]:
        """Cluster experiences using KMeans (v2.0)"""
        if not HAS_SKLEARN:
            return {0: list(range(len(self.experiences)))}
        if len(self.experiences) < 5:
            return {0: list(range(len(self.experiences)))}
        self._rebuild_tfidf_index()
        if self._tfidf_matrix is None:
            return {0: list(range(len(self.experiences)))}
        try:
            if n_clusters <= 0:
                n_clusters = max(2, min(10, len(self.experiences) // 10))
            n_clusters = min(n_clusters, len(self.experiences))
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=300)
            self._cluster_labels = kmeans.fit_predict(self._tfidf_matrix.toarray())
            self._clusters = defaultdict(list)
            for idx, label in enumerate(self._cluster_labels):
                self._clusters[int(label)].append(idx)
            self._cluster_dirty = False
            logger.info(f"Clustered {len(self.experiences)} experiences into {n_clusters} clusters")
            return dict(self._clusters)
        except Exception as e:
            logger.warning(f"Clustering failed: {e}")
            return {0: list(range(len(self.experiences)))}

    def get_cluster_summary(self) -> List[Dict]:
        """Get summary of each experience cluster (v2.0)"""
        if self._cluster_dirty or not self._clusters:
            self.cluster_experiences()
        summaries = []
        for cluster_id, indices in self._clusters.items():
            exps = [self.experiences[i] for i in indices if i < len(self.experiences)]
            if not exps:
                continue
            task_types = Counter(e.task_type for e in exps)
            success_rate = sum(1 for e in exps if e.success) / len(exps)
            avg_confidence = sum(e.confidence for e in exps) / len(exps)
            summaries.append({
                "cluster_id": cluster_id,
                "size": len(exps),
                "dominant_task_type": task_types.most_common(1)[0][0],
                "task_type_distribution": dict(task_types),
                "success_rate": round(success_rate, 3),
                "avg_confidence": round(avg_confidence, 3),
                "sample_commands": [e.command[:80] for e in exps[:3]],
            })
        return summaries

    def find_similar_experiences_fast(self, command: str, task_type: str = "", top_k: int = 5) -> List[Dict]:
        """Fast similarity search using TF-IDF index (v2.0)"""
        query = f"{task_type} {command}"
        results = self._find_similar_by_tfidf(query, top_k=top_k)
        output = []
        for idx, score in results:
            if idx < len(self.experiences):
                exp = self.experiences[idx]
                output.append({
                    "similarity": round(score, 3),
                    "task_type": exp.task_type,
                    "command": exp.command,
                    "action": exp.action,
                    "success": exp.success,
                    "confidence": exp.confidence,
                })
        return output

    def _cleanup_old_experiences(self):
        """Clean up old experiences to prevent memory bloat"""
        # Keep only the most recent 1000 experiences
        if len(self.experiences) > 1000:
            self.experiences = self.experiences[-1000:]
            self._tfidf_dirty = True
            self._cluster_dirty = True
        
        # Clean up old patterns with low confidence
        current_time = time.time()
        patterns_to_remove = []
        
        for pattern_id, pattern in self.patterns.items():
            # Remove patterns older than 30 days with low confidence
            if (current_time - pattern.last_updated > 30 * 24 * 3600 and 
                pattern.confidence < 0.3 and pattern.usage_count < 5):
                patterns_to_remove.append(pattern_id)
        
        for pattern_id in patterns_to_remove:
            del self.patterns[pattern_id]
    
    def get_adaptations(self, task_type: str, context: Dict) -> List[Dict]:
        """Get relevant adaptations for current situation"""
        adaptations = []
        
        # Get applicable patterns
        applicable_patterns = self._find_applicable_patterns(task_type, context)
        for pattern in applicable_patterns:
            if pattern.confidence >= self.adaptation_threshold:
                adaptations.append({
                    "type": "pattern",
                    "source": pattern.pattern_id,
                    "recommendation": pattern.recommended_action,
                    "confidence": pattern.confidence,
                    "success_rate": pattern.success_rate,
                    "usage_count": pattern.usage_count
                })
        
        # Get applicable adaptation rules
        applicable_rules = self._find_applicable_rules_for_context(task_type, context)
        for rule in applicable_rules:
            success_rate = rule.success_count / (rule.success_count + rule.failure_count) if (rule.success_count + rule.failure_count) > 0 else 0
            
            if success_rate >= self.adaptation_threshold:
                adaptations.append({
                    "type": "rule",
                    "source": rule.rule_id,
                    "recommendation": rule.action,
                    "confidence": success_rate,
                    "success_rate": success_rate,
                    "usage_count": rule.success_count + rule.failure_count,
                    "priority": rule.priority
                })
        
        # Sort by confidence and priority
        adaptations.sort(key=lambda x: (x["confidence"], x.get("priority", 0)), reverse=True)
        
        return adaptations[:5]  # Return top 5 adaptations
    
    def _find_applicable_patterns(self, task_type: str, context: Dict) -> List[LearningPattern]:
        """Find patterns applicable to current situation"""
        applicable = []
        
        for pattern in self.patterns.values():
            if pattern.task_type != task_type:
                continue
            
            # Check if trigger conditions match
            if self._pattern_matches_context(pattern, context):
                applicable.append(pattern)
        
        return applicable
    
    def _pattern_matches_context(self, pattern: LearningPattern, context: Dict) -> bool:
        """Check if pattern matches current context"""
        for condition in pattern.trigger_conditions:
            if '=' in condition:
                key, value = condition.split('=', 1)
                if str(context.get(key, '')).lower() != value.lower():
                    return False
            elif condition.lower() not in str(context).lower():
                return False
        
        return True
    
    def _find_applicable_rules_for_context(self, task_type: str, context: Dict) -> List[AdaptationRule]:
        """Find adaptation rules applicable to current context"""
        applicable = []
        
        # Create a temporary experience to check rule matching
        temp_experience = Experience(
            task_type=task_type,
            command="",
            context=context,
            action="",
            result={},
            success=False,
            confidence=0.0,
            timestamp=time.time()
        )
        
        for rule in self.adaptation_rules.values():
            if self._rule_matches_experience(rule, temp_experience):
                applicable.append(rule)
        
        return applicable
    
    def get_performance_metrics(self, task_type: Optional[str] = None) -> Dict:
        """Get performance metrics for learning evaluation"""
        metrics = {}
        
        if task_type:
            task_metrics = self.performance_metrics.get(task_type, [])
            if task_metrics:
                metrics[task_type] = self._calculate_task_metrics(task_metrics)
        else:
            for t_type, task_metrics in self.performance_metrics.items():
                if task_metrics:
                    metrics[t_type] = self._calculate_task_metrics(task_metrics)
        
        # Overall metrics
        all_metrics = []
        for task_metrics in self.performance_metrics.values():
            all_metrics.extend(task_metrics)
        
        if all_metrics:
            metrics["overall"] = self._calculate_task_metrics(all_metrics)
        
        return metrics
    
    def _calculate_task_metrics(self, task_metrics: List[Dict]) -> Dict:
        """Calculate metrics for a specific task"""
        if not task_metrics:
            return {}
        
        recent_metrics = task_metrics[-50:]  # Last 50 experiences
        
        success_rate = sum(1 for m in recent_metrics if m["success"]) / len(recent_metrics)
        avg_confidence = sum(m["confidence"] for m in recent_metrics) / len(recent_metrics)
        
        # Calculate improvement over time
        if len(recent_metrics) >= 10:
            early = recent_metrics[:len(recent_metrics)//2]
            late = recent_metrics[len(recent_metrics)//2:]
            
            early_success = sum(1 for m in early if m["success"]) / len(early)
            late_success = sum(1 for m in late if m["success"]) / len(late)
            
            improvement = late_success - early_success
        else:
            improvement = 0.0
        
        return {
            "total_experiences": len(task_metrics),
            "recent_experiences": len(recent_metrics),
            "success_rate": success_rate,
            "average_confidence": avg_confidence,
            "improvement_trend": improvement,
            "last_updated": max(m["timestamp"] for m in recent_metrics)
        }
    
    def get_learning_summary(self) -> Dict:
        """Get comprehensive learning summary"""
        return {
            "total_experiences": len(self.experiences),
            "total_patterns": len(self.patterns),
            "total_adaptation_rules": len(self.adaptation_rules),
            "performance_metrics": self.get_performance_metrics(),
            "pattern_types": self._get_pattern_type_summary(),
            "learning_rate": self.learning_rate,
            "last_save_time": time.time()
        }
    
    def _get_pattern_type_summary(self) -> Dict:
        """Get summary of pattern types"""
        type_counts = defaultdict(int)
        for pattern in self.patterns.values():
            type_counts[pattern.pattern_type] += 1
        
        return dict(type_counts)
    
    def set_learning_rate(self, rate: float):
        """Set learning rate for pattern updates"""
        self.learning_rate = max(0.01, min(1.0, rate))
    
    def reset_learning_data(self):
        """Reset all learning data"""
        self.experiences.clear()
        self.patterns.clear()
        self.adaptation_rules.clear()
        self.performance_metrics.clear()
        
        # Remove storage files
        try:
            import shutil
            if os.path.exists(self.storage_path):
                shutil.rmtree(self.storage_path)
            os.makedirs(self.storage_path, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to reset learning data: {e}")
    
    def export_learning_data(self, export_path: str):
        """Export learning data to file"""
        export_data = {
            "experiences": [
                {
                    "task_type": exp.task_type,
                    "command": exp.command,
                    "context": exp.context,
                    "action": exp.action,
                    "result": exp.result,
                    "success": exp.success,
                    "confidence": exp.confidence,
                    "timestamp": exp.timestamp,
                    "metadata": exp.metadata
                } for exp in self.experiences
            ],
            "patterns": {
                pid: {
                    "pattern_id": p.pattern_id,
                    "task_type": p.task_type,
                    "pattern_type": p.pattern_type,
                    "trigger_conditions": p.trigger_conditions,
                    "recommended_action": p.recommended_action,
                    "confidence": p.confidence,
                    "success_rate": p.success_rate,
                    "usage_count": p.usage_count,
                    "last_updated": p.last_updated
                } for pid, p in self.patterns.items()
            },
            "adaptation_rules": {
                rid: {
                    "rule_id": r.rule_id,
                    "condition": r.condition,
                    "action": r.action,
                    "priority": r.priority,
                    "success_count": r.success_count,
                    "failure_count": r.failure_count,
                    "last_applied": r.last_applied
                } for rid, r in self.adaptation_rules.items()
            },
            "performance_metrics": dict(self.performance_metrics),
            "learning_summary": self.get_learning_summary()
        }
        
        with open(export_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        logger.info(f"Learning data exported to {export_path}")
