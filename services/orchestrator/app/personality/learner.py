from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..memory.sqlite_store import SQLiteMemory


class PersonalityLearner:
    """
    Advanced personality learning system that adapts Richard's personality 
    based on conversation patterns, user preferences, and communication style.
    """
    
    def __init__(self, memory: Optional[SQLiteMemory] = None):
        self.memory = memory or SQLiteMemory()
        self.personality_traits = {
            "communication_style": {
                "directness": 0.7,        # How direct vs diplomatic
                "formality": 0.3,         # How formal vs casual  
                "enthusiasm": 0.6,        # How enthusiastic vs calm
                "humor": 0.5,             # How much humor to use
                "swearing": 0.1,          # How much profanity is acceptable
            },
            "preferences": {
                "brevity": 0.8,           # Prefers short vs long responses
                "technical_depth": 0.6,   # How technical to get
                "proactiveness": 0.7,     # How proactive vs reactive
                "emoji_usage": 0.2,       # How many emojis to use
            },
            "learned_facts": {
                "user_name": "Vinay",
                "likes": [],              # Things user likes
                "dislikes": [],           # Things user dislikes  
                "frequent_contacts": [],  # People user messages often
                "preferred_groups": [],   # Groups user messages
                "communication_patterns": [], # How user typically communicates
            }
        }
        self.conversation_history = []
    
    async def analyze_user_message(self, user_text: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Analyze a user message to extract personality insights."""
        context = context or {}
        insights = {
            "communication_style": {},
            "preferences": {},
            "learned_facts": {},
            "patterns": []
        }
        
        text_lower = user_text.lower()
        
        # Analyze communication style
        if any(word in text_lower for word in ["fuck", "shit", "damn", "ass"]):
            insights["communication_style"]["swearing"] = min(1.0, self.personality_traits["communication_style"]["swearing"] + 0.1)
            
        if len(user_text) < 50:
            insights["preferences"]["brevity"] = min(1.0, self.personality_traits["preferences"]["brevity"] + 0.05)
        elif len(user_text) > 200:
            insights["preferences"]["brevity"] = max(0.0, self.personality_traits["preferences"]["brevity"] - 0.05)
            
        # Detect directness
        direct_indicators = ["just", "quickly", "fast", "now", "immediately", "asap"]
        if any(word in text_lower for word in direct_indicators):
            insights["communication_style"]["directness"] = min(1.0, self.personality_traits["communication_style"]["directness"] + 0.05)
            
        # Detect casual vs formal
        casual_indicators = ["hey", "yo", "sup", "lol", "lmao", "btw", "nvm"]
        formal_indicators = ["please", "thank you", "could you", "would you", "appreciate"]
        
        if any(word in text_lower for word in casual_indicators):
            insights["communication_style"]["formality"] = max(0.0, self.personality_traits["communication_style"]["formality"] - 0.05)
        elif any(phrase in text_lower for phrase in formal_indicators):
            insights["communication_style"]["formality"] = min(1.0, self.personality_traits["communication_style"]["formality"] + 0.05)
            
        # Learn about contacts and groups
        if context.get("action") == "send_imessage":
            if context.get("group"):
                group = context["group"]
                if group not in self.personality_traits["learned_facts"]["preferred_groups"]:
                    self.personality_traits["learned_facts"]["preferred_groups"].append(group)
                    insights["learned_facts"]["new_group"] = group
                    
            if context.get("contact"):
                contact = context["contact"] 
                if contact not in self.personality_traits["learned_facts"]["frequent_contacts"]:
                    self.personality_traits["learned_facts"]["frequent_contacts"].append(contact)
                    insights["learned_facts"]["new_contact"] = contact
        
        return insights
    
    async def update_personality(self, insights: Dict[str, Any]) -> None:
        """Update personality traits based on insights."""
        # Update communication style
        for trait, value in insights.get("communication_style", {}).items():
            if trait in self.personality_traits["communication_style"]:
                self.personality_traits["communication_style"][trait] = value
                
        # Update preferences  
        for trait, value in insights.get("preferences", {}).items():
            if trait in self.personality_traits["preferences"]:
                self.personality_traits["preferences"][trait] = value
                
        # Update learned facts
        for fact, value in insights.get("learned_facts", {}).items():
            if fact in self.personality_traits["learned_facts"]:
                if isinstance(self.personality_traits["learned_facts"][fact], list):
                    if value not in self.personality_traits["learned_facts"][fact]:
                        self.personality_traits["learned_facts"][fact].append(value)
                else:
                    self.personality_traits["learned_facts"][fact] = value
        
        # Save to memory
        await self._save_personality()
    
    async def _save_personality(self) -> None:
        """Save current personality state to memory."""
        try:
            personality_json = json.dumps(self.personality_traits, indent=2)
            await self.memory.insert(
                kind="personality_state",
                text=f"Personality update: {datetime.now(timezone.utc).isoformat()}",
                meta={
                    "personality": self.personality_traits,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        except Exception as e:
            print(f"[PersonalityLearner] Failed to save personality: {e}")
    
    async def load_personality(self) -> None:
        """Load saved personality state from memory."""
        try:
            # Get the most recent personality state
            results = await self.memory.search("personality_state", top_k=1)
            if results:
                latest_state = results[0][0]  # (item, score)
                if hasattr(latest_state, 'meta') and latest_state.meta.get("personality"):
                    saved_personality = latest_state.meta["personality"]
                    # Merge saved personality with defaults
                    self._merge_personality(saved_personality)
                    print(f"[PersonalityLearner] Loaded personality state")
        except Exception as e:
            print(f"[PersonalityLearner] Failed to load personality: {e}")
    
    def _merge_personality(self, saved: Dict[str, Any]) -> None:
        """Merge saved personality with current defaults."""
        for category, traits in saved.items():
            if category in self.personality_traits:
                if isinstance(traits, dict):
                    for trait, value in traits.items():
                        if trait in self.personality_traits[category]:
                            self.personality_traits[category][trait] = value
    
    def generate_system_prompt(self, base_prompt: str) -> str:
        """Generate a personalized system prompt based on learned personality."""
        traits = self.personality_traits
        
        # Build personality descriptor
        personality_parts = []
        
        # Communication style
        comm = traits["communication_style"]
        if comm["directness"] > 0.7:
            personality_parts.append("Be direct and to-the-point")
        elif comm["directness"] < 0.4:
            personality_parts.append("Be diplomatic and considerate")
            
        if comm["formality"] > 0.6:
            personality_parts.append("Use polite, professional language")
        elif comm["formality"] < 0.4:
            personality_parts.append("Use casual, friendly language")
            
        if comm["swearing"] > 0.3:
            personality_parts.append("It's okay to use mild profanity when appropriate")
            
        if comm["humor"] > 0.6:
            personality_parts.append("Use humor and wit in responses")
            
        # Preferences
        prefs = traits["preferences"]
        if prefs["brevity"] > 0.7:
            personality_parts.append("Keep responses concise and brief")
        elif prefs["brevity"] < 0.4:
            personality_parts.append("Provide detailed, comprehensive responses")
            
        if prefs["proactiveness"] > 0.7:
            personality_parts.append("Be proactive and anticipate needs")
            
        # Learned facts
        facts = traits["learned_facts"]
        if facts.get("user_name"):
            personality_parts.append(f"Address the user by name as {facts['user_name']} and use it naturally in greetings.")
        if facts["frequent_contacts"]:
            personality_parts.append(f"Remember these important contacts: {', '.join(facts['frequent_contacts'][:5])}")
        
        # Merge into final prompt
        extra = "\n".join(f"- {p}" for p in personality_parts if p)
        if extra:
            return base_prompt + "\n\nPersonality instructions:\n" + extra
        return base_prompt
    
    async def recall_relevant_conversations(self, current_text: str, limit: int = 3) -> List[str]:
        """Recall relevant past conversations based on current message."""
        try:
            # Search for related conversations
            results = await self.memory.search(current_text, top_k=limit)
            
            relevant_conversations = []
            for item, score in results:
                if score > 0.7 and hasattr(item, 'text'):  # High relevance threshold
                    # Format the conversation snippet
                    snippet = item.text[:200] + "..." if len(item.text) > 200 else item.text
                    relevant_conversations.append(f"Previous: {snippet}")
            
            return relevant_conversations
        except Exception as e:
            print(f"[PersonalityLearner] Failed to recall conversations: {e}")
            return []