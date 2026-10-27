# transport

Contact and link model used by the simulator (implemented in `simulator/engine.py::_contacts` and the
per-mode exchange functions in `simulator/record_node.py` and `simulator/cpmm_node.py`):

* A contact exists for a simulation step when two alive nodes are within `radio_range_m`.
* Per contact per step the byte budget is `bandwidth_Bps x step_s`, split evenly per direction.
* Every mode pays 8 B per offered identifier (summary-vector / digest anti-entropy), offers are delta-based
  per peer, and payload bytes are charged at their encoded size.
* Responders are sinks for record modes; sensor nodes are producer-only in every mode.
* Energy proxy: 1 uJ/B transmitted and 0.5 uJ/B received, split across the pair.
