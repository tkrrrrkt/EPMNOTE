"""
EPM Note Engine - Writer Agent

Generates article content using Claude 3.5 Sonnet.
"""

import logging
import re
from dataclasses import dataclass, field

from src.config import get_anthropic_client
from src.agents.research_agent import ResearchResult

logger = logging.getLogger(__name__)


@dataclass
class DraftResult:
    """Result of article draft generation."""

    draft_content_md: str = ""
    title_candidates: list[str] = field(default_factory=list)
    image_prompts: list[str] = field(default_factory=list)
    sns_posts: dict[str, str] = field(default_factory=dict)


class WriterAgent:
    """
    Agent for generating article content.

    Uses Claude 3.5 Sonnet for high-quality Japanese article generation.
    """

    # Target word count
    TARGET_WORDS_MIN = 3000
    TARGET_WORDS_MAX = 4500
    CANONICAL_SSoT = "SSoT"

    def __init__(self) -> None:
        """Initialize the writer agent."""
        self.client = get_anthropic_client()

    def generate_draft(
        self,
        research_result: ResearchResult,
        essences: list[dict],
        target_persona: str,
        article_title: str,
    ) -> DraftResult:
        """
        Generate article draft based on research and user essences.

        Args:
            research_result: Research analysis results.
            essences: User-provided essence snippets.
            target_persona: Target reader persona.
            article_title: Base article title.

        Returns:
            Complete draft result with content, titles, and SNS posts.
        """
        logger.info(f"Generating draft for: {article_title}")

        # Step 1: Generate main content
        content = self._generate_content(
            research_result, essences, target_persona, article_title
        )

        # Step 1.5: Refine content (compression + summaries + CTA)
        refined_content = self._refine_content(
            content=content,
            target_persona=target_persona,
            article_title=article_title,
        )
        refined_content = self._normalize_terms(refined_content)

        # Step 2: Generate title candidates
        titles = self._generate_titles(article_title, target_persona, refined_content[:500])
        titles = [self._normalize_terms(t) for t in titles]

        # Step 3: Generate image prompts
        image_prompts = self._generate_image_prompts(refined_content, research_result)
        image_prompts = [self._normalize_terms(p) for p in image_prompts]

        # Step 4: Generate SNS posts
        sns_posts = self._generate_sns_posts(
            titles[0] if titles else article_title,
            refined_content,
        )
        sns_posts = {k: self._normalize_terms(v) for k, v in sns_posts.items()}

        return DraftResult(
            draft_content_md=refined_content,
            title_candidates=titles,
            image_prompts=image_prompts,
            sns_posts=sns_posts,
        )

    def _generate_content(
        self,
        research_result: ResearchResult,
        essences: list[dict],
        target_persona: str,
        article_title: str,
    ) -> str:
        """Generate the main article content."""
        # Format essences for prompt
        essence_text = ""
        for e in essences:
            category = e.get("category", "")
            content = e.get("content", "")
            if isinstance(category, str):
                cat_label = category
            else:
                cat_label = category.value if hasattr(category, "value") else str(category)
            essence_text += f"【{cat_label}】{content}\n\n"

        # Format outline
        outline_text = "\n".join(
            f"- {h}" for h in research_result.suggested_outline
        )

        prompt = f"""あなたは経営管理・FP&Aの専門家として、Note向けの記事を執筆します。

## 記事タイトル
{article_title}

## ターゲット読者
{target_persona}

## 推奨構成
{outline_text}

## 差別化ポイント
{chr(10).join(f"- {gap}" for gap in research_result.competitor_analysis.content_gaps[:3])}

## 著者のエッセンス（必ず記事に反映）
{essence_text if essence_text else "（なし）"}

## 執筆ガイドライン
1. 読者の「あるある」から始める（共感→解決→実践の流れ）
2. 専門用語は必ず解説を添える
3. 具体例・数字・ケーススタディを多用
4. 「今週の一手」として実践可能なアクションを提示（CTAテンプレに沿う）
5. Markdown形式で見出し（##, ###）を適切に使用
6. 各見出し（##, ###）の直後に**1行の要約**を入れる（形式: **要点:** ...）
7. 文字数は{self.TARGET_WORDS_MIN}-{self.TARGET_WORDS_MAX}文字程度
8. 表記は「SSoT」に統一

## CTAテンプレ（本文末尾に1回だけ）
### 今週の一手
- [今週すぐやれる具体行動1]
- [今週すぐやれる具体行動2]
- [今週すぐやれる具体行動3]

#### CTA
「SSoTの整備を具体的に進めたい方は、無料の壁打ち相談やデモのご案内が可能です。必要ならお気軽にご相談ください。」

## 出力
Markdown形式で記事本文を出力してください。
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        return response.content[0].text

    def _generate_titles(
        self,
        base_title: str,
        target_persona: str,
        content_preview: str,
    ) -> list[str]:
        """Generate title candidates."""
        prompt = f"""以下の記事に対して、Note向けのタイトル候補を5つ提案してください。

## 元のタイトル
{base_title}

## ターゲット読者
{target_persona}

## 記事冒頭
{content_preview}

## タイトル作成ガイドライン
1. 30-50文字程度
2. 読者の課題・悩みに共感する表現
3. 解決策や得られるベネフィットを示唆
4. 数字や具体性を含める（可能な場合）
5. 【】や「」を効果的に使用

