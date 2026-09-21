import html
import io
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime, format_datetime
from urllib.parse import urlparse

from PIL import Image, ImageOps

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

# Email image source width.
#
# MJR social/web graphics are normally 1200px wide.
# Mailchimp/email clients can scale these down for display
# while retaining a sharper source image.
IMAGE_WIDTH = 1200

# High JPEG quality for graphics containing text/screenshots.
JPEG_QUALITY = 95

# Folder created in the GitHub repository.
EMAIL_IMAGE_DIR = "email-images"

# Public URL for those images through GitHub Pages.
EMAIL_IMAGE_URL = (
    f"{GITHUB_PAGES_BASE}/email-images"
)

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
                "MJR-Morning-Brief-Feed/1.5; "
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

    ElementTree handles the final XML escaping, so visible
    text is not manually HTML-escaped here.
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
# ORIGINAL STORY IMAGE
# ============================================================

def get_image(item):
    """Find the story image in the MJR source RSS item."""

    media_content = item.find(
        f"{{{MEDIA_NS}}}content"
    )

    if media_content is not None:

        image_url = media_content.get("url")

        if image_url:
            return image_url.strip()

    media_thumbnail = item.find(
        f"{{{MEDIA_NS}}}thumbnail"
    )

    if media_thumbnail is not None:

        image_url = media_thumbnail.get("url")

        if image_url:
            return image_url.strip()

    # BD also places the image URL in <comments>.
    comments = item.findtext(
        "comments",
        "",
    ).strip()

    if comments.startswith("http"):
        return comments

    return ""


# ============================================================
# EMAIL-SAFE JPEG IMAGE
# ============================================================

def make_safe_filename(link, index):
    """
    Create a predictable JPEG filename from the story URL.
    """

    parsed = urlparse(link)

    slug = parsed.path.rstrip("/").split("/")[-1]

    slug = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "-",
        slug,
    )

    slug = slug.strip("-").lower()

    if not slug:
        slug = f"story-{index}"

    # Prevent excessively long filenames.
    slug = slug[:100]

    return f"{index:02d}-{slug}.jpg"


def prepare_rgb_image(image):
    """
    Convert an image to RGB while safely handling
    transparency.
    """

    image = ImageOps.exif_transpose(
        image
    )

    if image.mode in (
        "RGBA",
        "LA",
    ):

        rgba_image = image.convert(
            "RGBA"
        )

        background = Image.new(
            "RGB",
            rgba_image.size,
            "white",
        )

        background.paste(
            rgba_image,
            mask=rgba_image.getchannel("A"),
        )

        return background

    if image.mode == "P":

        rgba_image = image.convert(
            "RGBA"
        )

        background = Image.new(
            "RGB",
            rgba_image.size,
            "white",
        )

        background.paste(
            rgba_image,
            mask=rgba_image.getchannel("A"),
        )

        return background

    return image.convert(
        "RGB"
    )


