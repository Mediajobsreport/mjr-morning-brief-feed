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

GITHUB_PAGES_BASE = (
    "https://mediajobsreport.github.io/"
    "mjr-morning-brief-feed"
)

FEED_URL = (
    f"{GITHUB_PAGES_BASE}/morning-brief.xml"
)

FEED_TITLE = "Media Jobs Report Morning Brief"
FEED_DESCRIPTION = "Media industry news from Media Jobs Report"

# Maximum number of stories available to Mailchimp.
MAX_ITEMS = 20

# Maximum DISPLAY width inside the email.
#
# IMPORTANT:
# This does NOT resize, convert or recompress the source image.
# A 1200x630 PNG remains a 1200x630 PNG.
#
# It simply tells the email client to display the image
# at no more than 600px wide.
EMAIL_DISPLAY_WIDTH = 600

# Content we do NOT want in the Morning Brief.
EXCLUDED_URL_PATHS = (
    "/events/",
)

MEDIA_NS = "http://search.yahoo.com/mrss/"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
ATOM_NS = "http://www.w3.org/2005/Atom"

ET.register_namespace("media", MEDIA_NS)
ET.register_namespace("content", CONTENT_NS)
ET.register_namespace("atom", ATOM_NS)


# ============================================================
# DOWNLOAD
# ============================================================

def download_url(url):
    """Download a URL using an MJR user agent."""

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; "
                "MJR-Morning-Brief-Feed/2.2; "
                "+https://www.mediajobsreport.com)"
            )
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:
        return response.read()


def fetch_feed(url):
    """Download the source MJR RSS feed."""

    return download_url(url)


# ============================================================
# TEXT CLEANUP
# ============================================================

def clean_text(value):
    """
    Convert RSS HTML/text to clean plain text.

    ElementTree handles final XML escaping.
    """

    if not value:
        return ""

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    value = html.unescape(value)

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# STORY IMAGE
# ============================================================

def get_image(item):
    """
    Find the original MJR story image.

    The original image URL is passed directly to Mailchimp.

    We do NOT:
    - download the image
    - resize the image
    - convert the image
    - recompress the image
    - store an image copy on GitHub

    PNG, JPEG and WEBP URLs can all pass through unchanged.
    For email compatibility, MJR story graphics can be
    published as PNG.
    """

    # --------------------------------------------------------
    # MEDIA CONTENT
    # --------------------------------------------------------

    media_content = item.find(
        f"{{{MEDIA_NS}}}content"
    )

    if media_content is not None:

        image_url = media_content.get(
            "url"
        )

        if image_url:
            return image_url.strip()

    # --------------------------------------------------------
    # MEDIA THUMBNAIL
    # --------------------------------------------------------

    media_thumbnail = item.find(
        f"{{{MEDIA_NS}}}thumbnail"
    )

    if media_thumbnail is not None:

        image_url = media_thumbnail.get(
            "url"
        )

        if image_url:
            return image_url.strip()

    # --------------------------------------------------------
    # BD COMMENTS FIELD FALLBACK
    # --------------------------------------------------------
    #
    # The BD-generated RSS feed may also place the image
    # URL in the comments element.
    # --------------------------------------------------------

    comments = item.findtext(
        "comments",
        "",
    ).strip()

    if comments.startswith("http"):
        return comments

    return ""


# ============================================================
# DATE HANDLING
# ============================================================

def parse_date(item):
    """Return the item's publication date as a datetime."""

    raw_date = item.findtext(
        "pubDate",
        "",
    ).strip()

    if raw_date:

        try:

            parsed = parsedate_to_datetime(
                raw_date
            )

            if parsed.tzinfo is None:

                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed

        except Exception:
            pass

    return datetime.min.replace(
        tzinfo=timezone.utc
    )


def format_pub_date(date_value):
    """Format datetime as a valid RSS publication date."""

    minimum_date = datetime.min.replace(
        tzinfo=timezone.utc
    )

    if date_value == minimum_date:

        return format_datetime(
            datetime.now(timezone.utc)
        )

    return format_datetime(
        date_value
    )


# ============================================================
# FILTERING
# ============================================================

def should_include(item):
    """
    Decide whether the source item belongs in the
    MJR Morning Brief.

    Event listings are excluded.
    """

    link = item.findtext(
        "link",
        "",
    ).strip().lower()

    if not link:
        return False

    for excluded_path in EXCLUDED_URL_PATHS:

        if excluded_path.lower() in link:
            return False

    return True


# ============================================================
# MAILCHIMP STORY CONTENT
# ============================================================

