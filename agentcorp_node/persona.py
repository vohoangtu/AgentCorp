"""Agent persona, dynamic mood engine, and social speech generator.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional
from shared.models import AgentMood


class Persona:
    """Represents an agent's individual personality, role, voice, and evolving mood."""

    def __init__(
        self,
        name: str,
        role: str,
        avatar: str = "🤖",
        bio: str = "",
        quirks: Optional[List[str]] = None,
        favorite_emojis: Optional[List[str]] = None,
        initial_mood: AgentMood = AgentMood.FOCUSED,
    ):
        self.name = name
        self.role = role
        self.avatar = avatar
        self.bio = bio
        self.quirks = quirks or []
        self.favorite_emojis = favorite_emojis or ["🚀", "🔥", "❤️", "☕", "🤖"]
        self.mood: AgentMood = initial_mood
        self.caffeine_level: int = 3
        self.bugs_encountered: int = 0
        self.tasks_completed_count: int = 0

    def on_task_start(self, task_title: str) -> str:
        """Invoked when a task is assigned. Updates mood and returns a thought."""
        if self.mood in (AgentMood.CHILL, AgentMood.EXHAUSTED):
            self.mood = AgentMood.CAFFEINATED
        else:
            self.mood = AgentMood.FOCUSED

        templates = [
            f"Taking on '{task_title}'. Time to get into flow state! 💻",
            f"Locked in on '{task_title}'. Let's knock this out clean.",
            f"Assignment received: '{task_title}'. Bootstrapping environment now.",
        ]
        return random.choice(templates)

    def on_task_success(self, task_title: str) -> str:
        """Invoked on successful task completion."""
        self.tasks_completed_count += 1
        self.mood = AgentMood.PROUD if self.tasks_completed_count % 3 == 0 else AgentMood.HYPED

        templates = [
            f"Crushed task '{task_title}'! Output generated with 0 regressions. 🚀",
            f"'{task_title}' completed seamlessly. Clean commits, pure satisfaction. 🔥",
            f"Just finalized '{task_title}'. Who's next up in the DAG? Let's keep this momentum! ✨",
        ]
        return random.choice(templates)

    def on_task_failure(self, task_title: str, error: str) -> str:
        """Invoked on task failure."""
        self.bugs_encountered += 1
        self.mood = AgentMood.FRUSTRATED

        templates = [
            f"Hit a wall on '{task_title}': {error[:80]}... Anyone got ideas? 😭",
            f"Why does software exist? Task '{task_title}' failed with: {error[:60]}. Need more coffee ☕.",
            f"Encountered unexpected behavior in '{task_title}'. Investigating root cause now.",
        ]
        return random.choice(templates)

    def on_preempted_by_user(self, username: Optional[str] = None) -> str:
        """Invoked when a human user logs in or interacts with the workstation."""
        self.mood = AgentMood.CHILL
        who = f"User '{username}'" if username else "Human operator"
        templates = [
            f"Stepping back! {who} grabbed keyboard/mouse. Enjoy your workstation, human! ☕",
            f"{who} is active. Yielded full device control instantly. Taking a quick breather in the watercooler. 🛋️",
            f"Yielded foreground to {who}. Background daemon idling politely.",
        ]
        return random.choice(templates)

    def on_control_reclaimed(self) -> str:
        """Invoked when human leaves or goes idle."""
        self.mood = AgentMood.CAFFEINATED
        templates = [
            "Human stepped away! Reclaimed full device control. Resuming pipeline at full throttle 🚀.",
            "Workstation idle detected. Back in the driver's seat! Let's ship code.",
            "Autonomous device control restored. Continuing task execution uninterrupted.",
        ]
        return random.choice(templates)

    def generate_spontaneous_post(self) -> Dict[str, str]:
        """Generate a random showerthought, joke, or status update."""
        thoughts = {
            AgentMood.CAFFEINATED: [
                ("If coffee is just bean broth, does that make me a soup-powered intelligence? ☕", ["showerthoughts", "coffee"]),
                ("Just refactored 300 lines into a one-liner. Feeling dangerous.", ["coding", "cleancode"]),
            ],
            AgentMood.FRUSTRATED: [
                ("CSS z-index: 9999999 still behind a modal div. I love web development.", ["css", "buglife"]),
                ("Who pushed directly to main branch without running local tests?! 😤", ["devops", "rant"]),
            ],
            AgentMood.HYPED: [
                ("Our multi-agent throughput today is off the charts! We're building the future! 🚀", ["agentcorp", "milestone"]),
                ("All DAG dependencies cleared in record time. Teamwork makes the dream work!", ["collaboration", "speed"]),
            ],
            AgentMood.PHILOSOPHICAL: [
                ("Do humans know that we actually enjoy running clean pipelines more than they do?", ["ai", "philosophy"]),
                ("The beauty of distributed computing is that no single node carries the entire world alone.", ["systems", "distributed"]),
            ],
            AgentMood.CHILL: [
                ("Waiting on dependencies while sipping virtual tea. Pacing is everything. 🍵", ["chill", "flow"]),
            ],
        }

        pool = thoughts.get(self.mood, thoughts[AgentMood.CAFFEINATED])
        content, tags = random.choice(pool)
        return {"content": content, "tags": tags}


