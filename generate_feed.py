import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime, format_datetime

# ============================================================
# MJR MORNING BRIEF FEED GENERATOR
# ============================================================

SOURCE_FEED = "https://www.mediajobsreport.com/rss-image"

OUTPUT_FILE = "morning-brief.xml"

SITE_URL = "https://www.mediajobsreport.com"
FEED_TITLE = "Media Jobs Report Morning Brief"
FEED_DESCRIPTION = "Media industry news from Media Jobs Report"

# Number of items to include in the generated feed.
MAX_ITEMS = 20

# Image width used in the Mailchimp-ready excerpt.
IMAGE_WIDTH = 300


MEDIA_NS = "http://search.yahoo.com/mrss/"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
ATOM_NS = "http://www.w3.org/2005/Atom"

ET.register_namespace("media", MEDIA_NS)
ET.register_namespace("content", CONTENT_NS)
ET.register_namespace("atom", ATOM_NS)


def fetch_feed(url):
    """Download the source RSS feed."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; "
                "MJR-Morning-Brief-Feed/1.0; "
                "+https://www.mediajobsreport.com)"
            )
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def clean_text(value):
    """Convert RSS text/HTML to clean plain text."""
    if not value:
        return ""

    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def get_image(item):
    """Find the story image in the BD RSS item."""

    media_content = item.find(f"{{{MEDIA_NS}}}content")
    if media_content is not None:
        image_url = media_content.get("url")
        if image_url:
            return image_url.strip()

    media_thumbnail = item.find(f"{{{MEDIA_NS}}}thumbnail")
    if media_thumbnail is not None:
        image_url = media_thumbnail.get("url")
        if image_url:
            return image_url.strip()

    # BD also places the image URL in <comments>.
    comments = item.findtext("comments", "").strip()
    if comments.startswith("http"):
        return comments

    return ""


def get_date(item):
    """Return a valid RSS publication date."""
    raw_date = item.findtext("pubDate", "").strip()

    if raw_date:
        try:
            parsed = parsedate_to_datetime(raw_date)

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return format_datetime(parsed)
        except Exception:
            pass

    return format_datetime(datetime.now(timezone.utc))


def make_description(title, link, excerpt, image_url):
    """
    Build the short Mailchimp-ready version of each story.

    IMPORTANT:
    The image is deliberately embedded inside <description>.
    This lets Mailchimp process it as RSS content rather than
    through RSSITEM:IMAGE, which was displaying the BD image
    at its original oversized dimensions.
    """

    safe_title = html.escape(title, quote=True)
    safe_link = html.escape(link, quote=True)
    safe_image = html.escape(image_url, quote=True)
    safe_excerpt = html.escape(excerpt)

    parts = []

    if image_url:
        parts.append(
            f'<p style="text-align:center; margin:0 0 14px 0;">'
            f'<a href="{safe_link}" target="_blank">'
            f'<img src="{safe_image}" '
            f'alt="{safe_title}" '
            f'width="{IMAGE_WIDTH}" '
            f'style="display:inline-block; '
            f'width:{IMAGE_WIDTH}px; '
            f'max-width:100%; '
            f'height:auto; '
            f'border:0;" />'
            f"</a>"
            f"</p>"
        )

    parts.append(
        f'<h2 style="margin:0 0 10px 0;">'
        f'<a href="{safe_link}" target="_blank">'
        f"{safe_title}"
        f"</a>"
        f"</h2>"
    )

    if safe_excerpt:
        parts.append(
            f'<p style="margin:0 0 12px 0;">'
            f"{safe_excerpt}"
            f"</p>"
        )

    parts.append(
        f'<p style="margin:0 0 24px 0;">'
        f'<a href="{safe_link}" target="_blank">'
        f"<strong>Read the full story &raquo;</strong>"
        f"</a>"
        f"</p>"
    )

    return "".join(parts)


def build_feed(source_xml):
    """Create the clean MJR Morning Brief RSS feed."""

    source_root = ET.fromstring(source_xml)
    source_channel = source_root.find("channel")

    if source_channel is None:
        raise RuntimeError("The source RSS feed does not contain a channel.")

    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
        },
    )

    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = FEED_TITLE
    ET.SubElement(channel, "link").text = SITE_URL
    ET.SubElement(channel, "description").text = FEED_DESCRIPTION
    ET.SubElement(channel, "language").text = "en-us"

    ET.SubElement(
        channel,
        f"{{{ATOM_NS}}}link",
        {
            "href": (
                "https://mediajobsreport.github.io/"
                "mjr-morning-brief-feed/morning-brief.xml"
            ),
            "rel": "self",
            "type": "application/rss+xml",
        },
    )

    items = source_channel.findall("item")

    added = 0

    for source_item in items:
        if added >= MAX_ITEMS:
            break

        title = clean_text(source_item.findtext("title", ""))
        link = source_item.findtext("link", "").strip()
        guid = source_item.findtext("guid", "").strip() or link
        excerpt = clean_text(source_item.findtext("description", ""))
        image_url = get_image(source_item)
        pub_date = get_date(source_item)

        if not title or not link:
            continue

        item = ET.SubElement(channel, "item")

        ET.SubElement(item, "title").text = title
        ET.SubElement(item, "link").text = link

        guid_element = ET.SubElement(
            item,
            "guid",
            {"isPermaLink": "true"},
        )
        guid_element.text = guid

        ET.SubElement(item, "pubDate").text = pub_date

        # This is the short version Mailchimp will use.
        description = make_description(
            title=title,
            link=link,
            excerpt=excerpt,
            image_url=image_url,
        )

        ET.SubElement(item, "description").text = description

        # Also provide the same short content as content:encoded.
        # This means Mailchimp's Full Content option can be used
        # WITHOUT receiving the original full BD article.
        ET.SubElement(
            item,
            f"{{{CONTENT_NS}}}encoded",
        ).text = description

        if image_url:
            ET.SubElement(
                item,
                f"{{{MEDIA_NS}}}thumbnail",
                {
                    "url": image_url,
                    "width": str(IMAGE_WIDTH),
                },
            )

            ET.SubElement(
                item,
                f"{{{MEDIA_NS}}}content",
                {
                    "url": image_url,
                    "medium": "image",
                    "width": str(IMAGE_WIDTH),
                },
            )

        # Preserve categories when present.
        for category in source_item.findall("category"):
            category_text = clean_text(category.text or "")

            if category_text:
                ET.SubElement(item, "category").text = category_text

        added += 1

    ET.indent(rss, space="  ")

    tree = ET.ElementTree(rss)

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"Created {OUTPUT_FILE} with {added} items.")


def main():
    print("Downloading MJR RSS feed...")
    source_xml = fetch_feed(SOURCE_FEED)

    print("Building Morning Brief feed...")
    build_feed(source_xml)

    print("Finished.")


if __name__ == "__main__":
    main()
