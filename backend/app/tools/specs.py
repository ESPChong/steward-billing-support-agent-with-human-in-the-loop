"""Tool schemas shown to the LLM. Read tools run inline; write tools are
captured as pending actions and executed only after human approval."""

READ_TOOLS = {
    "get_subscription": {
        "description": "Get the customer's current subscription (tier, status, price, billing period).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "get_invoices": {
        "description": "List all invoices for the current customer, including amounts and statuses.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "search_billing_policies": {
        "description": "Search the internal billing policy knowledge base. Cite the policy title in replies.",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string", "description": "Search query."}},
                       "required": ["query"]},
    },
}

WRITE_TOOLS = {
    "issue_refund": {
        "description": "Issue a refund for one of the customer's invoices. REQUIRES human approval.",
        "parameters": {"type": "object",
                       "properties": {"invoice_id": {"type": "string"},
                                      "amount_cents": {"type": "integer"},
                                      "reason": {"type": "string"}},
                       "required": ["invoice_id", "amount_cents", "reason"]},
    },
    "change_plan": {
        "description": "Upgrade, downgrade, or cancel the customer's subscription. REQUIRES human approval.",
        "parameters": {"type": "object",
                       "properties": {"tier": {"type": "string", "enum": ["free", "starter", "pro", "enterprise"]},
                                      "action": {"type": "string", "enum": ["upgrade", "downgrade", "cancel"]}},
                       "required": ["tier", "action"]},
    },
    "update_billing_email": {
        "description": "Change the customer's billing email address. REQUIRES human approval (PII change).",
        "parameters": {"type": "object",
                       "properties": {"new_email": {"type": "string"}},
                       "required": ["new_email"]},
    },
}

ESCALATE_TOOL = {
    "escalate_to_human": {
        "description": "Hand the conversation to a human billing specialist (out of scope, angry customer, "
                       "or repeated rejections).",
        "parameters": {"type": "object",
                       "properties": {"summary": {"type": "string", "description": "Brief handoff summary."}},
                       "required": ["summary"]},
    },
}


def tool_schemas() -> list[dict]:
    merged = {**READ_TOOLS, **WRITE_TOOLS, **ESCALATE_TOOL}
    return [{"type": "function",
             "function": {"name": name, "description": spec["description"],
                          "parameters": spec["parameters"]}}
            for name, spec in merged.items()]