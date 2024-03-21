import json
from functools import partial
from typing import Any, List, Literal, Optional, Sequence, TypedDict, Union

import httpx
import respx

from openai.pagination import SyncCursorPage
from openai.types.beta.assistant import Assistant
from openai.types.beta.assistant_tool_param import AssistantToolParam

from openai.types.beta.thread import Thread
from openai.types.beta.thread_deleted import ThreadDeleted
from openai.types.beta.thread_update_params import ThreadUpdateParams
from openai.types.beta.thread_create_params import (
    ThreadCreateParams,
    Message as ThreadMessageCreateParams,
)

from openai.types.beta.threads.text import Text
from openai.types.beta.threads.text_content_block import TextContentBlock

from openai.types.beta.threads.message import Message
from openai.types.beta.threads.message_create_params import MessageCreateParams
from openai.types.beta.threads.message_update_params import MessageUpdateParams

from openai.types.beta.threads.run import Run, LastError, RequiredAction, Usage
from openai.types.beta.threads.run_status import RunStatus
from openai.types.beta.threads.run_create_params import RunCreateParams

from ._base import StatefulMock, CallContainer
from .assistants import AssistantsMock
from ..decorators import side_effect
from ..state import StateStore
from ..utils import model_dict, model_parse, utcnow_unix_timestamp_s

__all__ = ["ThreadsMock", "MessagesMock", "RunsMock"]


class ThreadsMock(StatefulMock):
    def __init__(self) -> None:
        super().__init__()
        self.url = self.BASE_URL + "/threads"
        self.create = CallContainer()
        self.retrieve = CallContainer()
        self.update = CallContainer()
        self.delete = CallContainer()

        self.messages = MessagesMock()
        self.runs = RunsMock()

    def _register_routes(self, **common: Any) -> None:
        self.create.route = respx.post(url__regex=self.url).mock(
            side_effect=partial(self._create, **common)
        )
        self.retrieve.route = respx.get(url__regex=self.url + r"/(?P<id>\w+)").mock(
            side_effect=partial(self._retrieve, **common)
        )
        self.update.route = respx.post(url__regex=self.url + r"/(?P<id>\w+)").mock(
            side_effect=partial(self._update, **common)
        )
        self.delete.route = respx.delete(url__regex=self.url + r"/(?P<id>\w+)").mock(
            side_effect=partial(self._delete, **common)
        )

    def __call__(
        self,
        *,
        latency: Optional[float] = None,
        failures: Optional[int] = None,
        state_store: Optional[StateStore] = None,
    ):
        def getter(*args: Any, **kwargs: Any):
            return dict(
                latency=latency or 0,
                failures=failures or 0,
                state_store=kwargs["used_state"],
            )

        return self._make_decorator("threads_mock", getter, state_store or StateStore())

    @side_effect
    def _create(
        self,
        request: httpx.Request,
        route: respx.Route,
        state_store: StateStore,
        **kwargs: Any,
    ) -> httpx.Response:
        self.create.route = route

        content: ThreadCreateParams = json.loads(request.content)

        thread = Thread(
            id=self._faker.beta.thread.id(),
            created_at=utcnow_unix_timestamp_s(),
            metadata=content.get("metadata"),
            object="thread",
        )
        messages = [
            self.messages._parse_message_create_params(thread.id, m)
            for m in content.get("messages", [])
        ]

        state_store.beta.threads.put(thread)
        for message in messages:
            state_store.beta.threads.messages.put(message)

        return httpx.Response(status_code=201, json=model_dict(thread))

    @side_effect
    def _retrieve(
        self,
        request: httpx.Request,
        route: respx.Route,
        id: str,
        state_store: StateStore,
        **kwargs: Any,
    ) -> httpx.Response:
        self.retrieve.route = route

        *_, id = request.url.path.split("/")
        thread = state_store.beta.threads.get(id)

        if not thread:
            return httpx.Response(status_code=404)

        else:
            return httpx.Response(status_code=200, json=model_dict(thread))

    @side_effect
    def _update(
        self,
        request: httpx.Request,
        route: respx.Route,
        id: str,
        state_store: StateStore,
        **kwargs: Any,
    ) -> httpx.Response:
        self.update.route = route

        *_, id = request.url.path.split("/")
        content: ThreadUpdateParams = json.loads(request.content)

        thread = state_store.beta.threads.get(id)

        if not thread:
            return httpx.Response(status_code=404)

        thread.metadata = content.get("metadata", thread.metadata)

        state_store.beta.threads.put(thread)

        return httpx.Response(status_code=200, json=model_dict(thread))

    @side_effect
    def _delete(
        self,
        request: httpx.Request,
        route: respx.Route,
        id: str,
        state_store: StateStore,
        **kwargs: Any,
    ) -> httpx.Response:
        self.delete.route = route

        *_, id = request.url.path.split("/")
        deleted = state_store.beta.threads.delete(id)

        return httpx.Response(
            status_code=200,
            json=model_dict(
                ThreadDeleted(id=id, deleted=deleted, object="thread.deleted")
            ),
        )


