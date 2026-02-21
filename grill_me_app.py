"""
Grill Me — AI-powered BBQ assistant web app.

Combines a simulated grill controller (using the thermodynamic model from
GrillBot.py) with a Claude-powered chat interface for grilling advice.

Usage:
    ANTHROPIC_API_KEY=<key> python grill_me_app.py

Then open http://localhost:5000 in your browser.
"""

import json
import os
import threading
import time

import anthropic
from flask import Flask, Response, jsonify, render_template, request

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Thermodynamic model parameters (from GrillBot.py)
# dT/dt = MODEL_A*(T - T_AMB) + MODEL_B*u + MODEL_C
# ---------------------------------------------------------------------------
MODEL_A = -0.00425  # heat loss coefficient
MODEL_B = 1.299     # heat addition rate per unit burner input
MODEL_C = 0.557     # baseline heat (pilot light effect)
T_AMB = 72.0        # ambient temperature (°F)
MAX_TEMP = 700.0    # max expected grill temperature (°F)

# ---------------------------------------------------------------------------
# Grill simulation state
# front_burner / back_burner: 0.0 (off) → 1.0 (full)
# ---------------------------------------------------------------------------
_grill = {
    "temperature": T_AMB,
    "target_temperature": 350.0,
    "front_burner": 0.0,
    "back_burner": 0.0,
    "is_on": False,
}
_lock = threading.Lock()


def _simulate_step(T: float, u: float) -> float:
    """Advance temperature by one second given average burner setting u."""
    dT = MODEL_A * (T - T_AMB) + MODEL_B * u + MODEL_C
    return T + dT


def _simulation_loop() -> None:
    """Background thread: update grill temperature every second."""
    while True:
        with _lock:
            if _grill["is_on"]:
                u = (_grill["front_burner"] + _grill["back_burner"]) / 2.0
                _grill["temperature"] = _simulate_step(_grill["temperature"], u)
        time.sleep(1)


threading.Thread(target=_simulation_loop, daemon=True).start()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    with _lock:
        return jsonify(dict(_grill))


@app.route("/api/ignite", methods=["POST"])
def api_ignite():
    data = request.get_json(silent=True) or {}
    target = float(data.get("target", 350))
    front = float(data.get("front_burner", -1))
    back = float(data.get("back_burner", -1))

    with _lock:
        _grill["is_on"] = True
        _grill["target_temperature"] = target
        # If burner values not provided, set them based on target temperature
        if front < 0 or back < 0:
            u = max(0.0, min(1.0, (target - T_AMB) / 500.0))
            _grill["front_burner"] = u
            _grill["back_burner"] = u
        else:
            _grill["front_burner"] = max(0.0, min(1.0, front))
            _grill["back_burner"] = max(0.0, min(1.0, back))

    return jsonify({"success": True})


@app.route("/api/burners", methods=["POST"])
def api_burners():
    data = request.get_json(silent=True) or {}
    with _lock:
        if "front_burner" in data:
            _grill["front_burner"] = max(0.0, min(1.0, float(data["front_burner"])))
        if "back_burner" in data:
            _grill["back_burner"] = max(0.0, min(1.0, float(data["back_burner"])))
    return jsonify({"success": True})


@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    with _lock:
        _grill["is_on"] = False
        _grill["front_burner"] = 0.0
        _grill["back_burner"] = 0.0
    return jsonify({"success": True})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])

    with _lock:
        temp = _grill["temperature"]
        target = _grill["target_temperature"]
        front = _grill["front_burner"]
        back = _grill["back_burner"]
        is_on = _grill["is_on"]

    if is_on:
        grill_status = (
            f"RUNNING — current temp {temp:.1f}°F, target {target:.0f}°F, "
            f"front burner {front * 100:.0f}%, back burner {back * 100:.0f}%"
        )
    else:
        grill_status = f"OFF — grill is at {temp:.1f}°F (cooling)"

    system_prompt = (
        "You are GrillBot, an expert BBQ and grilling assistant built into a smart grill controller. "
        "You provide concise, practical advice on temperatures, techniques, meat doneness, food safety, "
        "seasoning, recipes, and troubleshooting. You have real-time access to the grill's status.\n\n"
        f"Current grill status: {grill_status}\n\n"
        "Keep responses focused and actionable. Use Fahrenheit. Always flag food-safety concerns. "
        "When the grill is running, reference its current readings in your advice where relevant."
    )

    client = anthropic.Anthropic()

    def generate():
        try:
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=1024,
                system=system_prompt,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text})}\n\n"
        except anthropic.APIError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port)