## 出力形式
1. タイトル案1
2. タイトル案2
3. タイトル案3
4. タイトル案4
5. タイトル案5
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        content = response.content[0].text
        titles = []
        for line in content.split("\n"):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                import re
                match = re.match(r"[\d\.\-\s]*(.+)", line)
                if match:
                    titles.append(match.group(1).strip())

        return titles[:5] if titles else [base_title]

    def _generate_image_prompts(
        self,
        content: str,
        research_result: ResearchResult,
    ) -> list[str]:
        """Generate prompts for image generation."""
        prompt = f"""以下の記事に挿入する図解のプロンプトを2-3個作成してください。

## 記事内容（抜粋）
{content[:1500]}

## 差別化ポイント
{chr(10).join(f"- {gap}" for gap in research_result.competitor_analysis.content_gaps[:2])}

## 出力形式
図解ごとに、以下の形式で出力してください：

### 図解1: [タイトル]
- 目的: [この図解で伝えたいこと]
- 形式: [フロー図/表/マトリクス/比較図など]
- 要素: [含める要素のリスト]

### 図解2: [タイトル]
...
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        content = response.content[0].text

        # Split by "### 図解" markers
        prompts = []
        current = []
        for line in content.split("\n"):
            if line.strip().startswith("### 図解"):
                if current:
                    prompts.append("\n".join(current))
                current = [line]
            elif current:
                current.append(line)

        if current:
            prompts.append("\n".join(current))

        return prompts[:3]

    def _generate_sns_posts(self, title: str, content: str) -> dict[str, str]:
        """Generate SNS post drafts."""
        prompt = f"""以下の記事に対して、SNS投稿文を作成してください。

## 記事タイトル
{title}

## 記事内容（抜粋）
{content[:800]}

## 出力形式

### X (Twitter) 投稿文（140文字以内）
[投稿文]

### LinkedIn 投稿文（300文字程度）
[投稿文]

※記事のリンクは含めないでください（後で追加します）
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        content = response.content[0].text

        # Parse X and LinkedIn posts
        x_post = ""
        linkedin_post = ""

        lines = content.split("\n")
        current_section = None

        for line in lines:
            if "X (Twitter)" in line or "Twitter" in line:
                current_section = "x"
            elif "LinkedIn" in line:
                current_section = "linkedin"
            elif line.strip() and not line.startswith("#"):
                if current_section == "x" and len(x_post) < 280:
                    x_post += line.strip() + " "
                elif current_section == "linkedin":
                    linkedin_post += line.strip() + "\n"

        return {
            "x": x_post.strip()[:280],
            "linkedin": linkedin_post.strip(),
        }

    def revise_draft(
        self,
        original_content: str,
        feedback: str,
        score_breakdown: dict,
    ) -> str:
        """
        Revise a draft based on reviewer feedback.

        Args:
            original_content: Original draft content.
            feedback: Reviewer feedback.
            score_breakdown: Score breakdown by category.

        Returns:
            Revised content.
        """
        prompt = f"""以下の記事を、レビューフィードバックに基づいて改善してください。

## 現在の記事
{original_content}

## レビュースコア
- ターゲット訴求力: {score_breakdown.get('target_appeal', 0)}/30
- 論理構成: {score_breakdown.get('logical_structure', 0)}/40
- SEO適合性: {score_breakdown.get('seo_fitness', 0)}/30

## フィードバック
{feedback}

## 改善ガイドライン
1. スコアが低い項目を重点的に改善
2. フィードバックの具体的な指摘に対応
3. 冗長な表現を削り、読みやすさを改善（全体で10-15%程度の圧縮を目安）
4. 各見出し（##, ###）の直後に**1行の要約**を入れる（形式: **要点:** ...）
5. 文字数は{self.TARGET_WORDS_MIN}-{self.TARGET_WORDS_MAX}文字を維持
6. Markdown形式を維持
7. 表記は「SSoT」に統一

## CTAテンプレ（本文末尾に1回だけ）
### 今週の一手
- [今週すぐやれる具体行動1]
- [今週すぐやれる具体行動2]
- [今週すぐやれる具体行動3]

#### CTA
「SSoTの整備を具体的に進めたい方は、無料の壁打ち相談やデモのご案内が可能です。必要ならお気軽にご相談ください。」

## 出力
改善後の記事本文をMarkdown形式で出力してください。
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        revised = response.content[0].text
        refined = self._refine_content(
            content=revised,
            target_persona="",
            article_title="",
        )
        return self._normalize_terms(refined)

    def _normalize_terms(self, text: str) -> str:
        """Normalize term variants (SSOT/SSoT) to a single canonical form."""
        if not text:
            return text
        return re.sub(r"\bSSOT\b", self.CANONICAL_SSoT, text, flags=re.IGNORECASE)

    def _refine_content(self, content: str, target_persona: str, article_title: str) -> str:
        """Refine content: compress, add summaries, and inject CTA."""
        prompt = f"""あなたは編集者です。以下のMarkdown記事を改善してください。

## 目的
1. 冗長な表現や重複を削り、読みやすくする（10-15%程度の圧縮を目安）
2. 各見出し（##, ###）の直後に**1行の要約**を追加（形式: **要点:** ...）
3. 本文末尾に「今週の一手」セクションとCTAを**1回だけ**入れる
4. 表記は「SSoT」に統一

## 注意
- 文字数は{self.TARGET_WORDS_MIN}-{self.TARGET_WORDS_MAX}文字程度を維持
- Markdown形式を維持
- 既に「今週の一手」がある場合はテンプレに合わせて内容を整理・統一する

## CTAテンプレ
### 今週の一手
- [今週すぐやれる具体行動1]
- [今週すぐやれる具体行動2]
- [今週すぐやれる具体行動3]

#### CTA
「SSoTの整備を具体的に進めたい方は、無料の壁打ち相談やデモのご案内が可能です。必要ならお気軽にご相談ください。」

## 記事本文
{content}

## 出力
改善後のMarkdown本文のみを出力してください。
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        return response.content[0].text
