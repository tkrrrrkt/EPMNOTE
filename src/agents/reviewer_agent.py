"""
EPM Note Engine - Reviewer Agent

Evaluates article quality using a structured scoring rubric.
Includes validation of the 11 mandatory article structure elements.
"""

import json
import logging
import re
from dataclasses import dataclass, field

from src.config import get_anthropic_client

logger = logging.getLogger(__name__)


# 11 mandatory structure elements with detection patterns
STRUCTURE_ELEMENTS = {
    "hook": {
        "name": "会議の一言（冒頭フック）",
        "pattern": r"「[^」]+？」",
        "description": "「〇〇〇〇？」という会議での発言から始まる共感フック",
    },
    "conclusion": {
        "name": "結論3行",
        "pattern": r"\*\*結論から言います",
        "description": "「**結論から言います。**」で始まる結論",
    },
    "toc": {
        "name": "目次",
        "pattern": r"##\s*目次",
        "description": "## 目次 セクション",
    },
    "diagram": {
        "name": "一枚絵（テキスト図解）",
        "pattern": r"[┌└│─┐┘├┤┬┴┼]",
        "description": "罫線文字を使ったテキスト図解",
    },
    "causes": {
        "name": "原因/問題（3つ構造）",
        "pattern": r"(原因[①②③1-3]|問題[①②③1-3]|##.*原因.*[①②③1-3])",
        "description": "3つに構造化された原因/問題の説明",
    },
    "roadmap": {
        "name": "打ち手/ロードマップ",
        "pattern": r"(Week\s*\d|Month\s*\d|\d+日|ロードマップ|ステップ[①②③1-3])",
        "description": "期間を明示した解決策のロードマップ",
    },
    "antipattern": {
        "name": "アンチパターン",
        "pattern": r"(失敗[①②③1-3]|アンチパターン|よくある失敗|落とし穴)",
        "description": "失敗パターンの紹介",
    },
    "it_corner": {
        "name": "情シス/DXコーナー",
        "pattern": r"(情シス|DX|IT).*方へ|##.*情シス|##.*DX",
        "description": "情シス/DX向けの固定コーナー",
    },
    "checklist": {
        "name": "チェックリスト",
        "pattern": r"-\s*\[\s*[\sx]\s*\]|今日の持ち帰り|セルフチェック",
        "description": "チェックボックス形式のリスト",
    },
    "related": {
        "name": "次に読む",
        "pattern": r"(次に読む|関連記事|準備中|もっと深く|テンプレート.*欲しい)",
        "description": "関連記事へのリンク",
    },
    "cta": {
        "name": "控えめCTA",
        "pattern": r"(プロフィール.*リンク|壁打ち.*相談|お気軽に)",
        "description": "控えめなCTA（1行）",
    },
}


@dataclass
class StructureCheckResult:
    """Result of structure element check."""

    element_name: str
    found: bool
    description: str


@dataclass
class ScoreBreakdown:
    """Score breakdown by evaluation criteria."""

    target_appeal: int = 0  # 0-25: ターゲット訴求力
    logical_structure: int = 0  # 0-30: 論理構成
    seo_fitness: int = 0  # 0-25: SEO適合性
    article_structure: int = 0  # 0-20: 記事構造（11要素）


@dataclass
class ReviewResult:
    """Complete review result."""

    score: int = 0  # 0-100: Total score
    breakdown: ScoreBreakdown = None
    feedback: str = ""
    passed: bool = False  # score >= 80
    structure_checks: list = field(default_factory=list)  # Structure check results
    missing_elements: list = field(default_factory=list)  # Missing structure elements

    def __post_init__(self):
        if self.breakdown is None:
            self.breakdown = ScoreBreakdown()
        self.passed = self.score >= 80


