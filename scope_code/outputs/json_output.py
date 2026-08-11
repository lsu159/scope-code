"""JSON output — serializes a modification plan to JSON.

For machine-readable output: other agents, CI/CD pipelines,
or programmatic consumers of the Scope Code framework.
"""

import json
from pathlib import Path
from typing import Optional

from ..models.plan import ModificationPlan


class JSONOutput:
    """Serializes a ModificationPlan to JSON format.

    Usage:
        output = JSONOutput()
        json_str = output.render(plan)
        output.save(plan, "plan.json")
    """

    def render(
        self,
        plan: ModificationPlan,
        indent: int = 2,
        ensure_ascii: bool = False,
    ) -> str:
        """Render a modification plan as a JSON string.

        Args:
            plan: The modification plan to render.
            indent: JSON indentation level.
            ensure_ascii: Whether to escape non-ASCII characters.

        Returns:
            JSON formatted string.
        """
        data = plan.model_dump()
        return json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)

    def render_dict(self, plan: ModificationPlan) -> dict:
        """Render a modification plan as a Python dict.

        Useful for programmatic consumers that need structured data
        without JSON string serialization overhead.

        Args:
            plan: The modification plan.

        Returns:
            Dict representation of the plan.
        """
        return plan.model_dump()

    def save(
        self,
        plan: ModificationPlan,
        output_path: str,
        indent: int = 2,
    ) -> str:
        """Save the plan as a JSON file.

        Args:
            plan: The modification plan.
            output_path: Path to write the JSON file.
            indent: JSON indentation level.

        Returns:
            Absolute path to the saved file.
        """
        content = self.render(plan, indent=indent)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path.resolve())

    def load(self, path: str) -> ModificationPlan:
        """Load a JSON file back into a ModificationPlan.

        Args:
            path: Path to a JSON file previously saved by this class.

        Returns:
            Reconstituted ModificationPlan.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return ModificationPlan.model_validate(data)