class MessagesMock(StatefulMock):
    def __init__(self) -> None:
        super().__init__()
        self.url = self.BASE_URL + r"/threads/(?P<thread_id>\w+)/messages"
        self.create = CallContainer()
        self.list = CallContainer()
        self.retrieve = CallContainer()
        self.update = CallContainer()

    def _register_routes(self, **common: Any) -> None:
        self.retrieve.route = respx.get(url__regex=self.url + r"/(?P<id>\w+)").mock(
            side_effect=partial(self._retrieve, **common)
        )
        self.update.route = respx.post(url__regex=self.url + r"/(?P<id>\w+)").mock(
            side_effect=partial(self._update, **common)
        )
        self.create.route = respx.post(url__regex=self.url).mock(
            side_effect=partial(self._create, **common)
        )
        self.list.route = respx.get(url__regex=self.url).mock(
            side_effect=partial(self._list, **common)
        )

    def __call__(
        self,
        *,
        latency: Optional[float] = None,
        failures: Optional[int] = None,
        state_store: Optional[StateStore] = None,
        validate_thread_exists: Optional[bool] = None,
    ):
        def getter(*args: Any, **kwargs: Any):
            return dict(
                latency=latency or 0,
                failures=failures or 0,
                state_store=kwargs["used_state"],
                validate_thread_exists=validate_thread_exists or False,
            )

        return self._make_decorator(
            "messages_mock", getter, state_store or StateStore()
        )

    @side_effect
    def _create(
        self,
        request: httpx.Request,
        route: respx.Route,
        thread_id: str,
        state_store: StateStore,
        validate_thread_exists: bool,
        **kwargs: Any,
    ) -> httpx.Response:
        self.create.route = route

        if validate_thread_exists:
            thread = state_store.beta.threads.get(thread_id)

            if not thread:
                return httpx.Response(status_code=404)

        content: MessageCreateParams = json.loads(request.content)
        message = self._parse_message_create_params(thread_id, content)

        state_store.beta.threads.messages.put(message)

        return httpx.Response(status_code=201, json=model_dict(message))

    @side_effect
    def _list(
        self,
        request: httpx.Request,
        route: respx.Route,
        thread_id: str,
        state_store: StateStore,
        validate_thread_exists: bool,
        **kwargs: Any,
    ) -> httpx.Response:
        self.list.route = route

        if validate_thread_exists:
            thread = state_store.beta.threads.get(thread_id)

            if not thread:
                return httpx.Response(status_code=404)

        limit = request.url.params.get("limit")
        order = request.url.params.get("order")
        after = request.url.params.get("after")
        before = request.url.params.get("before")

        messages = SyncCursorPage[Message](
            data=state_store.beta.threads.messages.list(
                thread_id,
                limit,
                order,
                after,
                before,
            )
        )

        return httpx.Response(status_code=200, json=model_dict(messages))

    @side_effect
    def _retrieve(
        self,
        request: httpx.Request,
        route: respx.Route,
        thread_id: str,
        id: str,
        state_store: StateStore,
        validate_thread_exists: bool,
        **kwargs: Any,
    ) -> httpx.Response:
        self.retrieve.route = route

        if validate_thread_exists:
            thread = state_store.beta.threads.get(thread_id)

            if not thread:
                return httpx.Response(status_code=404)

        *_, id = request.url.path.split("/")
        message = state_store.beta.threads.messages.get(id)

        if not message:
            return httpx.Response(status_code=404)

        else:
            return httpx.Response(status_code=200, json=model_dict(message))

    @side_effect
    def _update(
        self,
        request: httpx.Request,
        route: respx.Route,
        thread_id: str,
        id: str,
        state_store: StateStore,
        validate_thread_exists: bool,
        **kwargs: Any,
    ) -> httpx.Response:
        self.update.route = route

        if validate_thread_exists:
            thread = state_store.beta.threads.get(thread_id)

            if not thread:
                return httpx.Response(status_code=404)

        *_, id = request.url.path.split("/")
        content: MessageUpdateParams = json.loads(request.content)

        message = state_store.beta.threads.messages.get(id)

        if not message:
            return httpx.Response(status_code=404)

        message.metadata = content.get("metadata", message.metadata)

        state_store.beta.threads.messages.put(message)

        return httpx.Response(status_code=200, json=model_dict(message))

    def _parse_message_create_params(
        self,
        thread_id: str,
        create_message: Union[ThreadMessageCreateParams, MessageCreateParams],
    ) -> Message:
        return Message(
            id=self._faker.beta.thread.message.id(),
            content=[
                TextContentBlock(
                    text=Text(annotations=[], value=create_message["content"]),
                    type="text",
                )
            ],
            created_at=utcnow_unix_timestamp_s(),
            file_ids=create_message.get("file_ids", []),
            object="thread.message",
            role=create_message["role"],
            status="completed",
            thread_id=thread_id,
        )


