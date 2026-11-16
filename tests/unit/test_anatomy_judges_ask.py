import asyncio

from engine.original.judges import _Base


class Boom(_Base):
    name = "boom"

    async def _ask(self, image, prompt):
        raise RuntimeError("judge offline")


class Echo(_Base):
    name = "echo"

    async def _ask(self, image, prompt):
        return f"seen {prompt}"


def test_ask_returns_the_judges_text():
    assert asyncio.run(Echo().ask(b"x", "how many arms?")) == "seen how many arms?"


def test_ask_never_raises_and_returns_empty_text_when_the_judge_fails():
    assert asyncio.run(Boom().ask(b"x", "how many arms?")) == ""
