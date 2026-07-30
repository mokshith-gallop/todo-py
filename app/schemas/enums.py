from enum import Enum


class Priority(str, Enum):
    NONE = "none"
    LOW = "low"
    MED = "med"
    HIGH = "high"