class ReviewerAgent:
    """
    Agent for reviewing and scoring article quality.

    Uses a structured rubric:
    - Target Appeal (25 points): How well the article addresses the target persona
    - Logical Structure (30 points): Flow, coherence, and argumentation
    - SEO Fitness (25 points): Keyword usage and competitive positioning
    - Article Structure (20 points): Presence of 11 mandatory elements
    """

    PASS_THRESHOLD = 80

    def __init__(self) -> None:
        """Initialize the reviewer agent."""
        self.client = get_anthropic_client()

    def check_structure(self, content: str) -> tuple[list[StructureCheckResult], list[str]]:
        """
        Programmatically check for the 11 mandatory structure elements.

        Args:
            content: Article content in Markdown.

        Returns:
            Tuple of (all check results, list of missing element names).
        """
        results = []
        missing = []

        for key, element in STRUCTURE_ELEMENTS.items():
            pattern = element["pattern"]
            found = bool(re.search(pattern, content, re.IGNORECASE | re.MULTILINE))

            results.append(StructureCheckResult(
                element_name=element["name"],
                found=found,
                description=element["description"],
            ))

            if not found:
                missing.append(element["name"])

        return results, missing

    def calculate_structure_score(self, missing_count: int) -> int:
        """
        Calculate structure score based on missing elements.

        Args:
            missing_count: Number of missing structure elements.

        Returns:
            Score out of 20.
        """
        # 11 elements total, each worth ~1.8 points
        # Full score (20) if all present, deduct ~1.8 per missing
        total_elements = len(STRUCTURE_ELEMENTS)
        found_count = total_elements - missing_count
        return int((found_count / total_elements) * 20)

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

        # Step 1: Programmatic structure check
        structure_checks, missing_elements = self.check_structure(draft_content)
        structure_score = self.calculate_structure_score(len(missing_elements))

        # Step 2: Quantitative SEO analysis
        quantitative_seo_score = 50.0  # Default
        seo_analysis = None
        try:
            from src.agents.research_agent import ResearchAgent
            research_agent = ResearchAgent()
            keywords = [kw.strip() for kw in seo_keywords.split(",") if kw.strip()]
            if keywords:
                seo_analysis = research_agent.analyze_keyword_density(draft_content, keywords)
                quantitative_seo_score = seo_analysis.overall_seo_score
                logger.info(f"Quantitative SEO score: {quantitative_seo_score:.0f}/100")
        except Exception as e:
            logger.warning(f"SEO analysis in review failed (non-critical): {e}")

        # Format SEO metrics for prompt
        seo_metrics_info = ""
        if seo_analysis and seo_analysis.primary_keyword:
            pk = seo_analysis.primary_keyword
            positions_str = ", ".join(pk.positions) if pk.positions else "なし"
            suggestions_str = "\n".join(f"  - {s}" for s in seo_analysis.suggestions[:3])
            seo_metrics_info = f"""
## 定量的SEO分析結果（参考）
- 主要キーワード: {pk.keyword}
- 出現回数: {pk.count}回
- キーワード密度: {pk.density:.2f}%
- 配置位置: {positions_str}
- 定量スコア: {quantitative_seo_score:.0f}/100
- 改善提案:
{suggestions_str}

上記の定量分析を参考にSEO適合性を評価してください。
"""

        # Format missing elements for prompt
        missing_info = ""
        if missing_elements:
            missing_info = f"""
## ⚠️ 構造チェック結果（プログラム検出）
以下の必須要素が検出されませんでした：
{chr(10).join(f"- {elem}" for elem in missing_elements)}

この情報を考慮して評価してください。
"""

        prompt = f"""あなたは経営管理・FP&Aコンテンツの品質審査官です。以下の記事を評価してください。

## 評価対象記事
{draft_content}

## ターゲット読者
{target_persona}

## ターゲットSEOキーワード
{seo_keywords}
{seo_metrics_info}{missing_info}
## 評価基準（4カテゴリ・100点満点）

### 1. ターゲット訴求力（25点満点）
- ペルソナの課題・悩みに直接言及しているか
- 「会議の一言」で共感を得られるか
- 読者が「自分のことだ」と感じられるか
- 情シス/DXコーナーで副読者も拾えているか

### 2. 論理構成（30点満点）
- 冒頭→結論3行→本論の流れが明確か
- 原因/問題が3つに構造化されているか
- 打ち手/ロードマップが期間付きで具体的か
- 各セクションのつながりが自然か

### 3. SEO適合性（25点満点）
- キーワードが適切に配置されているか（タイトル、見出し、本文）
- 見出し構成が競合に勝てる内容か
- チェックリスト/次に読むで読者の行動を促しているか
- 控えめCTAが適切か

### 4. 記事構造（20点満点）※プログラム検出スコア: {structure_score}/20
以下の11必須要素の品質を評価：
1. 会議の一言（共感フック）
2. 結論3行
3. 目次
4. 一枚絵（テキスト図解）
5. 原因/問題 3つ
6. 打ち手/ロードマップ
7. アンチパターン
8. 情シス/DXコーナー
9. チェックリスト
10. 次に読む
11. 控えめCTA

## 出力形式（JSON）
{{
  "target_appeal": {{
    "score": [0-25の整数],
    "evaluation": "[評価コメント]",
    "improvements": ["改善点1", "改善点2"]
  }},
  "logical_structure": {{
    "score": [0-30の整数],
    "evaluation": "[評価コメント]",
    "improvements": ["改善点1", "改善点2"]
  }},
  "seo_fitness": {{
    "score": [0-25の整数],
    "evaluation": "[評価コメント]",
    "improvements": ["改善点1", "改善点2"]
  }},
  "article_structure": {{
    "score": [0-20の整数],
    "evaluation": "[評価コメント]",
    "missing_elements": ["不足要素1", "不足要素2"],
    "quality_issues": ["品質問題1", "品質問題2"]
  }},
  "overall_feedback": "[総合フィードバック]",
  "strengths": ["強み1", "強み2"],
  "priority_improvements": ["最優先改善点1", "最優先改善点2"]
}}

JSONのみを出力してください。
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
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

            # Use programmatic structure score as base, AI can adjust within range
            ai_structure_score = result.get("article_structure", {}).get("score", 0)
            # Blend programmatic and AI scores (60% programmatic, 40% AI)
            final_structure_score = int(structure_score * 0.6 + ai_structure_score * 0.4)

            # Blend AI SEO score with quantitative score (60% AI, 40% quantitative)
            ai_seo_score = result.get("seo_fitness", {}).get("score", 0)
            # Convert quantitative score (0-100) to 25-point scale
            quantitative_seo_component = (quantitative_seo_score / 100) * 25
            final_seo_score = int(ai_seo_score * 0.6 + quantitative_seo_component * 0.4)
            logger.info(f"SEO score blend: AI={ai_seo_score}, Quant={quantitative_seo_component:.1f}, Final={final_seo_score}")

            breakdown = ScoreBreakdown(
                target_appeal=result.get("target_appeal", {}).get("score", 0),
                logical_structure=result.get("logical_structure", {}).get("score", 0),
                seo_fitness=final_seo_score,
                article_structure=final_structure_score,
            )

            total_score = (
                breakdown.target_appeal
                + breakdown.logical_structure
                + breakdown.seo_fitness
                + breakdown.article_structure
            )

            # Build feedback text
            feedback_parts = [
                f"## 総合スコア: {total_score}/100点",
                f"合格ライン: {self.PASS_THRESHOLD}点",
                "",
                f"### ターゲット訴求力: {breakdown.target_appeal}/25点",
                result.get("target_appeal", {}).get("evaluation", ""),
                "",
                f"### 論理構成: {breakdown.logical_structure}/30点",
                result.get("logical_structure", {}).get("evaluation", ""),
                "",
                f"### SEO適合性: {breakdown.seo_fitness}/25点",
                result.get("seo_fitness", {}).get("evaluation", ""),
                "",
                f"### 記事構造: {breakdown.article_structure}/20点",
                result.get("article_structure", {}).get("evaluation", ""),
            ]

            # Add missing elements warning
            if missing_elements:
                feedback_parts.extend([
                    "",
                    "#### ⚠️ 検出されなかった必須要素:",
                ])
                for elem in missing_elements:
                    feedback_parts.append(f"- {elem}")

            # Add quality issues if any
            quality_issues = result.get("article_structure", {}).get("quality_issues", [])
            if quality_issues:
                feedback_parts.extend([
                    "",
                    "#### 構造の品質問題:",
                ])
                for issue in quality_issues:
                    feedback_parts.append(f"- {issue}")

            feedback_parts.extend([
                "",
                "## 総合フィードバック",
                result.get("overall_feedback", ""),
                "",
                "## 強み",
            ])

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
                structure_checks=structure_checks,
                missing_elements=missing_elements,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse review response: {e}")
            # Return a default result with structure checks
            return ReviewResult(
                score=0,
                breakdown=ScoreBreakdown(),
                feedback=f"レビューの解析に失敗しました。\n\n生の出力:\n{content}",
                passed=False,
                structure_checks=structure_checks,
                missing_elements=missing_elements,
            )

    def quick_check(self, draft_content: str) -> dict:
        """
        Perform a quick quality check without full scoring.
        Includes programmatic structure element detection.

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

        # Structure check
        structure_checks, missing_elements = self.check_structure(draft_content)
        structure_score = self.calculate_structure_score(len(missing_elements))
        found_count = len(STRUCTURE_ELEMENTS) - len(missing_elements)

        issues = []

        if word_count < 2500:
            issues.append(f"文字数が少ない可能性があります（{word_count}文字）")
        elif word_count > 5000:
            issues.append(f"文字数が多い可能性があります（{word_count}文字）")

        if heading_count < 5:
            issues.append(f"見出しが少ない可能性があります（{heading_count}個）")

        if not has_action_item:
            issues.append("具体的なアクション項目がない可能性があります")

        # Structure issues
        if len(missing_elements) > 3:
            issues.append(f"必須構造要素が不足しています（{found_count}/11検出）")
            for elem in missing_elements[:3]:  # Show first 3
                issues.append(f"  - {elem}")
            if len(missing_elements) > 3:
                issues.append(f"  - 他{len(missing_elements) - 3}個...")

        return {
            "word_count": word_count,
            "heading_count": heading_count,
            "has_action_item": has_action_item,
            "structure_found": found_count,
            "structure_total": len(STRUCTURE_ELEMENTS),
            "structure_score": structure_score,
            "missing_elements": missing_elements,
            "issues": issues,
            "quick_pass": len(issues) == 0 and len(missing_elements) <= 2,
        }
