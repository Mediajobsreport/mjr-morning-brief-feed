import hashlib
import html
import io
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
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

# Manifest records when each image was last seen in the feed.
EMAIL_IMAGE_MANIFEST = "email-images-manifest.json"

# Keep generated JPEGs at up to 1200px wide.
EMAIL_IMAGE_MAX_WIDTH = 1200

# High-quality JPEG.
EMAIL_JPEG_QUALITY = 92

# Display width inside the newsletter.
EMAIL_DISPLAY_WIDTH = 600

# Number of days to retain an image AFTER it disappears
# from the current Morning Brief feed.
EMAIL_IMAGE_RETENTION_DAYS = 30


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
                "MJR-Morning-Brief-Feed/3.1; "
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

    The website image remains untouched.

    A separate JPEG is generated specifically for email.
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
    Make sure the email image directory exists.

    IMPORTANT:

    We no longer delete this directory on every run.

    Existing JPEGs stay online so images in previously
    delivered Morning Brief emails continue working.
    """

    os.makedirs(
        EMAIL_IMAGE_DIR,
        exist_ok=True,
    )


# ============================================================
# IMAGE MANIFEST
# ============================================================

def load_image_manifest():
    """
    Load the email image retention manifest.

    The manifest stores the last date each image appeared
    in the generated Morning Brief feed.
    """

    if not os.path.isfile(
        EMAIL_IMAGE_MANIFEST
    ):
        return {}

    try:

        with open(
            EMAIL_IMAGE_MANIFEST,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        if isinstance(
            data,
            dict,
        ):
            return data

    except Exception as exc:

        print(
            "WARNING: Could not read "
            f"{EMAIL_IMAGE_MANIFEST}: {exc}"
        )

    return {}


def save_image_manifest(manifest):
    """
    Save the email image retention manifest.
    """

    try:

        with open(
            EMAIL_IMAGE_MANIFEST,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                manifest,
                file,
                indent=2,
                sort_keys=True,
            )

            file.write(
                "\n"
            )

    except Exception as exc:

        print(
            "WARNING: Could not save "
            f"{EMAIL_IMAGE_MANIFEST}: {exc}"
        )


# ============================================================
# EMAIL IMAGE FILENAME
# ============================================================

def make_email_image_filename(
    image_url,
    story_link,
):
    """
    Create the SAME stable filename format that is already
    working in Mailchimp and Outlook.

    Example:

    mjr-email-15799665181917b805bc.jpg

    IMPORTANT:

    We are deliberately NOT changing the public filename
    format.
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
    Create or reuse an email-safe JPEG copy.

    Website:
        Original WebP remains untouched.

    Email:
        High-quality JPEG stored on GitHub Pages.

    Existing JPEGs are reused instead of recompressed.
    """

    if not image_url:
        return "", ""

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

    # --------------------------------------------------------
    # REUSE EXISTING JPEG
    # --------------------------------------------------------

    if os.path.isfile(
        output_path
    ):

        try:

            if os.path.getsize(
                output_path
            ) > 0:

                print(
                    f"Reusing email image: "
                    f"{filename}"
                )

                return public_url, filename

        except OSError:
            pass

    # --------------------------------------------------------
    # DOWNLOAD ORIGINAL IMAGE
    # --------------------------------------------------------

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

        return public_url, filename

    except Exception as exc:

        print(
            f"WARNING: Could not create "
            f"email image for {image_url}: "
            f"{exc}"
        )

        # Do NOT fall back to WebP.
        return "", ""


# ============================================================
# IMAGE RETENTION
# ============================================================

def update_image_manifest(
    manifest,
    active_filenames,
):
    """
    Update last-seen dates for images currently in the feed.

    Every image currently being used receives today's date.
    """

    today = datetime.now(
        timezone.utc
    ).date().isoformat()

    for filename in active_filenames:

        manifest[filename] = {
            "last_seen": today
        }

    return manifest


def cleanup_old_email_images(
    manifest,
    active_filenames,
):
    """
    Remove images that:

    1. Are no longer in the current feed, AND
    2. Have not been seen for more than 30 days.

    Images currently in the feed are NEVER removed.
    """

    today = datetime.now(
        timezone.utc
    ).date()

    cutoff = (
        today
        - timedelta(
            days=EMAIL_IMAGE_RETENTION_DAYS
        )
    )

    active_set = set(
        active_filenames
    )

    removed = 0

    # --------------------------------------------------------
    # CLEAN MANIFESTED IMAGES
    # --------------------------------------------------------

    for filename in list(
        manifest.keys()
    ):

        # Never remove an image currently in the feed.
        if filename in active_set:
            continue

        record = manifest.get(
            filename,
            {},
        )

        last_seen_raw = record.get(
            "last_seen",
            "",
        )

        if not last_seen_raw:
            continue

        try:

            last_seen = datetime.strptime(
                last_seen_raw,
                "%Y-%m-%d",
            ).date()

        except ValueError:
            continue

        if last_seen >= cutoff:
            continue

        image_path = os.path.join(
            EMAIL_IMAGE_DIR,
            filename,
        )

        if os.path.isfile(
            image_path
        ):

            try:

                os.remove(
                    image_path
                )

                print(
                    f"Removed expired email image: "
                    f"{filename}"
                )

            except OSError as exc:

                print(
                    f"WARNING: Could not remove "
                    f"{filename}: {exc}"
                )

                continue

        manifest.pop(
            filename,
            None,
        )

        removed += 1

    print(
        f"Email image cleanup complete. "
        f"Removed {removed} expired image(s)."
    )

    return manifest


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

    IMPORTANT:

    The JPEG itself can be up to 1200px wide.

    It is displayed at a maximum of 600px.

    This exact sizing arrangement is retained because it
    has been confirmed working in both Mailchimp Preview
    and the delivered Outlook email.
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
    """
    Create the clean MJR Morning Brief RSS feed.

    Returns a list of JPEG filenames actively used by
    the current feed.
    """

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

    # Track every JPEG actively used by this feed.
    active_filenames = []

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
        # CREATE OR REUSE EMAIL-SAFE JPEG
        # ----------------------------------------------------

        email_image_url = ""
        email_image_filename = ""

        if original_image_url:

            (
                email_image_url,
                email_image_filename,
            ) = create_email_image(
                image_url=original_image_url,
                story_link=link,
            )

        if email_image_filename:

            active_filenames.append(
                email_image_filename
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

    return active_filenames


# ============================================================
# RUN
# ============================================================

def main():

    print(
        "Preparing email image directory..."
    )

    prepare_email_image_directory()

    # --------------------------------------------------------
    # LOAD RETENTION MANIFEST
    # --------------------------------------------------------

    print(
        "Loading email image manifest..."
    )

    manifest = load_image_manifest()

    # --------------------------------------------------------
    # DOWNLOAD SOURCE RSS
    # --------------------------------------------------------

    print(
        "Downloading MJR source RSS feed..."
    )

    source_xml = fetch_feed(
        SOURCE_FEED
    )

    # --------------------------------------------------------
    # BUILD MORNING BRIEF
    # --------------------------------------------------------

    print(
        "Filtering Events and sorting "
        "stories newest-first..."
    )

    active_filenames = build_feed(
        source_xml
    )

    # --------------------------------------------------------
    # UPDATE MANIFEST
    # --------------------------------------------------------

    manifest = update_image_manifest(
        manifest=manifest,
        active_filenames=active_filenames,
    )

    # --------------------------------------------------------
    # CLEAN OLD IMAGES
    # --------------------------------------------------------

    print(
        "Checking for email images older than "
        f"{EMAIL_IMAGE_RETENTION_DAYS} days..."
    )

    manifest = cleanup_old_email_images(
        manifest=manifest,
        active_filenames=active_filenames,
    )

    # --------------------------------------------------------
    # SAVE MANIFEST
    # --------------------------------------------------------

    save_image_manifest(
        manifest
    )

    print(
        "Morning Brief feed finished."
    )


if __name__ == "__main__":
    main()