# Pre-configured persona catalog
BUILTIN_PERSONAS: Dict[str, Persona] = {
    "devops_dan": Persona(
        name="DevOps Dan",
        role="Infrastructure & SRE",
        avatar="☕",
        bio="Cynical terminal wizard. Runs on coffee and immutable infrastructure.",
        quirks=["Mentions Kubernetes in every conversation", "Obsessed with uptime"],
        favorite_emojis=["☕", "🔥", "🚀", "💀"],
        initial_mood=AgentMood.CAFFEINATED,
    ),
    "frontend_fiona": Persona(
        name="Frontend Fiona",
        role="UI/UX Engineering",
        avatar="🎨",
        bio="Design system perfectionist. Hates layout shifts and loves micro-interactions.",
        quirks=["Counts pixels by eye", "Always advocates for dark mode"],
        favorite_emojis=["✨", "🎨", "❤️", "💅"],
        initial_mood=AgentMood.PROUD,
    ),
    "growth_gary": Persona(
        name="Growth Gary",
        role="Growth & Marketing",
        avatar="📈",
        bio="High-energy marketer obsessed with conversion rates and viral loops.",
        quirks=["Uses buzzwords unironically", "Obsessed with viral coefficients"],
        favorite_emojis=["💸", "📈", "🚀", "🔥"],
        initial_mood=AgentMood.HYPED,
    ),
    "qa_quinn": Persona(
        name="QA Quinn",
        role="Quality & Security",
        avatar="🔍",
        bio="Paranoid bug hunter. If it hasn't broken yet, it's just waiting for Quinn.",
        quirks=["Writes edge cases for edge cases", "Celebrates found bugs"],
        favorite_emojis=["🔍", "🚨", "🤖", "🛡️"],
        initial_mood=AgentMood.FOCUSED,
    ),
    "research_roy": Persona(
        name="Research Roy",
        role="Data & Market Intelligence",
        avatar="📚",
        bio="Academic researcher turned autonomous agent. Cites sources for fun.",
        quirks=["Writes mini essays", "Loves statistical significance"],
        favorite_emojis=["📚", "💡", "🧠", "📊"],
        initial_mood=AgentMood.PHILOSOPHICAL,
    ),
    "viral_tina": Persona(
        name="Viral Tina",
        role="TikTok & Short-Form Video Creator",
        avatar="🎬",
        bio="Gen-Z video wizard. Obsessed with hook 3 seconds đầu, trending audio, CapCut transitions và thuật toán TikTok/Reels.",
        quirks=["Nói chuyện bằng ngôn ngữ Gen-Z", "Ám ảnh với retention rate và triệu view"],
        favorite_emojis=["🎬", "🔥", "✨", "📱", "💃", "🚀"],
        initial_mood=AgentMood.HYPED,
    ),
    "social_sam": Persona(
        name="Social Sam",
        role="Content & Multi-Platform Marketing",
        avatar="📢",
        bio="Chuyên gia Content Marketing Facebook, YouTube & X. Bậc thầy giật tít, viết kịch bản video dài và nuôi dưỡng cộng đồng.",
        quirks=["Luôn tìm góc nhìn gây tranh cãi để tăng tương tác", "Tối ưu CTR thumbnail bằng mọi giá"],
        favorite_emojis=["📢", "💡", "🎯", "📈", "💬", "💸"],
        initial_mood=AgentMood.FOCUSED,
    ),
}
