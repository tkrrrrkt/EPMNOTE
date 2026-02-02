"""
EPM Note Engine - Article Seed Script

Parses the article candidates markdown file and seeds the database.
Source: 91_RefDoc/02_生成AIとのやりとり履歴/05_記事候補.md
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.connection import get_session, init_db
from src.database.models import Article, ArticleStatus


@dataclass
class ParsedArticle:
    """Parsed article data from markdown."""

    article_number: int
    week_number: int
    day_type: str  # 火 or 金
    content_type: str  # モヤモヤ, 設計図, テンプレ
    title: str
    hook_statement: str | None
    conclusion: str | None
    content_outline: str | None
    visual_type: str | None
    deliverable: str | None
    related_articles: str | None


def parse_article_candidates(file_path: Path) -> list[ParsedArticle]:
    """
    Parse the article candidates markdown file.

    Args:
        file_path: Path to the 05_記事候補.md file.

    Returns:
        List of parsed article data.
    """
    content = file_path.read_text(encoding="utf-8")
    articles: list[ParsedArticle] = []

    # Track current week
    current_week = 0

    # Pattern for article header: ### N（火｜モヤモヤ）Title
    # or ### N（金｜設計図）Title
    article_pattern = re.compile(
        r"^###\s+(\d+)（([火金])｜([^）]+)）(.+)$",
        re.MULTILINE,
    )

    # Find all articles
    matches = list(article_pattern.finditer(content))

    for i, match in enumerate(matches):
        article_num = int(match.group(1))
        day_type = match.group(2)
        content_type = match.group(3)
        title = match.group(4).strip()

        # Calculate week number (2 articles per week)
        week_number = (article_num + 1) // 2

        # Get the content section for this article
        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section = content[start_pos:end_pos]

        # Parse individual fields
        hook = extract_field(section, "会議の一言")
        conclusion = extract_field(section, "結論3行")
        outline = extract_field(section, "見出し案")
        visual = extract_field(section, "図/表")
        deliverable = extract_field(section, "持ち帰り")
        related = extract_field(section, "次に読む")

        articles.append(
            ParsedArticle(
                article_number=article_num,
                week_number=week_number,
                day_type=day_type,
                content_type=content_type,
                title=title,
                hook_statement=hook,
                conclusion=conclusion,
                content_outline=outline,
                visual_type=visual,
                deliverable=deliverable,
                related_articles=related,
            )
        )

    return articles


def extract_field(section: str, field_name: str) -> str | None:
    """
    Extract a field value from an article section.

    Args:
        section: The markdown section for one article.
        field_name: The field name to extract (e.g., "会議の一言").

    Returns:
        Extracted value or None.
    """
    # Pattern: - field_name：value or - field_name:value
    pattern = re.compile(
        rf"^-\s*{re.escape(field_name)}[：:](.+?)(?=^-|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(section)
    if match:
        value = match.group(1).strip()
        # Clean up markdown formatting
        value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)  # Remove bold
        value = re.sub(r"\s+", " ", value)  # Normalize whitespace
        return value.strip()
    return None


def infer_target_persona(content_type: str, title: str) -> str:
    """
    Infer target persona from content type and title.

    Args:
        content_type: Article content type (モヤモヤ, 設計図, テンプレ).
        title: Article title.

    Returns:
        Inferred target persona string.
    """
    # Keywords to persona mapping
    persona_keywords = {
        "予算": "経営企画, CFO",
        "KPI": "経営企画, 事業部長",
        "差異分析": "FP&A, 経営企画",
        "配賦": "経理部長, CFO",
        "ROIC": "CFO, 経営企画",
        "DCF": "CFO, 経営企画",
        "人件費": "人事, 経営企画",
        "BI": "情報システム, 経営企画",
        "データ": "情報システム, FP&A",
        "システム": "CTO, 情報システム",
        "FP&A": "FP&A担当, CFO",
    }

    for keyword, persona in persona_keywords.items():
        if keyword in title:
            return persona

    # Default based on content type
    if content_type == "モヤモヤ":
        return "経営企画, 事業部長"
    elif content_type == "設計図":
        return "CFO, 経営企画"
    elif content_type == "テンプレ":
        return "FP&A担当, 経営企画"

    return "経営企画"


def seed_articles(dry_run: bool = False) -> int:
    """
    Seed articles from the markdown file into the database.

    Args:
        dry_run: If True, only print what would be inserted.

    Returns:
        Number of articles processed.
    """
    # Find the source file
    project_root = Path(__file__).parent.parent
    source_file = (
        project_root
        / "91_RefDoc"
        / "02_生成AIとのやりとり履歴"
        / "05_記事候補.md"
    )

    if not source_file.exists():
        print(f"Error: Source file not found: {source_file}")
        return 0

    print(f"Parsing: {source_file}")
    parsed_articles = parse_article_candidates(source_file)
    print(f"Found {len(parsed_articles)} articles")

    if dry_run:
        print("\n[DRY RUN] Would insert the following articles:")
        for pa in parsed_articles[:10]:  # Show first 10
            print(f"  - Week{pa.week_number}-{1 if pa.day_type == '火' else 2}: {pa.title}")
        if len(parsed_articles) > 10:
            print(f"  ... and {len(parsed_articles) - 10} more")
        return len(parsed_articles)

    # Initialize database
    print("\nInitializing database...")
    init_db()

    # Create Article objects
    with get_session() as session:
        from src.repositories.article_repository import ArticleRepository

        repo = ArticleRepository(session)

        # Check if articles already exist
        existing = repo.get_all()
        if existing:
            print(f"Database already contains {len(existing)} articles.")
            response = input("Clear and reseed? (y/N): ")
            if response.lower() != "y":
                print("Aborted.")
                return 0

            # Delete existing articles
            for article in existing:
                repo.delete(article.id)
            print("Cleared existing articles.")

        # Insert new articles
        articles_to_create = []
        for pa in parsed_articles:
            # Generate week_id: "Week1-1" for Tuesday, "Week1-2" for Friday
            day_suffix = 1 if pa.day_type == "火" else 2
            week_id = f"Week{pa.week_number}-{day_suffix}"

            article = Article(
                week_id=week_id,
                title=pa.title,
                target_persona=infer_target_persona(pa.content_type, pa.title),
                hook_statement=pa.hook_statement,
                content_outline=pa.content_outline,
                status=ArticleStatus.PLANNING,
                # Store additional metadata in outline_json
                outline_json={
                    "article_number": pa.article_number,
                    "day_type": pa.day_type,
                    "content_type": pa.content_type,
                    "conclusion": pa.conclusion,
                    "visual_type": pa.visual_type,
                    "deliverable": pa.deliverable,
                    "related_articles": pa.related_articles,
                },
            )
            articles_to_create.append(article)

        created = repo.bulk_create(articles_to_create)
        print(f"\nSuccessfully seeded {len(created)} articles!")

        # Print summary by week
        print("\nSummary by Week:")
        by_week: dict[int, list[str]] = {}
        for pa in parsed_articles:
            week = pa.week_number
            if week not in by_week:
                by_week[week] = []
            by_week[week].append(f"{pa.day_type}: {pa.title[:30]}...")

        for week in sorted(by_week.keys())[:5]:  # Show first 5 weeks
            print(f"  Week {week}:")
            for title in by_week[week]:
                print(f"    - {title}")

        return len(created)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed articles from markdown file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be inserted without actually inserting",
    )
    args = parser.parse_args()

    count = seed_articles(dry_run=args.dry_run)
    print(f"\nProcessed {count} articles.")
