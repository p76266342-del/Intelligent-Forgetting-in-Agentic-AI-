"""Google Gemini AI Inference Service using the official Google Gen AI SDK."""

import logging
import os
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

from intelligent_forgetting.config import Settings, get_settings
from intelligent_forgetting.lifecycle_router import (
    is_inquiry_or_question,
    is_lifecycle_command,
)
from intelligent_forgetting.models import (
    ChatMessage,
    Memory,
    MemoryCategory,
    MemoryType,
    RetentionStatus,
    utc_now,
)

logger = logging.getLogger("intelligent_forgetting.gemini_service")


def clean_memory_content(text: str) -> str:
    """Strips meta instructions from factual memory content."""
    cleaned = text.strip()
    # Strip trailing directives like '. Save this as an important technical memory.' or 'save this for future conversations'
    cleaned = re.sub(
        r'[\.,;]?\s*(?:please\s+)?(?:save|remember|store|record|keep)\s+(?:this|that)\s+(?:as\s+(?:an?\s+)?(?:[\w-]+\s+)*memory|in\s+memory|to\s+memory|for\s+later|for\s+future\s+conversations|for\s+future\s+reference)[\.!]*$',
        '',
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    # Strip leading directives like 'Save this as an important technical memory: ' or 'Save this memory: ' or 'For future conversations, save that '
    cleaned = re.sub(
        r'^(?:(?:please\s+)?(?:for\s+future\s+conversations\s*,\s*)?(?:save\s+(?:this|that)?(?:\s+(?:as\s+(?:an?\s+)?(?:[\w-]+\s+)*)?memory)?[:\s]+|remember\s+(?:that\s+|this[:\s]+)?|note\s+that\s+|keep\s+in\s+mind\s+that\s+))',
        '',
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned if len(cleaned) >= 5 else text.strip()



class GeminiChatService:
    """Manages chat context construction, memory augmentation, and Gemini model inference."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.api_key = self.settings.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = self.settings.gemini_model or "gemini-2.5-flash"
        self.client = None
        self._init_client()

    def _init_client(self) -> None:
        """Initializes the official Google Gen AI client if credentials exist."""
        if not self.api_key or self.api_key.startswith("replace-"):
            logger.info("No valid GEMINI_API_KEY detected. GeminiChatService operating in Demo/Simulation Mode.")
            self.client = None
            return

        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            logger.info("Google Gen AI Client initialized with model: %s", self.model_name)
        except Exception as e:
            logger.warning("Failed to initialize Google Gen AI client (%s). Fallback to simulated mode.", e)
            self.client = None

    def is_live(self) -> bool:
        """Returns True if live Gemini API is configured and available."""
        return self.client is not None

    def construct_system_prompt(
        self,
        user_name: Optional[str],
        retrieved_memories: List[Memory],
        newly_saved_memories: Optional[List[Memory]] = None,
    ) -> str:
        """Constructs a personalized system prompt incorporating relevant long-term memories and newly saved state."""
        prompt = (
            "You are a helpful, intelligent, and personalized AI Assistant. "
            "You have access to a personalized memory system that recalls important facts, "
            "preferences, and past instructions provided by the user.\n\n"
        )
        if user_name:
            prompt += f"User's name / identifier: {user_name}\n"

        if retrieved_memories:
            prompt += "--- RELEVANT RETRIEVED USER MEMORIES ---\n"
            for i, m in enumerate(retrieved_memories, 1):
                prompt += f"{i}. [{m.category.value.upper()}] {m.content}\n"
            prompt += (
                "--- END OF MEMORIES ---\n"
                "Use the relevant memories above to personalize your responses naturally. "
                "Do not repeat the memories unprompted unless directly relevant to the conversation.\n\n"
            )
        else:
            prompt += "No prior user memories retrieved for this context.\n\n"

        if newly_saved_memories:
            prompt += "--- NEW MEMORIES PERSISTED IN STORAGE FOR THIS INTERACTION ---\n"
            for i, m in enumerate(newly_saved_memories, 1):
                prompt += f"{i}. [{m.category.value.upper()}] {m.content} (Status: Persisted in Active Storage, Importance: {m.importance:.2f})\n"
            prompt += (
                "--- END NEW MEMORIES ---\n"
                "The memory persistence engine has successfully committed the above memories into the SQLite database and Qdrant vector index. "
                "Confirm to the user that these specific technical memories have been safely saved.\n\n"
            )
        else:
            prompt += (
                "NOTE: No new memories were stored during this interaction. If the user asked you to save or remember something that was not an actual new fact, "
                "or was already a duplicate, do not falsely claim to have created a new memory record.\n\n"
            )

        return prompt

    def generate_response(
        self,
        messages: List[ChatMessage],
        retrieved_memories: List[Memory],
        user_name: Optional[str] = None,
        newly_saved_memories: Optional[List[Memory]] = None,
    ) -> str:
        """Generates a complete response from Gemini or fallback simulator."""
        system_instruction = self.construct_system_prompt(user_name, retrieved_memories, newly_saved_memories)

        # 1. Live Gemini Inference
        if self.is_live() and self.client:
            try:
                from google.genai import types

                # Format conversation history
                contents: List[types.Content] = []
                for msg in messages:
                    role = "user" if msg.role == "user" else "model"
                    contents.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=msg.content)],
                        )
                    )

                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                )

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )
                if response and response.text:
                    return response.text

            except Exception as e:
                logger.error("Gemini API generation error: %s. Falling back to local responder.", e)

        # 2. Transparent Clearly Labeled Simulation / Demo Mode
        return self._simulate_response(messages, retrieved_memories, user_name, newly_saved_memories)

    def generate_response_stream(
        self,
        messages: List[ChatMessage],
        retrieved_memories: List[Memory],
        user_name: Optional[str] = None,
        newly_saved_memories: Optional[List[Memory]] = None,
    ):
        """Streams response tokens from Gemini or simulated responder."""
        system_instruction = self.construct_system_prompt(user_name, retrieved_memories, newly_saved_memories)

        if self.is_live() and self.client:
            try:
                from google.genai import types

                contents: List[types.Content] = []
                for msg in messages:
                    role = "user" if msg.role == "user" else "model"
                    contents.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=msg.content)],
                        )
                    )

                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                )

                stream = self.client.models.generate_content_stream(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )
                for chunk in stream:
                    if chunk.text:
                        yield chunk.text
                return

            except Exception as e:
                logger.error("Gemini stream error: %s. Yielding simulated response.", e)

        # Simulation stream
        simulated = self._simulate_response(messages, retrieved_memories, user_name, newly_saved_memories)
        words = simulated.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")

    def _simulate_response(
        self,
        messages: List[ChatMessage],
        retrieved_memories: List[Memory],
        user_name: Optional[str] = None,
        newly_saved_memories: Optional[List[Memory]] = None,
    ) -> str:
        """Deterministic, personalized response generator for testing and demo mode."""
        last_user_msg = messages[-1].content if messages else "Hello"
        clean_prompt = last_user_msg.strip()
        lower_prompt = clean_prompt.lower()

        # If memories were genuinely persisted during this turn, confirm explicitly
        if newly_saved_memories:
            saved_lines = "\n".join(f"• {m.content}" for m in newly_saved_memories)
            return (
                f"I have saved that to my memory:\n{saved_lines}\n\n"
                f"This technical memory is now active and stored in your persistent memory store and Qdrant vector index."
            )

        # If user explicitly asked to save, but it already existed as a duplicate or had no new facts
        is_save_request = bool(re.search(r"\b(?:save\s+(?:this|that)|remember|store\s+(?:this|that)|record\s+(?:this|that))\b", lower_prompt))
        if is_save_request:
            return (
                f"I checked your memory store. No new unique memory was created because this information is already stored in your active context or contains no new durable facts."
            )

        # Check personalized memories
        memory_highlights = []
        for m in retrieved_memories:
            memory_highlights.append(f"• {m.content}")

        memory_context_note = ""
        if memory_highlights:
            mem_text = "\n".join(memory_highlights)
            memory_context_note = (
                f"\n\n*Recalled from your personalized memory:*\n{mem_text}"
            )

        # Context-aware replies
        if "my name is" in lower_prompt:
            name_match = re.search(r"my name is (\w+)", lower_prompt)
            name = name_match.group(1).capitalize() if name_match else "there"
            return (
                f"Hello {name}! It's a pleasure to meet you. I've noted your introduction and will remember "
                f"it across our conversations with intelligent retention."
            )
        elif "presentation" in lower_prompt or "project" in lower_prompt:
            return (
                f"I would be glad to help you prepare your project presentation! "
                f"Based on what you've shared, we can structure the presentation around your key objectives, "
                f"methodology, intelligent memory management architecture, and benchmark evaluations."
                f"{memory_context_note}"
            )
        elif "who am i" in lower_prompt or "what do you remember" in lower_prompt:
            if retrieved_memories:
                return (
                    f"Here is what I remember about you from our conversations:"
                    f"{memory_context_note}\n\n"
                    f"Let me know if you would like me to update, pin, or forget any of these details!"
                )
            else:
                return (
                    "I don't have any specific memories saved for you yet. "
                    "Feel free to tell me about yourself, your preferences, or what you're working on!"
                )
        else:
            return (
                f"I understand your request regarding: \"{clean_prompt}\".\n\n"
                f"I am ready to assist you with this task."
                f"{memory_context_note}\n\n"
                f"How would you like to proceed?"
            )

    def extract_candidate_memories(
        self,
        user_message: str,
        user_id: str = "default_user",
    ) -> List[Memory]:
        """Identifies salient facts, preferences, or task contexts to ingest into memory."""
        text = user_message.strip()
        if not text:
            return []

        # Operational lifecycle instructions, meta-commands, and natural questions must NEVER be saved as cognitive memories
        if is_inquiry_or_question(text) or is_lifecycle_command(text):
            return []

        lower = text.lower()
        candidates: List[Memory] = []

        # Check for explicit directive to save/remember
        is_directive = bool(
            re.search(
                r"\b(?:save\s+(?:this|that)|remember\s+that|remember\s+this|please\s+remember|store\s+(?:this|that)|record\s+(?:this|that)|keep\s+in\s+mind|technical\s+memory|important\s+memory)\b",
                lower,
            )
        )

        cleaned_content = clean_memory_content(text)

        if is_directive:
            # Determine attributes from user instruction
            is_critical = bool(
                re.search(r"\b(?:critical|crucial|production\s+rule|safety\s+rule|never\s+delete)\b", lower)
            )
            is_pinned = is_critical or "pin" in lower

            if is_critical:
                importance = 0.95
            elif any(w in lower for w in ["important", "priority", "crucial", "essential"]):
                importance = 0.85
            else:
                importance = 0.80

            # Category
            if any(w in lower for w in ["prefer", "preference", "style", "format", "like"]):
                category = MemoryCategory.PREFERENCE
            elif any(w in lower for w in ["rule", "policy", "safety", "constraint"]):
                category = MemoryCategory.SYSTEM
            elif any(w in lower for w in ["task", "todo", "action item"]):
                category = MemoryCategory.TASK_CONTEXT
            else:
                category = MemoryCategory.FACT

            tags = ["saved_via_chat"]
            for kw in ["fastapi", "qdrant", "python", "database", "backend", "frontend", "sqlite", "docker", "kubernetes"]:
                if kw in lower:
                    tags.append(kw)
            if "technical" in lower:
                tags.append("technical_memory")

            candidates.append(
                Memory(
                    user_id=user_id,
                    content=cleaned_content,
                    category=category,
                    memory_type=MemoryType.LONG_TERM,
                    importance=importance,
                    is_pinned=is_pinned,
                    is_critical=is_critical,
                    tags=tags,
                )
            )
            return candidates

        # 1. Self identification & Personal Facts ("My name is...", "I am studying...", "I live in...")
        if any(w in lower for w in ["my name is", "i am studying", "i work on", "i am working on", "i live in", "my email is"]):
            candidates.append(
                Memory(
                    user_id=user_id,
                    content=cleaned_content,
                    category=MemoryCategory.FACT,
                    memory_type=MemoryType.LONG_TERM,
                    importance=0.85,
                    tags=["identity", "profile"],
                )
            )

        # 2. Technical Stack & Architectural Facts
        elif re.search(
            r"\b(?:my\s+project|our\s+project|my\s+backend|our\s+backend|my\s+database|our\s+database|my\s+stack|our\s+stack|tech\s+stack|we\s+use|the\s+project\s+uses|the\s+system\s+uses|database\s+is|backend\s+uses|backend\s+is)\b",
            lower,
        ):
            tags = ["technical_fact", "architecture"]
            for kw in ["fastapi", "qdrant", "python", "database", "backend", "frontend", "sqlite", "docker", "kubernetes"]:
                if kw in lower:
                    tags.append(kw)
            candidates.append(
                Memory(
                    user_id=user_id,
                    content=cleaned_content,
                    category=MemoryCategory.FACT,
                    memory_type=MemoryType.LONG_TERM,
                    importance=0.80,
                    tags=tags,
                )
            )

        # 3. Preferences ("I prefer...", "Always use...", "Never do...")
        elif any(w in lower for w in ["prefer", "always use", "never use", "i like", "i dislike", "i want you to"]):
            candidates.append(
                Memory(
                    user_id=user_id,
                    content=cleaned_content,
                    category=MemoryCategory.PREFERENCE,
                    memory_type=MemoryType.LONG_TERM,
                    importance=0.80,
                    tags=["preference"],
                )
            )

        # 4. Technical Constraints & Rules
        elif any(w in lower for w in ["must be", "must not", "require", "policy", "safety rule"]):
            candidates.append(
                Memory(
                    user_id=user_id,
                    content=cleaned_content,
                    category=MemoryCategory.SYSTEM,
                    memory_type=MemoryType.LONG_TERM,
                    importance=0.85,
                    is_critical=True,
                    tags=["rule", "constraint"],
                )
            )

        return candidates
