"""Tag encoding/decoding for EventKit items.

Since EventKit does not support native tags, we store tags as hashtags
in the notes field (e.g., #work #urgent). This is human-readable and
works well in most applications.
"""

import re
from typing import Tuple

# Regex pattern to find hashtags in notes (at end of notes, after newlines)
# Matches lines that contain only hashtags (with optional spaces between them)
HASHTAG_LINE_PATTERN = re.compile(r'\n*(?:^|\n)((?:#[a-z0-9_]+\s*)+)$', re.IGNORECASE)

# Pattern to extract individual hashtags
HASHTAG_PATTERN = re.compile(r'#([a-z0-9_]+)', re.IGNORECASE)


def _normalize_tag(tag: str) -> str:
    """Normalize a tag: lowercase, replace spaces with underscores, strip."""
    normalized = tag.strip().lower()
    # Replace spaces and hyphens with underscores for hashtag format
    normalized = re.sub(r'[\s-]+', '_', normalized)
    # Remove any characters that aren't alphanumeric or underscore
    normalized = re.sub(r'[^a-z0-9_]', '', normalized)
    return normalized


def encode_tags(tags: list[str] | None) -> str:
    """Encode tags as hashtag string.

    Args:
        tags: List of tag strings, or None/empty list

    Returns:
        Hashtag string to append to notes, or empty string if no tags
    """
    if not tags:
        return ""

    # Normalize tags and convert to hashtags
    normalized = [_normalize_tag(t) for t in tags if t.strip()]
    # Remove empty strings and duplicates while preserving order
    seen = set()
    unique = []
    for tag in normalized:
        if tag and tag not in seen:
            seen.add(tag)
            unique.append(tag)

    if not unique:
        return ""

    hashtags = " ".join(f"#{tag}" for tag in sorted(unique))
    return f"\n\n{hashtags}"


def decode_tags(notes: str | None) -> Tuple[str, list[str]]:
    """Extract tags from notes and return clean notes.

    Args:
        notes: The notes field content, may contain hashtags at the end

    Returns:
        Tuple of (clean_notes, tags_list)
        - clean_notes: Notes with hashtag line removed
        - tags_list: List of extracted tags (without # prefix), or empty list
    """
    if not notes:
        return "", []

    # Find hashtags at the end of the notes
    match = HASHTAG_LINE_PATTERN.search(notes)
    if not match:
        return notes, []

    hashtag_line = match.group(1)

    # Extract individual tags from the hashtag line
    tags = HASHTAG_PATTERN.findall(hashtag_line)
    tags = [t.lower() for t in tags]

    # Remove the hashtag line from notes
    clean_notes = HASHTAG_LINE_PATTERN.sub("", notes).strip()

    return clean_notes, tags


def merge_notes_with_tags(
    notes: str | None,
    tags: list[str] | None
) -> str:
    """Combine user notes with hashtags.

    This removes any existing hashtags from notes and appends new ones.

    Args:
        notes: User's notes content
        tags: List of tags to apply

    Returns:
        Combined notes string with hashtags appended
    """
    # Remove any existing tags
    clean_notes, _ = decode_tags(notes)

    # Add new tags
    tag_string = encode_tags(tags)

    if clean_notes and tag_string:
        return clean_notes + tag_string
    elif clean_notes:
        return clean_notes
    elif tag_string:
        return tag_string.strip()  # Remove leading newlines if no notes
    else:
        return ""


def update_tags(
    notes: str | None,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None
) -> str:
    """Update tags in notes by adding or removing specific tags.

    Args:
        notes: Current notes content with possible tags
        add_tags: Tags to add (if not already present)
        remove_tags: Tags to remove (if present)

    Returns:
        Updated notes string with modified tags
    """
    clean_notes, existing_tags = decode_tags(notes)

    # Convert to set for easier manipulation
    tag_set = set(_normalize_tag(t) for t in existing_tags if t)

    # Add new tags
    if add_tags:
        for tag in add_tags:
            normalized = _normalize_tag(tag)
            if normalized:
                tag_set.add(normalized)

    # Remove specified tags
    if remove_tags:
        for tag in remove_tags:
            normalized = _normalize_tag(tag)
            tag_set.discard(normalized)

    # Convert back to sorted list for consistent output
    final_tags = sorted(tag_set) if tag_set else None

    return merge_notes_with_tags(clean_notes, final_tags)


def has_tag(notes: str | None, tag: str) -> bool:
    """Check if notes contain a specific tag.

    Args:
        notes: Notes content to check
        tag: Tag to look for (case-insensitive)

    Returns:
        True if the tag is present
    """
    _, tags = decode_tags(notes)
    normalized = _normalize_tag(tag)
    return normalized in [_normalize_tag(t) for t in tags]


def filter_by_tags(
    items: list[dict],
    required_tags: list[str],
    notes_key: str = "notes"
) -> list[dict]:
    """Filter a list of items by required tags.

    Args:
        items: List of item dicts with notes field
        required_tags: Tags that must all be present
        notes_key: Key in item dict containing notes

    Returns:
        Filtered list containing only items with all required tags
    """
    if not required_tags:
        return items

    normalized_required = [_normalize_tag(t) for t in required_tags if t.strip()]
    if not normalized_required:
        return items

    result = []
    for item in items:
        notes = item.get(notes_key, "")
        _, item_tags = decode_tags(notes)
        item_tags_normalized = [_normalize_tag(t) for t in item_tags]

        if all(req in item_tags_normalized for req in normalized_required):
            result.append(item)

    return result
