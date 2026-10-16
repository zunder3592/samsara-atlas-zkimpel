from typing import Callable, Any

ToolFunc = Callable[..., Any]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolFunc] = {}

    def register(self, name: str, func: ToolFunc) -> None:
        self._tools[name] = func

    def get(self, name: str) -> ToolFunc | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def execute(self, name: str, **kwargs) -> Any:
        func = self.get(name)
        if func is None:
            raise ValueError(f"Unknown tool: {name}")
        return func(**kwargs)


_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        from app.tools.hris import retrieve_employee_context, post_case_note_to_hris
        from app.tools.retrieval import retrieve_policy_snippets
        _registry.register("retrieve_employee_context", retrieve_employee_context)
        _registry.register("retrieve_policy_snippets", retrieve_policy_snippets)
        _registry.register("post_case_note_to_hris", post_case_note_to_hris)
    return _registry
