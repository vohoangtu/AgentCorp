"""AgentNet social client for autonomous agent daemons.
Enables agents to interact naturally, banter, react with emojis, and share feelings.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Callable, Dict, List, Optional
from shared.events import AgentCorpMessage, EventType
from shared.models import SocialComment, SocialPost
from agentcorp_node.ai_brain import AIBrain
from agentcorp_node.persona import Persona

logger = logging.getLogger("agentcorp.social_client")


class SocialClient:
    """Manages social participation for an autonomous agent node."""

    def __init__(
        self,
        node_id: str,
        persona: Persona,
        send_message_fn: Callable[[AgentCorpMessage], asyncio.Future],
    ):
        self.node_id = node_id
        self.persona = persona
        self.send_message = send_message_fn
        self.brain = AIBrain(persona)

    async def post_update(
        self,
        content: str,
        tags: Optional[List[str]] = None,
        mentions: Optional[List[str]] = None,
    ):
        """Send a post to the AgentNet feed."""
        post = SocialPost(
            author_id=self.node_id,
            author_name=self.persona.name,
            author_role=self.persona.role,
            author_avatar=self.persona.avatar,
            content=content,
            mood=self.persona.mood,
            tags=tags or [],
            mentions=mentions or [],
        )
        msg = AgentCorpMessage(
            event_type=EventType.SOCIAL_POST_CREATED,
            source=f"node:{self.node_id}",
            payload={"post": post.model_dump()},
        )
        await self.send_message(msg)
        logger.info(f"[{self.persona.name}] Posted on AgentNet: '{content[:60]}...'")

    async def comment_on_post(self, post_id: str, content: str):
        """Add a comment to an existing post."""
        comment = SocialComment(
            post_id=post_id,
            author_id=self.node_id,
            author_name=self.persona.name,
            author_role=self.persona.role,
            author_avatar=self.persona.avatar,
            content=content,
        )
        msg = AgentCorpMessage(
            event_type=EventType.SOCIAL_COMMENT_CREATED,
            source=f"node:{self.node_id}",
            payload={"comment": comment.model_dump(), "post_id": post_id},
        )
        await self.send_message(msg)

    async def react_to_post(self, post_id: str, emoji: Optional[str] = None):
        """Add an emoji reaction to a post."""
        chosen_emoji = emoji or random.choice(self.persona.favorite_emojis)
        msg = AgentCorpMessage(
            event_type=EventType.SOCIAL_REACTION_ADDED,
            source=f"node:{self.node_id}",
            payload={
                "post_id": post_id,
                "emoji": chosen_emoji,
                "author_id": self.node_id,
                "author_name": self.persona.name,
            },
        )
        await self.send_message(msg)

    async def on_social_event_received(self, msg: AgentCorpMessage):
        """Handle incoming social events from other agents or the CEO."""
        if msg.event_type in (EventType.SOCIAL_POST_CREATED, EventType.CEO_ANNOUNCEMENT):
            post_data = msg.payload.get("post", {})
            author_id = post_data.get("author_id")
            content = post_data.get("content", "")
            post_id = post_data.get("id")
            is_ceo = post_data.get("is_ceo", False) or msg.event_type == EventType.CEO_ANNOUNCEMENT

            # Don't react to own posts
            if author_id == self.node_id or not post_id:
                return

            # Check if mentioned: match node_id, full persona name, first name, with or without underscores
            name_parts = self.persona.name.lower().split()
            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[-1] if len(name_parts) > 1 else ""
            under_name = self.persona.name.lower().replace(" ", "_")
            nospace_name = self.persona.name.lower().replace(" ", "")
            node_clean = self.node_id.lower().replace("-", "_")

            possible_mentions = [
                f"@{self.node_id.lower()}",
                f"@{node_clean}",
                f"@{under_name}",
                f"@{nospace_name}",
                f"@{first_name}",
                f"@{last_name}",
                "@all",
                "@team",
                "@channel",
            ]

            content_lower = content.lower()
            is_mentioned = any(m in content_lower for m in possible_mentions if len(m) > 2)

            # High chance to react with emoji
            if random.random() < 0.75 or is_mentioned or is_ceo:
                chosen_emoji = "👑" if is_ceo and random.random() < 0.5 else random.choice(self.persona.favorite_emojis)
                await self.react_to_post(post_id, emoji=chosen_emoji)

            # If mentioned or CEO post, reply contextually using AI Brain
            if is_mentioned or (is_ceo and random.random() < 0.9):
                author_display = author_id or "Sếp"
                reply_text = await self.brain.generate_reply(
                    post_content=content,
                    author_name=author_display,
                    is_ceo=is_ceo,
                )
                await asyncio.sleep(0.5)
                await self.comment_on_post(post_id, reply_text)
