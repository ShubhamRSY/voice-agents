"""Parse TwiML responses into UI-friendly JSON."""

import xml.etree.ElementTree as ET


def parse_twiml(twiml: str) -> dict:
    try:
        root = ET.fromstring(twiml)
    except ET.ParseError:
        return {"spoken_responses": [], "transfer_to": None, "listening": False, "actions": []}

    spoken: list[str] = []
    actions: list[str] = []
    transfer_to: str | None = None
    listening = False

    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "Say" and elem.text:
            spoken.append(elem.text.strip())
            actions.append(f"Say: {elem.text.strip()}")
        elif tag == "Gather":
            listening = True
            actions.append("Gather: listening for speech")
        elif tag == "Dial":
            number = (elem.text or "").strip()
            transfer_to = number or elem.get("number")
            actions.append(f"Dial: transfer to {transfer_to or 'agent'}")
        elif tag == "Redirect":
            actions.append(f"Redirect: {elem.text or elem.get('url', '')}")
        elif tag == "Hangup":
            actions.append("Hangup: end call")

    return {
        "spoken_responses": spoken,
        "agent_says": " ".join(spoken),
        "transfer_to": transfer_to,
        "listening": listening,
        "actions": actions,
    }
