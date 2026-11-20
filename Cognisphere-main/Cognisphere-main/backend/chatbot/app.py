"""Web chat UI.  Run:  python app.py   then open http://127.0.0.1:7860"""
import gradio as gr

from bot import answer


def _text(content):
    """Gradio versions differ: content can be a string or a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text", ""))
    if isinstance(content, (list, tuple)):
        return " ".join(_text(c) for c in content)
    return ""


def _clean_history(history):
    """Accepts both history formats (list of dicts, or list of [user, bot] pairs)."""
    clean = []
    for item in history or []:
        if isinstance(item, dict):
            role = "user" if item.get("role") == "user" else "assistant"
            text = _text(item.get("content"))
            if text:
                clean.append({"role": role, "content": text})
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            if item[0]:
                clean.append({"role": "user", "content": _text(item[0])})
            if item[1]:
                clean.append({"role": "assistant", "content": _text(item[1])})
    return clean


def respond(message, history):
    return answer(_text(message), _clean_history(history))


demo = gr.ChatInterface(
    fn=respond,
    title="Krishi Mitra - Indian Agriculture Assistant",
    description="Ask about crops, soil, pests, irrigation, mandi, schemes, dairy and more. "
                "Hindi and English both work.",
    examples=[
        "गेहूं की बुवाई का सही समय और बीज दर क्या है?",
        "Best rabi crops for sandy loam soil in Uttar Pradesh?",
        "How do I apply for PM-KISAN and what documents are needed?",
        "Tomato leaves are curling and turning yellow. What could it be?",
    ],
)

if __name__ == "__main__":
    demo.launch()
