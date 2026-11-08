# Oscilloscope Recordings

These oscilloscope recordings were taken from a door entry system to observe the electrical signals associated with the door release, doorbell, simulated load, and doorbell detection circuit.

## Measurement Setup

Terminal **4** was used as the voltage reference. The probe locations are listed below.

## Recordings

| File | Measurement | Description |
|---|---|---|
| `splg0001.csv` | B relative to 4 | Voltage recorded while the **door release button** is pressed. Captures the resulting voltage changes at terminal B. |
| `splg0002.csv` | 5 relative to 4 | Voltage recorded while the **doorbell is rung**. Captures the signal associated with the doorbell activation. |
| `splg0003.csv` | B relative to 4 | Voltage recorded while terminals **4 and B are connected through a 1 $\Omega$ shunt resistor**. Captures the system's response to the applied load. |
| `splg0004.csv` | Between the Zener and PC817C,[^detection] relative to 4 | Voltage recorded while investigating a non-working doorbell detection circuit. The doorbell was pressed near the middle of the recording. |
| `splg0006.csv` | After the 1N4148 diode connected to terminal 5,[^detection] relative to 4 | Doorbell signal measured with the diode output open, like the open-circuit terminal 5 measurement in `splg0002.csv`. The resistor, Zener and optocoupler were not connected. |

[^detection]: See the [circuit diagram](../../diagram.svg) for the detection circuit.
