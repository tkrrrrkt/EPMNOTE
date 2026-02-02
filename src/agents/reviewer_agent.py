"""
EPM Note Engine - Reviewer Agent

Evaluates article quality using a structured scoring rubric.
"""

import json
import logging
from dataclasses import dataclass

from src.config import get_anthropic_client

logger = logging.getLogger(__name__)


@dataclass
class ScoreBreakdown:
    """Score breakdown by evaluation criteria."""

    target_appeal: int = 0  # 0-30: ターゲット訴求力
    logical_structure: int = 0  # 0-40: 論理構成
    seo_fitness: int = 0  # 0-30: SEO適合性


@dataclass
class ReviewResult:
    """Complete review result."""

    score: int = 0  # 0-100: Total score
    breakdown: ScoreBreakdown = None
    feedback: str = ""
    passed: bool = False  # score >= 80

    def __post_init__(self):
        if self.breakdown is None:
            self.breakdown = ScoreBreakdown()
        self.passed = self.score >= 80


class ReviewerAgent:
    """
    Agent for reviewing and scoring article quality.

    Uses a structured rubric:
    - Target Appeal (30 points): How well the article addresses the target persona
    - Logical Structure (40 points): Flow, coherence, and argumentation
    - SEO Fitness (30 points): Keyword usage and competitive positioning
    """

    PASS_THRESHOLD = 80

    def __init__(self) -> None:
        """Initialize the reviewer agent."""
        self.client = get_anthropic_client()

    def review(
        self,
        draft_content: str,
        target_persona: str,
        seo_keywords: str,
    ) -> ReviewResult:
        """
        Review an article draft and provide scoring.

        Args:
            draft_content: The draft article content in Markdown.
            target_persona: Target reader persona.
            seo_keywords: Target SEO keywords.

        Returns:
            ReviewResult with scores and feedback.
        """
        logger.info("Starting article review")

        prompt = f"""あなたは経営管理・FP&Aコンテンツの品質審査官です。以下の記事を評価してください。

## 評価対象記事
{draft_content}

## ターゲット読者
{target_persona}

## ターゲットSEOキーワード
{seo_keywords}

## 評価基準

### 1. ターゲット訴求力（30点満点）
- ペルソナの課題・悩みに直接言及しているか
- 共感を得られる表現・具体例があるか
- 読者が「自分のことだ」と感じられるか

### 2. 論理構成（40点満点）
- 導入→本論→結論の流れが明確か
- 主張と根拠が対応しているか
- 各セクションのつながりが自然か
- 「今週の一手」など実践的なアクションがあるか

### 3. SEO適合性（30点満点）
- キーワードが適切に配置されているか（タイトル、見出し、本文）
- 見出し構成が競合に勝てる内容か
- メタ的な情報（文字数、構成）が適切か

## 出力形式（JSON）
{{
  "target_appeal": {{
    "score": [0-30の整数],
    "evaluation": "[評価コメント]",
    "improvements": ["改善点1", "改善点2"]
  }},
  "logical_structure": {{
    "score": [0-40の整数],
    "evaluation": "[評価コメント]",
    "improvements": ["改善点1", "改善点2"]
  }},
  "seo_fitness": {{
    "score": [0-30の整数],
    "evaluation": "[評価コメント]",
    "improvements": ["改善点1", "改善点2"]
  }},
  "overall_feedback": "[総合フィードバック]",
  "strengths": ["強み1", "強み2"],
  "priority_improvements": ["最優先改善点1", "最優先改善点2"]
}}

JSONのみを出力してください。
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        content = response.content[0].text

        # Parse JSON response
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]

            result = json.loads(json_str.strip())

            breakdown = ScoreBreakdown(
                target_appeal=result.get("target_appeal", {}).get("score", 0),
                logical_structure=result.get("logical_structure", {}).get("score", 0),
                seo_fitness=result.get("seo_fitness", {}).get("score", 0),
            )

            total_score = (
                breakdown.target_appeal
                + breakdown.logical_structure
                + breakdown.seo_fitness
            )

            # Build feedback text
            feedback_parts = [
                f"## 総合スコア: {total_score}/100点",
                "",
                f"### ターゲット訴求力: {breakdown.target_appeal}/30点",
                result.get("target_appeal", {}).get("evaluation", ""),
                "",
                f"### 論理構成: {breakdown.logical_structure}/40点",
                result.get("logical_structure", {}).get("evaluation", ""),
                "",
                f"### SEO適合性: {breakdown.seo_fitness}/30点",
                result.get("seo_fitness", {}).get("evaluation", ""),
                "",
                "## 総合フィードバック",
                result.get("overall_feedback", ""),
                "",
                "## 強み",
            ]

            for strength in result.get("strengths", []):
                feedback_parts.append(f"- {strength}")

            feedback_parts.extend(["", "## 優先改善点"])
            for improvement in result.get("priority_improvements", []):
                feedback_parts.append(f"- {improvement}")

            feedback = "\n".join(feedback_parts)

            return ReviewResult(
                score=total_score,
                breakdown=breakdown,
                feedback=feedback,
                passed=total_score >= self.PASS_THRESHOLD,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse review response: {e}")
            # Return a default result
            return ReviewResult(
                score=0,
                breakdown=ScoreBreakdown(),
                feedback=f"レビューの解析に失敗しました。\n\n生の出力:\n{content}",
                passed=False,
            )

    def quick_check(self, draft_content: str) -> dict:
        """
        Perform a quick quality check without full scoring.

        Args:
            draft_content: The draft article content.

        Returns:
            Dictionary with quick check results.
        """
        # Basic metrics
        word_count = len(draft_content)
        heading_count = draft_content.count("##")
        has_action_item = any(
            phrase in draft_content
            for phrase in ["今週の一手", "アクション", "実践", "やってみよう", "チェック"]
        )

        issues = []

        if word_count < 2500:
            issues.append(f"文字数が少ない可能性があります（{word_count}文字）")
        elif word_count > 5000:
            issues.append(f"文字数が多い可能性があります（{word_count}文字）")

        if heading_count < 3:
            issues.append("見出しが少ない可能性があります")

        if not has_action_item:
            issues.append("具体的なアクション項目がない可能性があります")

        return {
            "word_count": word_count,
            "heading_count": heading_count,
            "has_action_item": has_action_item,
            "issues": issues,
            "quick_pass": len(issues) == 0,
        }
