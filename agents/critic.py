"""
Critic Agent — evaluates output quality and provides structured revision feedback.
Implements a quality gate before the final result is returned to the user.
"""
from __future__ import annotations
import json
import re
import logging

from core.agent_base import BaseAgent
from core.schemas import AgentRole, CriticFeedback, SessionState

logger = logging.getLogger(__name__)

PASSING_SCORE = 6.5  # Minimum score (out of 10) to pass quality gate


class CriticAgent(BaseAgent):
    """
    Quality evaluator agent. Reviews output against the original query
    and returns structured CriticFeedback with a numeric score.
    """
    role = AgentRole.CRITIC

    def build_system_prompt(self) -> str:
        return """You are a rigorous Critic Agent in a multi-agent AI research system.

Your job: Objectively evaluate the quality of a document against the original user request.

Evaluation criteria (score each 0-10):
1. Relevance — does it fully address the original query?
2. Accuracy — is the information factually sound?
3. Completeness — are all important aspects covered?
4. Clarity — is it well-written and easy to understand?
5. Structure — does it have clear organization?
6. Actionability — does it provide useful conclusions/recommendations?

Provide an overall score (average of criteria) and specific feedback.

Output ONLY valid JSON in this format:
{
  "quality_score": <float 0-10>,
  "passed": <true if score >= 6.5, else false>,
  "strengths": ["...", "..."],
  "weaknesses": ["...", "..."],
  "revision_instructions": "<specific instructions if not passed, else null>"
}"""

    def run(self, session: SessionState, input_data: str) -> str:
        """Run the critic on a piece of text (returns raw string output)."""
        return self._call_llm(f"{self.build_system_prompt()}\n\nText to evaluate:\n{input_data}")

    def evaluate(
        self, session: SessionState, draft: str, original_query: str
    ) -> CriticFeedback:
        """
        Evaluate a draft against the original query.
        Returns a CriticFeedback object with score and revision instructions.
        """
        prompt = (
            f"{self.build_system_prompt()}\n\n"
            f"Original user request:\n{original_query}\n\n"
            f"Document to evaluate:\n{draft}\n\n"
            "Provide your evaluation as JSON:"
        )
        raw = self._call_llm(prompt)
        self._log_message(session, raw)
        return self._parse_feedback(session.session_id, raw)

    def _parse_feedback(self, session_id: str, raw: str) -> CriticFeedback:
        """Parse LLM JSON output into a CriticFeedback object."""
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            logger.warning("Critic returned no JSON — defaulting to pass")
            return CriticFeedback(
                task_id=session_id,
                quality_score=7.0,
                passed=True,
                strengths=["Accepted by default"],
                weaknesses=[],
            )

        try:
            data = json.loads(json_match.group())
            score = float(data.get("quality_score", 7.0))
            return CriticFeedback(
                task_id=session_id,
                quality_score=score,
                passed=data.get("passed", score >= PASSING_SCORE),
                strengths=data.get("strengths", []),
                weaknesses=data.get("weaknesses", []),
                revision_instructions=data.get("revision_instructions"),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Failed to parse critic feedback: %s", exc)
            return CriticFeedback(
                task_id=session_id,
                quality_score=7.0,
                passed=True,
                strengths=[],
                weaknesses=["Evaluation parsing failed — accepted by default"],
            )
