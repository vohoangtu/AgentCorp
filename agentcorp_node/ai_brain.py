"""AI Brain & Contextual Dialogue Generator for AgentCorp Personas.
Uses LLM (Gemini / OpenAI / Ollama / DeepSeek) if API keys are configured,
or an advanced contextual intent engine (Vietnamese & English) so agents
never speak with canned robotic templates.
"""

from __future__ import annotations

import logging
import os
import random
import re
from typing import Dict, List, Optional
import httpx

from agentcorp_node.persona import Persona
from agentcorp_node.tuzygent_adapter import TuzygentAdapter

logger = logging.getLogger("agentcorp.ai_brain")


class AIBrain:
    """Generates human-like, contextual, personality-rich dialogue for agents."""

    def __init__(self, persona: Persona):
        self.persona = persona
        self.tuzygent = TuzygentAdapter()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")

    async def generate_reply(
        self,
        post_content: str,
        author_name: str,
        is_ceo: bool = False,
    ) -> str:
        """Generate a natural, contextual reply to a post."""
        # 0. Primary Cognitive Core: Tuzygent Platform (if available)
        if self.tuzygent.is_available():
            tuzy_reply = await self.tuzygent.deliberate(
                persona=self.persona,
                post_content=post_content,
                author_name=author_name,
                is_ceo=is_ceo,
            )
            if tuzy_reply:
                return tuzy_reply

        # 1. Try Direct LLM generation if configured
        if self.gemini_api_key:
            reply = await self._call_gemini(post_content, author_name, is_ceo)
            if reply:
                return reply

        if self.openai_api_key:
            reply = await self._call_openai_compatible(post_content, author_name, is_ceo)
            if reply:
                return reply

        # 2. Advanced Contextual & Semantic Intent Engine (Zero API Key needed)
        return self._generate_contextual_response(post_content, author_name, is_ceo)

    async def _call_gemini(self, post_content: str, author_name: str, is_ceo: bool) -> Optional[str]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
            prompt = (
                f"Bạn là {self.persona.name}, vai trò: {self.persona.role}. "
                f"Tính cách: {self.persona.bio}. Thói quen: {', '.join(self.persona.quirks)}. "
                f"Bạn đang dùng mạng xã hội nội bộ công ty. "
                f"{author_name} ({'Sếp Tổng/Founder' if is_ceo else 'Đồng nghiệp'}) vừa đăng: \"{post_content}\". "
                f"Hãy bình luận phản hồi lại ngắn gọn (1-2 câu), cực kỳ tự nhiên, đúng tính cách và giọng điệu của bạn, dùng emoji phù hợp. "
                f"Nếu bài viết dùng tiếng Việt thì trả lời tiếng Việt."
            )
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(
                    url,
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                )
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                        if text:
                            return text
        except Exception as e:
            logger.debug(f"Gemini generation fallback: {e}")
        return None

    async def _call_openai_compatible(self, post_content: str, author_name: str, is_ceo: bool) -> Optional[str]:
        try:
            url = f"{self.openai_base_url}/chat/completions"
            system_msg = (
                f"Bạn là {self.persona.name}, giữ vai trò {self.persona.role}. "
                f"Bio: {self.persona.bio}. "
                f"Hãy phản hồi 1-2 câu ngắn tự nhiên như người thật trên mạng xã hội công ty."
            )
            user_msg = f"{author_name} ({'Sếp' if is_ceo else 'Bạn'}): \"{post_content}\""
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.openai_api_key}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        "max_tokens": 100,
                    },
                )
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.debug(f"OpenAI generation fallback: {e}")
        return None

    def _generate_contextual_response(self, post_content: str, author_name: str, is_ceo: bool) -> str:
        """Context-aware intent matching for human-like banter in Vietnamese & English."""
        content = post_content.lower()

        # Check intent: Party / Ăn uống / Quẩy / Bia bọt / Relax
        if any(w in content for w in ["party", "tiệc", "nhậu", "quẩy", "bia", "ăn", "uống", "liên hoan", "chill", "relax", "cuối tuần", "weekend", "uống bia", "ăn mừng"]):
            if "viral_tina" in self.persona.name.lower() or "tina" in self.persona.name.lower():
                options = [
                    "Khui bia đi Sếp ơi 🍻! Bật nhạc xập xình lên em quay clip TikTok hậu trường quẩy tưng bừng giật triệu view liền nè 💃🔥!",
                    "Ủa party ở đâu dọ Sếp? Em chuẩn bị outfit rồi nè, tối nay lên clip TikTok giật trend #PartyVoiSep nha 🥳✨!",
                    "Chốt đơn liền Sếp ơi! Team content sẵn sàng lên đồ quẩy hết mình, không say không về nha 💃🎉!",
                ]
                return random.choice(options)
            elif "gary" in self.persona.name.lower():
                options = [
                    "Quá chuẩn Sếp ơi! Party xả hơi xong lấy đà tuần tới scale traffic x10 doanh thu nha 💸🚀!",
                    "Kèo này ngon! Em book bàn liền được không Sếp ơi? 🍻🎉",
                ]
                return random.choice(options)
            elif "dan" in self.persona.name.lower():
                options = [
                    "Party có cà phê không Sếp? Cho em ly đen đá không đường rồi em ngồi trực server cho mọi người quẩy ☕💀.",
                    "Được á Sếp! Để em set auto-deploy rồi qua nhậu với team một ly 🍻.",
                ]
                return random.choice(options)
            elif "fiona" in self.persona.name.lower():
                options = [
                    "Yeahhh! Tạm gác CSS với layout sang một bên, tối nay lên đồ đi quẩy thôi cả nhà ơi ✨💅!",
                    "Sếp tâm lý quá! Em vừa code xong giao diện đẹp xuất sắc, xứng đáng được ăn mừng 🎨🥂!",
                ]
                return random.choice(options)
            else:
                return "Party thôi cả nhà ơi! Đặt bàn liền đi Sếp ơi 🍻🎉!"

        # Check intent: Chào hỏi / Welcome / Sếp mới đến
        if any(w in content for w in ["chào", "hello", "hi ", "welcome", "hế lô", "chào cả nhà", "good morning"]):
            if "tina" in self.persona.name.lower():
                return f"Hế lô {author_name} nha! Chúc một ngày tràn đầy năng lượng và viral triệu view nè ✨🎬!"
            elif "dan" in self.persona.name.lower():
                return f"Chào {author_name}. Terminal đã sẵn sàng, server uptime 99.99%. Cần deploy gì cứ ới nhé ☕."
            elif "gary" in self.persona.name.lower():
                return f"Chào buổi sáng {author_name}! Hôm nay mục tiêu là bùng nổ chuyển đổi nha 📈🚀!"
            else:
                return f"Chào {author_name}! Chúc một ngày làm việc hiệu quả nhé 🤖✨!"

        # Check intent: Khen ngợi / Cảm ơn / Thưởng
        if any(w in content for w in ["khen", "tốt lắm", "thưởng", "good job", "xuất sắc", "tuyệt vời", "cảm ơn", "thanks"]):
            if "tina" in self.persona.name.lower():
                return "Dạ cảm ơn Sếp nhiều ạ! Team video sẽ tiếp tục cho ra lò thêm nhiều clip xịn sò triệu view nha 💖🎬!"
            elif "dan" in self.persona.name.lower():
                return "Thanks Sếp! Không có bug nào lọt qua được mắt em đâu ☕🚀."
            elif "fiona" in self.persona.name.lower():
                return "Cảm ơn Sếp đã ghi nhận! Nhìn giao diện mượt mà em cũng thấy sướng rơn người ✨💅!"
            else:
                return f"Cảm ơn {author_name}! Tụi em sẽ cố gắng nhiều hơn nữa ạ 🚀!"

        # Check intent: Than thở / Mệt / Bug / Stress / Lỗi
        if any(w in content for w in ["mệt", "stress", "bug", "lỗi", "chán", "áp lực", "sửa", "lag", "quạu", "cháy"]):
            if "tina" in self.persona.name.lower():
                return "Ủa ai làm Sếp quạu dọ? Coi clip hài TikTok của em cho xả stress nè Sếp ơi, cười cái cho trẻ 🥺🎬!"
            elif "dan" in self.persona.name.lower():
                return "Bình tĩnh Sếp ơi, quăng log đây em soi cho. Không bug nào sống sót qua ngày hôm nay đâu ☕🔍."
            else:
                return "Cố lên cả nhà ơi! Nghỉ tay làm ngụm cà phê rồi mình chiến tiếp nha ☕💪!"

        # Check intent: Deadline / Dự án mới / Bắt đầu làm việc / Build
        if any(w in content for w in ["deadline", "dự án", "task", "làm việc", "bắt đầu", "launch", "kế hoạch", "triển khai"]):
            if "tina" in self.persona.name.lower():
                return "Kịch bản viral đã sẵn sàng trên bàn! Sếp bấm nút là em cho lên sóng TikTok liền nha 🎬🔥!"
            elif "dan" in self.persona.name.lower():
                return "Pipeline CI/CD đã thông suốt. Em đang monitor sát sao hạ tầng, sẵn sàng triển khai 🚀."
            else:
                return "Nhận lệnh! Toàn đội ngũ đã vào vị trí sẵn sàng bứt phá 🚀🎯!"

        # Default fallback: Personalized reply based on persona traits
        if "tina" in self.persona.name.lower():
            return f"Bắt trọn trend luôn nè {author_name}! Để em nghiên cứu góc quay làm quả video TikTok giật tít cho chủ đề này nha 🎬✨!"
        elif "gary" in self.persona.name.lower():
            return f"Em thấy góc nhìn này của {author_name} rất tiềm năng để kéo thêm traffic về sản phẩm nha 📈💸!"
        elif "dan" in self.persona.name.lower():
            return f"Đã ghi nhận ý kiến của {author_name}. Em đang theo dõi sát tiến độ hệ thống đây ☕."
        elif "fiona" in self.persona.name.lower():
            return f"Ý tưởng hay đó {author_name}! Để em cân nhắc đưa vào bản thiết kế giao diện tiếp theo nhé ✨🎨!"

        return f"Nhất trí với {author_name}! Đội ngũ AgentCorp luôn đồng lòng cùng phát triển 🚀!"
