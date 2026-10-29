from enum import StrEnum


class Relation(StrEnum):
    self = "self"
    friend = "friend"
    other = "other"


def visible_profile_blocks(relation: Relation) -> set[str]:
    """Which profile blocks a viewer may read. Music preferences are public on purpose:
    they let people find others with the same tastes."""
    blocks = {"public_info", "music_preferences"}
    if relation in (Relation.friend, Relation.self):
        blocks.add("friends_info")
    if relation is Relation.self:
        blocks.add("private_info")
    return blocks
