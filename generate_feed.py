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
FEED_URL = (
    "https://mediajobsreport.github.io/"
    "mjr-morning-brief-feed/morning-brief.xml"
)

FEED_TITLE = "Media Jobs Report Morning Brief"
FEED_DESCRIPTION = "Media industry news from Media Jobs Report"

# Maximum number of stories available to Mailchimp.
MAX_ITEMS = 20

# Width of story images in the newsletter.
IMAGE_WIDTH = 300

# URLs containing any of these paths will NOT be included.
EXCLUDED_URL_PATHS = (
    "/events/",
)

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
                "MJR-Morning-Brief-Feed/1.1; "
                "+https://www.mediajobsreport.com)"
            )
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def clean_text(value):
    """Convert RSS HTML/text to clean plain text."""
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


def parse_date(item):
    """Return the item's publication date as a datetime."""

    raw_date = item.findtext("pubDate", "").strip()

    if raw_date:
        try:
            parsed = parsedate_to_datetime(raw_date)

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed

        except Exception:
            pass

    # Items without a usable date go to the bottom.
    return datetime.min.replace(tzinfo=timezone.utc)


def format_pub_date(date_value):
    """Format datetime as an RSS publication date."""

    if date_value == datetime.min.replace(tzinfo=timezone.utc):
        return format_datetime(datetime.now(timezone.utc))

    return format_datetime(date_value)


def should_include(item):
    """
    Determine whether an RSS item belongs in the Morning Brief.

    Events are excluded because the BD source feed currently
    places event listings ahead of news stories.
    """

    link = item.findtext("link", "").strip().lower()

    if not link:
        return False

    for excluded_path in EXCLUDED_URL_PATHS:
        if excluded_path.lower() in link:
            return False

    return True


def make_description(title, link, excerpt, image_url):
    """
    Build the short Mailchimp-ready version.

    Output:
    IMAGE
    HEADLINE
    SHORT EXCERPT
    READ THE FULL STORY
    """

    safe_title = html.escape(title, quote=True)
    safe_link = html.escape(link, quote=True)
    safe_image = html.escape(image_url, quote=True)
    safe_excerpt = html.escape(excerpt)

    parts = []

    # --------------------------------------------------------
    # STORY IMAGE
    # --------------------------------------------------------

    if image_url:
        parts.append(
            f'<p style="text-align:center; '
            f'margin:0 0 14px 0;">'
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

    # --------------------------------------------------------
    # HEADLINE
    # --------------------------------------------------------

    parts.append(
        f'<h2 style="margin:0 0 10px 0;">'
        f'<a href="{safe_link}" target="_blank">'
        f"{safe_title}"
        f"</a>"
        f"</h2>"
    )

    # --------------------------------------------------------
    # EXCERPT
    # --------------------------------------------------------

    if safe_excerpt:
        parts.append(
            f'<p style="margin:0 0 12px 0;">'
            f"{safe_excerpt}"
            f"</p>"
        )

    # --------------------------------------------------------
    # READ MORE LINK
    # --------------------------------------------------------

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
        raise RuntimeError(
            "The source RSS feed does not contain a channel."
        )

    # --------------------------------------------------------
    # COLLECT ELIGIBLE STORIES
    # --------------------------------------------------------

    eligible_items = []

    for source_item in source_channel.findall("item"):

        if not should_include(source_item):
            continue

        title = clean_text(
            source_item.findtext("title", "")
        )

        link = source_item.findtext(
            "link", ""
        ).strip()

        if not title or not link:
            continue

        publication_date = parse_date(source_item)

        eligible_items.append(
            (
                publication_date,
                source_item,
            )
        )

    # --------------------------------------------------------
    # NEWEST STORIES FIRST
    # --------------------------------------------------------

    eligible_items.sort(
        key=lambda entry: entry[0],
        reverse=True,
    )

    eligible_items = eligible_items[:MAX_ITEMS]

    # --------------------------------------------------------
    # CREATE NEW RSS DOCUMENT
    # --------------------------------------------------------

    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
        },
    )

    channel = ET.SubElement(
        rss,
        "channel",
    )

    ET.SubElement(
        channel,
        "title",
    ).text = FEED_TITLE

    ET.SubElement(
        channel,
        "link",
    ).text = SITE_URL

    ET.SubElement(
        channel,
        "description",
    ).text = FEED_DESCRIPTION

    ET.SubElement(
        channel,
        "language",
    ).text = "en-us"

    ET.SubElement(
        channel,
        f"{{{ATOM_NS}}}link",
        {
            "href": FEED_URL,
            "rel": "self",
            "type": "application/rss+xml",
        },
    )

    # --------------------------------------------------------
    # CREATE RSS ITEMS
    # --------------------------------------------------------

    added = 0

    for publication_date, source_item in eligible_items:

        title = clean_text(
            source_item.findtext("title", "")
        )

        link = source_item.findtext(
            "link", ""
        ).strip()

        guid = source_item.findtext(
            "guid", ""
        ).strip() or link

        excerpt = clean_text(
            source_item.findtext("description", "")
        )

        image_url = get_image(source_item)

        pub_date = format_pub_date(
            publication_date
        )

        item = ET.SubElement(
            channel,
            "item",
        )

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        ET.SubElement(
            item,
            "title",
        ).text = title

        # ----------------------------------------------------
        # STORY LINK
        # ----------------------------------------------------

        ET.SubElement(
            item,
            "link",
        ).text = link

        # ----------------------------------------------------
        # GUID
        # ----------------------------------------------------

        guid_element = ET.SubElement(
            item,
            "guid",
            {
                "isPermaLink": "true",
            },
        )

        guid_element.text = guid

        # ----------------------------------------------------
        # DATE
        # ----------------------------------------------------

        ET.SubElement(
            item,
            "pubDate",
        ).text = pub_date

        # ----------------------------------------------------
        # MAILCHIMP CONTENT
        # ----------------------------------------------------

        description = make_description(
            title=title,
            link=link,
            excerpt=excerpt,
            image_url=image_url,
        )

        # Short version for Mailchimp Excerpts.
        ET.SubElement(
            item,
            "description",
        ).text = description

        # IMPORTANT:
        # Full Content also receives ONLY our short version.
        #
        # This lets us use Mailchimp's Full Content image
        # handling without sending the original complete story.
        ET.SubElement(
            item,
            f"{{{CONTENT_NS}}}encoded",
        ).text = description

        # ----------------------------------------------------
        # MEDIA IMAGE
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # CATEGORIES
        # ----------------------------------------------------

        for category in source_item.findall(
            "category"
        ):

            category_text = clean_text(
                category.text or ""
            )

            if category_text:

                ET.SubElement(
                    item,
                    "category",
                ).text = category_text

        added += 1

    # --------------------------------------------------------
    # SAVE RSS FILE
    # --------------------------------------------------------

    ET.indent(
        rss,
        space="  ",
    )

    tree = ET.ElementTree(
        rss
    )

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(
        f"Created {OUTPUT_FILE} "
        f"with {added} Morning Brief stories."
    )


def main():

    print(
        "Downloading MJR source RSS feed..."
    )

    source_xml = fetch_feed(
        SOURCE_FEED
    )

    print(
        "Filtering Events and sorting "
        "stories newest-first..."
    )

    build_feed(
        source_xml
    )

    print(
        "Morning Brief feed finished."
    )


if __name__ == "__main__":
    main()
