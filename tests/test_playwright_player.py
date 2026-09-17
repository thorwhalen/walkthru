"""The Playwright CommandPlayer: the vocabulary, the table seam, and unknown commands.

Driven against a fake page, so no browser is needed.
"""

import pytest

from walkthru.adapters.playwright import (
    PAGE_COMMANDS,
    PlaywrightCommandPlayer,
    UnknownCommandError,
)
from walkthru.core.schema import Command


class FakeKeyboard:
    def __init__(self, log):
        self._log = log

    async def press(self, key):
        self._log.append(("press", key))


class FakeLocator:
    def __init__(self, log, selector):
        self._log, self._selector = log, selector

    async def scroll_into_view_if_needed(self):
        self._log.append(("scroll_into_view", self._selector))


class FakePage:
    def __init__(self):
        self.calls = []
        self.keyboard = FakeKeyboard(self.calls)

    async def goto(self, url, **kw):
        self.calls.append(("goto", url, kw))

    async def hover(self, selector, **kw):
        self.calls.append(("hover", selector, kw))

    async def click(self, selector, **kw):
        self.calls.append(("click", selector, kw))

    async def fill(self, selector, text, **kw):
        self.calls.append(("fill", selector, text))

    async def evaluate(self, expression, arg=None):
        self.calls.append(("evaluate", expression, arg))
        return "evaluated"

    async def wait_for_selector(self, selector, **kw):
        self.calls.append(("wait_for_selector", selector))

    async def set_viewport_size(self, size):
        self.calls.append(("viewport", size))

    def locator(self, selector):
        return FakeLocator(self.calls, selector)


@pytest.fixture
def page():
    return FakePage()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command,expected",
    [
        (Command(id="page.goto", params={"url": "https://x.dev"}), ("goto", "https://x.dev", {})),
        (Command(id="page.hover", params={"selector": "mark"}), ("hover", "mark", {})),
        (Command(id="page.click", params={"selector": "#b"}), ("click", "#b", {})),
        (Command(id="page.fill", params={"selector": "#i", "text": "hi"}), ("fill", "#i", "hi")),
        (Command(id="page.press", params={"key": "Enter"}), ("press", "Enter")),
        (Command(id="page.wait_for", params={"selector": ".ready"}), ("wait_for_selector", ".ready")),
        (Command(id="page.scroll", params={"selector": "#x"}), ("scroll_into_view", "#x")),
    ],
)
async def test_the_default_vocabulary_reaches_the_page(page, command, expected):
    await PlaywrightCommandPlayer(page).play(command)
    assert page.calls == [expected]


@pytest.mark.asyncio
async def test_extra_params_pass_through(page):
    """`timeout`, `force` and friends belong to the caller, not to the adapter."""
    await PlaywrightCommandPlayer(page).play(
        Command(id="page.hover", params={"selector": "mark", "timeout": 5000})
    )
    assert page.calls == [("hover", "mark", {"timeout": 5000})]


@pytest.mark.asyncio
async def test_set_viewport_coerces_to_the_playwright_shape(page):
    await PlaywrightCommandPlayer(page).play(
        Command(id="page.set_viewport", params={"width": "900", "height": "600"})
    )
    assert page.calls == [("viewport", {"width": 900, "height": 600})]


@pytest.mark.asyncio
async def test_wait_actually_waits(page):
    import time

    start = time.perf_counter()
    await PlaywrightCommandPlayer(page).play(Command(id="page.wait", params={"ms": 60}))
    assert time.perf_counter() - start >= 0.05
    assert page.calls == []


@pytest.mark.asyncio
async def test_an_unknown_command_raises_and_names_what_it_knows(page):
    with pytest.raises(UnknownCommandError, match="page.hover"):
        await PlaywrightCommandPlayer(page).play(Command(id="app.nope"))


@pytest.mark.asyncio
async def test_unknown_commands_can_be_skipped_deliberately(page):
    player = PlaywrightCommandPlayer(page, on_unknown="skip")
    assert await player.play(Command(id="app.nope")) is None
    assert page.calls == []


def test_on_unknown_is_validated(page):
    with pytest.raises(ValueError, match="on_unknown"):
        PlaywrightCommandPlayer(page, on_unknown="explode")


@pytest.mark.asyncio
async def test_the_command_table_is_a_seam(page):
    """An app extends the vocabulary without the adapter knowing about it."""
    seen = []

    async def save(page_, params):
        seen.append(params)
        return "saved"

    player = PlaywrightCommandPlayer(page, commands={**PAGE_COMMANDS, "app.save": save})
    assert await player.play(Command(id="app.save", params={"path": "/tmp/x"})) == "saved"
    assert seen == [{"path": "/tmp/x"}]
    await player.play(Command(id="page.hover", params={"selector": "m"}))  # still works
    assert page.calls == [("hover", "m", {})]


def test_known_lists_the_vocabulary(page):
    known = PlaywrightCommandPlayer(page).known
    assert "page.goto" in known and "page.hover" in known
    assert known == tuple(sorted(known))
