"""Record shapes and physical sanity bounds."""

# field -> (kind, lo, hi). Values outside bounds fail verification.
ATTACK_FIELDS = {
    "target": ("target", None, None),
    "logical_qubits": ("number", 100, 1e8),     # no attack on real cryptography needs fewer
    "physical_qubits": ("number", 1000, 1e10),
    "toffoli_or_t_count": ("number", 1e3, 1e30),  # Grover attacks on AES or SHA need around 1e24 gates
    "runtime": ("duration", 1e-3, 1e5),  # hours
}
HARDWARE_FIELDS = {
    "actor": ("text", None, None),  # supplied by the source configuration, not by the model
    "logical_qubits": ("number", 1, 1e8),
    "physical_qubits": ("number", 1, 1e10),
    "target_year": ("number", 2020, 2100),
    "target_month": ("number", 1, 12),
}
FIELDS = {"attack": ATTACK_FIELDS, "hardware": HARDWARE_FIELDS}

# Fields whose value being lower makes the attack cheaper (used by the router).
COST_FIELDS = ("logical_qubits", "physical_qubits", "toffoli_or_t_count", "runtime")

MAX_QUOTE = 700  # a quote may span a couple of sentences, never a whole abstract
CORE = {"attack": "target", "hardware": "actor"}
