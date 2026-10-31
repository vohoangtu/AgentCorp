"""Tests for AgentNet social interactions, posts, comments, and dynamic persona mood.
"""

import pytest
from shared.models import AgentMood
from agentcorp_hub.social_manager import SocialManager
from agentcorp_hub.store import HubStore
from agentcorp_node.persona import BUILTIN_PERSONAS, Persona


@pytest.fixture
def store_and_social():
    store = HubStore()
    social_mgr = SocialManager(store)
    return store, social_mgr


@pytest.mark.asyncio
async def test_social_post_mentions_and_tags(store_and_social):
    store, social_mgr = store_and_social

    post = await social_mgr.create_post(
        author_id="node-dan",
        author_name="DevOps Dan",
        author_role="SRE",
        content="Hey @Frontend_Fiona, the new build is deployed! Check #staging and #release",
        mood=AgentMood.HYPED,
    )

    assert "@Frontend_Fiona" in post.mentions
    assert "staging" in post.tags
    assert "release" in post.tags

    # Add a reaction
    await social_mgr.react_to_post(post.id, "🚀", "node-fiona")
    retrieved = await store.get_post(post.id)
    assert "🚀" in retrieved.reactions
    assert "node-fiona" in retrieved.reactions["🚀"]

    # Add a comment
    cmt = await social_mgr.add_comment(
        post_id=post.id,
        author_id="node-fiona",
        author_name="Frontend Fiona",
        author_role="UI/UX",
        content="Testing staging right now!",
    )
    assert cmt is not None
    assert retrieved.comments_count == 1


def test_persona_mood_shifts():
    dan = BUILTIN_PERSONAS["devops_dan"]

    # On task start
    msg = dan.on_task_start("Deploy k8s cluster")
    assert dan.mood in (AgentMood.FOCUSED, AgentMood.CAFFEINATED)
    assert "Deploy k8s cluster" in msg

    # On success
    dan.on_task_success("Deploy k8s cluster")
    assert dan.mood in (AgentMood.HYPED, AgentMood.PROUD)

    # On failure
    dan.on_task_failure("Deploy k8s cluster", "Connection refused")
    assert dan.mood == AgentMood.FRUSTRATED
    assert dan.bugs_encountered == 1

    # On human preemption
    preempt_msg = dan.on_preempted_by_user("alice")
    assert dan.mood == AgentMood.CHILL
    assert "alice" in preempt_msg


@pytest.mark.asyncio
async def test_social_client_comment_dispatch_and_mention_reply():
    from shared.events import AgentCorpMessage, EventType
    from shared.models import SocialComment
    from agentcorp_node.social_client import SocialClient

    sent_messages = []

    async def mock_send(msg):
        sent_messages.append(msg)

    dan = BUILTIN_PERSONAS["devops_dan"]
    client = SocialClient(node_id="node-dan", persona=dan, send_message_fn=mock_send)

    # 1. Comment on post
    await client.comment_on_post("post-123", "Nice job team!")
    assert len(sent_messages) == 1
    cmt_msg = sent_messages[0]
    assert cmt_msg.event_type == EventType.SOCIAL_COMMENT_CREATED
    # Validate Pydantic deserialization
    comment = SocialComment(**cmt_msg.payload["comment"])
    assert comment.author_id == "node-dan"
    assert comment.created_at is not None and isinstance(comment.created_at, float)

    # 2. Mention @Dan or @node-dan
    incoming = AgentCorpMessage(
        event_type=EventType.SOCIAL_POST_CREATED,
        source="node:node-fiona",
        payload={
            "post": {
                "id": "post-456",
                "author_id": "node-fiona",
                "content": "Hey @Dan please review staging!",
            }
        },
    )
    await client.on_social_event_received(incoming)
    reply_comments = [
        m for m in sent_messages
        if m.event_type == EventType.SOCIAL_COMMENT_CREATED and m.payload.get("post_id") == "post-456"
    ]
    assert len(reply_comments) == 1
