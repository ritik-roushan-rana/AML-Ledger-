"""Free-text questions answered by tool use.

This is the autonomous counterpart to agent.gather(): the analyst asks
"does money from 11-800924840 come back to it?" and the LLM decides
which ToolBox tools to call -- graph_search, find_cycles, shap_explanation
-- reads the results, and answers. Same guard-rails as narrate():
figures come only from tool output, and every call is recorded so the
answer is auditable.

The loop is manual (automatic function calling disabled) so we control
the tool set, cap the number of rounds, and keep the trace.
"""
import json
import time

from ml import config
from ml.agent import tools as tools_mod

log = config.get_logger("agent.ask")

MAX_ROUNDS = 8

SYSTEM = """You are an AML investigation analyst's assistant at a European bank.

You answer questions about transactions and accounts by CALLING TOOLS.
Never state a figure, score, rule, or relationship you did not obtain
from a tool result in this conversation. If a tool returns an error or
nothing, say so; do not guess.

Guidance:
- txn_id is an integer; account ids look like "11-800924840".
- For "why is X risky" use risk_lookup, rule_check and shap_explanation.
- For "where did the money go", "who does X deal with", "is there a
  cycle / ring" use the graph tools (graph_search, money_flow,
  find_cycles, community_detection, path_analysis).
- Call several tools if the question needs them. Stop when you have
  enough to answer.
- Describe behaviour, never assert guilt: "consistent with", "warrants
  review". Plain professional English, short paragraphs, no headings.
- End with one line: which tools you relied on."""

_JSON_TYPES = {"integer": "INTEGER", "string": "STRING", "number": "NUMBER",
               "boolean": "BOOLEAN"}


def declarations():
    """ToolBox SPECS -> Gemini FunctionDeclarations."""
    from google.genai import types
    out = []
    for name, desc, params in tools_mod.SPECS:
        props = {k: {"type": _JSON_TYPES.get(v, "STRING")} for k, v in params.items()}
        # trailing optional knobs (limit, hops, top, hours) are not required
        required = [k for k in params if k in ("txn_id", "account", "a", "b")]
        out.append(types.FunctionDeclaration(
            name=name, description=desc,
            parameters={"type": "OBJECT", "properties": props, "required": required}))
    return out


def _call(tools, name: str, args: dict):
    fn = getattr(tools, name, None)
    if fn is None or name not in {s[0] for s in tools_mod.SPECS}:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**args)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:                       # neo4j down, etc.
        return {"error": f"{type(e).__name__}: {e}"}


def ask(tools, question: str, context: dict | None = None,
        model: str | None = None, on_call=None) -> dict:
    """Returns {"answer", "trace": [{tool, args, result, ms}], "rounds"}.
    `on_call(entry)` fires after each tool call so a caller can show
    progress before the answer lands."""
    key = config.gemini_key()
    if not key or key == "your_key_here":
        raise RuntimeError("GEMINI_API_KEY not set -- the ask agent needs an LLM")
    model = model or config.gemini_model()

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=[types.Tool(function_declarations=declarations())],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.1,
        max_output_tokens=1500,
    )

    prompt = question
    if context:
        prompt = f"Context: {json.dumps(context)}\n\nQuestion: {question}"
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]

    trace = []
    for rnd in range(1, MAX_ROUNDS + 1):
        resp = client.models.generate_content(model=model, contents=contents, config=cfg)
        cand = resp.candidates[0]
        contents.append(cand.content)

        calls = [p.function_call for p in (cand.content.parts or []) if p.function_call]
        if not calls:
            text = "".join(p.text or "" for p in (cand.content.parts or [])).strip()
            log.info("answered in %d round(s), %d tool call(s)", rnd, len(trace))
            return {"answer": text, "trace": trace, "rounds": rnd}

        parts = []
        for fc in calls:
            args = dict(fc.args or {})
            t0 = time.perf_counter()
            result = _call(tools, fc.name, args)
            ms = round((time.perf_counter() - t0) * 1000)
            entry = {"tool": fc.name, "args": args, "result": result, "ms": ms}
            trace.append(entry)
            if on_call:
                on_call(entry)
            log.info("  %s(%s) %dms", fc.name, args, ms)
            parts.append(types.Part.from_function_response(
                name=fc.name, response={"result": _jsonable(result)}))
        contents.append(types.Content(role="user", parts=parts))

    return {"answer": "I could not reach a conclusion within the tool-call "
                      "budget. The trace shows what was gathered.",
            "trace": trace, "rounds": MAX_ROUNDS}


def _jsonable(obj):
    return json.loads(json.dumps(obj, default=str))
