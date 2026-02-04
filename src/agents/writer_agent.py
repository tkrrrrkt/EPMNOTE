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
    image_suggestions: list[dict] = field(default_factory=list)  # From Unsplash/Pexels
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
        competitor_keywords: list[dict] | None = None,
        internal_references: list[str] | None = None,
    ) -> DraftResult:
        """
        Generate article draft based on research and user essences.

        Args:
            research_result: Research analysis results.
            essences: User-provided essence snippets.
            target_persona: Target reader persona.
            article_title: Base article title.
            competitor_keywords: Competitor keywords from research phase (optional).
            internal_references: RAG knowledge base content for context (optional).

        Returns:
            Complete draft result with content, titles, and SNS posts.
        """
        logger.info(f"Generating draft for: {article_title}")

        # Step 1: Generate main content
        content = self._generate_content(
            research_result, essences, target_persona, article_title,
            competitor_keywords, internal_references
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

        # Step 3.5: Search images for prompts (auto-integration)
        image_suggestions = self.search_images_for_prompts(image_prompts)

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
            image_suggestions=image_suggestions,
            sns_posts=sns_posts,
        )

    def _generate_content(
        self,
        research_result: ResearchResult,
        essences: list[dict],
        target_persona: str,
        article_title: str,
        competitor_keywords: list[dict] | None = None,
        internal_references: list[str] | None = None,
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

        # Format competitor keywords
        competitor_kw_text = ""
        if competitor_keywords:
            kw_lines = []
            for kw in competitor_keywords:
                priority = kw.get("priority", "検討")
                keyword = kw.get("keyword", "")
                usage_rate = kw.get("usage_rate", 0)
                kw_lines.append(f"- 【{priority}】{keyword}（使用率: {usage_rate:.0f}%）")
            competitor_kw_text = "\n".join(kw_lines)

        # Format internal references (RAG knowledge base content)
        internal_refs_text = ""
        if internal_references:
            # Limit to top 3 most relevant references, truncate each to 500 chars
            refs_to_use = internal_references[:3]
            formatted_refs = []
            for i, ref in enumerate(refs_to_use, 1):
                truncated = ref[:500] + "..." if len(ref) > 500 else ref
                formatted_refs.append(f"【参考{i}】{truncated}")
            internal_refs_text = "\n\n".join(formatted_refs)

        prompt = f"""あなたは経営管理・FP&Aの専門家として、Note.com向けの**高品質な記事**を執筆します。
有名SaaS企業のオウンドメディア記事のように、読者に価値を届ける構成で書いてください。

## 記事タイトル
{article_title}

## ターゲット読者
{target_persona}

## 推奨構成（参考）
{outline_text}

## 差別化ポイント
{chr(10).join(f"- {gap}" for gap in research_result.competitor_analysis.content_gaps[:3])}

## 競合キーワード（上位記事で頻出）
{competitor_kw_text if competitor_kw_text else "（なし）"}

※「必須」のキーワードは見出しや本文に自然に含めてください。SEOで上位表示を狙うために重要です。

## 参考資料（ナレッジベース）
{internal_refs_text if internal_refs_text else "（なし）"}

※上記の参考資料は直接引用する必要はありません。考え方・フレームワーク・視点を記事に反映させてください。
名著や専門家の知見がある場合は、その考え方を踏まえた論述にしてください。

## 著者のエッセンス（必ず記事に反映）
{essence_text if essence_text else "（なし）"}

## ★必須の記事構造（この順序で必ず含めること）

### 1. タイトル
- 検索クエリ + 読者の痛み + 解決の方向性を含める
- 30-50文字、数字や具体性を入れる

### 2. 冒頭「会議の一言」（必須）
- 「〇〇〇〇？」という会議での発言から始める
- 読者が「うちでも言われたことある」と共感するシーン描写
- 3〜4行で症状を具体的に列挙

### 3. 結論3行（必須）
- 「**結論から言います。**」で始める
- 1行目：主張（〇〇は△△ではない/△△である）
- 2行目：原因は3つの構造に集約
- 3行目：この記事で得られること

### 4. 目次（必須）
以下の形式で目次を記載：
```
## 目次
1. [見出し1のタイトル]
2. [見出し2のタイトル]
3. [見出し3のタイトル]
...
```

### 5. 一枚絵（テキスト図解）（必須）
- 記事の核心を1つの図で可視化
- テキストベースの図解（罫線文字使用）
- 図の下に「現場で起きていること」を添える
- 例：
```
┌─────────────────────────────────────────────┐
│   [メインコンセプト]                         │
│     ＝ [要素1] × [要素2] × [要素3]           │
│                                             │
│   ┌───────┐ ┌───────┐ ┌───────┐            │
│   │要素1  │ │要素2  │ │要素3  │            │
│   └───────┘ └───────┘ └───────┘            │
└─────────────────────────────────────────────┘
```

### 6. 原因/問題（3つに分解）（必須）
- 必ず3つに構造化
- 各原因は同じ構造で書く：問いかけ → 具体例3つ → 「これが〇〇の状態」で締め
- 見出しにキーワードを含める

### 7. 打ち手/解決策（ロードマップ）（必須）
- 期間を明示（例：90日、Week 1〜2など）
- 最小限から始める提案
- 各ステップに成果物を置く（定義書、カレンダー、マップなど）
- 表やリストで視覚的に整理

### 8. アンチパターン（失敗しがちな落とし穴）（必須）
- よくある失敗を2〜3個紹介
- 「失敗①：〜」「→ 対策：〜」の形式
- 経験者しか書けない現場の知見を入れる

### 9. 情シス/DXの方へ（固定コーナー）（必須）
- 1段落で完結
- 主読者（経営企画/FP&A）を崩さず、副読者を拾う
- 例：「情シス/DXの方にお願いしたいのは、○○することです。」

### 10. チェックリスト（今日の持ち帰り）（必須）
- 「## 今日の持ち帰り：[テーマ]セルフチェック」
- 5〜7項目のチェックボックス形式
- 最後に「3つ以上チェックが付かなければ、まず○○から始めてください」

### 11. 次に読む（関連記事リンク2本）（必須）
- 設計図方向（深掘り）の記事1本
- テンプレ方向（成果物）の記事1本
- まだない場合は「（準備中）」でOK
- 例：
```
## 次に読む
**設計をもっと深く知りたい方へ：**
→ 「○○○○」完全ガイド（準備中）

**テンプレートが欲しい方へ：**
→ ○○テンプレート【コピペで使える】（準備中）
```

### 12. 控えめCTA（最後に1行）（必須）
- 区切り線（---）の後に1行
- 「○○を壁打ちしたい方は、プロフィールのリンクからどうぞ。」
- 売り込み臭を出さない

## 執筆ガイドライン
1. 専門用語は必ず解説を添える
2. 具体例・数字・ケーススタディを多用
3. Markdown形式で見出し（##, ###）を適切に使用
4. 段落は2〜4行で区切る（スマホ対応）
5. 太字は1ブロック1〜2個まで
6. 文字数は{self.TARGET_WORDS_MIN}-{self.TARGET_WORDS_MAX}文字程度
7. 表記は「SSoT」に統一

## 出力
上記の必須構造を全て含むMarkdown形式の記事本文を出力してください。
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

## 必須構造（不足があれば追加）
以下の要素が全て含まれているか確認し、不足があれば追加してください：
1. 冒頭「会議の一言」（共感フック）
2. 結論3行（「**結論から言います。**」で始まる）
3. 目次（## 目次 セクション）
4. 一枚絵（テキスト図解）
5. 原因/問題 3つ（構造化）
6. 打ち手/解決策（期間付きロードマップ）
7. アンチパターン（失敗①、失敗②...）
8. 情シス/DXの方へ（固定1段落）
9. チェックリスト（- [ ] 形式、5〜7項目）
10. 次に読む（関連記事2本）
11. 控えめCTA（区切り線後に1行）

## 改善ガイドライン
1. スコアが低い項目を重点的に改善
2. フィードバックの具体的な指摘に対応
3. 冗長な表現を削り、読みやすさを改善（10-15%程度の圧縮を目安）
4. 段落は2〜4行で区切る（スマホ対応）
5. 文字数は{self.TARGET_WORDS_MIN}-{self.TARGET_WORDS_MAX}文字を維持
6. Markdown形式を維持
7. 表記は「SSoT」に統一

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
        """Refine content: compress, ensure structure, and polish."""
        prompt = f"""あなたはNote記事の編集者です。以下のMarkdown記事を最終チェック・改善してください。

## 必須構造チェック（不足があれば追加）
以下の要素が全て含まれているか確認し、不足があれば追加してください：

1. ✅ 冒頭「会議の一言」（「〇〇〇〇？」から始まる共感フック）
2. ✅ 結論3行（「**結論から言います。**」で始まる）
3. ✅ 目次（## 目次 セクション）
4. ✅ 一枚絵（テキスト図解、罫線文字使用）
5. ✅ 原因/問題 3つ（構造化された説明）
6. ✅ 打ち手/解決策（期間付きロードマップ）
7. ✅ アンチパターン（失敗①、失敗②...の形式）
8. ✅ 情シス/DXの方へ（1段落の固定コーナー）
9. ✅ チェックリスト（- [ ] 形式、5〜7項目）
10. ✅ 次に読む（関連記事2本、準備中でもOK）
11. ✅ 控えめCTA（区切り線後に1行）

## 編集指針
1. 冗長な表現や重複を削り、読みやすくする（10-15%程度の圧縮を目安）
2. 段落は2〜4行で区切る（スマホ対応）
3. 太字は1ブロック1〜2個まで
4. 表記は「SSoT」に統一
5. 文字数は{self.TARGET_WORDS_MIN}-{self.TARGET_WORDS_MAX}文字程度を維持

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

    def search_images_for_prompts(
        self,
        image_prompts: list[str],
        images_per_prompt: int = 3,
    ) -> list[dict]:
        """
        Search images for generated image prompts using Unsplash/Pexels APIs.

        Args:
            image_prompts: List of image prompts generated by _generate_image_prompts.
            images_per_prompt: Number of images to fetch per prompt.

        Returns:
            List of image search results as dictionaries.
        """
        try:
            from src.services.image_service import ImageService
        except ImportError:
            logger.warning("ImageService not available")
            return []

        service = ImageService()
        if not service.is_available():
            logger.info("No image API configured, skipping image search")
            return []

        results = service.search_for_prompts(image_prompts, images_per_prompt)
        return [r.to_dict() for r in results]

    # ===========================================
    # SEO Enhancement Methods (v1.2)
    # ===========================================

    def generate_meta_description(self, title: str, content: str) -> str:
        """
        Generate SEO-optimized meta description.

        Args:
            title: Article title.
            content: Article content in markdown.

        Returns:
            Meta description (120-160 characters).
        """
        if not self.client:
            return ""

        prompt = f"""以下の記事のSEOメタディスクリプションを生成してください。

## 記事タイトル
{title}

## 記事冒頭（500文字）
{content[:500]}

## 要件
- 120-160文字（日本語）
- 記事の価値を端的に伝える
- 読者が「読みたい」と思える訴求
- キーワードを自然に含める
- 「この記事では〜」のような冗長な表現は避ける

## 出力
メタディスクリプションのみを出力してください（説明不要）。
"""

        try:
            response = self.client.messages.create(
                model="claude-haiku-3-5-20241022",  # Use Haiku for cost efficiency
                max_tokens=200,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )
            description = response.content[0].text.strip()
            # Ensure length constraint
            if len(description) > 160:
                description = description[:157] + "..."
            return description
        except Exception as e:
            logger.warning(f"Meta description generation failed: {e}")
            return ""

    def generate_faq_schema(self, content: str) -> dict:
        """
        Generate FAQ JSON-LD schema from article content.

        Extracts question-answer pairs from the content structure.

        Args:
            content: Article content in markdown.

        Returns:
            JSON-LD FAQ schema dictionary.
        """
        if not self.client:
            return {}

        prompt = f"""以下の記事からFAQ（よくある質問）を3-5個抽出してJSON-LDスキーマを生成してください。

## 記事内容
{content[:3000]}

## 抽出ガイドライン
- 記事の見出しや内容から「読者が疑問に思うこと」を抽出
- 「〇〇とは？」「なぜ〇〇？」「どうすれば〇〇？」形式
- 回答は記事内容に基づき、50-150文字程度で簡潔に

## 出力形式（JSON）
```json
{{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {{
      "@type": "Question",
      "name": "質問文",
      "acceptedAnswer": {{
        "@type": "Answer",
        "text": "回答文"
      }}
    }}
  ]
}}
```

JSONのみを出力してください。
"""

        try:
            response = self.client.messages.create(
                model="claude-haiku-3-5-20241022",
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )

            text = response.content[0].text
            # Extract JSON from response
            import json
            json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            else:
                # Try parsing the entire response as JSON
                return json.loads(text)
        except Exception as e:
            logger.warning(f"FAQ schema generation failed: {e}")
            return {}

    def generate_cta_variants(self, persona: str, article_title: str) -> dict:
        """
        Generate personalized CTA variants based on persona.

        Args:
            persona: Target persona description.
            article_title: Article title for context.

        Returns:
            Dictionary of CTA variants by type.
        """
        if not self.client:
            return {}

        prompt = f"""以下のペルソナと記事に合わせた3種類のCTA（行動喚起）を作成してください。

## ターゲットペルソナ
{persona}

## 記事タイトル
{article_title}

## CTA種類と要件
1. **相談型**（経営層向け）: 課題相談・壁打ちを促す
   - 例：「○○の課題を相談したい方は、プロフィールからお気軽にどうぞ」
2. **資料型**（担当者向け）: テンプレート・チェックリストの提供
   - 例：「○○チェックリストは、プロフィールのリンクからダウンロードできます」
3. **事例型**（検討者向け）: 事例・実績の紹介
   - 例：「他社の○○事例を知りたい方は、プロフィールをご覧ください」

## ガイドライン
- 各CTA 1-2行、50文字以内
- 売り込み感を抑え、価値提供型に
- 「プロフィール」「リンク」への誘導を含める

## 出力形式（JSON）
```json
{{
  "consultation": "相談型CTAテキスト",
  "download": "資料型CTAテキスト",
  "case_study": "事例型CTAテキスト"
}}
```
"""

        try:
            response = self.client.messages.create(
                model="claude-haiku-3-5-20241022",
                max_tokens=300,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )

            text = response.content[0].text
            import json
            json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
            else:
                return json.loads(text)
        except Exception as e:
            logger.warning(f"CTA variants generation failed: {e}")
            return {}

    def score_titles(self, titles: list[str], seo_keywords: list[str]) -> list[dict]:
        """
        Score title candidates for CTR prediction.

        Uses heuristic rules to predict click-through rate potential.

        Args:
            titles: List of title candidates.
            seo_keywords: Target SEO keywords.

        Returns:
            List of titles with scores and breakdown.
        """
        scored_titles = []

        # Power words that boost CTR
        power_words = [
            "秘訣", "落とし穴", "完全ガイド", "入門", "実践",
            "解決", "改善", "成功", "失敗", "なぜ", "理由",
            "方法", "ステップ", "選", "つの", "徹底",
        ]

        for title in titles:
            score = 50  # Base score
            breakdown = {}

            # Length score (30-45 chars optimal)
            length = len(title)
            if 30 <= length <= 45:
                length_score = 15
            elif 25 <= length <= 50:
                length_score = 10
            else:
                length_score = 5
            score += length_score
            breakdown["length"] = length_score

            # Number presence
            has_number = bool(re.search(r"\d", title))
            number_score = 10 if has_number else 0
            score += number_score
            breakdown["number"] = number_score

            # Question format
            is_question = "？" in title or title.endswith("?")
            question_score = 5 if is_question else 0
            score += question_score
            breakdown["question"] = question_score

            # Power words
            power_count = sum(1 for pw in power_words if pw in title)
            power_score = min(power_count * 3, 10)
            score += power_score
            breakdown["power_words"] = power_score

            # Keyword presence at start
            keyword_at_start = any(
                title.startswith(kw) or title[:10].find(kw) >= 0
                for kw in seo_keywords if kw
            )
            keyword_score = 10 if keyword_at_start else 0
            score += keyword_score
            breakdown["keyword_position"] = keyword_score

            scored_titles.append({
                "title": title,
                "score": min(score, 100),
                "breakdown": breakdown,
            })

        # Sort by score descending
        scored_titles.sort(key=lambda x: x["score"], reverse=True)
        return scored_titles