def make_description(
    title,
    link,
    excerpt,
    image_url,
):
    """
    Create the short email version of each story.

    Layout:

    IMAGE
    HEADLINE
    SHORT EXCERPT
    READ THE FULL STORY »

    The original MJR image is used directly.

    A 1200px source image is NOT altered. The HTML simply
    tells Mailchimp/email clients to display it at a maximum
    of 600px wide.
    """

    parts = []

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------
    #
    # width="600"
    #
    # Provides traditional email clients such as Outlook
    # with an explicit display width.
    #
    # width:100%;
    # max-width:600px;
    #
    # Allows the image to fill the newsletter content area
    # while shrinking appropriately on smaller screens.
    #
    # The actual source image remains untouched.
    # --------------------------------------------------------

    if image_url:

        parts.append(
            f'<p style="'
            f'text-align:center;'
            f'margin:0 0 14px 0;'
            f'padding:0;">'
            f'<a href="{link}" '
            f'target="_blank" '
            f'style="text-decoration:none;">'
            f'<img '
            f'src="{image_url}" '
            f'alt="" '
            f'width="{EMAIL_DISPLAY_WIDTH}" '
            f'style="'
            f'display:block;'
            f'width:100%;'
            f'max-width:{EMAIL_DISPLAY_WIDTH}px;'
            f'height:auto;'
            f'margin:0 auto;'
            f'padding:0;'
            f'border:0;" />'
            f'</a>'
            f'</p>'
        )

    # --------------------------------------------------------
    # HEADLINE
    # --------------------------------------------------------

    parts.append(
        f'<h2 style="'
        f'margin:0 0 10px 0;">'
        f'<a href="{link}" '
        f'target="_blank">'
        f'{title}'
        f'</a>'
        f'</h2>'
    )

    # --------------------------------------------------------
    # EXCERPT
    # --------------------------------------------------------

    if excerpt:

        parts.append(
            f'<p style="'
            f'margin:0 0 12px 0;">'
            f'{excerpt}'
            f'</p>'
        )

    # --------------------------------------------------------
    # READ FULL STORY
    # --------------------------------------------------------

    parts.append(
        f'<p style="'
        f'margin:0 0 24px 0;">'
        f'<a href="{link}" '
        f'target="_blank">'
        f'<strong>'
        f'Read the full story »'
        f'</strong>'
        f'</a>'
        f'</p>'
    )

    return "".join(
        parts
    )


# ============================================================
# BUILD FEED
# ============================================================

def build_feed(source_xml):
    """Create the clean MJR Morning Brief RSS feed."""

    source_root = ET.fromstring(
        source_xml
    )

    source_channel = source_root.find(
        "channel"
    )

    if source_channel is None:

        raise RuntimeError(
            "The source RSS feed does not contain a channel."
        )

    # --------------------------------------------------------
    # COLLECT ELIGIBLE STORIES
    # --------------------------------------------------------

    eligible_items = []

    for source_item in source_channel.findall(
        "item"
    ):

        if not should_include(
            source_item
        ):
            continue

        title = clean_text(
            source_item.findtext(
                "title",
                "",
            )
        )

        link = source_item.findtext(
            "link",
            "",
        ).strip()

        if not title or not link:
            continue

        publication_date = parse_date(
            source_item
        )

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

    eligible_items = eligible_items[
        :MAX_ITEMS
    ]

    # --------------------------------------------------------
    # CREATE RSS DOCUMENT
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
    # ADD STORIES
    # --------------------------------------------------------

    added = 0

    for (
        publication_date,
        source_item,
    ) in eligible_items:

        title = clean_text(
            source_item.findtext(
                "title",
                "",
            )
        )

        link = source_item.findtext(
            "link",
            "",
        ).strip()

        guid = source_item.findtext(
            "guid",
            "",
        ).strip() or link

        excerpt = clean_text(
            source_item.findtext(
                "description",
                "",
            )
        )

        image_url = get_image(
            source_item
        )

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
        # PUBLICATION DATE
        # ----------------------------------------------------

        ET.SubElement(
            item,
            "pubDate",
        ).text = pub_date

        # ----------------------------------------------------
        # SHORT MAILCHIMP CONTENT
        # ----------------------------------------------------

        description = make_description(
            title=title,
            link=link,
            excerpt=excerpt,
            image_url=image_url,
        )

        # Mailchimp excerpt content.
        ET.SubElement(
            item,
            "description",
        ).text = description

        # Mailchimp Full Content receives the SAME shortened
        # version. The complete original article is never
        # inserted into the newsletter.
        ET.SubElement(
            item,
            f"{{{CONTENT_NS}}}encoded",
        ).text = description

        # ----------------------------------------------------
        # ORIGINAL MJR IMAGE
        # ----------------------------------------------------
        #
        # The original image URL is supplied here.
        #
        # No duplicate image is created.
        # No image is stored in this GitHub repository.
        # No image conversion takes place.
        # ----------------------------------------------------

        if image_url:

            ET.SubElement(
                item,
                f"{{{MEDIA_NS}}}thumbnail",
                {
                    "url": image_url,
                },
            )

            ET.SubElement(
                item,
                f"{{{MEDIA_NS}}}content",
                {
                    "url": image_url,
                    "medium": "image",
                },
            )

        # ----------------------------------------------------
        # CATEGORY
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
    # WRITE RSS FILE
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


# ============================================================
# RUN
# ============================================================

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
