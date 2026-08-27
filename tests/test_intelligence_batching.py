from app.core.model_router import LLMError
from app.intelligence.batching import PostItem, run_in_batches


def _items(n: int) -> list[PostItem]:
    return [
        PostItem(post_id=i + 1, index=i, content=f"post {i}", media_type="text") for i in range(n)
    ]


def test_happy_path_one_call_per_batch():
    calls: list[int] = []

    def call(batch):
        calls.append(len(batch))
        return {it.index: f"r{it.index}" for it in batch}

    results, errors = run_in_batches(_items(10), batch_size=10, call=call, task="t")
    assert calls == [10]
    assert errors == {}
    assert len(results) == 10


def test_batch_failure_falls_back_to_per_post_once():
    seen: list[int] = []

    def call(batch):
        seen.append(len(batch))
        if len(batch) > 1:
            raise LLMError("batch blew up")
        it = batch[0]
        return {it.index: f"r{it.index}"}

    results, errors = run_in_batches(_items(3), batch_size=3, call=call, task="t")
    assert seen == [3, 1, 1, 1]  # one batch attempt, then per-post
    assert errors == {}
    assert results == {0: "r0", 1: "r1", 2: "r2"}


def test_partial_batch_response_triggers_fallback():
    def call(batch):
        if len(batch) > 1:
            return {batch[0].index: "only-first"}  # omits the rest
        it = batch[0]
        return {it.index: f"r{it.index}"}

    results, _ = run_in_batches(_items(3), batch_size=3, call=call, task="t")
    assert results == {0: "r0", 1: "r1", 2: "r2"}


def test_persistent_per_post_failure_is_recorded_not_raised():
    def call(batch):
        if len(batch) > 1:
            raise LLMError("batch fail")
        if batch[0].index == 1:
            raise LLMError("post 1 always fails")
        it = batch[0]
        return {it.index: f"r{it.index}"}

    results, errors = run_in_batches(_items(3), batch_size=3, call=call, task="t")
    assert set(results) == {0, 2}
    assert 1 in errors and "post 1 always fails" in errors[1]