class PartialFunction(TypedDict):
    name: str
    arguments: str


class PartialRequiredActionFunctionToolCall(TypedDict):
    id: str
    function: PartialFunction
    type: Literal["function"]


class PartialRequiredActionSubmitToolOutputs(TypedDict):
    tool_calls: List[PartialRequiredActionFunctionToolCall]


class PartialRequiredAction(TypedDict):
    submit_tool_outputs: PartialRequiredActionSubmitToolOutputs
    type: Literal["submit_tool_outputs"]


class PartialLastError(TypedDict, total=False):
    code: Literal["server_error", "rate_limit_exceeded", "invalid_prompt"]
    message: str


class PartialRun(TypedDict, total=False):
    status: RunStatus
    required_action: PartialRequiredAction
    last_error: PartialLastError
    expires_at: int
    started_at: int
    cancelled_at: int
    failed_at: int
    completed_at: int
    model: str
    instructions: str
    tools: List[AssistantToolParam]
    file_ids: List[str]


class MultiMethodSequence(TypedDict, total=False):
    create: Sequence[PartialRun]
    retrieve: Sequence[PartialRun]


class RunsMock(StatefulMock):
    def __init__(self) -> None:
        super().__init__()
        self.url = self.BASE_URL + r"/threads/(?P<thread_id>\w+)/runs"
        self.create = CallContainer()
        self.list = CallContainer()
        self.retrieve = CallContainer()
        self.update = CallContainer()

    def _register_routes(self, **common: Any) -> None:
        self.retrieve.route = respx.get(url__regex=self.url + r"/(?P<id>\w+)").mock(
            side_effect=partial(self._retrieve, **common)
        )
        self.create.route = respx.post(url__regex=self.url).mock(
            side_effect=partial(self._create, **common)
        )
        self.list.route = respx.get(url__regex=self.url).mock(
            side_effect=partial(self._list, **common)
        )

    def __call__(
        self,
        *,
        sequence: Optional[MultiMethodSequence] = None,
        latency: Optional[float] = None,
        failures: Optional[int] = None,
        state_store: Optional[StateStore] = None,
        validate_thread_exists: Optional[bool] = None,
        validate_assistant_exists: Optional[bool] = None,
    ):
        def getter(*args: Any, **kwargs: Any):
            return dict(
                sequence=sequence or {},
                latency=latency or 0,
                failures=failures or 0,
                state_store=kwargs["used_state"],
                validate_thread_exists=validate_thread_exists or False,
                validate_assistant_exists=validate_assistant_exists or False,
            )

        return self._make_decorator("runs_mock", getter, state_store or StateStore())

    @side_effect
    def _create(
        self,
        request: httpx.Request,
        route: respx.Route,
        thread_id: str,
        sequence: MultiMethodSequence,
        state_store: StateStore,
        validate_thread_exists: bool,
        validate_assistant_exists: bool,
        **kwargs: Any,
    ) -> httpx.Response:
        self.create.route = route
        failures: int = kwargs.get("failures", 0)

        if validate_thread_exists:
            thread = state_store.beta.threads.get(thread_id)

            if not thread:
                return httpx.Response(status_code=404)

        content: RunCreateParams = json.loads(request.content)

        partial_run = (
            self._next_partial_run(sequence, route.call_count, failures, "create") or {}
        )
        if validate_assistant_exists:
            asst = state_store.beta.assistants.get(content["assistant_id"])

            if not asst:
                return httpx.Response(status_code=404)

            partial_run = self._merge_partial_run_with_assistant(partial_run, asst)

        run = Run(
            id=self._faker.beta.thread.run.id(),
            object="thread.run",
            created_at=utcnow_unix_timestamp_s(),
            thread_id=thread_id,
            assistant_id=content["assistant_id"],
            status=partial_run.get("status", "queued"),
            required_action=model_parse(
                RequiredAction,
                partial_run.get("required_action"),
            ),
            last_error=model_parse(
                LastError,
                partial_run.get("last_error"),
            ),
            expires_at=partial_run.get("expires_at"),
            started_at=partial_run.get("started_at"),
            cancelled_at=partial_run.get("cancelled_at"),
            failed_at=partial_run.get("failed_at"),
            completed_at=partial_run.get("completed_at"),
            model=partial_run.get("model", "gpt-3.5-turbo"),
            instructions=partial_run.get("instructions", ""),
            tools=AssistantsMock._parse_tool_params(partial_run.get("tools", [])),
            file_ids=partial_run.get("file_ids", []),
            metadata=content.get("metadata"),
            usage=Usage(
                completion_tokens=0,
                prompt_tokens=0,
                total_tokens=0,
            ),
        )

        state_store.beta.threads.runs.put(run)

        return httpx.Response(status_code=201, json=model_dict(run))

    def _retrieve(
        self,
        request: httpx.Request,
        route: respx.Route,
        thread_id: str,
        id: str,
        sequence: MultiMethodSequence,
        state_store: StateStore,
        validate_thread_exists: bool,
        validate_assistant_exists: bool,
        **kwargs: Any,
    ) -> httpx.Response:
        self.retrieve.route = route
        failures: int = kwargs.get("failures", 0)

        if validate_thread_exists:
            thread = state_store.beta.threads.get(thread_id)

            if not thread:
                return httpx.Response(status_code=404)

        *_, id = request.url.path.split("/")
        run = state_store.beta.threads.runs.get(id)

        if not run:
            return httpx.Response(status_code=404)

        partial_run = (
            self._next_partial_run(sequence, route.call_count, failures, "retrieve")
            or {}
        )

        if validate_assistant_exists:
            asst = state_store.beta.assistants.get(run.assistant_id)
            if asst:
                partial_run = self._merge_partial_run_with_assistant(partial_run, asst)

        run.status = partial_run.get("status", run.status)
        run.expires_at = partial_run.get("expires_at", run.expires_at)
        run.started_at = partial_run.get("started_at", run.started_at)
        run.cancelled_at = partial_run.get("cancelled_at", run.cancelled_at)
        run.failed_at = partial_run.get("failed_at", run.failed_at)
        run.completed_at = partial_run.get("completed_at", run.completed_at)
        run.model = partial_run.get("model", run.model)
        run.instructions = partial_run.get("instructions", run.instructions)
        run.file_ids = partial_run.get("file_ids", run.file_ids)

        if partial_run.get("required_action"):
            run.required_action = model_parse(
                RequiredAction, partial_run.get("required_action")
            )

        if partial_run.get("last_error"):
            run.last_error = model_parse(LastError, partial_run.get("last_error"))

        if partial_run.get("tools"):
            run.tools = AssistantsMock._parse_tool_params(partial_run.get("tools", []))

        state_store.beta.threads.runs.put(run)

        return httpx.Response(status_code=200, json=model_dict(run))

    def _list(
        self,
        request: httpx.Request,
        route: respx.Route,
        thread_id: str,
        sequence: MultiMethodSequence,
        state_store: StateStore,
        validate_thread_exists: bool,
        validate_assistant_exists: bool,
        **kwargs: Any,
    ):
        self.list.route = route

        if validate_thread_exists:
            thread = state_store.beta.threads.get(thread_id)

            if not thread:
                return httpx.Response(status_code=404)

        if validate_assistant_exists:
            # TODO: what should be done here?
            pass

        if sequence:
            # TODO: should there be a method sequence for list?
            pass

        limit = request.url.params.get("limit")
        order = request.url.params.get("order")
        after = request.url.params.get("after")
        before = request.url.params.get("before")

        runs = SyncCursorPage[Run](
            data=state_store.beta.threads.runs.list(
                thread_id, limit, order, after, before
            )
        )

        return httpx.Response(status_code=200, json=model_dict(runs))

    @staticmethod
    def _next_partial_run(
        sequence: MultiMethodSequence,
        call_count: int,
        failures: int,
        method: Literal["create", "retrieve"],
    ) -> Optional[PartialRun]:
        used_sequence = sequence.get(method, [])
        net_ix = call_count - failures
        try:
            return used_sequence[net_ix]
        except IndexError:
            return None

    @staticmethod
    def _merge_partial_run_with_assistant(
        run: Optional[PartialRun], asst: Assistant
    ) -> PartialRun:
        if not run:
            return {
                "file_ids": asst.file_ids,
                "instructions": asst.instructions or "",
                "model": asst.model,
                "tools": model_dict(asst.tools),  # type: ignore
            }
        else:
            return {
                "file_ids": run.get("file_ids", asst.file_ids),
                "instructions": run.get("instructions", asst.instructions or ""),
                "model": run.get("model", asst.model),
                "tools": run.get("tools", model_dict(asst.tools)),  # type: ignore
            }
