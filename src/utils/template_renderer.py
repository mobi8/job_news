#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

# Template directory path
TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"


def get_template_env() -> Environment:
    """Create and return Jinja2 environment for template rendering."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,  # We handle HTML escaping manually in notifications
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_template(template_path: str, context: Dict[str, Any]) -> str:
    """
    Render a template with the given context.

    Args:
        template_path: Path to template relative to templates/ (e.g., "telegram/job_alert.txt")
        context: Dictionary of variables to pass to the template

    Returns:
        Rendered template string

    Raises:
        TemplateNotFound: If template file does not exist
    """
    env = get_template_env()
    try:
        template = env.get_template(template_path)
        return template.render(context)
    except TemplateNotFound:
        raise TemplateNotFound(
            f"Template not found: {template_path} (looked in {TEMPLATE_DIR})"
        )
