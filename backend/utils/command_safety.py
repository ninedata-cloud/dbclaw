import re
from typing import Optional


DANGEROUS_COMMAND_PATTERNS = [
    "rm",
    "rmdir",
    "del",
    "delete",
    "mv",
    "move",
    "chmod",
    "chown",
    "chgrp",
    "kill",
    "pkill",
    "killall",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "mkfs",
    "fdisk",
    "parted",
    "dd",
    "iptables",
    "firewall",
    "useradd",
    "userdel",
    "usermod",
    "groupadd",
    "groupdel",
    ">>",
    "tee",
    "wget",
    "curl -o",
    "apt install",
    "yum install",
    "dnf install",
    "systemctl stop",
    "systemctl start",
    "systemctl restart",
    "service stop",
    "service start",
    "service restart",
]

DESTRUCTIVE_COMMAND_PATTERNS = {
    "rm",
    "rmdir",
    "del",
    "delete",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "mkfs",
    "fdisk",
    "parted",
    "dd",
}

READ_ONLY_COMMAND_HINTS = {
    "df",
    "du",
    "free",
    "ps",
    "top",
    "htop",
    "iostat",
    "vmstat",
    "sar",
    "ss",
    "netstat",
    "journalctl",
    "tail",
    "cat",
    "uptime",
    "hostname",
    "lsblk",
    "mount",
    "dmesg",
    "sysctl",
}

BENIGN_COMMAND_HINTS = {"echo", "printf", "true", "false", "test", "[", "grep", "head", "wc"}

STRICTLY_BLOCKED_COMMAND_PATTERNS = [
    "rm",
    "rmdir",
    "mkfs",
    "dd",
    "shutdown",
    "reboot",
    "poweroff",
    "init",
    "halt",
    "kill -9",
    "killall",
    "pkill",
    "mv",
    "cp",
    "chmod",
    "chown",
    "useradd",
    "userdel",
    "passwd",
    "iptables",
    "systemctl stop",
    "systemctl disable",
    "service stop",
    "> /dev/",
    "fdisk",
    "parted",
    "wipefs",
]


def split_command_segments(command: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"\|\||&&|[;|\n]", command) if segment.strip()]


def extract_base_command(segment: str) -> str:
    cleaned = re.sub(r"^\d?>\S+\s*", "", segment).strip()
    if not cleaned:
        return ""
    token = re.split(r"\s+", cleaned, maxsplit=1)[0]
    return token.lower()


def command_pattern_matches(command_lower: str, pattern: str) -> bool:
    normalized = pattern.strip().lower()
    if not normalized:
        return False
    if normalized in {">>", "> /dev/"}:
        return normalized in command_lower

    tokens = re.split(r"\s+", normalized)
    phrase = r"\s+".join(re.escape(token) for token in tokens)
    return re.search(rf"(^|[\s;|&()]){phrase}(?=$|[\s;|&()])", command_lower) is not None


def looks_clearly_read_only_command(command: str) -> bool:
    segments = split_command_segments(command.lower())
    if not segments:
        return False

    allowed_commands = READ_ONLY_COMMAND_HINTS | BENIGN_COMMAND_HINTS
    for segment in segments:
        base_command = extract_base_command(segment)
        if not base_command or base_command not in allowed_commands:
            return False
    return True


def first_matching_command_pattern(command: str, patterns: list[str]) -> Optional[str]:
    command_lower = command.lower()
    for pattern in patterns:
        if command_pattern_matches(command_lower, pattern):
            return pattern
    return None
