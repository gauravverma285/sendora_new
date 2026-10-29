def build_template_components(header=None, body_params=None, button_params=None):
    """Build the Meta `template.components` array for a template send,
    from plain values an external caller supplies directly (not the
    HTML-form-shaped `final_data` the in-app campaign wizard uses)."""
    components = []

    if header:
        media_type = header["type"]
        media_obj = {"id": header["id"]}
        if header.get("filename"):
            media_obj["filename"] = header["filename"]
        components.append({
            "type": "HEADER",
            "parameters": [{"type": media_type, media_type: media_obj}],
        })

    if body_params:
        components.append({
            "type": "BODY",
            "parameters": [{"type": "text", "text": str(value)} for value in body_params],
        })

    for button in (button_params or []):
        if button["sub_type"] == "url":
            components.append({
                "type": "BUTTON",
                "sub_type": "url",
                "index": button["index"],
                "parameters": [{"type": "text", "text": button["value"]}],
            })
        elif button["sub_type"] == "copy_code":
            components.append({
                "type": "BUTTON",
                "sub_type": "copy_code",
                "index": button["index"],
                "parameters": [{"type": "coupon_code", "coupon_code": button["value"]}],
            })

    return components


def build_whatsapp_payload(to, template_name, language, header=None, body_params=None, button_params=None):
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": build_template_components(header, body_params, button_params),
        },
    }
