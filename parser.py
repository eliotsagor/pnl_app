"""Parse TradeSteward screenshots using Claude API vision."""
import base64
import json
import os
import re

import anthropic


PARSE_PROMPT = """You are reading a TradeSteward strategy P&L screenshot. Extract each strategy line.

Each line has two dollar values followed by a strategy description. The LEFT value is "Strategy Profits" (the daily P&L). The RIGHT value is "Open Premium" (ignore this).

Return ONLY a JSON object with this structure:
{
  "lines": [
    {"label": "MOC no stop", "value": -3330},
    {"label": "Price Action Iron Condor Lite", "value": -1085},
    ...
  ],
  "total": 12345
}

Rules:
- "value" is the LEFT number (Strategy Profits) as a number (negative for losses, positive for gains).
- Use the exact label text as shown in the screenshot, including spelling like "1:1", "$2", "$3", etc.
- If a headline total is shown at the very top of the screenshot (e.g. "$12,616.00 15.51%"), include it as "total". Otherwise omit it.
- Strip dollar signs, commas, and ".00" from values - return integers when possible.
- Return ONLY the JSON, no markdown fences, no explanation."""


def parse_screenshot(image_bytes: bytes, media_type: str = "image/png") -> dict:
    """Send the screenshot to Claude and parse the response.

    Returns: {"lines": [{"label": str, "value": float}, ...], "total": float or None}
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": PARSE_PROMPT},
                ],
            }
        ],
    )

    text = response.content[0].text.strip()
    # Strip code fences if present
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


def aggregate_to_sheets(parsed_lines, label_to_sheet):
    """Convert parsed [{label, value}] into {sheet_name: total_value} using the mapping.

    Returns a tuple of (sheet_values, unmapped_labels).
    """
    sheet_values = {}
    unmapped = []
    for entry in parsed_lines:
        label = entry["label"].strip()
        value = float(entry["value"])
        sheet = label_to_sheet.get(label)
        if sheet is None:
            # Try case-insensitive lookup
            for k, v in label_to_sheet.items():
                if k.lower() == label.lower():
                    sheet = v
                    break
        if sheet is None:
            unmapped.append({"label": label, "value": value})
            continue
        sheet_values[sheet] = sheet_values.get(sheet, 0) + value
    return sheet_values, unmapped
