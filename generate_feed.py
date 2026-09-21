import hashlib
import html
import io
import os
import re
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime, format_datetime

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

# Content we do NOT want in the Morning Brief.
EXCLUDED_URL_PATHS = (
    "/events/",
)


# ============================================================
# EMAIL IMAGE SETTINGS
# ============================================================

EMAIL_IMAGE_DIR = "email-images"

EMAIL_IMAGE_BASE_URL = (
    f"{GITHUB_PAGES_BASE}/{EMAIL_IMAGE_DIR}"
)

# Keep the generated JPEG up to 1200px wide.
# This gives us good image quality for high-resolution screens.
EMAIL_IMAGE_MAX_WIDTH = 1200

# High-quality JPEG for email.
EMAIL_JPEG_QUALITY = 92

# Actual display width inside the newsletter.
EMAIL_DISPLAY_WIDTH = 600


# ============================================================
# XML NAMESPACES
# ============================================================

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

    ElementTree handles the final XML escaping.
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

    The original website image may remain WebP.

    We create a separate JPEG specifically for the
    Morning Brief email.
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
# EMAIL IMAGE DIRECTORY
# ============================================================

def prepare_email_image_directory():
    """
    Prepare a fresh email image directory for this test.

    IMPORTANT:
    This is the same simple approach that produced the
    working JPEG URLs.

    Once delivery and sizing are confirmed, retention can
    be added separately without changing the URL format.
    """

    if os.path.isdir(
        EMAIL_IMAGE_DIR
    ):

        shutil.rmtree(
            EMAIL_IMAGE_DIR
        )

    os.makedirs(
        EMAIL_IMAGE_DIR,
        exist_ok=True,
    )


# ============================================================
# EMAIL IMAGE FILENAME
# ============================================================

def make_email_image_filename(
    image_url,
    story_link,
):
    """
    Create the stable filename format that was already
    confirmed in the generated RSS.

    Example:

    mjr-email-15799665181917b805bc.jpg
    """

    identity = (
        f"{story_link}|{image_url}"
    ).encode(
        "utf-8"
    )

    digest = hashlib.sha256(
        identity
    ).hexdigest()[:20]

    return (
        f"mjr-email-"
        f"{digest}.jpg"
    )


# ============================================================
# CREATE EMAIL-SAFE JPEG
# ============================================================

def create_email_image(
    image_url,
    story_link,
):
    """
    Create an email-safe JPEG copy of the original image.

    The MJR website image remains untouched.

    Original MJR WebP/PNG/JPEG
              |
              v
       Email JPEG copy
              |
              v
       GitHub Pages
              |
              v
         Mailchimp
              |
              v
          Outlook
    """

    if not image_url:
        return ""

    filename = make_email_image_filename(
        image_url=image_url,
        story_link=story_link,
    )

    output_path = os.path.join(
        EMAIL_IMAGE_DIR,
        filename,
    )

    public_url = (
        f"{EMAIL_IMAGE_BASE_URL}/"
        f"{filename}"
    )

    try:

        print(
            f"Downloading story image: "
            f"{image_url}"
        )

        image_bytes = download_url(
            image_url
        )

        with Image.open(
            io.BytesIO(image_bytes)
        ) as original_image:

            # ------------------------------------------------
            # FIX EXIF ORIENTATION
            # ------------------------------------------------

            image = ImageOps.exif_transpose(
                original_image
            )

            # ------------------------------------------------
            # HANDLE TRANSPARENCY
            # ------------------------------------------------

            has_transparency = (
                image.mode in (
                    "RGBA",
                    "LA",
                )
                or (
                    image.mode == "P"
                    and "transparency"
                    in image.info
                )
            )

            if has_transparency:

                rgba_image = image.convert(
                    "RGBA"
                )

                background = Image.new(
                    "RGB",
                    rgba_image.size,
                    (255, 255, 255),
                )

                background.paste(
                    rgba_image,
                    mask=rgba_image.getchannel(
                        "A"
                    ),
                )

                image = background

            else:

                image = image.convert(
                    "RGB"
                )

            # ------------------------------------------------
            # RESIZE ONLY IF LARGER THAN 1200PX
            # ------------------------------------------------

            width, height = image.size

            if width > EMAIL_IMAGE_MAX_WIDTH:

                new_width = (
                    EMAIL_IMAGE_MAX_WIDTH
                )

                new_height = round(
                    height
                    * new_width
                    / width
                )

                image = image.resize(
                    (
                        new_width,
                        new_height,
                    ),
                    Image.Resampling.LANCZOS,
                )

            # ------------------------------------------------
            # SAVE HIGH-QUALITY JPEG
            # ------------------------------------------------

            image.save(
                output_path,
                format="JPEG",
                quality=EMAIL_JPEG_QUALITY,
                optimize=True,
                progressive=False,
                subsampling=0,
            )

        print(
            f"Created email image: "
            f"{filename}"
        )

        return public_url

    except Exception as exc:

        print(
            f"WARNING: Could not create "
            f"email image for {image_url}: "
            f"{exc}"
        )

        # Do NOT fall back to the original WebP.
        # Classic Outlook may not display WebP correctly.
        return ""


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

    IMAGE
    HEADLINE
    SHORT EXCERPT
    READ THE FULL STORY »

    The JPEG itself can be up to 1200px wide.

    It is explicitly displayed at a maximum of 600px.

    The HTML width attribute is important for Classic Outlook.
    The CSS keeps the image responsive on smaller screens.
    """

    parts = []

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    if image_url:

        parts.append(
            f'<p style="'
            f'text-align:center;'
            f'margin:0 0 14px 0;'
            f'padding:0;">'

            f'<a '
            f'href="{link}" '
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
            f'border:0;'
            f'outline:none;'
            f'text-decoration:none;'
            f'-ms-interpolation-mode:bicubic;" />'

            f'</a>'

            f'</p>'
        )

    # --------------------------------------------------------
    # HEADLINE
    # --------------------------------------------------------

    parts.append(
        f'<h2 style="'
        f'margin:0 0 10px 0;">'

        f'<a '
        f'href="{link}" '
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

        f'<a '
        f'href="{link}" '
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

        original_image_url = get_image(
            source_item
        )

        # ----------------------------------------------------
        # CREATE EMAIL-SAFE JPEG
        # ----------------------------------------------------

        email_image_url = ""

        if original_image_url:

            email_image_url = create_email_image(
                image_url=original_image_url,
                story_link=link,
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
            image_url=email_image_url,
        )

        ET.SubElement(
            item,
            "description",
        ).text = description

        ET.SubElement(
            item,
            f"{{{CONTENT_NS}}}encoded",
        ).text = description

        # ----------------------------------------------------
        # EMAIL-SAFE JPEG FOR MAILCHIMP
        # ----------------------------------------------------

        if email_image_url:

            ET.SubElement(
                item,
                f"{{{MEDIA_NS}}}thumbnail",
                {
                    "url": email_image_url,
                },
            )

            ET.SubElement(
                item,
                f"{{{MEDIA_NS}}}content",
                {
                    "url": email_image_url,
                    "medium": "image",
                    "type": "image/jpeg",
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
        "Preparing email image directory..."
    )

    prepare_email_image_directory()

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
