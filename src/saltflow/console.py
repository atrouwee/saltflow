"""How the tool talks, kept small.

  * a line the tool prints is a receipt: a mark, a label, the fact;
  * dress the output only when a human is watching; piped output stays plain.
"""
import os
import sys

AMBER, GREY, RED, GREEN, BOLD, RESET = ("\033[38;5;214m", "\033[38;5;245m", "\033[38;5;203m",
                                        "\033[38;5;114m", "\033[1m", "\033[0m")
COL = 10                                   # width of the label column


def interactive():
    return sys.stdout.isatty() and os.environ.get("TERM", "") not in ("", "dumb")


def _c(code, text):
    return f"{code}{text}{RESET}" if interactive() else text


def receipt(label, text, tone="accent"):
    """`◆ label      text` -- the unit of output."""
    mark = _c({"bad": RED, "good": GREEN, "quiet": GREY}.get(tone, AMBER), "◆")
    print(f"  {mark} {_c(GREY, label.ljust(COL))} {text}")


def note(text):
    print(f"  {' ' * COL}  {_c(GREY, text)}")


def step(title):
    print(f"\n{_c(BOLD, title)}")


def fail(text, *details):
    print(f"\n  {_c(RED, '!!')} {text}", file=sys.stderr)
    for d in details:
        print(f"      {d}", file=sys.stderr)
    sys.exit(1)