def convert_image_to_jpeg(
    source_url,
    filename,
):
    """
    Download the original MJR story image and create an
    email-safe JPEG.

    Images wider than 1200px are reduced to 1200px.
    Images already 1200px or smaller are NOT enlarged.

    JPEG quality is intentionally high because many MJR
    graphics contain text, logos, screenshots and other
    details that can look soft with aggressive compression.
    """

    if not source_url:
        return ""

    try:

        image_data = download_url(
            source_url
        )

        with Image.open(
            io.BytesIO(image_data)
        ) as original_image:

            image = prepare_rgb_image(
                original_image
            )

            # ------------------------------------------------
            # RESIZE ONLY WHEN ORIGINAL IS WIDER THAN 1200PX
            # ------------------------------------------------

            if image.width > IMAGE_WIDTH:

                ratio = (
                    IMAGE_WIDTH /
                    float(image.width)
                )

                new_height = max(
                    1,
                    round(
                        image.height *
                        ratio
                    ),
                )

                image = image.resize(
                    (
                        IMAGE_WIDTH,
                        new_height,
                    ),
                    Image.Resampling.LANCZOS,
                )

            # ------------------------------------------------
            # SAVE EMAIL-SAFE JPEG
            # ------------------------------------------------

            output_path = os.path.join(
                EMAIL_IMAGE_DIR,
                filename,
            )

            image.save(
                output_path,
                "JPEG",
                quality=JPEG_QUALITY,
                optimize=True,
                progressive=False,
                subsampling=0,
            )

        return (
            f"{EMAIL_IMAGE_URL}/"
            f"{filename}"
        )

    except Exception as error:

        print(
            "WARNING: Could not convert image:"
        )

        print(
            source_url
        )

        print(
            error
        )

        # Do not fall back to WEBP.
        #
        # If conversion fails, the story is sent without
        # an image rather than risking a broken Outlook image.
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
    """

    parts = []

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    if image_url:

        parts.append(
            f'<p style="text-align:center;'
            f'margin:0 0 14px 0;">'
            f'<a href="{link}" target="_blank">'
            f'<img src="{image_url}" '
            f'alt="" '
            f'width="600" '
            f'style="display:block;'
            f'width:100%;'
            f'max-width:600px;'
            f'height:auto;'
            f'margin:0 auto;'
            f'border:0;" />'
            f"</a>"
            f"</p>"
        )

    # --------------------------------------------------------
    # HEADLINE
    # --------------------------------------------------------

    parts.append(
        f'<h2 style="margin:0 0 10px 0;">'
        f'<a href="{link}" target="_blank">'
        f"{title}"
        f"</a>"
        f"</h2>"
    )

    # --------------------------------------------------------
    # EXCERPT
    # --------------------------------------------------------

    if excerpt:

        parts.append(
            f'<p style="margin:0 0 12px 0;">'
            f"{excerpt}"
            f"</p>"
        )

    # --------------------------------------------------------
    # READ FULL STORY
    # --------------------------------------------------------

    parts.append(
        f'<p style="margin:0 0 24px 0;">'
        f'<a href="{link}" target="_blank">'
        f"<strong>"
        f"Read the full story »"
        f"</strong>"
        f"</a>"
        f"</p>"
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
    # CREATE/CLEAN EMAIL IMAGE DIRECTORY
    # --------------------------------------------------------

    os.makedirs(
        EMAIL_IMAGE_DIR,
        exist_ok=True,
    )

    # Remove previously generated JPEGs so old stories
    # do not accumulate indefinitely.
    for filename in os.listdir(
        EMAIL_IMAGE_DIR
    ):

        if filename.lower().endswith(
            ".jpg"
        ):

            try:

                os.remove(
                    os.path.join(
                        EMAIL_IMAGE_DIR,
                        filename,
                    )
                )

            except OSError:
                pass

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

        story_number = added + 1

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

        original_image_url = get_image(
            source_item
        )

        # ----------------------------------------------------
        # CREATE EMAIL-SAFE JPEG
        # ----------------------------------------------------

        email_image_url = ""

        if original_image_url:

            image_filename = make_safe_filename(
                link,
                story_number,
            )

            print(
                f"Creating email image "
                f"{story_number}: "
                f"{image_filename}"
            )

            email_image_url = (
                convert_image_to_jpeg(
                    original_image_url,
                    image_filename,
                )
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
        # DATE
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
            image_url=email_image_url,
        )

        # Mailchimp Excerpt content.
        ET.SubElement(
            item,
            "description",
        ).text = description

        # Mailchimp Full Content.
        #
        # We intentionally put the SAME short version here.
        # The complete original article is never inserted
        # into the newsletter.
        ET.SubElement(
            item,
            f"{{{CONTENT_NS}}}encoded",
        ).text = description

        # ----------------------------------------------------
        # MEDIA IMAGE
        # ----------------------------------------------------

        if email_image_url:

            ET.SubElement(
                item,
                f"{{{MEDIA_NS}}}thumbnail",
                {
                    "url": email_image_url,
                    "width": str(
                        IMAGE_WIDTH
                    ),
                },
            )

            ET.SubElement(
                item,
                f"{{{MEDIA_NS}}}content",
                {
                    "url": email_image_url,
                    "medium": "image",
                    "width": str(
                        IMAGE_WIDTH
                    ),
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
